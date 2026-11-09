"""Checks for the retention sweep. Run: python test_retention.py"""

import io
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from PIL import Image

from src.multimodal import intake, retention

checks = 0
failures = 0


def check(name, condition):
    global checks, failures
    checks += 1
    if condition:
        print(f"PASS  {name}")
    else:
        failures += 1
        print(f"FAIL  {name}")


def png_bytes():
    image = Image.new("RGB", (400, 200), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def names_in(directory):
    return sorted(p.name for p in Path(directory).iterdir())


def raises(exception_type, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except exception_type:
        return True
    except Exception:
        return False
    return False


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["UPLOAD_DIR"] = tmp
        os.environ["UPLOAD_RETENTION_HOURS"] = "24"
        os.environ.pop("RETENTION_SWEEP_MINUTES", None)

        with mock.patch.object(intake, "record"), mock.patch.object(retention, "record"):
            # Interval setting
            check("default interval is 10 minutes", retention._interval_seconds() == 600)
            os.environ["RETENTION_SWEEP_MINUTES"] = "0.5"
            check("interval 0.5 minutes is 30 seconds", retention._interval_seconds() == 30)
            os.environ["RETENTION_SWEEP_MINUTES"] = "0"
            check("interval 0 is refused", raises(ValueError, retention._interval_seconds))
            os.environ["RETENTION_SWEEP_MINUTES"] = "abc"
            check("interval abc is refused", raises(ValueError, retention._interval_seconds))
            os.environ.pop("RETENTION_SWEEP_MINUTES")

            # Back-dated expiry with now=
            intake.accept_upload("sample.png", png_bytes())
            check("upload stored as image plus sidecar", len(names_in(tmp)) == 2)
            check("fresh upload is kept by a sweep", retention.sweep_once() == 0 and len(names_in(tmp)) == 2)

            future = datetime.now(timezone.utc) + timedelta(hours=25)
            file_id = next(Path(tmp).glob("*.json")).stem
            check(
                "get_upload refuses an expired file",
                raises(intake.UploadUnavailable, intake.get_upload, file_id, now=future),
            )
            retention.sweep_once(now=future)
            check("sweep deletes the expired upload", names_in(tmp) == [])

            # A failing purge must not raise or leak details
            with mock.patch.object(retention, "purge_expired", side_effect=OSError("secret path")):
                check("failing purge returns 0 without raising", retention.sweep_once() == 0)
                logged = retention.record.call_args
                check(
                    "failure log holds only the exception type",
                    logged is not None
                    and logged.args == ("retention_sweep_failed",)
                    and logged.kwargs == {"error_type": "OSError"},
                )

            # Real thread, tiny retention and interval
            os.environ["UPLOAD_RETENTION_HOURS"] = "0.0001"
            os.environ["RETENTION_SWEEP_MINUTES"] = "0.02"
            intake.accept_upload("sample.png", png_bytes())
            check("short-lived upload stored", len(names_in(tmp)) == 2)
            check("sweeper starts", retention.start_sweeper() is True)
            check("sweeper is running", retention.is_running())
            check("second start is ignored", retention.start_sweeper() is False)
            deadline = time.time() + 15
            while names_in(tmp) and time.time() < deadline:
                time.sleep(0.5)
            check("thread deleted the expired upload on its own", names_in(tmp) == [])
            retention.stop_sweeper()
            check("sweeper stops", not retention.is_running())

    print(f"\n{checks - failures}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())