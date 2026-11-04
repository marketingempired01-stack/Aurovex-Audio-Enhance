/* ==========================================================================
   Auravox — waveform rendering on <canvas>
   Draws rounded peak bars with a gradient, plus a played-progress overlay
   and a playhead line. Handles devicePixelRatio and resize automatically.
   ========================================================================== */
"use strict";

class Waveform {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} theme  {base, played, head}
   */
  constructor(canvas, theme = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.peaks = null;
    this.progress = 0;            // 0..1
    this.theme = Object.assign({
      base: "#2b2e33",              // fallback
      playedTop: "#dfe3e8",         // A track: cool neutral played
      playedBottom: "#8a9099",
      baseTop: "#2b2e33",           // unplayed bars
      baseBottom: "#1a1c1f",
      head: "#ffffff",
    }, theme);
    this._resize = this._resize.bind(this);
    window.addEventListener("resize", this._resize);
    // HiDPI sizing
    this._resize();
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(10, rect.width || this.canvas.clientWidth || 300);
    const h = Math.max(10, this.canvas.getAttribute("height") * 1 || rect.height || 88);
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.canvas.style.height = `${h}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = w; this.h = h;
    this.draw();
  }

  setPeaks(peaks) {
    this.peaks = peaks && peaks.length ? peaks : null;
    this.draw();
  }

  setProgress(p) {
    this.progress = Math.min(1, Math.max(0, p || 0));
    this.draw();
  }

  draw() {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);
    if (!this.peaks) {
      // placeholder line
      ctx.strokeStyle = "rgba(255,255,255,0.12)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, h / 2);
      ctx.lineTo(w, h / 2);
      ctx.stroke();
      return;
    }

    const mid = h / 2;
    const n = this.peaks.length;
    const barW = 2.2;
    const gap = 1.8;
    const step = barW + gap;
    const bars = Math.max(1, Math.floor(w / step));
    const playedX = this.progress * w;

    for (let i = 0; i < bars; i++) {
      const x = i * step;
      // sample the peaks array at this pixel position
      const idx = Math.min(n - 1, Math.floor((i / bars) * n));
      const amp = this.peaks[idx] || 0;
      const barH = Math.max(2, amp * (h * 0.86));

      const grad = ctx.createLinearGradient(0, mid - barH / 2, 0, mid + barH / 2);
      if (x <= playedX) {
        grad.addColorStop(0, this.theme.playedTop);
        grad.addColorStop(1, this.theme.playedBottom);
      } else {
        grad.addColorStop(0, this.theme.baseTop);
        grad.addColorStop(1, this.theme.baseBottom);
      }
      ctx.fillStyle = grad;

      const r = barW / 2;
      const y = mid - barH / 2;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(x, y, barW, barH, r);
      } else {
        ctx.rect(x, y, barW, barH);
      }
      ctx.fill();
    }

    // playhead
    if (this.progress > 0 && this.progress < 1) {
      ctx.fillStyle = this.theme.head;
      ctx.fillRect(playedX - 1, 2, 2, h - 4);
      ctx.beginPath();
      ctx.arc(playedX, 4, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

window.Waveform = Waveform;
