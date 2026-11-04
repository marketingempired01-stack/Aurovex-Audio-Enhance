"""
Auravox — job store & background worker.

Jobs are in-memory records that track a file while it moves through the
pipeline: queued -> processing -> completed | failed. Files live under
DATA_DIR/jobs/<id>/ and are removed automatically after JOB_TTL_SEC.
"""
from __future__ import annotations

import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config


@dataclass
class Job:
    id: str
    status: str = "queued"          # queued | processing | completed | failed
    progress: float = 0.0           # 0..100
    stage: str = "Waiting in queue"
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    settings: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    # file names (relative to job dir)
    input_file: str = ""
    work_wav: str = "work.wav"      # canonical decoded 48 kHz wav
    enhanced_wav: str = "enhanced.wav"
    mp3_cache: str = "enhanced.mp3"
    enhanced_video: str = ""        # e.g. "enhanced_video.mp4" for video uploads
    original_name: str = ""

    @property
    def dir(self) -> Path:
        return config.JOBS_DIR / self.id

    def path(self, name: str) -> Path:
        return self.dir / name

    def touch(self) -> None:
        self.updated_at = time.time()

    def update(self, *, status: Optional[str] = None, progress: Optional[float] = None,
               stage: Optional[str] = None) -> None:
        if status is not None:
            self.status = status
        if progress is not None:
            self.progress = float(min(100.0, max(0.0, progress)))
        if stage is not None:
            self.stage = stage
        self.touch()

    def fail(self, message: str) -> None:
        self.status = "failed"
        self.error = message
        self.stage = "Failed"
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "status": self.status,
            "progress": round(self.progress, 1),
            "stage": self.stage,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "meta": dict(self.meta),
            "settings": dict(self.settings),
        }
        if self.status == "completed":
            result["files"] = {
                "original": f"/api/jobs/{self.id}/files/original",
                "enhanced": f"/api/jobs/{self.id}/files/enhanced",
                "waveform_original": f"/api/jobs/{self.id}/waveform/original",
                "waveform_enhanced": f"/api/jobs/{self.id}/waveform/enhanced",
                "download_wav": f"/api/jobs/{self.id}/download?format=wav",
                "download_mp3": f"/api/jobs/{self.id}/download?format=mp3",
            }
            if self.enhanced_video:
                result["files"]["video"] = f"/api/jobs/{self.id}/files/video"
                result["files"]["download_video"] = f"/api/jobs/{self.id}/download?format=video"
        return result


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, settings: Dict[str, Any], original_name: str, input_file: str) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            settings=settings,
            original_name=original_name,
            input_file=input_file,
        )
        ext = Path(input_file).suffix.lower()
        if ext in config.VIDEO_EXTENSIONS:
            job.enhanced_video = f"enhanced_video{ext}"
        job.dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        shutil.rmtree(job.dir, ignore_errors=True)
        return True

    def prune(self, ttl_sec: int) -> int:
        """Remove jobs (and their files) older than ttl_sec."""
        cutoff = time.time() - ttl_sec
        removed = 0
        with self._lock:
            stale = [jid for jid, j in self._jobs.items() if j.updated_at < cutoff]
            for jid in stale:
                job = self._jobs.pop(jid)
                shutil.rmtree(job.dir, ignore_errors=True)
                removed += 1
        return removed


store = JobStore()

# Single (by default) background worker for enhancement jobs.
executor = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_JOBS, thread_name_prefix="enhance")


def submit(job_id: str, fn) -> None:
    executor.submit(fn, job_id)
