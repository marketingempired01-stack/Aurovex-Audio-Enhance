# Troubleshooting

## Installation problems

### `python` is not recognised / wrong version
Install Python 3.11 from python.org and re-run the installer with
**“Add python.exe to PATH”** ticked. Verify with `python --version`.

### `ERROR: Could not find a version that satisfies the requirement DeepFilterNet`
You are using Python 3.12 or 3.13. The native `deepfilterlib` wheel only
supports Python 3.8–3.11. Create the virtual environment with Python 3.11:

    py -3.11 -m venv .venv

### `Microsoft Visual C++ 14.0 or greater is required` during pip install
You are on a Python version without prebuilt wheels (or a 32-bit Python).
Switch to 64-bit Python 3.11, delete `.venv`, and reinstall.

### pip fails with SSL / proxy errors
Try: `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt`
or install through your organisation's proxy (`set HTTPS_PROXY=...`).

### `torch` install is very slow
The PyTorch wheel is ~200 MB. Let it finish, or install a CPU-only wheel
explicitly:

    pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cpu

## Runtime problems

### The app says “FFmpeg was not found”
Install FFmpeg (`winget install Gyan.FFmpeg`) and restart the app, **or**
simply `pip install imageio-ffmpeg` — Auravox automatically falls back to the
bundled binary. You can also point directly at an executable:

    set FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe

### `model_ready: false` / “Failed to load DeepFilterNet model”
The first run downloads the ~10 MB checkpoint from GitHub. If your network
blocks GitHub, download `DeepFilterNet3.zip` manually and place it as
described in `docs/MODEL_SETUP.md` (offline installation).

### Port 8000 is already in use
Start on another port:

    set PORT=9000
    start.bat

or edit the port inside `start.bat`.

### “Unsupported file type” for a valid audio file
Auravox validates by extension: MP3, WAV, M4A, FLAC, AAC, OGG. Rename exotic
containers (e.g. `.webm`, `.wma`) to one of these only if they really contain
standard audio — or convert them first with FFmpeg:

    ffmpeg -i input.wma output.wav

### Enhancement is slow
* Check the device shown in the settings card — `CPU` is normal and still
  faster than real-time on modern machines.
* For NVIDIA GPUs install CUDA PyTorch (see `docs/INSTALL.md` § GPU).
* Very long files are chunked (90 s chunks) which adds a little overhead.

### The computer runs out of memory on huge files
Auravox chunks long recordings automatically. If it still happens:
* lower `CHUNK_SEC` (e.g. `set CHUNK_SEC=45`)
* raise `MAX_CONCURRENT_JOBS` is NOT recommended; keep it at 1
* make sure nothing else is eating RAM (browser tabs with huge audio, DAWs…)

### Enhanced audio is too quiet / too loud
Use the **Loudness normalisation** setting (−16 LUFS is the voice standard) or
turn it off to keep the original level.

### Enhanced audio sounds “too clean” / slightly dull
* Set **Noise reduction strength** below maximum (e.g. 20–26 dB) — this caps
  the attenuation and keeps some natural room tone.
* Turn the **Extra cleanup pass** off.
* Use the **Gentle** profile for already-decent recordings.

### Background voices of other people are still audible
Overlapping speech of equal loudness cannot be perfectly separated by any
model. DeepFilterNet strongly attenuates quieter background talkers; make sure
the main speaker is closest to the microphone. For dedicated speaker
separation, see the optional ClearerVoice-Studio notes in
`docs/MODEL_SETUP.md`.

### Downloads return 404 after a while
Temporary jobs are deleted automatically after 1 hour (configurable via
`JOB_TTL_SEC`). Re-run the enhancement or download promptly.

### Windows Defender / antivirus flags the app
It is a local Python web server; add an exclusion for the project folder if
needed. Nothing is ever uploaded.

## Development

### Code changes are not picked up
Use `start_dev.bat` — it runs Uvicorn with `--reload`.

### Reset everything
Delete the `data/` folder (all temporary jobs) and restart. The AI model
cache lives in your user profile and is kept.
