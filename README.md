# MemWatch

**Lightweight RAM Optimizer & System Monitor for Windows**
Made by [zadwen](https://github.com/zadwen)

MemWatch sits in your system tray and continuously watches CPU/RAM usage,
graphing it live, and can automatically trim memory the moment usage
crosses a threshold you set — instead of you having to remember to run a
cleaner tool manually.

## Features

- **Continuous monitoring** — background thread polls system stats every
  2 seconds, not a one-shot scan
- **Live RAM/CPU cards** + rolling usage graph
- **One-click "Clean RAM Now"** — trims the working set of every
  non-critical running process
- **Auto-clean mode** — set a % threshold; MemWatch cleans automatically
  once it's crossed (with a cooldown so it doesn't thrash)
- **Standby list purge** when run as Administrator, for a deeper clean
- **Top process table** — see what's actually eating your RAM
- **System tray** — minimizes out of the way and keeps watching
- **Start with Windows** toggle (per-user, no admin required)

## How the cleaning works

MemWatch doesn't kill processes or delete anything. It asks Windows to:

1. `EmptyWorkingSet()` on each process — pages get moved to the
   standby list, which Windows reloads on demand if needed.
2. (Admin only) Purge the standby list itself via
   `NtSetSystemInformation(MemoryPurgeStandbyList)` — the same
   technique tools like RAMMap's "Empty Standby List" use.

Both are safe, standard OS memory-manager operations.

## Running from source

```bash
pip install -r requirements.txt
python main.py
```

Run as Administrator for the deeper standby-list purge to kick in.

## Building the .exe

```bash
pip install pyinstaller
python -c "from core.icon import generate; generate('assets')"
pyinstaller build.spec
```

The built `MemWatch.exe` will be in `dist/`. Tagged pushes (`v*`) also
trigger an automatic Windows build via GitHub Actions
(`.github/workflows/build.yml`).

## Project structure

```
memwatch/
├── core/
│   ├── branding.py     # identity — colors, name, author
│   ├── optimizer.py     # RAM stats + cleaning engine
│   ├── watcher.py       # background monitoring thread
│   ├── startup.py       # Windows "start on login" registry hook
│   └── icon.py           # programmatic monogram icon generator
├── main.py               # Tkinter UI + tray
├── build.spec
└── .github/workflows/build.yml
```

---

© zadwen — all rights reserved
