"""
watcher.py
Runs continuously in a background thread, polling system stats and
(optionally) auto-triggering a RAM cleanup when usage crosses a
threshold. This is what makes MemWatch behave like a persistent
monitor rather than a one-shot cleaner tool.
"""

import threading
import time
from collections import deque

from core import optimizer, logger


class Watcher:
    def __init__(self, on_update=None, poll_seconds=2, history_len=60):
        self.on_update = on_update          # callback(stats: dict)
        self.poll_seconds = poll_seconds
        self.history = deque(maxlen=history_len)

        self.auto_clean = False
        self.threshold_percent = 85
        self.cooldown_seconds = 60
        self._last_clean_time = 0
        self._warned_this_spike = False     # avoid log spam while sitting above threshold

        self._stop_event = threading.Event()
        self._thread = None
        self.last_clean_report = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        logger.log_event("watcher stopped")

    def _run(self):
        logger.log_event("watcher started")
        while not self._stop_event.is_set():
            stats = optimizer.get_stats()
            self.history.append(stats)

            over_threshold = stats["ram_percent"] >= self.threshold_percent
            if over_threshold and self.auto_clean:
                now = time.time()
                if now - self._last_clean_time >= self.cooldown_seconds:
                    self.last_clean_report = optimizer.clean_ram()
                    self._last_clean_time = now
                    self._warned_this_spike = False
                    stats["auto_cleaned"] = True
                    stats["clean_report"] = self.last_clean_report
                    logger.log_clean(self.last_clean_report, auto=True)
            elif over_threshold and not self.auto_clean and not self._warned_this_spike:
                logger.log_high_usage(stats["ram_percent"], self.threshold_percent)
                self._warned_this_spike = True
            elif not over_threshold:
                self._warned_this_spike = False

            if self.on_update:
                try:
                    self.on_update(stats)
                except Exception:
                    pass

            self._stop_event.wait(self.poll_seconds)
