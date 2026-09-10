"""
config.py
Persists user settings (auto-clean, threshold, window position) to
%APPDATA%/MemWatch/config.json so a background monitoring tool
actually behaves like one — it shouldn't forget your settings every
time it restarts or Windows reboots it via the startup hook.
"""

import json
import os
import sys

APP_FOLDER_NAME = "MemWatch"

DEFAULTS = {
    "auto_clean": False,
    "threshold_percent": 85,
    "cooldown_seconds": 60,
    "poll_seconds": 2,
    "window_geometry": "520x620",
}


def get_data_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.config")
    path = os.path.join(base, APP_FOLDER_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _config_path() -> str:
    return os.path.join(get_data_dir(), "config.json")


def load() -> dict:
    path = _config_path()
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/unreadable config — fall back to defaults rather than crash
    return cfg


def save(cfg: dict):
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass  # non-fatal — settings just won't persist this run
