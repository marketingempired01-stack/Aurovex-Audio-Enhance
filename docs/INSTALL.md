# Auravox — Installation (Windows)

Everything runs locally. No API keys, no cloud services.

## 1. Install Python 3.11

- Download **Python 3.11.x** from https://www.python.org/downloads/
- Run the installer and **tick “Add python.exe to PATH”**.
- Python 3.12/3.13 will NOT work (the DeepFilterNet native library has no
  wheels for them yet). Python 3.9, 3.10 and 3.11 are supported.

Check in a new Command Prompt:

    python --version     -> should print 3.11.x

## 2. Install FFmpeg (recommended)

FFmpeg is used to decode MP3/M4A/AAC/OGG/FLAC and to encode MP3.

- Easiest: `winget install Gyan.FFmpeg` (or `choco install ffmpeg`)
- Or download the full build from https://www.gyan.dev/ffmpeg/builds/ and add
  its `bin` folder to your PATH.

If you skip this step Auravox will fall back to the FFmpeg binary bundled with
the `imageio-ffmpeg` Python package — decoding and MP3 export still work.

## 3. Get the project & install dependencies

Open Command Prompt in the project folder (the one containing `start.bat`):

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

The first install downloads PyTorch (~200 MB). Everything stays on your PC.

### GPU acceleration (optional)

For NVIDIA GPUs, install CUDA-enabled PyTorch **instead of** the CPU wheels:

    pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121
    pip install -r requirements.txt

Auravox auto-detects CUDA and falls back to CPU automatically. CPU mode is
already fast: DeepFilterNet 3 runs ~10-20× faster than real-time on a modern
desktop CPU.

## 4. Model weights (automatic)

The pretrained DeepFilterNet3 checkpoint (~10 MB) is downloaded **once** on the
first enhancement run to your user cache folder
(`%LOCALAPPDATA%\DeepFilterNet\DeepFilterNet3` on Windows). See
`docs/MODEL_SETUP.md` for details and offline installation.

## 5. Start the app

Double-click **`start.bat`** (or `start_dev.bat` for auto-reload during
development) and open http://localhost:8000 in your browser.

## 6. Verify

- The header of the settings card shows `Powered by DeepFilterNet 3 · device: …`
- Visit http://localhost:8000/api/health — `"model_ready": true` means the AI
  model is loaded and everything is operational.

## Troubleshooting

See `docs/TROUBLESHOOTING.md`.
