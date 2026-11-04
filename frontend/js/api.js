/* ==========================================================================
   Auravox — API client
   ========================================================================== */
"use strict";

const API = (() => {

  /** Upload an audio file with settings. Returns {job_id}. Uses XHR for upload progress. */
  function uploadAudio(file, settings, onUploadProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/enhance");
      xhr.responseType = "json";

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onUploadProgress) {
          onUploadProgress(e.loaded / e.total);
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
        else reject(new Error((xhr.response && xhr.response.detail) || `Upload failed (${xhr.status})`));
      };
      xhr.onerror = () => reject(new Error("Network error — is the Auravox server running?"));

      const form = new FormData();
      form.append("file", file);
      form.append("settings", JSON.stringify(settings));
      xhr.send(form);
    });
  }

  /** Re-run enhancement on an existing job's file with new settings. */
  async function reprocess(jobId, settings) {
    const res = await fetch(`/api/jobs/${jobId}/reprocess`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Re-processing failed");
    return res.json();
  }

  /** Poll job status once. */
  async function getJob(jobId) {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error("Job not found");
    return res.json();
  }

  /** Fetch waveform peaks. */
  async function getWaveform(jobId, which) {
    const res = await fetch(`/api/jobs/${jobId}/waveform/${which}`);
    if (!res.ok) throw new Error("Waveform not available");
    return res.json();
  }

  /** Server health / engine info. */
  async function getHealth() {
    const res = await fetch("/api/health");
    return res.json();
  }

  /* ------- URLs (used directly by <audio> and download links) ------- */
  const fileURL = (jobId, which) => `/api/jobs/${jobId}/files/${which}`;
  const downloadURL = (jobId, format) => `/api/jobs/${jobId}/download?format=${format}`;

  return { uploadAudio, reprocess, getJob, getWaveform, getHealth, fileURL, downloadURL };
})();
