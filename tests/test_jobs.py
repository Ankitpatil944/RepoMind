import threading
import time

from app import jobs


def _wait(job_id: str, status: str, timeout: float = 5.0):
    end = time.time() + timeout
    while time.time() < end:
        j = jobs.get(job_id)
        if j and j.status == status:
            return j
        time.sleep(0.01)
    raise AssertionError(f"job never reached {status}: {jobs.get(job_id)}")


def test_job_reports_progress_and_result():
    gate = threading.Event()

    def work(progress):
        progress("parsing", 3, 10)
        gate.wait(2)
        return {"files_indexed": 10}

    job = jobs.submit("demo", work)
    running = _wait(job.id, "running")
    end = time.time() + 2
    while running.phase != "parsing" and time.time() < end:
        time.sleep(0.01)
    assert (running.phase, running.done, running.total) == ("parsing", 3, 10)
    gate.set()
    done = _wait(job.id, "done")
    assert done.result == {"files_indexed": 10}
    assert done.view()["elapsed_s"] >= 0


def test_job_failure_is_captured():
    def boom(_progress):
        raise RuntimeError("clone failed")

    job = jobs.submit("demo", boom)
    failed = _wait(job.id, "error")
    assert failed.error == "clone failed"
    assert failed.result is None
