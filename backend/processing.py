"""
Auravox — enhancement pipeline.

Pipeline stages (progress %):
    3   decoding input with FFmpeg
    10  loading the AI model
    14  enhancing (chunked, with progress callbacks)
    86  finishing DSP (low-cut filter, loudness normalisation)
    93  rendering WAV + waveform data
    100 done

Long recordings are processed in overlapping chunks with raised-cosine
cross-fades, which keeps memory usage flat regardless of file length.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np
from scipy import signal

from . import audio as audio_io
from . import config
from .engine import engine
from .jobs import Job, store

ProgressCb = Callable[[float, str], None]


# ---------------------------------------------------------------------------
# Chunked enhancement with overlap-add cross-fade
# ---------------------------------------------------------------------------
def enhance_long(
    audio: np.ndarray,
    atten_lim_db: Optional[float],
    post_filter: bool,
    mask_only: bool,
    progress_cb: Optional[ProgressCb] = None,
) -> np.ndarray:
    """
    Enhance [channels, samples] audio, splitting long input into overlapping
    chunks so memory stays bounded on huge files.
    """
    sr = engine.sample_rate
    n = audio.shape[1]
    chunk_len = int(config.CHUNK_SEC * sr)
    overlap = int(config.CHUNK_OVERLAP_SEC * sr)

    if n <= chunk_len:
        if progress_cb:
            progress_cb(0.0, "Enhancing voice")
        return engine.enhance_chunk(
            audio, post_filter=post_filter, mask_only=mask_only, atten_lim_db=atten_lim_db
        )

    hop = chunk_len - overlap

    # Chunk offsets: step by `hop`, clamped so the last chunk ends exactly at n.
    offsets = sorted(set(min(o, max(0, n - chunk_len)) for o in range(0, n, hop)))

    out = np.zeros_like(audio)
    weight = np.zeros(n, dtype=np.float32)

    # raised-cosine cross-fade ramp (0 -> 1); flat middle
    ramp = np.ones(chunk_len, dtype=np.float32)
    if overlap > 0:
        fade = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, overlap, dtype=np.float32))
        ramp[:overlap] = fade
        ramp[-overlap:] = fade[::-1]

    n_chunks = len(offsets)
    for i, off in enumerate(offsets):
        end = min(off + chunk_len, n)
        valid = end - off
        chunk = audio[:, off:end]
        if valid < chunk_len:  # last chunk may be short — pad for the model
            chunk = np.pad(chunk, ((0, 0), (0, chunk_len - valid)))
        enhanced = engine.enhance_chunk(
            chunk, post_filter=post_filter, mask_only=mask_only, atten_lim_db=atten_lim_db
        )
        w = ramp[:valid].copy()
        if i == 0:  # no fade-in at the start of the file
            w[:min(overlap, valid)] = 1.0
        if i == n_chunks - 1:  # no fade-out at the end of the file
            w[max(0, valid - overlap):] = 1.0
        out[:, off:end] += enhanced[:, :valid] * w
        weight[off:end] += w
        if progress_cb:
            progress_cb(i / n_chunks, f"Enhancing voice (part {i + 1}/{n_chunks})")

    weight = np.maximum(weight, 1e-6)
    out /= weight[np.newaxis, :]
    return np.ascontiguousarray(out, dtype=np.float32)


# ---------------------------------------------------------------------------
# Finishing DSP (real, transparent signal processing)
# ---------------------------------------------------------------------------
def apply_highpass(audio: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    """2nd-order Butterworth low-cut — removes rumble / DC / handling noise."""
    if not cutoff_hz or cutoff_hz <= 0:
        return audio
    sos = signal.butter(2, cutoff_hz, btype="highpass", fs=sr, output="sos")
    return signal.sosfilt(sos, audio, axis=-1).astype(np.float32)


def normalize_loudness(audio: np.ndarray, sr: int, target_lufs: Optional[float]) -> np.ndarray:
    """
    Loudness-normalise to `target_lufs` (EBU R128) and guarantee the peak
    stays below -1 dBFS. `None` leaves the level untouched.
    """
    if target_lufs is None:
        return audio
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(sr)
        # pyloudnorm expects [samples, channels]
        loudness = meter.integrated_loudness(audio.T)
        if not np.isfinite(loudness) or loudness < -70:  # near-silent input
            return audio
        gain_db = float(target_lufs) - float(loudness)
        gain_db = max(-24.0, min(24.0, gain_db))         # sanity clamp
        out = audio * (10.0 ** (gain_db / 20.0))
    except Exception:
        return audio
    peak = float(np.abs(out).max() or 0.0)
    if peak > 0.891:  # -1 dBFS
        out = out * (0.891 / peak)
    return np.ascontiguousarray(out, dtype=np.float32)


# ---------------------------------------------------------------------------
# Full job pipeline
# ---------------------------------------------------------------------------
def _parse_settings(settings: dict) -> dict:
    """Fill defaults / clamp values so bad client input can't break the model."""
    def _get(key, default, cast, lo=None, hi=None):
        try:
            val = cast(settings.get(key, default))
        except Exception:
            val = default
        if lo is not None:
            val = max(lo, val)
        if hi is not None:
            val = min(hi, val)
        return val

    return {
        "profile": str(settings.get("profile", "standard")) if settings.get("profile", "standard") in ("standard", "gentle") else "standard",
        "noise_reduction_db": _get("noise_reduction_db", 40, float, 6, 40),
        "post_filter": bool(settings.get("post_filter", True)),
        "highpass_hz": _get("highpass_hz", 60, float, 0, 240),
        "loudness": settings.get("loudness", -16),
        "wav_bit_depth": _get("wav_bit_depth", 24, int, 16, 24),
        "mp3_bitrate": _get("mp3_bitrate", 320, int, 96, 320),
    }


