"""
optimizer.py
Windows-only RAM optimization engine.

Two techniques, same ones used by "RAM cleaner" style utilities:
  1. EmptyWorkingSet() on each process — asks Windows to trim the
     process's physical working set back to the OS (pages get moved to
     the standby list, not lost — Windows reloads them on demand).
  2. NtSetSystemInformation(MemoryPurgeStandbyList) — purges the
     standby list itself. Requires admin; silently skipped otherwise.

Nothing here kills processes or deletes data. It only asks the OS
memory manager to reclaim pages that are already reclaimable.
"""

import ctypes
import sys
import time

import psutil

IS_WINDOWS = sys.platform.startswith("win")

# PIDs we never touch — trimming these can destabilize the OS.
_PROTECTED_NAMES = {
    "system", "system idle process", "csrss.exe", "wininit.exe",
    "winlogon.exe", "smss.exe", "services.exe", "lsass.exe",
    "memory compression",
}


def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_stats() -> dict:
    """Snapshot of current system load."""
    vm = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    return {
        "timestamp": time.time(),
        "cpu_percent": cpu,
        "ram_percent": vm.percent,
        "ram_used_gb": vm.used / (1024 ** 3),
        "ram_total_gb": vm.total / (1024 ** 3),
        "ram_available_gb": vm.available / (1024 ** 3),
    }


def get_top_processes(limit: int = 8) -> list:
    """Top RAM-consuming processes, excluding this process itself."""
    procs = []
    my_pid = psutil.Process().pid
    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            if p.info["pid"] == my_pid:
                continue
            mem = p.info["memory_info"]
            if not mem:
                continue
            procs.append({
                "pid": p.info["pid"],
                "name": p.info["name"] or "unknown",
                "ram_mb": mem.rss / (1024 ** 2),
                "cpu_percent": p.info["cpu_percent"] or 0.0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: x["ram_mb"], reverse=True)
    return procs[:limit]


def _trim_process_working_set(pid: int) -> bool:
    if not IS_WINDOWS:
        return False
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_SET_QUOTA = 0x0100
    access = PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA
    handle = ctypes.windll.kernel32.OpenProcess(access, False, pid)
    if not handle:
        return False
    try:
        return bool(ctypes.windll.psapi.EmptyWorkingSet(handle))
    except Exception:
        return False
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _purge_standby_list() -> bool:
    """Admin-only. Returns False (silently) if not elevated or unsupported."""
    if not IS_WINDOWS or not is_admin():
        return False
    try:
        ntdll = ctypes.WinDLL("ntdll.dll")
        SystemMemoryListInformation = 0x50
        MemoryPurgeStandbyList = 4
        command = ctypes.c_int(MemoryPurgeStandbyList)
        status = ntdll.NtSetSystemInformation(
            SystemMemoryListInformation, ctypes.byref(command), ctypes.sizeof(command)
        )
        return status == 0
    except Exception:
        return False


def clean_ram() -> dict:
    """
    Runs a full cleanup pass. Returns a report dict:
    { trimmed: int, skipped: int, freed_mb: float, standby_purged: bool }
    """
    if not IS_WINDOWS:
        return {"trimmed": 0, "skipped": 0, "freed_mb": 0.0, "standby_purged": False,
                "error": "MemWatch's cleaning engine is Windows-only."}

    before = psutil.virtual_memory().used
    trimmed, skipped = 0, 0

    for p in psutil.process_iter(["pid", "name"]):
        name = (p.info["name"] or "").lower()
        if name in _PROTECTED_NAMES:
            continue
        if _trim_process_working_set(p.info["pid"]):
            trimmed += 1
        else:
            skipped += 1

    standby_purged = _purge_standby_list()

    time.sleep(0.3)  # let the OS settle before re-measuring
    after = psutil.virtual_memory().used
    freed_mb = max(0.0, (before - after) / (1024 ** 2))

    return {
        "trimmed": trimmed,
        "skipped": skipped,
        "freed_mb": freed_mb,
        "standby_purged": standby_purged,
    }
