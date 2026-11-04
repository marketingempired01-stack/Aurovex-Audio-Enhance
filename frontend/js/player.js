/* ==========================================================================
   Auravox — custom audio player (one per track: original / enhanced)
   ========================================================================== */
"use strict";

class AudioPlayer {
  /**
   * @param {HTMLElement} root   .player element
   * @param {object} opts { onPlay, onPause, onTimeUpdate, waveTheme }
   */
  constructor(root, opts = {}) {
    this.root = root;
    this.opts = opts;
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.playBtn = root.querySelector(".play-btn");
    this.iconPlay = root.querySelector(".icon-play");
    this.iconPause = root.querySelector(".icon-pause");
    this.canvas = root.querySelector(".wave-canvas");
    this.tCur = root.querySelector(".t-cur");
    this.tDur = root.querySelector(".t-dur");
    this.volume = root.querySelector(".volume");
    this.wave = new Waveform(this.canvas, opts.waveTheme);

    // ---- events ----
    this.playBtn.addEventListener("click", () => this.toggle());
    this.audio.addEventListener("play", () => {
      this._setPlaying(true);
      this._loop();
      this.opts.onPlay && this.opts.onPlay(this);
    });
    this.audio.addEventListener("pause", () => {
      this._setPlaying(false);
      this.opts.onPause && this.opts.onPause(this);
    });
    this.audio.addEventListener("ended", () => {
      this._setPlaying(false);
      this.setProgress(0);
    });
    this.audio.addEventListener("loadedmetadata", () => {
      this.tDur.textContent = fmtTime(this.audio.duration);
    });
    this.audio.addEventListener("timeupdate", () => {
      if (this._raf) return; // RAF handles updates while playing
      this._syncTime();
    });
    this.audio.addEventListener("error", () => {
      this._setPlaying(false);
    });

    // seek by clicking the waveform
    this.canvas.addEventListener("click", (e) => {
      if (!this.audio.duration) return;
      const rect = this.canvas.getBoundingClientRect();
      const p = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      this.audio.currentTime = p * this.audio.duration;
      this._syncTime();
    });

    // volume
    this.volume.addEventListener("input", () => {
      this.audio.volume = parseFloat(this.volume.value);
    });

    this._setPlaying(false); // initial icon state
  }

  setSource(url) {
    this.audio.src = url;
    this.audio.load();
  }

  setPeaks(peaks) {
    this.wave.setPeaks(peaks);
  }

  toggle() {
    if (this.audio.paused) {
      // pause the other player via callback contract (app handles exclusivity)
      this.opts.beforePlay && this.opts.beforePlay(this);
      this.audio.play().catch(() => {});
    } else {
      this.audio.pause();
    }
  }

  pause() { this.audio.pause(); }

  play() { this.audio.play().catch(() => {}); }

  isPlaying() { return !this.audio.paused && !this.audio.ended; }

  currentTime() { return this.audio.currentTime || 0; }

  seekTo(t) {
    if (isFinite(t)) {
      this.audio.currentTime = t;
      this._syncTime();
    }
  }

  setProgress(p) {
    this.wave.setProgress(p);
  }

  _setPlaying(playing) {
    // playing → play icon (center), stopped/paused → pause icon
    this.iconPlay.hidden = !playing;
    this.iconPause.hidden = playing;
    this.root.classList.toggle("playing", playing);
  }

  _syncTime() {
    const dur = this.audio.duration || 0;
    const cur = this.audio.currentTime || 0;
    this.tCur.textContent = fmtTime(cur);
    if (dur) this.wave.setProgress(cur / dur);
    this.opts.onTimeUpdate && this.opts.onTimeUpdate(this, cur, dur);
  }

  _loop() {
    cancelAnimationFrame(this._raf);
    const tick = () => {
      if (this.audio.paused) { this._syncTime(); this._raf = null; return; }
      this._syncTime();
      this._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  }
}

function fmtTime(s) {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

window.AudioPlayer = AudioPlayer;
window.fmtTime = fmtTime;
