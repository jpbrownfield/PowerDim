"""Manual "Check for Updates" flow.

Queries the latest GitHub release, and -- only if its checksum (and, once
configured, its Authenticode signer thumbprint) verify -- hands the downloaded
exe off to a generated .bat script for the actual file swap, since a running
exe can't overwrite its own file on disk. Nothing here runs automatically or
on a timer; it's only ever triggered by the tray's "Check for Updates" click.
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .version import __version__

logger = logging.getLogger(__name__)

GITHUB_REPO = "jpbrownfield/PowerDim"
_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_ASSET_NAME = "PowerDim.exe"
_CHECKSUM_ASSET_NAME = "PowerDim.exe.sha256"

# Fill this in with the thumbprint printed by scripts/generate_codesign_cert.ps1
# once you've generated your signing cert and wired it into CI. Until then,
# downloaded updates are only checksum-verified, not signature-pinned.
EXPECTED_SIGNER_THUMBPRINT = "8EF3A8402ECA10CC8CFD3695E2574CD1610B66EB"

_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "PowerDim"
_UPDATE_DIR = _STATE_DIR / "update"


class UpdateError(Exception):
    """Raised for any verification/apply failure -- always caught by the tray
    and shown to the user rather than left to crash anything."""


@dataclass
class UpdateInfo:
    version: str  # tag_name, e.g. "v1.2.3"
    exe_url: str
    checksum_url: str | None


def _parse_version(tag: str) -> tuple[int, int, int]:
    text = tag[1:] if tag.startswith("v") else tag
    parts = text.split(".")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except (IndexError, ValueError) as exc:
        raise UpdateError(f"Unrecognized version tag: {tag!r}") from exc


def is_newer(remote_tag: str, local_version: str = __version__) -> bool:
    try:
        return _parse_version(remote_tag) > _parse_version(local_version)
    except UpdateError:
        return False


def fetch_latest_release(timeout: float = 10.0) -> UpdateInfo | None:
    """None on any network/parse failure rather than raising -- this is a
    manual, user-initiated check, so a connectivity hiccup should just look
    like "no update found," not an error dialog."""
    try:
        with urllib.request.urlopen(_RELEASES_API_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.warning("Failed to check for updates", exc_info=True)
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    exe_url = assets.get(_ASSET_NAME)
    if not exe_url:
        return None
    return UpdateInfo(
        version=data.get("tag_name", ""),
        exe_url=exe_url,
        checksum_url=assets.get(_CHECKSUM_ASSET_NAME),
    )


def check_for_update() -> UpdateInfo | None:
    info = fetch_latest_release()
    if info is None or not is_newer(info.version):
        return None
    return info


def _download(url: str, timeout: float = 30.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _verify_signature(exe_path: Path) -> None:
    """Best-effort Authenticode check via PowerShell's Get-AuthenticodeSignature
    -- far simpler than reimplementing WinVerifyTrust in ctypes for a check that
    only ever runs once per manual update. Skipped entirely until a thumbprint
    has been pinned."""
    if not EXPECTED_SIGNER_THUMBPRINT:
        return
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-AuthenticodeSignature -LiteralPath '{exe_path}') | "
            "ForEach-Object { $_.Status; $_.SignerCertificate.Thumbprint }",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2 or lines[0] != "Valid" or lines[1].upper() != EXPECTED_SIGNER_THUMBPRINT.upper():
        raise UpdateError("Downloaded update failed signature verification.")


def download_update(info: UpdateInfo) -> Path:
    """Download and verify (checksum, then optionally a pinned signature) into
    %LOCALAPPDATA%\\PowerDim\\update, all without touching the running exe."""
    _UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    exe_bytes = _download(info.exe_url)
    if info.checksum_url:
        expected = _download(info.checksum_url).decode("utf-8").strip().split()[0]
        actual = hashlib.sha256(exe_bytes).hexdigest()
        if expected.lower() != actual.lower():
            raise UpdateError("Downloaded update failed checksum verification.")
    dest = _UPDATE_DIR / "PowerDim_new.exe"
    dest.write_bytes(exe_bytes)
    _verify_signature(dest)
    return dest


# Waits for our own PID to disappear (belt-and-suspenders alongside the
# caller exiting right after apply_update() returns) before swapping files,
# since Windows won't let another process delete/overwrite an exe that's
# still mapped in via a handle without FILE_SHARE_DELETE.
_BAT_TEMPLATE = """@echo off
if exist "{target}.old" del /f /q "{target}.old" >NUL 2>&1
:wait
tasklist /fi "PID eq {pid}" | find "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto wait
)
move /y "{target}" "{target}.old" >NUL
move /y "{new_exe}" "{target}" >NUL
start "" "{target}"
del /f /q "{target}.old" >NUL 2>&1
del "%~f0"
"""


def apply_update(new_exe_path: Path) -> None:
    """Hands the actual file swap off to a generated .bat, since a running exe
    can't overwrite its own file. The caller must exit the app right after this
    returns -- the .bat's own PID-wait loop is just a second safety net."""
    if not getattr(sys, "frozen", False):
        raise UpdateError("Updating only works from the built .exe, not when running from source.")
    target = Path(sys.executable)
    bat_path = _UPDATE_DIR / "apply_update.bat"
    bat_path.write_text(_BAT_TEMPLATE.format(pid=os.getpid(), target=target, new_exe=new_exe_path))
    detached_process = 0x00000008
    create_new_process_group = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        creationflags=detached_process | create_new_process_group,
        close_fds=True,
    )
