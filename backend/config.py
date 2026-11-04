"""
Auravox — central configuration.

All values can be overridden with environment variables, e.g.:

    MAX_UPLOAD_MB=1000 PORT=9000 python -m uvicorn backend.main:app

Everything runs locally. Nothing is ever sent to external services.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent      # project root
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
JOBS_DIR = DATA_DIR / "jobs"

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# Upload limits (protects the server from oversized / abusive uploads)
# ---------------------------------------------------------------------------
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_DURATION_SEC = int(os.environ.get("MAX_DURATION_SEC", "14400"))  # 4 hours

# Accepted input formats (validated by extension AND by actual decoding)
ALLOWED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg",          # audio
    ".mp4", ".mov", ".m4v", ".mkv", ".webm",                  # video (audio track is enhanced)
}

# Video containers: the audio track is enhanced and re-muxed back into a video
# file with the original picture (stream-copied, no re-encoding).
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}

# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
# Number of enhancement jobs processed at the same time. Keep at 1 unless you
# have plenty of RAM — the AI model is shared and processes are serialised.
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "1"))

# Long files are enhanced in overlapping chunks to bound memory usage.
CHUNK_SEC = float(os.environ.get("CHUNK_SEC", "90"))
CHUNK_OVERLAP_SEC = float(os.environ.get("CHUNK_OVERLAP_SEC", "1.0"))

# ---------------------------------------------------------------------------
# Job retention — temporary files are deleted automatically after this period
# ---------------------------------------------------------------------------
JOB_TTL_SEC = int(os.environ.get("JOB_TTL_SEC", "3600"))        # 1 hour
CLEANUP_INTERVAL_SEC = int(os.environ.get("CLEANUP_INTERVAL_SEC", "300"))

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
# Which pretrained DeepFilterNet model to use. "DeepFilterNet3" (48 kHz) is the
# newest and highest quality. Weights are downloaded once to the local cache
# (see docs/MODEL_SETUP.md) and never touched again.
DF_MODEL = os.environ.get("DF_MODEL", "DeepFilterNet3")

# Auto-select CUDA when available; override with DF_DEVICE=cpu / cuda
DF_DEVICE = os.environ.get("DF_DEVICE", "auto")  # auto | cpu | cuda

# ---------------------------------------------------------------------------
# FFmpeg discovery: explicit path > PATH > bundled (imageio-ffmpeg) binary
# ---------------------------------------------------------------------------
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "")
