"""
Auravox — AI enhancement engine (DeepFilterNet 3).

Wraps the open-source DeepFilterNet model (https://github.com/Rikorose/DeepFilterNet,
MIT / Apache-2.0 dual licence) and exposes ONLY controls the model genuinely
implements:

* `profile`             -> standard (deep filtering) | gentle (ERB mask only)
* `noise_reduction_db`  -> `atten_lim_db` (noise attenuation limit, in dB)
* `post_filter`         -> DeepFilterNet's optional post-filter pass

Model instances are cached per configuration (each variant is only a few MB).
"""
from __future__ import annotations

import threading
from typing import Optional, Tuple

import numpy as np
import torch
from df.enhance import enhance as df_enhance
from df.enhance import init_df

from . import config


class EngineError(RuntimeError):
    pass


class DeepFilterNetEngine:
    """Thread-safe, lazily-loaded DeepFilterNet wrapper."""

    def __init__(self) -> None:
        self._models: dict = {}
        self._lock = threading.Lock()          # guards model cache
        self._infer_lock = threading.Lock()    # serialises inference
        self._sample_rate = 48000
        self._ready = False
        self._error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def warm_up(self) -> None:
        """Pre-load the default model so the first request is fast."""
        try:
            self.get_model(post_filter=True, mask_only=False)
            self._ready = True
        except Exception as exc:  # surface the error via /api/health
            self._error = f"{type(exc).__name__}: {exc}"

    @property
    def ready(self) -> bool:
        return self._ready and self._error is None

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def device(self) -> str:
        if config.DF_DEVICE == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    @property
    def engine_name(self) -> str:
        return f"DeepFilterNet {config.DF_MODEL.replace('DeepFilterNet', '') or '3'}"

    # ------------------------------------------------------------------ #
    # Model handling
    # ------------------------------------------------------------------ #
    def get_model(self, post_filter: bool, mask_only: bool) -> Tuple[torch.nn.Module, "object"]:
        """
        Return (model, df_state) for the given configuration, loading it on
        first use. `init_df` downloads the pretrained checkpoint to the local
        cache on the very first run (one-time, ~10 MB).
        """
        key = (bool(post_filter), bool(mask_only))
        with self._lock:
            if key in self._models:
                return self._models[key]
            try:
                model, df_state, _suffix = init_df(
                    config.DF_MODEL,
                    post_filter=key[0],
                    log_level="WARNING",
                    log_file=None,          # never write enhance.log into CWD
                    config_allow_defaults=True,
                    epoch="best",
                    mask_only=key[1],
                )
            except Exception as exc:
                raise EngineError(f"Failed to load DeepFilterNet model: {exc}") from exc
            self._sample_rate = int(df_state.sr())
            self._models[key] = (model, df_state)
            return model, df_state

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def enhance_chunk(
        self,
        audio: np.ndarray,
        post_filter: bool = True,
        mask_only: bool = False,
        atten_lim_db: Optional[float] = None,
    ) -> np.ndarray:
        """
        Enhance one chunk of audio.

        audio: float32 numpy array of shape [channels, samples] at
               `self.sample_rate`.
        atten_lim_db: maximum noise attenuation in dB (None = unlimited).
        Returns enhanced audio with identical shape.
        """
        if audio.ndim != 2:
            raise EngineError(f"Expected [channels, samples], got shape {audio.shape}")
        model, df_state = self.get_model(post_filter=post_filter, mask_only=mask_only)
        x = torch.from_numpy(np.ascontiguousarray(audio))
        with self._infer_lock:
            try:
                y = df_enhance(model, df_state, x, pad=True, atten_lim_db=atten_lim_db)
            except Exception as exc:
                raise EngineError(f"AI inference failed: {exc}") from exc
        out = y.cpu().numpy()
        return np.ascontiguousarray(out, dtype=np.float32)


# Singleton used by the processing pipeline
engine = DeepFilterNetEngine()
