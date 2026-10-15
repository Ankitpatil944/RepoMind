"""Background indexing jobs.

Indexing a large repo can take minutes, so the UI starts a job and polls it. Jobs run
one at a time on a single worker thread (embedding is CPU-bound and they all write to
the same database). State is in memory: it survives page reloads but not an API
restart, which is fine because re-running ingest resumes from what was stored.
"""

import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from time import time

MAX_KEPT = 50

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
_lock = threading.Lock()
_jobs: "OrderedDict[str, Job]" = OrderedDict()


@dataclass
class Job:
    id: str
    source: str
    status: str = "queued"  # queued | running | done | error
    phase: str = "queued"
    done: int = 0
    total: int = 0
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time)
    finished_at: float | None = None

    def view(self) -> dict:
        d = asdict(self)
        d["elapsed_s"] = round((self.finished_at or time()) - self.created_at, 1)
        return d


def _set(job: Job, **changes) -> None:
    with _lock:
        for k, v in changes.items():
            setattr(job, k, v)


def submit(source: str, work: Callable[[Callable[[str, int, int], None]], dict]) -> Job:
    """Queue `work(progress)`; it returns the ingest result dict."""
    job = Job(id=uuid.uuid4().hex[:12], source=source)
    with _lock:
        _jobs[job.id] = job
        while len(_jobs) > MAX_KEPT:
            _jobs.popitem(last=False)

    def progress(phase: str, done: int, total: int) -> None:
        _set(job, phase=phase, done=done, total=total)

    def run() -> None:
        _set(job, status="running", phase="starting")
        try:
            result = work(progress)
        except Exception as e:  # surfaced to the user, not swallowed
            _set(job, status="error", error=str(e) or type(e).__name__, finished_at=time())
        else:
            _set(job, status="done", phase="done", result=result, finished_at=time())

    _pool.submit(run)
    return job


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)
