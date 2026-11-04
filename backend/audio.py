"""
Auravox — audio I/O.

* Decodes every supported input format (MP3/WAV/M4A/FLAC/AAC/OGG) with FFmpeg
  into a canonical 48 kHz float32 WAV that the AI model consumes.
* Encodes output as WAV (16/24-bit) or MP3 (libmp3lame).
* Computes waveform peak data for the frontend visualiser.

FFmpeg is located in this order:
    1. FFMPEG_PATH environment variable
    2. `ffmpeg` on the system PATH
    3. the binary bundled with the `imageio-ffmpeg` pip package
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple

import numpy as np
import soundfile as sf

from . import config

_ffmpeg_cache: str | None = None


class AudioError(RuntimeError):
    """Raised for invalid audio input or encoding failures."""


# ---------------------------------------------------------------------------
# FFmpeg discovery
# ---------------------------------------------------------------------------
def ffmpeg_exe() -> str:
    """Return a usable ffmpeg executable path or raise AudioError."""
    global _ffmpeg_cache
    if _ffmpeg_cache and os.path.isfile(_ffmpeg_cache):
        return _ffmpeg_cache

    candidates = []
    if config.FFMPEG_PATH:
        candidates.append(config.FFMPEG_PATH)
    which = shutil.which("ffmpeg")
    if which:
        candidates.append(which)
    try:
        import imageio_ffmpeg  # bundled static binary — great fallback
        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    for cand in candidates:
        if cand and os.path.isfile(cand):
            _ffmpeg_cache = cand
            return cand
    raise AudioError(
        "FFmpeg was not found. Install it (see docs/INSTALL.md) or set FFMPEG_PATH."
    )


def ffmpeg_available() -> bool:
    try:
        ffmpeg_exe()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Decode / encode
# ---------------------------------------------------------------------------
def decode_audio(src: str | Path, dst_wav: str | Path, max_channels: int = 2) -> Tuple[np.ndarray, int]:
    """
    Decode any supported audio file to a float32 WAV at the given sample rate.

    Preserves mono/stereo; only mixes down files with more than `max_channels`.
    Returns (audio, sr) where audio has shape [channels, samples].
    Raises AudioError when the file is not decodable audio.
    """
    src, dst_wav = str(src), str(dst_wav)

    def _run(channels: Optional[int]) -> None:
        cmd = [
            ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-i", src,
            "-vn", "-sn", "-dn",              # no video/subtitles/data streams
            "-map", "0:a:0",                  # first audio stream only
            "-ar", "48000",                   # model sample rate
            "-acodec", "pcm_f32le",
        ]
        if channels is not None:
            cmd += ["-ac", str(channels)]
        cmd.append(dst_wav)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.isfile(dst_wav):
            raise AudioError(
                "Could not decode this file. Is it a valid audio recording? "
                f"(ffmpeg: {proc.stderr.strip()[:300]})"
            )

    _run(None)
    try:
        data, sr = sf.read(dst_wav, always_2d=True, dtype="float32")
    except Exception as exc:
        raise AudioError(f"Decoded file could not be read: {exc}")
    if data.shape[1] > max_channels:
        _run(max_channels)  # proper ffmpeg mix-down for 5.1/7.1 sources
        data, sr = sf.read(dst_wav, always_2d=True, dtype="float32")
    audio = np.ascontiguousarray(data.T)  # -> [channels, samples]
    if audio.shape[1] == 0:
        raise AudioError("The audio file contains no samples.")
    return audio, sr


def encode_mp3(src_wav: str | Path, dst_mp3: str | Path, bitrate: str = "320k") -> None:
    """Encode a WAV file to MP3 with libmp3lame."""
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src_wav),
        "-codec:a", "libmp3lame",
        "-b:a", str(bitrate),
        str(dst_mp3),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.isfile(dst_mp3):
        raise AudioError(f"MP3 encoding failed: {proc.stderr.strip()[:300]}")


def write_wav(path: str | Path, audio: np.ndarray, sr: int, subtype: str = "PCM_24") -> None:
    """Write [channels, samples] float audio to a WAV file."""
    sf.write(str(path), audio.T, sr, subtype=subtype)


def read_wav(path: str | Path) -> Tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    return np.ascontiguousarray(data.T), sr


# ---------------------------------------------------------------------------
# Waveform peaks for the UI visualiser
# ---------------------------------------------------------------------------
def compute_peaks(path: str | Path, buckets: int = 1200) -> List[float]:
    """
    Compute normalised peak amplitudes (0..1) in `buckets` vertical slices.
    Reads the file in blocks so even hour-long recordings stay memory friendly.
    """
    with sf.SoundFile(str(path)) as f:
        total = len(f)
        if total <= 0:
            return []
        buckets = max(10, min(buckets, total))
        per_bucket = total / buckets
        peaks = np.zeros(buckets, dtype=np.float32)
        pos = 0
        blocksize = 65536
        while True:
            block = f.read(blocksize, dtype="float32", always_2d=True)
            if block.size == 0:
                break
            absmax = np.abs(block).max(axis=1)  # per-frame max over channels
            n = len(absmax)
            # map frames [pos, pos+n) onto bucket indices
            start_b = int(pos / per_bucket)
            end_b = min(buckets, int((pos + n) / per_bucket) + 1)
            for b in range(start_b, end_b):
                lo = max(0, int(b * per_bucket) - pos)
                hi = min(n, int((b + 1) * per_bucket) - pos + 1)
                if hi > lo:
                    peaks[b] = max(peaks[b], float(absmax[lo:hi].max()))
            pos += n
    m = float(peaks.max()) or 1.0
    return [round(float(p) / m, 4) for p in peaks]


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------
def media_type_for(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".m4v": "video/x-m4v",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
    }.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# Video: replace the sound of a video with the enhanced audio
# ---------------------------------------------------------------------------
def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in config.VIDEO_EXTENSIONS


def mux_enhanced_video(video_src: str | Path, audio_wav: str | Path, dst_video: str | Path) -> None:
    """Re-mux `video_src` with the enhanced `audio_wav` as its soundtrack.

    The video stream is copied bit-for-bit (no quality loss, very fast);
    the audio is encoded to AAC (or Opus for WebM). Raises AudioError on failure.
    """
    ext = Path(dst_video).suffix.lower()
    if ext == ".webm":
        audio_args = ["-c:a", "libopus", "-b:a", "160k"]
    else:
        audio_args = ["-c:a", "aac", "-b:a", "192k"]
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_src), "-i", str(audio_wav),
        "-map", "0:v:0", "-map", "1:a:0",     # original picture + enhanced sound
        "-c:v", "copy",
    ] + audio_args + ["-map_metadata", "0", "-shortest"]
    if ext in (".mp4", ".mov", ".m4v"):
        cmd += ["-movflags", "+faststart"]
    cmd.append(str(dst_video))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.isfile(dst_video):
        raise AudioError(f"Video remux failed: {proc.stderr.strip()[:300]}")


def file_duration(path: str | Path) -> float:
    try:
        return float(sf.info(str(path)).duration)
    except Exception:
        return 0.0
