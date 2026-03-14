"""Debug endpoints for capturing backend logs during E2E tests.

Only registered when ENVIRONMENT != "production".
"""

import logging
from io import StringIO

from fastapi import APIRouter

router = APIRouter(prefix="/debug", tags=["debug"])

_capture_handler: logging.StreamHandler[StringIO] | None = None
_capture_buffer: StringIO | None = None


@router.post("/start-log-capture")
async def start_log_capture() -> dict[str, str]:
    """Attach a handler to the root logger and capture all output."""
    global _capture_handler, _capture_buffer

    # Clean up any previous capture
    if _capture_handler:
        logging.getLogger().removeHandler(_capture_handler)
        _capture_handler.close()

    _capture_buffer = StringIO()
    _capture_handler = logging.StreamHandler(_capture_buffer)
    _capture_handler.setLevel(logging.DEBUG)
    _capture_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(_capture_handler)
    return {"status": "capturing"}


@router.post("/stop-log-capture")
async def stop_log_capture() -> dict[str, str]:
    """Remove the capture handler and return the collected logs."""
    global _capture_handler, _capture_buffer

    log_text = ""
    if _capture_handler and _capture_buffer:
        _capture_handler.flush()
        log_text = _capture_buffer.getvalue()
        logging.getLogger().removeHandler(_capture_handler)
        _capture_handler.close()
        _capture_handler = None
        _capture_buffer = None

    return {"log": log_text}
