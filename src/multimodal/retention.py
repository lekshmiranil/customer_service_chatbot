"""Background sweep that deletes uploads past their retention period.

The sweep runs in one daemon thread per server process. It only calls
purge_expired, so the retention rules stay in intake.py. Failures are logged
by exception type only, never by message, so no path or file content reaches
the log.

Setting: RETENTION_SWEEP_MINUTES (default 10, must be greater than zero).
"""

import os
import threading

from src.multimodal.intake import purge_expired
from src.pipeline.metrics import record

DEFAULT_SWEEP_MINUTES = 10.0

_lock = threading.Lock()
_thread = None
_stop = threading.Event()


def _interval_seconds() -> float:
    raw = os.getenv("RETENTION_SWEEP_MINUTES", "").strip()
    if not raw:
        return DEFAULT_SWEEP_MINUTES * 60
    try:
        minutes = float(raw)
    except ValueError:
        raise ValueError(f"RETENTION_SWEEP_MINUTES must be a number, got {raw!r}") from None
    if minutes <= 0:
        raise ValueError(f"RETENTION_SWEEP_MINUTES must be greater than zero, got {raw!r}")
    return minutes * 60


def sweep_once(now=None) -> int:
    """Runs one purge and returns how many uploads were deleted. Never raises."""
    try:
        return purge_expired(now=now)
    except Exception as exc:
        record("retention_sweep_failed", error_type=type(exc).__name__)
        return 0


def _run(interval: float) -> None:
    while not _stop.wait(interval):
        sweep_once()


def start_sweeper() -> bool:
    """Starts the sweep thread once. Returns False if it is already running.

    The interval is read before the thread starts, so a bad setting fails at
    app start instead of silently inside the thread.
    """
    global _thread
    interval = _interval_seconds()
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        _thread = threading.Thread(
            target=_run, args=(interval,), name="upload-retention-sweep", daemon=True
        )
        _thread.start()
        return True


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def stop_sweeper() -> None:
    """Stops the sweep thread. Used by tests; the app lets the daemon die with the process."""
    global _thread
    with _lock:
        _stop.set()
        thread = _thread
    if thread is not None:
        thread.join(timeout=5)
    with _lock:
        _thread = None