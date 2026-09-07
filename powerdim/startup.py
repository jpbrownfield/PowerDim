"""Run-on-startup registration via the per-user Run registry key.

HKCU (not HKLM) so no admin rights are needed; this only affects the current
Windows user, matching how a tray app is normally auto-started.
"""
import os
import sys
import winreg

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "PowerDim"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller --onefile build: sys.executable *is* the app itself.
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except OSError:
                pass
