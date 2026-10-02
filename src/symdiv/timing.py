"""External wall-clock supervisor for potentially uninterruptible solver work."""
import os
import signal
import subprocess
import time


def shared_clock():
    """POSIX clock_gettime has a common origin, unlike macOS Python 3.9 monotonic."""
    return time.clock_gettime(time.CLOCK_MONOTONIC)


def local_origin(shared_started):
    """Translate a shared start timestamp into this interpreter's clock domain."""
    return time.monotonic() - max(0, shared_clock() - shared_started)


def supervise(command, cwd, started, budget_seconds):
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    timeout = max(0.001, budget_seconds-(time.monotonic()-started))
    expired = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        expired = True
        # Kill the worker and its provider subprocess together. Killing only the
        # worker could leave a request running and unaccounted in the background.
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        stdout, stderr = process.communicate()
    return {"timed_out":expired,"returncode":process.returncode,"stdout":stdout,"stderr":stderr,
            "elapsed_seconds":time.monotonic()-started}
