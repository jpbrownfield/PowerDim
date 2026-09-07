"""Centralized logging setup: a rotating file under %LOCALAPPDATA%\\PowerDim so
logs are still inspectable when running --noconsole, plus a console handler
when a console is actually attached (e.g. run_test_tray.py)."""
import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path

_LOG_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PowerDim"
_LOG_FILE = _LOG_DIR / "powerdim.log"


def configure_logging() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=1_000_000, backupCount=3
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger("powerdim")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)

    # sys.stdout is None under --noconsole/pythonw; writing to it would raise.
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
