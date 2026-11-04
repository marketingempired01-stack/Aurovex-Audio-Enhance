"""
Auravox — FastAPI backend.

Run from the project root:

    python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

All processing is local. No external APIs, no telemetry, no uploads anywhere.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import audio as audio_io
from . import config, processing
from .engine import engine
from .jobs import Job, store, submit

APP_VERSION = "1.0.0"

app = FastAPI(
    title="Auravox — AI Voice Enhancement",
    version=APP_VERSION,
    description="Private, local AI speech enhancement (DeepFilterNet 3).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # local dev tool — the server is only exposed on your machine
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """Never let the browser cache HTML/CSS/JS — UI edits show up on refresh."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".css", ".js")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _startup() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    # Load the AI model in the background so the server binds instantly.
    threading.Thread(target=engine.warm_up, name="model-warmup", daemon=True).start()
    # Periodic temp-file cleanup.
    threading.Thread(
        target=processing.run_cleanup_loop,
        args=(store, config.CLEANUP_INTERVAL_SEC, config.JOB_TTL_SEC),
        name="job-cleanup",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Capabilities — the single source of truth for settings shown in the UI.
# Only real, model-backed controls are listed here (no fake sliders).
# ---------------------------------------------------------------------------
def _capabilities() -> dict:
    return {
        "app": "Auravox",
        "version": APP_VERSION,
        "engine": engine.engine_name,
        "engine_repo": "https://github.com/Rikorose/DeepFilterNet",
        "model": config.DF_MODEL,
        "device": engine.device,
        "model_ready": engine.ready,
        "sample_rate": engine.sample_rate,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "max_duration_sec": config.MAX_DURATION_SEC,
        "allowed_extensions": sorted(config.ALLOWED_EXTENSIONS),
        "settings": [
            {
                "id": "profile",
                "group": "ai",
                "type": "select",
                "label": "Enhancement profile",
                "default": "standard",
                "description": "Standard uses DeepFilterNet's deep-filtering stage for maximum clarity. "
                               "Gentle uses the ERB mask only — more conservative, preserves more of the "
                               "original ambience.",
                "options": [
                    {"value": "standard", "label": "Standard — maximum clarity"},
                    {"value": "gentle", "label": "Gentle — maximum voice preservation"},
                ],
            },
            {
                "id": "noise_reduction_db",
                "group": "ai",
                "type": "slider",
                "label": "Noise reduction strength",
                "min": 6, "max": 40, "step": 1, "default": 40, "unit": "dB",
                "description": "Caps how much background noise is removed (model attenuation limit). "
                               "Maximum = full suppression; lower values keep a little natural room tone.",
            },
            {
                "id": "post_filter",
                "group": "ai",
                "type": "toggle",
                "label": "Extra cleanup pass (post-filter)",
                "default": True,
                "description": "DeepFilterNet's post-filter over-attenuates very noisy sections slightly. "
                               "Great for fan/traffic noise; turn off for already-clean recordings.",
            },
            {
                "id": "highpass_hz",
                "group": "dsp",
                "type": "select",
                "label": "Low-cut filter",
                "default": 60,
                "description": "Removes rumble, table bumps and DC offset below the cutoff.",
                "options": [
                    {"value": 0, "label": "Off"},
                    {"value": 20, "label": "20 Hz"},
                    {"value": 60, "label": "60 Hz (recommended)"},
                    {"value": 80, "label": "80 Hz"},
                    {"value": 120, "label": "120 Hz"},
                ],
            },
            {
                "id": "loudness",
                "group": "dsp",
                "type": "select",
                "label": "Loudness normalisation",
                "default": -16,
                "description": "Normalises the enhanced voice to a broadcast-style target (EBU R128).",
                "options": [
                    {"value": "off", "label": "Off"},
                    {"value": -14, "label": "−14 LUFS (podcast / web)"},
                    {"value": -16, "label": "−16 LUFS (voice standard)"},
                    {"value": -23, "label": "−23 LUFS (broadcast)"},
                ],
            },
            {
                "id": "wav_bit_depth",
                "group": "output",
                "type": "select",
                "label": "WAV quality",
                "default": 24,
                "description": "Bit depth used for WAV downloads.",
                "options": [
                    {"value": 16, "label": "16-bit"},
                    {"value": 24, "label": "24-bit (recommended)"},
                ],
            },
            {
                "id": "mp3_bitrate",
                "group": "output",
                "type": "select",
                "label": "MP3 quality",
                "default": 320,
                "description": "Bitrate used for MP3 downloads.",
                "options": [
                    {"value": 192, "label": "192 kbps"},
                    {"value": 256, "label": "256 kbps"},
                    {"value": 320, "label": "320 kbps (recommended)"},
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Ranged file responses (audio seeking needs HTTP Range support)
# ---------------------------------------------------------------------------
def _ranged_response(path: Path, media_type: str, request: Request, download_name: Optional[str] = None):
    if not path.is_file():
        raise HTTPException(404, "File not found (it may have expired — jobs are cleaned up automatically).")
    file_size = path.stat().st_size
    headers = {"Accept-Ranges": "bytes"}
    if download_name:
        headers["Content-Disposition"] = f'attachment; filename="{download_name}"'
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=media_type, headers=headers)

    m = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not m:
        raise HTTPException(416, "Invalid Range header", headers={"Content-Range": f"bytes */{file_size}"})
    start_s, end_s = m.group(1), m.group(2)
    start = int(start_s) if start_s else 0
    end = min(file_size - 1, int(end_s)) if end_s else file_size - 1
    if start >= file_size or start > end:
        raise HTTPException(416, "Range not satisfiable", headers={"Content-Range": f"bytes */{file_size}"})
    length = end - start + 1

    def _iter():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers.update({
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(length),
    })
    return StreamingResponse(_iter(), status_code=206, media_type=media_type, headers=headers)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok" if engine.ready or engine.error is None else "degraded",
        "version": APP_VERSION,
        "engine": engine.engine_name,
        "model_ready": engine.ready,
        "model_error": engine.error,
        "device": engine.device,
        "ffmpeg": audio_io.ffmpeg_available(),
        "active_jobs": sum(1 for j in store.all() if j.status in ("queued", "processing")),
    }


@app.get("/api/capabilities")
def capabilities():
    return _capabilities()


@app.post("/api/enhance")
async def enhance_endpoint(
    request: Request,
    file: UploadFile = File(...),
    settings: str = Form(default="{}"),
):
    # ---- parse settings ------------------------------------------------ #
    try:
        settings_dict = json.loads(settings) if settings else {}
        if not isinstance(settings_dict, dict):
            raise ValueError
    except Exception:
        raise HTTPException(400, "Invalid settings payload.")

    # ---- validate file name / extension -------------------------------- #
    original_name = os.path.basename(file.filename or "audio")
    ext = Path(original_name).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext or 'unknown'}'. "
            f"Accepted: {', '.join(sorted(e.lstrip('.') for e in config.ALLOWED_EXTENSIONS))}.",
        )

    # ---- stream to disk with a hard size cap --------------------------- #
    job = store.create(settings_dict, original_name, input_file=f"input{ext}")
    dest = job.path(job.input_file)
    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MiB chunks — bounded memory
                if not chunk:
                    break
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413,
                        f"File is larger than the {config.MAX_UPLOAD_MB} MB limit. "
                        "Split the recording or raise MAX_UPLOAD_MB.",
                    )
                out.write(chunk)
    except HTTPException:
        store.delete(job.id)
        raise
    except Exception as exc:
        store.delete(job.id)
        raise HTTPException(500, f"Could not store upload: {exc}")
    finally:
        await file.close()

    if size == 0:
        store.delete(job.id)
        raise HTTPException(400, "The uploaded file is empty.")

    # ---- kick off the pipeline ---------------------------------------- #
    job.update(status="queued", progress=1, stage="Waiting in queue")
    submit(job.id, processing.process_job)
    return JSONResponse({"job_id": job.id, "status": job.status}, status_code=202)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    return job.to_dict()


