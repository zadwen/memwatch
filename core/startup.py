"""
startup.py
Registers/unregisters MemWatch to launch on Windows login via the
HKCU Run key — same approach used in salah-app / FocusLock, no admin
required since it's per-user.
"""

import sys
import os

from core.branding import APP_NAME

IS_WINDOWS = sys.platform.startswith("win")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

if IS_WINDOWS:
    import winreg


def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'


def is_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool):
    if not IS_WINDOWS:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _exe_path() + " --minimized")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
