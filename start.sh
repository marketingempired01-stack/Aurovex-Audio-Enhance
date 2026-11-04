#!/usr/bin/env bash
# Auravox — start script for Linux / macOS
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8000}"

echo "=========================================="
echo "  Auravox - AI Voice Enhancement (local)"
echo "=========================================="

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[info] ffmpeg not found on PATH — bundled fallback (imageio-ffmpeg) will be used."
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[setup] Creating virtual environment (requires Python 3.9-3.11)..."
  python3 -m venv .venv
fi

if [ ! -f ".venv/deps.ok" ]; then
  echo "[setup] Installing dependencies (first run only)..."
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/deps.ok
fi

echo "[run] Starting Auravox on http://localhost:${PORT}"
.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}" "$@"