@app.delete("/api/jobs/{job_id}")
def job_delete(job_id: str):
    if not store.delete(job_id):
        raise HTTPException(404, "Unknown job.")
    return {"deleted": True}


@app.post("/api/jobs/{job_id}/reprocess")
async def job_reprocess(job_id: str, request: Request):
    """Re-run enhancement on an already-uploaded file with new settings."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    if not job.path(job.input_file).is_file():
        raise HTTPException(410, "The original upload has expired.")
    try:
        body = await request.json()
        settings_dict = body.get("settings", {}) if isinstance(body, dict) else {}
    except Exception:
        settings_dict = {}
    new_job = store.create(settings_dict, job.original_name, input_file=job.input_file)
    # share the same input file (both jobs reference the same name in different dirs)
    src = job.path(job.input_file)
    dst = new_job.path(new_job.input_file)
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    new_job.update(status="queued", progress=1, stage="Waiting in queue")
    submit(new_job.id, processing.process_job)
    return JSONResponse({"job_id": new_job.id, "status": new_job.status}, status_code=202)


@app.get("/api/jobs/{job_id}/files/{which}")
def job_file(job_id: str, which: str, request: Request):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    if which == "original":
        path = job.path(job.input_file)
    elif which == "enhanced":
        path = job.path(job.enhanced_wav)
    elif which == "video":
        if not job.enhanced_video:
            raise HTTPException(404, "This job has no video output.")
        path = job.path(job.enhanced_video)
    else:
        raise HTTPException(404, "Unknown file.")
    return _ranged_response(path, audio_io.media_type_for(path), request)


@app.get("/api/jobs/{job_id}/waveform/{which}")
def job_waveform(job_id: str, which: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    peaks = (job.meta.get("peaks") or {}).get(which)
    if peaks is None:
        raise HTTPException(404, "Waveform not ready.")
    return {"peaks": peaks, "duration": job.meta.get("duration"), "channels": job.meta.get("channels")}


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str, request: Request, format: str = "wav"):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    if job.status != "completed":
        raise HTTPException(409, "Job is not finished yet.")
    stem = Path(job.original_name).stem or "enhanced"
    if format == "wav":
        path = job.path(job.enhanced_wav)
        return _ranged_response(path, "audio/wav", request, download_name=f"{stem}_enhanced.wav")
    if format == "mp3":
        mp3_path = job.path(job.mp3_cache)
        if not mp3_path.is_file():
            bitrate = f"{int(job.settings.get('mp3_bitrate', 320))}k"
            try:
                audio_io.encode_mp3(job.path(job.enhanced_wav), mp3_path, bitrate=bitrate)
            except Exception as exc:
                raise HTTPException(500, f"MP3 encoding failed: {exc}")
        return _ranged_response(mp3_path, "audio/mpeg", request, download_name=f"{stem}_enhanced.mp3")
    if format == "video":
        if not job.enhanced_video:
            raise HTTPException(400, "This upload has no video — only audio output.")
        vpath = job.path(job.enhanced_video)
        if not vpath.is_file():
            raise HTTPException(409, "Enhanced video is not ready yet.")
        return _ranged_response(
            vpath, audio_io.media_type_for(vpath), request,
            download_name=f"{stem}_enhanced{vpath.suffix}",
        )
    raise HTTPException(400, "format must be 'wav', 'mp3' or 'video'")


# ---------------------------------------------------------------------------
# Static frontend (mounted last so /api/* always wins)
# ---------------------------------------------------------------------------
if config.FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT, reload=False)
