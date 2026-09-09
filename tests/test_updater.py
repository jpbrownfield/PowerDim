import hashlib
import json
from io import BytesIO

import pytest

from powerdim import updater


def test_is_newer_true_for_higher_patch():
    assert updater.is_newer("v1.2.4", "1.2.3")


def test_is_newer_false_for_equal():
    assert not updater.is_newer("v1.2.3", "1.2.3")


def test_is_newer_false_for_lower():
    assert not updater.is_newer("v1.2.2", "1.2.3")


def test_is_newer_handles_major_and_minor_bumps():
    assert updater.is_newer("v2.0.0", "1.9.9")
    assert updater.is_newer("v1.3.0", "1.2.9")


def test_is_newer_false_for_unparseable_tag():
    assert not updater.is_newer("not-a-version", "1.2.3")


class _FakeResponse:
    def __init__(self, data: bytes):
        self._buf = BytesIO(data)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_fetch_latest_release_parses_assets(monkeypatch):
    payload = {
        "tag_name": "v9.9.9",
        "assets": [
            {"name": "PowerDim.exe", "browser_download_url": "https://example.invalid/PowerDim.exe"},
            {"name": "PowerDim.exe.sha256", "browser_download_url": "https://example.invalid/PowerDim.exe.sha256"},
        ],
    }
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda url, timeout=10.0: _FakeResponse(json.dumps(payload).encode())
    )

    info = updater.fetch_latest_release()

    assert info.version == "v9.9.9"
    assert info.exe_url == "https://example.invalid/PowerDim.exe"
    assert info.checksum_url == "https://example.invalid/PowerDim.exe.sha256"


def test_fetch_latest_release_returns_none_without_exe_asset(monkeypatch):
    payload = {"tag_name": "v9.9.9", "assets": []}
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda url, timeout=10.0: _FakeResponse(json.dumps(payload).encode())
    )

    assert updater.fetch_latest_release() is None


def test_fetch_latest_release_returns_none_on_network_error(monkeypatch):
    def raise_error(url, timeout=10.0):
        raise OSError("no network")

    monkeypatch.setattr(updater.urllib.request, "urlopen", raise_error)

    assert updater.fetch_latest_release() is None


def test_check_for_update_returns_none_when_not_newer(monkeypatch):
    # is_newer's default local_version is bound to __version__ at import time
    # (currently "0.0.0" from powerdim/version.py), so compare against that
    # directly rather than trying to monkeypatch it after the fact.
    monkeypatch.setattr(
        updater, "fetch_latest_release", lambda: updater.UpdateInfo(version="v0.0.0", exe_url="x", checksum_url=None)
    )

    assert updater.check_for_update() is None


def test_check_for_update_returns_info_when_newer(monkeypatch):
    info = updater.UpdateInfo(version="v99.0.0", exe_url="x", checksum_url=None)
    monkeypatch.setattr(updater, "fetch_latest_release", lambda: info)

    assert updater.check_for_update() is info


def test_download_update_rejects_checksum_mismatch(tmp_path, monkeypatch):
    exe_bytes = b"fake-exe-contents"
    responses = iter([exe_bytes, b"deadbeef  PowerDim.exe"])
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda url, timeout=30.0: _FakeResponse(next(responses)))
    monkeypatch.setattr(updater, "_UPDATE_DIR", tmp_path)

    info = updater.UpdateInfo(version="v9.9.9", exe_url="x", checksum_url="y")

    with pytest.raises(updater.UpdateError):
        updater.download_update(info)


def test_download_update_accepts_matching_checksum(tmp_path, monkeypatch):
    exe_bytes = b"fake-exe-contents"
    checksum = hashlib.sha256(exe_bytes).hexdigest()
    responses = iter([exe_bytes, f"{checksum}  PowerDim.exe".encode()])
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda url, timeout=30.0: _FakeResponse(next(responses)))
    monkeypatch.setattr(updater, "_UPDATE_DIR", tmp_path)
    monkeypatch.setattr(updater, "EXPECTED_SIGNER_THUMBPRINT", "", raising=False)

    info = updater.UpdateInfo(version="v9.9.9", exe_url="x", checksum_url="y")
    dest = updater.download_update(info)

    assert dest.read_bytes() == exe_bytes


def test_apply_update_raises_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)

    with pytest.raises(updater.UpdateError):
        updater.apply_update(tmp_path / "PowerDim_new.exe")
