# Auravox — Professional AI Voice Enhancement

A complete, self-hosted alternative to Adobe Podcast *Enhance Speech*.
Upload any recording → AI removes noise, fans, traffic, echo and background
conversations → download studio-clean audio. **Everything runs locally. No
cloud, no API keys, no telemetry.**

![status](https://img.shields.io/badge/engine-DeepFilterNet%203-blue) ![privacy](https://img.shields.io/badge/privacy-100%25%20local-green) ![license](https://img.shields.io/badge/models-MIT%20%2F%20Apache--2.0-blue)

---

## Features

- **AI noise removal** — fans, AC, traffic, keyboard, room noise (DeepFilterNet 3)
- **Background conversation reduction** — quieter competing talkers are strongly attenuated
- **Echo & reverb reduction** — room reflections cleaned up by the enhancement pass
- **Natural voice preservation** — tuned against over-smoothing; “Gentle” profile available
- **6 input formats** — MP3, WAV, M4A, FLAC, AAC, OGG
- **Before/After comparison** — dual players with waveforms, independent play/pause, one-click A/B switching with the playhead kept in sync
- **Real processing settings only** — every control maps to a genuine model or DSP parameter (see below)
- **Export** — enhanced WAV (16/24-bit) and MP3 (up to 320 kbps)
- **Long recordings** — chunked processing with overlap cross-fading; flat memory usage; hours-long files supported
- **Progress display** — live stage + percentage + ETA
- **Auto device selection** — CUDA GPU when available, automatic CPU fallback

---

## Model comparison & selection

Four leading open-source speech enhancement models were evaluated:

| | **DeepFilterNet 3** | Resemble Enhance | ClearerVoice-Studio (MossFormer2) | VoiceFixer |
|---|---|---|---|---|
| **Quality** (DNS/WB-PESQ) | Excellent — PESQ ≈ 3.17, STOI 0.94–0.95, CSIG 4.34 | Excellent (best perceptual polish; 44.1 kHz enhancer) | SOTA-class on SE benchmarks (16 k & 48 k models) | Good for *degraded* audio, prone to over-smoothing |
| **CPU speed** | **Real-time to 20× real-time** (RTF ≈ 0.05 measured) | Slow (~0.2–0.5× real-time) | Slow (large models) | Slow |
| **GPU needed?** | No (optional) | Strongly recommended | Strongly recommended | Recommended |
| **Voice naturalness** | Very high (deep filtering, psychoacoustic design) | High | High | Medium (“underwater” artifacts reported) |
| **Background voices** | Partial — attenuates quieter talkers (DNS-trained) | Partial | **Best** (dedicated speech-separation & target-speaker models) | No |
| **Echo/reverb** | Reduces (trained with reverb augmentation) | Yes (enhancer stage) | Partial | Partial |
| **License** | **MIT OR Apache-2.0** (commercial OK) | MIT | Apache-2.0 | MIT |
| **Install size / deps** | Small (tiny model, pip wheels win/mac/linux, Py3.8–3.11) | Medium (PyTorch + 2 models) | Large (multi-model toolkit, ModelScope/HF downloads) | Medium (stale, older stack) |
| **Maintenance** | Active (v0.5.x) | Moderate | Active | Stale |

### Verdict: DeepFilterNet 3 (default engine)

1. **CPU-first, real-time-class speed** — measured RTF ≈ 0.06 on a 2-core
   machine (≈16× faster than real-time), so it works beautifully even on
   laptops without a GPU. The competitors need a GPU to feel interactive.
2. **Natural voice quality** — the deep-filtering + ERB design is explicitly
   perceptually motivated; PESQ 3.17 / STOI 0.94 on the standard
   VoiceBank-DEMAND benchmark, matching or beating much heavier systems.
3. **Permissive licensing** — MIT / Apache-2.0 dual licence, including the
   pretrained weights. Safe for personal and commercial use.
4. **Effortless install** — one pip package, wheels for Windows/macOS/Linux,
   ~10 MB checkpoint that downloads automatically on first use.
5. **Real controls exposed** — `atten_lim_db` (noise attenuation limit),
   `post_filter`, and `mask_only` are genuine model parameters, which lets
   the UI offer *real* settings instead of placebo sliders.

**Honest limitation:** no single model can perfectly remove *overlapping*
speech of equal loudness. DeepFilterNet strongly suppresses quieter background
talkers (it is trained on DNS data with competing human sounds), and
ClearerVoice-Studio's separation models could be plugged in later via the
engine interface (`backend/engine.py`) if dedicated speaker separation is
needed — see `docs/MODEL_SETUP.md` § Alternative engines.

---

## Architecture

```
┌───────────────────────────  Browser (frontend/)  ───────────────────────────┐
│  drag&drop upload · settings panel · progress · waveforms · A/B players     │
│  vanilla JS (api.js / waveform.js / player.js / app.js) — no external CDN   │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │ HTTP (JSON + multipart + ranged audio)
┌──────────────────────────────────▼─────────────────────────────────────────┐
│ FastAPI (backend/main.py)                                                  │
│   POST /api/enhance            validate → store → queue job                │
│   GET  /api/jobs/{id}          status / progress / stage                   │
│   GET  /api/jobs/{id}/files/…  original & enhanced audio (HTTP Range)      │
│   GET  /api/jobs/{id}/waveform/…  peak data for the visualiser             │
│   GET  /api/jobs/{id}/download   WAV / MP3 export (lazy MP3 encode)        │
│   POST /api/jobs/{id}/reprocess  re-run with new settings (no re-upload)   │
│   GET  /api/capabilities       real, model-backed settings list            │
│                                                                          │
│  jobs.py        in-memory job store · worker pool · TTL file cleanup      │
│  processing.py  decode → chunked AI enhance → DSP finishing → encode      │
│  engine.py      DeepFilterNet 3 wrapper (model cache, device auto)        │
│  audio.py       FFmpeg decode · WAV/MP3 encode · waveform peaks           │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │ local inference only
                    ┌──────────────▼──────────────┐
                    │  DeepFilterNet 3 (PyTorch)  │  CPU or CUDA
                    │  ~10 MB checkpoint, local   │
                    └─────────────────────────────┘
```

**Processing pipeline** (`backend/processing.py`):

1. **Decode** — FFmpeg converts any input to 48 kHz float WAV (canonical form)
2. **Enhance** — DeepFilterNet 3, chunked (90 s + 1 s overlap, raised-cosine
   cross-fade) with live progress
3. **Finish** — optional low-cut (Butterworth) + loudness normalisation
   (EBU R128 via pyloudnorm), peak safety at −1 dBFS
4. **Render** — WAV (16/24-bit) + waveform peak data; MP3 encoded lazily on
   first download request
5. **Cleanup** — all job files deleted automatically after `JOB_TTL_SEC` (1 h)

---

## Project structure

```
auravox/
├── backend/
│   ├── main.py          FastAPI app, routes, capabilities, Range responses
│   ├── config.py        env-driven configuration
│   ├── engine.py        DeepFilterNet 3 wrapper (only real model knobs)
│   ├── processing.py    enhancement pipeline + chunking + DSP finishing
│   ├── audio.py         FFmpeg decode/encode + waveform peaks
│   └── jobs.py          job store, worker pool, TTL cleanup
├── frontend/
│   ├── index.html       premium light UI (blue & white)
│   ├── css/styles.css   design system + animations
│   └── js/              api.js · waveform.js · player.js · app.js
├── docs/
│   ├── INSTALL.md       Windows installation guide
│   ├── MODEL_SETUP.md   model weights, offline install, alternative engines
│   └── TROUBLESHOOTING.md
├── requirements.txt
├── start.bat            Windows one-click start
├── start_dev.bat        Windows dev mode (auto-reload)
└── start.sh             Linux / macOS start
```

---

## Quick start

**Windows** (full guide in `docs/INSTALL.md`):

```bat
:: 1. install Python 3.11 from python.org (tick "Add to PATH")
:: 2. optional:  winget install Gyan.FFmpeg
:: 3. double-click start.bat   → opens http://localhost:8000
```

**Linux / macOS:**

```bash
./start.sh                # or: PORT=9000 ./start.sh
```

**Manual:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

First run downloads the ~10 MB model checkpoint once (see `docs/MODEL_SETUP.md`).

---

## Settings reference (all real — no placebo controls)

| Setting | Backed by | Effect |
|---|---|---|
| Enhancement profile: Standard / Gentle | `init_df(mask_only=…)` | Standard = deep filtering (max clarity); Gentle = ERB mask only (max voice preservation) |
| Noise reduction strength 6–40 dB | `enhance(atten_lim_db=…)` | Caps noise attenuation; *Maximum* = uncapped |
| Extra cleanup pass | `init_df(post_filter=True)` | Slight extra attenuation of very noisy sections |
| Low-cut filter 20/60/80/120 Hz | SciPy Butterworth | Removes rumble/DC |
| Loudness normalisation −14/−16/−23 LUFS | pyloudnorm (EBU R128) | Consistent output level |
| WAV 16/24-bit · MP3 192/256/320 kbps | soundfile · FFmpeg/lame | Export quality |

The frontend renders the settings list returned by `GET /api/capabilities` —
if a future engine lacks a control, the UI hides it automatically.

---

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | 8000 | HTTP port |
| `HOST` | 0.0.0.0 | bind address |
| `MAX_UPLOAD_MB` | 500 | upload size limit |
| `MAX_DURATION_SEC` | 14400 | max recording length (4 h) |
| `MAX_CONCURRENT_JOBS` | 1 | parallel enhancement jobs |
| `CHUNK_SEC` | 90 | chunk length for long files |
| `JOB_TTL_SEC` | 3600 | temp-file retention |
| `DF_MODEL` | DeepFilterNet3 | model name or custom dir |
| `FFMPEG_PATH` | *(auto)* | explicit ffmpeg binary |

---

## API overview

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/enhance` | multipart `file` + `settings` JSON → `{job_id}` (202) |
| `GET` | `/api/jobs/{id}` | status, progress, stage, meta, download links |
| `GET` | `/api/jobs/{id}/files/original|enhanced` | streaming audio (HTTP Range) |
| `GET` | `/api/jobs/{id}/waveform/original|enhanced` | peaks for visualisation |
| `GET` | `/api/jobs/{id}/download?format=wav|mp3` | enhanced export |
| `POST` | `/api/jobs/{id}/reprocess` | new job from the same upload, new settings |
| `DELETE` | `/api/jobs/{id}` | delete job + files |
| `GET` | `/api/capabilities` | engine info + real settings schema |
| `GET` | `/api/health` | engine/device/ffmpeg status |

---

## Privacy & security

- Audio is processed **entirely on the local machine** — no external APIs.
- The only network event in the app's lifetime is the one-time model download
  from the official DeepFilterNet GitHub repository (or none at all, with the
  offline procedure in `docs/MODEL_SETUP.md`).
- Uploads are validated (extension, size, real decodability), stored under
  random job IDs and deleted automatically after 1 hour.
- No accounts, no analytics, no CDN scripts — the frontend has zero external
  requests.

## Model & code licences

- DeepFilterNet (code + weights): **MIT OR Apache-2.0** — https://github.com/Rikorose/DeepFilterNet
- This project's code: use it however you like (MIT-style).
- FFmpeg: LGPL/GPL depending on your build (used as an external executable).
