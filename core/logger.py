"""
logger.py
A tool that claims to "monitor continuously" should leave a record.
Writes a small rotating log to %APPDATA%/MemWatch/logs/memwatch.log —
one line per clean event, plus periodic high-usage warnings. Kept
deliberately lightweight (no per-tick spam) so the file stays useful
instead of turning into noise.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from core.config import get_data_dir

_logger = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    log_dir = os.path.join(get_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "memwatch.log")

    logger = logging.getLogger("memwatch")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = RotatingFileHandler(log_path, maxBytes=512_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                                datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)

    _logger = logger
    return logger


def log_clean(report: dict, auto: bool = False):
    logger = get_logger()
    trigger = "auto" if auto else "manual"
    if report.get("error"):
        logger.warning("clean skipped (%s): %s", trigger, report["error"])
        return
    logger.info(
        "clean (%s) — freed %.0f MB, %d trimmed, %d skipped, standby_purged=%s",
        trigger, report.get("freed_mb", 0), report.get("trimmed", 0),
        report.get("skipped", 0), report.get("standby_purged", False),
    )


def log_high_usage(ram_percent: float, threshold: float):
    get_logger().warning("RAM at %.0f%% (threshold %.0f%%) — auto-clean is off, skipping", ram_percent, threshold)


def log_event(message: str):
    get_logger().info(message)


def get_log_path() -> str:
    return os.path.join(get_data_dir(), "logs", "memwatch.log")
