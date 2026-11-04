# Model Setup & AI Engine Notes

## Engine selection

Auravox uses **DeepFilterNet 3** (`DeepFilterNet` PyPI package v0.5.6) as its
enhancement engine. The selection was made after comparing the leading
open-source speech enhancement models (see README.md § Model Comparison).

## How model weights are handled

* DeepFilterNet's pretrained checkpoint is **NOT** bundled in the pip wheel.
* On the first enhancement run, `df.enhance.maybe_download_model()` downloads:

      https://github.com/Rikorose/DeepFilterNet/raw/main/models/DeepFilterNet3.zip

  (~10 MB, contains `config.ini` + `checkpoints/model_120.ckpt.best`).
* It is extracted into the local user cache:

  | OS      | Path |
  |---------|------|
  | Windows | `%LOCALAPPDATA%\DeepFilterNet\DeepFilterNet3` |
  | Linux   | `~/.cache/DeepFilterNet/DeepFilterNet3` |
  | macOS   | `~/Library/Caches/DeepFilterNet/DeepFilterNet3` |

* This is the **only** network access the app ever performs, and it happens
  once — afterwards Auravox works fully offline. No audio data is ever sent
  anywhere.

## Offline / air-gapped installation

On any machine with internet access:

1. Download `DeepFilterNet3.zip` from the URL above.
2. Copy it to the target machine and extract it into the cache folder listed
   in the table (`…/DeepFilterNet/DeepFilterNet3/` must contain
   `config.ini` and `checkpoints/`).
3. Auravox will detect the existing model and skip the download.

You can also point Auravox at a custom model directory (e.g. a fine-tuned
checkpoint) with:

    set DF_MODEL=C:\path\to\my_model_dir

The directory must follow the DeepFilterNet layout (`config.ini` +
`checkpoints/`). Keep `DF_MODEL=DeepFilterNet3` for the stock model.

## Which controls are real

Auravox only exposes settings the model genuinely implements (verified
against the DeepFilterNet source code):

| UI control | Model API | Notes |
|---|---|---|
| Enhancement profile: Standard / Gentle | `init_df(mask_only=...)` | Gentle disables the deep-filtering stage (ERB mask only) — more conservative |
| Noise reduction strength (6–40 dB) | `enhance(atten_lim_db=...)` | Caps attenuation; “Maximum” = uncapped |
| Extra cleanup pass | `init_df(post_filter=True)` | DeepFilterNet's post-filter (mask_pf) |
| Low-cut filter / Loudness / WAV / MP3 quality | Real DSP (SciPy, pyloudnorm, FFmpeg) | Transparent post-processing, clearly labelled “Finishing” & “Export” |

There are no fake sliders.

## Hardware requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | any x86-64 / ARM, 2 cores | 4+ cores (enhances ~10–20× faster than real-time) |
| RAM | 2 GB | 4 GB+ for very long files |
| GPU | none needed | any CUDA GPU (auto-detected) |
| Disk | ~1.5 GB (Python + packages) + ~10 MB model | — |

Long files are processed in 90-second overlapping chunks, so memory usage
stays flat regardless of recording length.

## Alternative engines (advanced)

The backend isolates the model behind `backend/engine.py` +
`backend/processing.py`. Other engines can be added by implementing the same
three-method interface (`warm_up`, `get_model`, `enhance_chunk`) and updating
the capability list in `backend/main.py`:

* **Resemble Enhance** (MIT, 44.1 kHz, best perceptual quality but much
  heavier — GPU strongly recommended).
* **ClearerVoice-Studio / MossFormer2_SE_48K** (Apache-2.0, excellent with
  competing speech, but large models and slower on CPU).
* **VoiceFixer** (restoration of badly degraded audio; tends to over-smooth).

See the model comparison in README.md for why DeepFilterNet 3 is the default.
