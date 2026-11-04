/* ==========================================================================
   Auravox — application orchestrator
   State machine: IDLE -> FILE_SELECTED -> UPLOADING -> PROCESSING -> DONE
   ========================================================================== */
"use strict";

(() => {
  // ------------------------------------------------------------------ //
  // Elements
  // ------------------------------------------------------------------ //
  const $ = (id) => document.getElementById(id);
  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const workspace = $("workspace");
  const fileCard = $("file-card");
  const fileNameEl = $("file-name");
  const fileChips = $("file-chips");
  const settingsCard = $("settings-card");
  const progressCard = $("progress-card");
  const resultsCard = $("results-card");
  const enhanceBtn = $("enhance-btn");
  const progressPct = $("progress-pct");
  const progressStage = $("progress-stage");
  const progressEta = $("progress-eta");
  const progressFill = $("progress-fill");
  const ringBar = $("ring-bar");
  const toast = $("toast");
  const noiseSlider = $("set-noise");
  const noiseValue = $("noise-value");

  // ------------------------------------------------------------------ //
  // State
  // ------------------------------------------------------------------ //
  const state = {
    file: null,
    jobId: null,
    job: null,
    playerA: null,
    playerB: null,
    abActive: "original",
    pollTimer: null,
    progressHistory: [],
    capabilities: null,
    durationSec: null,
  };

  const EXT_OK = ["mp3", "wav", "m4a", "flac", "aac", "ogg", "mp4", "mov", "m4v", "mkv", "webm"];

  // ------------------------------------------------------------------ //
  // Helpers
  // ------------------------------------------------------------------ //
  function showToast(msg, isError = false) {
    toast.textContent = msg;
    toast.classList.toggle("error", isError);
    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add("show"));
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => (toast.hidden = true), 300);
    }, isError ? 5200 : 3200);
  }

  function fmtBytes(b) {
    if (b > 1024 * 1024 * 1024) return `${(b / 1024 ** 3).toFixed(2)} GB`;
    if (b > 1024 * 1024) return `${(b / 1024 ** 2).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(b / 1024))} KB`;
  }

  function fmtDurationLocal(sec) {
    if (!isFinite(sec)) return "—";
    const m = Math.floor(sec / 60), s = Math.round(sec % 60);
    return m > 0 ? `${m} min ${s} s` : `${s} s`;
  }

  // fade-up on scroll
  const io = new IntersectionObserver(
    (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("in-view")),
    { threshold: 0.12 }
  );
  document.querySelectorAll(".fade-up").forEach((el) => io.observe(el));

  // slider fill (all range inputs: noise slider + volume sliders)
  function syncSliderFill(slider) {
    const p = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
    slider.style.setProperty("--fill", `${p}%`);
  }
  function syncAllSliders() {
    document.querySelectorAll('input[type="range"]').forEach(syncSliderFill);
  }
  function syncNoiseLabel() {
    const v = parseInt(noiseSlider.value, 10);
    noiseValue.textContent = v >= 40 ? "Maximum" : v >= 26 ? "Strong" : v >= 15 ? "Balanced" : "Light";
  }
  document.addEventListener("input", (e) => {
    if (e.target && e.target.matches('input[type="range"]')) syncSliderFill(e.target);
    if (e.target === noiseSlider) syncNoiseLabel();
  });
  syncAllSliders(); syncNoiseLabel();

  // ------------------------------------------------------------------ //
  // Capabilities (server tells us which settings are real)
  // ------------------------------------------------------------------ //
  async function loadCapabilities() {
    try {
      const res = await fetch("/api/capabilities");
      state.capabilities = await res.json();
      const c = state.capabilities;
      // hide any control the engine does not genuinely support
      const supported = new Set(c.settings.map((s) => s.id));
      const map = {
        profile: "set-profile", noise_reduction_db: "set-noise", post_filter: "set-postfilter",
        highpass_hz: "set-highpass", loudness: "set-loudness",
        wav_bit_depth: "set-wav", mp3_bitrate: "set-mp3",
      };
      for (const [key, id] of Object.entries(map)) {
        if (!supported.has(key)) {
          const el = $(id);
          const field = el && el.closest(".field");
          if (field) field.style.display = "none";
        }
      }
      const exts = c.allowed_extensions.map((e) => e.replace(".", "")).join(",");
      fileInput.accept = `.${EXT_OK.join(",.")},${exts},audio/*`;
    } catch {
      /* server not ready — controls still work with defaults */
    }
  }
  loadCapabilities();

  // ------------------------------------------------------------------ //
  // File selection
  // ------------------------------------------------------------------ //
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
  );
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) acceptFile(f);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) acceptFile(fileInput.files[0]);
    fileInput.value = "";
  });

  function acceptFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const maxMB = (state.capabilities && state.capabilities.max_upload_mb) || 500;
    if (!EXT_OK.includes(ext)) {
      showToast(`Unsupported file type "${ext}". Use MP3, WAV, M4A, FLAC, AAC, OGG — or MP4/MOV/MKV video.`, true);
      return;
    }
    if (file.size > maxMB * 1024 * 1024) {
      showToast(`File is ${fmtBytes(file.size)} — the limit is ${maxMB} MB.`, true);
      return;
    }
    if (file.size === 0) { showToast("That file is empty.", true); return; }

    state.file = file;
    // hide everything else until the user starts
    resultsCard.hidden = true;
    progressCard.hidden = true;
    workspace.hidden = false;
    settingsCard.hidden = false;
    fileCard.hidden = false;

    fileNameEl.textContent = file.name;
    fileChips.innerHTML = "";
    const chips = [
      ext.toUpperCase(),
      fmtBytes(file.size),
      state.durationSec ? fmtDurationLocal(state.durationSec) : null,
    ].filter(Boolean);
    chips.forEach((c) => {
      const s = document.createElement("span");
      s.className = "chip";
      s.textContent = c;
      fileChips.appendChild(s);
    });

    // local duration probe (browser decode)
    probeDuration(file).then((d) => {
      if (state.file !== file) return;
      state.durationSec = d;
      const s = document.createElement("span");
      s.className = "chip";
      s.textContent = fmtDurationLocal(d);
      fileChips.appendChild(s);
    }).catch(() => {});

    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function probeDuration(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const a = new Audio();
      a.preload = "metadata";
      a.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(a.duration); };
      a.onerror = () => { URL.revokeObjectURL(url); reject(); };
      a.src = url;
    });
  }

  $("file-remove").addEventListener("click", resetAll);

  // ------------------------------------------------------------------ //
  // Settings collection (only real, server-declared settings)
  // ------------------------------------------------------------------ //
  function collectSettings() {
    return {
      profile: document.querySelector('input[name="profile"]:checked')?.value || "standard",
      noise_reduction_db: parseInt(noiseSlider.value, 10),
      post_filter: $("set-postfilter").checked,
      highpass_hz: parseFloat($("set-highpass").value),
      loudness: $("set-loudness").value === "off" ? "off" : parseFloat($("set-loudness").value),
      wav_bit_depth: parseInt($("set-wav").value, 10),
      mp3_bitrate: parseInt($("set-mp3").value, 10),
    };
  }

  // ------------------------------------------------------------------ //
  // Enhancement flow
  // ------------------------------------------------------------------ //
  enhanceBtn.addEventListener("click", async () => {
    if (!state.file) return;
    enhanceBtn.disabled = true;
    progressCard.hidden = false;
    resultsCard.hidden = true;
    state.progressHistory = [{ t: Date.now(), p: 0 }];
    setProgress(2, "Uploading file…", "Starting…");
    progressCard.scrollIntoView({ behavior: "smooth", block: "center" });

    try {
      const { job_id } = await API.uploadAudio(state.file, collectSettings(), (frac) => {
        setProgress(Math.max(2, frac * 12), "Uploading file…", null);
      });
      state.jobId = job_id;
      setProgress(12, "Processing locally…", null);
      pollJob();
    } catch (err) {
      showToast(err.message, true);
      progressCard.hidden = true;
      enhanceBtn.disabled = false;
    }
  });

  function pollJob() {
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(async () => {
      try {
        const job = await API.getJob(state.jobId);
        state.job = job;
        if (job.status === "completed") {
          setProgress(100, "Done", null);
          setTimeout(() => showResults(job), 350);
          return;
        }
        if (job.status === "failed") {
          showToast(job.error || "Enhancement failed.", true);
          progressCard.hidden = true;
          enhanceBtn.disabled = false;
          return;
        }
        setProgress(job.progress, job.stage, null);
      } catch (err) {
        showToast(err.message, true);
      }
      pollJob();
    }, 700);
  }

  function setProgress(pct, stage, etaText) {
    const p = Math.min(100, Math.max(0, pct));
    progressPct.textContent = Math.round(p);
    progressFill.style.width = `${p}%`;
    ringBar.style.strokeDashoffset = String(264 - (264 * p) / 100);
    if (stage) progressStage.textContent = stage;

    // ETA from observed progress velocity
    if (etaText !== null && etaText !== undefined) {
      progressEta.textContent = etaText;
    } else {
      const now = Date.now();
      state.progressHistory.push({ t: now, p });
      if (state.progressHistory.length > 12) state.progressHistory.shift();
      const first = state.progressHistory[0];
      const dp = p - first.p;
      const dt = (now - first.t) / 1000;
      if (dp > 1 && dt > 0.4 && p < 99) {
        const remain = ((100 - p) * dt) / dp;
        progressEta.textContent =
          remain > 90 ? `About ${Math.ceil(remain / 60)} min left`
          : remain > 3 ? `About ${Math.ceil(remain)} seconds left`
          : "Almost done…";
      } else if (p >= 99) {
        progressEta.textContent = "Almost done…";
      }
    }
  }

  $("cancel-btn").addEventListener("click", async () => {
    clearTimeout(state.pollTimer);
    if (state.jobId) { try { await fetch(`/api/jobs/${state.jobId}`, { method: "DELETE" }); } catch {} }
    resetAll();
  });

  // ------------------------------------------------------------------ //
  // Results
  // ------------------------------------------------------------------ //
  async function showResults(job) {
    enhanceBtn.disabled = false;
    progressCard.hidden = true;
    resultsCard.hidden = false;

    const meta = job.meta || {};
    $("results-meta").textContent =
      `Duration ${fmtDurationLocal(meta.duration)} · ${meta.channels || 1} channel${(meta.channels || 1) > 1 ? "s" : ""} · enhanced locally`;

    $("download-wav").href = API.downloadURL(job.id, "wav");
    $("download-mp3").href = API.downloadURL(job.id, "mp3");

    // video download (only when the upload was a video)
    const dlVideo = $("download-video");
    if (dlVideo) {
      const vext = state.file ? (state.file.name.split(".").pop() || "video").toLowerCase() : "video";
      if (job.files && job.files.download_video) {
        dlVideo.href = API.downloadURL(job.id, "video");
        dlVideo.textContent = `↓ ${vext.toUpperCase()}`;
        dlVideo.hidden = false;
      } else {
        dlVideo.hidden = true;
      }
    }

    $("orig-format").textContent = state.file
      ? `${(state.file.name.split(".").pop() || "").toUpperCase()} · ${fmtBytes(state.file.size)}`
      : "Original";
    $("enh-format").textContent = `WAV · ${parseInt($("set-wav").value, 10)}-bit`;

    // players
    if (!state.playerA) {
      state.playerA = new AudioPlayer($("player-original"), {
        beforePlay: () => { state.playerB.pause(); setActiveAB("original", false); },
        onPlay: () => setActiveAB("original", true),
      });
      state.playerB = new AudioPlayer($("player-enhanced"), {
        beforePlay: () => { state.playerA.pause(); setActiveAB("enhanced", false); },
        onPlay: () => setActiveAB("enhanced", true),
        waveTheme: {
          playedTop: "#b7f5d6", playedBottom: "#35c27e",
          baseTop: "#2b2e33", baseBottom: "#1a1c1f",
          head: "#6ee7a8",
        },
      });
    }
    state.playerA.setSource(API.fileURL(job.id, "original"));
    state.playerB.setSource(API.fileURL(job.id, "enhanced"));
    state.playerA.setProgress(0);
    state.playerB.setProgress(0);

    // waveforms
    try {
      const [wA, wB] = await Promise.all([
        API.getWaveform(job.id, "original"),
        API.getWaveform(job.id, "enhanced"),
      ]);
      state.playerA.setPeaks(wA.peaks);
      state.playerB.setPeaks(wB.peaks);
    } catch {
      /* peaks are cosmetic */
    }

    resultsCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function setActiveAB(which, andScroll) {
    state.abActive = which;
    $("ab-original").classList.toggle("active", which === "original");
    $("ab-enhanced").classList.toggle("active", which === "enhanced");
    $("player-original").classList.toggle("active-ab", which === "original");
    $("player-enhanced").classList.toggle("active-ab", which === "enhanced");
    if (andScroll) return;
  }

  // A/B switch: swap which track plays, keeping the playhead position
  $("ab-switch").addEventListener("click", () => {
    if (!state.playerA || !state.playerB) return;
    const from = state.abActive === "original" ? state.playerA : state.playerB;
    const to = state.abActive === "original" ? state.playerB : state.playerA;
    const t = from.currentTime();
    const wasPlaying = from.isPlaying();
    from.pause();
    to.seekTo(t);
    if (wasPlaying) to.play();
    setActiveAB(state.abActive === "original" ? "enhanced" : "original");
  });

  $("ab-original").addEventListener("click", () => {
    if (!state.playerA) return;
    const t = state.playerB.currentTime();
    state.playerB.pause();
    state.playerA.seekTo(t);
    state.playerA.play();
    setActiveAB("original");
  });

  $("ab-enhanced").addEventListener("click", () => {
    if (!state.playerB) return;
    const t = state.playerA.currentTime();
    state.playerA.pause();
    state.playerB.seekTo(t);
    state.playerB.play();
    setActiveAB("enhanced");
  });

  // ------------------------------------------------------------------ //
  // Re-process / restart
  // ------------------------------------------------------------------ //
  $("reprocess-btn").addEventListener("click", async () => {
    if (!state.jobId) return;
    const btn = $("reprocess-btn");
    btn.disabled = true;
    try {
      const { job_id } = await API.reprocess(state.jobId, collectSettings());
      state.jobId = job_id;
      state.progressHistory = [{ t: Date.now(), p: 0 }];
      progressCard.hidden = false;
      resultsCard.hidden = true;
      setProgress(2, "Processing locally…", null);
      pollJob();
      progressCard.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (err) {
      showToast(err.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  $("restart-btn").addEventListener("click", resetAll);

  function resetAll() {
    clearTimeout(state.pollTimer);
    if (state.playerA) { state.playerA.pause(); state.playerB.pause(); }
    state.file = null;
    state.jobId = null;
    state.job = null;
    state.durationSec = null;
    workspace.hidden = true;
    progressCard.hidden = true;
    resultsCard.hidden = true;
    enhanceBtn.disabled = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
})();