def process_job(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    try:
        settings = _parse_settings(job.settings)
        job.settings.update(settings)
        job.update(status="processing", progress=2, stage="Validating audio")

        # ---- decode -------------------------------------------------- #
        job.update(progress=4, stage="Decoding audio")
        work_wav = job.path(job.work_wav)
        audio, sr = audio_io.decode_audio(job.path(job.input_file), work_wav)
        channels, n_samples = audio.shape
        duration = n_samples / sr
        if duration > config.MAX_DURATION_SEC:
            raise audio_io.AudioError(
                f"Recording is {duration/60:.0f} minutes long — the limit is "
                f"{config.MAX_DURATION_SEC/60:.0f} minutes."
            )
        job.meta.update({
            "duration": round(duration, 2),
            "sample_rate_in": 48000,
            "channels": channels,
            "engine": engine.engine_name,
            "model_sample_rate": engine.sample_rate,
        })

        # ---- model --------------------------------------------------- #
        job.update(progress=10, stage="Loading AI model")
        mask_only = settings["profile"] == "gentle"
        atten_lim_db = None if settings["noise_reduction_db"] >= 40 else float(settings["noise_reduction_db"])
        engine.get_model(post_filter=settings["post_filter"], mask_only=mask_only)
        job.meta["device"] = engine.device

        # ---- enhance ------------------------------------------------- #
        job.update(progress=13, stage="Enhancing voice")

        def _cb(frac: float, msg: str) -> None:
            job.update(progress=13 + 72 * float(frac), stage=msg)

        enhanced = enhance_long(
            audio,
            atten_lim_db=atten_lim_db,
            post_filter=settings["post_filter"],
            mask_only=mask_only,
            progress_cb=_cb,
        )

        # ---- finishing DSP -------------------------------------------- #
        job.update(progress=86, stage="Applying finishing touches")
        enhanced = apply_highpass(enhanced, sr, settings["highpass_hz"])
        loudness = settings["loudness"]
        enhanced = normalize_loudness(enhanced, sr, None if loudness in (None, "off", "none", "") else float(loudness))

        # ---- render --------------------------------------------------- #
        job.update(progress=93, stage="Rendering output")
        subtype = "PCM_24" if settings["wav_bit_depth"] == 24 else "PCM_16"
        enhanced_wav = job.path(job.enhanced_wav)
        audio_io.write_wav(enhanced_wav, enhanced, sr, subtype=subtype)

        job.meta["enhanced_size"] = enhanced_wav.stat().st_size
        job.meta["original_size"] = job.path(job.input_file).stat().st_size

        # waveform peaks for the UI
        job.meta["peaks"] = {
            "original": audio_io.compute_peaks(work_wav),
            "enhanced": audio_io.compute_peaks(enhanced_wav),
        }

        # ---- video remux: original picture + enhanced sound ----------- #
        if job.enhanced_video:
            job.update(progress=96, stage="Building enhanced video")
            audio_io.mux_enhanced_video(
                job.path(job.input_file), enhanced_wav, job.path(job.enhanced_video)
            )
            job.meta["is_video"] = True
            job.meta["enhanced_video_size"] = job.path(job.enhanced_video).stat().st_size

        job.update(status="completed", progress=100, stage="Done")
    except Exception as exc:
        job.fail(str(exc))


def run_cleanup_loop(store_, interval: int, ttl: int) -> None:
    """Blocking loop used by a daemon thread — prunes expired jobs."""
    while True:
        time.sleep(interval)
        try:
            store_.prune(ttl)
        except Exception:
            pass
