"""
MemWatch — Lightweight RAM Optimizer & System Monitor
Made by zadwen — https://github.com/zadwen

Runs continuously in the background, watching CPU/RAM, and can trim
memory automatically once usage crosses a threshold you set. Minimizes
to the system tray so it just sits there doing its job.
"""

import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from core import branding, optimizer, startup, config, logger
from core.watcher import Watcher

try:
    import pystray
    from PIL import Image
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _ensure_icon():
    ico = os.path.join(ASSETS_DIR, "icon.ico")
    png = os.path.join(ASSETS_DIR, "icon.png")
    if not (os.path.exists(ico) and os.path.exists(png)):
        from core.icon import generate
        generate(ASSETS_DIR)
    return ico, png


class GradientHeader(tk.Canvas):
    """Purple -> cyan gradient banner with the app name + tagline."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=92, highlightthickness=0, bd=0, **kwargs)
        self.bind("<Configure>", self._redraw)

    def _hex_to_rgb(self, h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def _redraw(self, event=None):
        self.delete("all")
        w = self.winfo_width() or 600
        h = int(self["height"])
        c1 = self._hex_to_rgb(branding.COLOR_ACCENT_1)
        c2 = self._hex_to_rgb(branding.COLOR_ACCENT_2)
        steps = max(w, 1)
        for i in range(steps):
            t = i / steps
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            self.create_line(i, 0, i, h, fill=f"#{r:02x}{g:02x}{b:02x}")

        self.create_text(20, h / 2 - 10, anchor="w", text=branding.APP_NAME,
                          fill="white", font=(branding.FONT_FAMILY, 18, "bold"))
        self.create_text(20, h / 2 + 16, anchor="w", text=branding.APP_TAGLINE,
                          fill="#f0f0ff", font=(branding.FONT_FAMILY, 9))
        self.create_text(w - 14, h - 12, anchor="e", text=f"by {branding.AUTHOR}",
                          fill="#f0f0ff", font=(branding.FONT_FAMILY, 9, "italic"))


class StatusPill(tk.Frame):
    """Small animated dot + label, e.g. 'Optimal' / 'Elevated' / 'Critical'."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=branding.COLOR_CARD, **kwargs)
        self.canvas = tk.Canvas(self, width=12, height=12, bg=branding.COLOR_CARD,
                                 highlightthickness=0)
        self.canvas.pack(side="left", padx=(0, 6))
        self.dot = self.canvas.create_oval(2, 2, 10, 10, fill=branding.COLOR_GOOD, outline="")
        self.label = tk.Label(self, text="Optimal", bg=branding.COLOR_CARD,
                               fg=branding.COLOR_TEXT, font=(branding.FONT_FAMILY, 10, "bold"))
        self.label.pack(side="left")
        self._pulse_state = 0
        self._pulse()

    def set_state(self, level: str, color: str):
        self.label.config(text=level)
        self.canvas.itemconfig(self.dot, fill=color)

    def _pulse(self):
        # gentle breathing effect so it reads as "alive" / continuously monitoring
        self._pulse_state = (self._pulse_state + 1) % 20
        size = 1 + abs(10 - self._pulse_state) * 0.15
        self.canvas.coords(self.dot, 6 - 4 - size, 6 - 4 - size, 6 + 4 + size, 6 + 4 + size)
        self.after(120, self._pulse)


class RamGraph(tk.Canvas):
    """Rolling line graph of recent RAM% history."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=branding.COLOR_CARD, highlightthickness=0, **kwargs)
        self.points = []

    def push(self, percent):
        self.points.append(percent)
        if len(self.points) > 60:
            self.points.pop(0)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width() or 400
        h = self.winfo_height() or 90
        if len(self.points) < 2:
            return
        # gridlines
        for frac in (0.25, 0.5, 0.75):
            y = h * (1 - frac)
            self.create_line(0, y, w, y, fill=branding.COLOR_CARD_BORDER)

        step = w / (len(self.points) - 1)
        coords = []
        for i, v in enumerate(self.points):
            x = i * step
            y = h - (v / 100.0) * h
            coords.extend([x, y])
        self.create_line(*coords, fill=branding.COLOR_ACCENT_2, width=2, smooth=True)


class MemWatchApp:
    def __init__(self, root, start_minimized=False):
        self.root = root
        self.cfg = config.load()

        self.root.title(f"{branding.APP_NAME} — made by {branding.AUTHOR}")
        self.root.geometry(self.cfg.get("window_geometry", "520x620"))
        self.root.minsize(480, 560)
        self.root.configure(bg=branding.COLOR_BG)

        self.icon_ico, self.icon_png = _ensure_icon()
        try:
            self.root.iconbitmap(self.icon_ico)
        except Exception:
            pass

        self.watcher = Watcher(on_update=self._on_stats, poll_seconds=self.cfg.get("poll_seconds", 2))
        self.watcher.auto_clean = self.cfg.get("auto_clean", False)
        self.watcher.threshold_percent = self.cfg.get("threshold_percent", 85)
        self.watcher.cooldown_seconds = self.cfg.get("cooldown_seconds", 60)
        self.tray_icon = None

        self._build_ui()
        logger.log_event(f"MemWatch v{branding.VERSION} starting "
                          f"(admin={optimizer.is_admin()}, auto_clean={self.watcher.auto_clean}, "
                          f"threshold={self.watcher.threshold_percent}%)")
        self.watcher.start()

        self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        if start_minimized and TRAY_AVAILABLE:
            self.root.after(200, self._minimize_to_tray)

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        GradientHeader(self.root).pack(fill="x", side="top")

        body = tk.Frame(self.root, bg=branding.COLOR_BG)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        # --- status row ---
        status_row = tk.Frame(body, bg=branding.COLOR_BG)
        status_row.pack(fill="x", pady=(0, 10))
        self.status_pill = StatusPill(status_row)
        self.status_pill.pack(side="left")
        self.admin_label = tk.Label(
            status_row,
            text=("Admin mode — full standby purge enabled" if optimizer.is_admin()
                  else "Standard mode — run as admin for deeper cleans"),
            bg=branding.COLOR_BG, fg=branding.COLOR_MUTED, font=(branding.FONT_FAMILY, 8))
        self.admin_label.pack(side="right")

        # --- stat cards ---
        cards = tk.Frame(body, bg=branding.COLOR_BG)
        cards.pack(fill="x", pady=(0, 12))
        cards.columnconfigure((0, 1), weight=1)

        self.ram_card, self.ram_value_lbl, self.ram_sub_lbl = self._make_card(cards, "RAM USAGE")
        self.ram_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.cpu_card, self.cpu_value_lbl, self.cpu_sub_lbl = self._make_card(cards, "CPU USAGE")
        self.cpu_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # --- graph ---
        graph_frame = tk.Frame(body, bg=branding.COLOR_CARD, bd=0)
        graph_frame.pack(fill="x", pady=(0, 12))
        tk.Label(graph_frame, text="RAM over time", bg=branding.COLOR_CARD,
                  fg=branding.COLOR_MUTED, font=(branding.FONT_FAMILY, 8, "bold"),
                  anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.graph = RamGraph(graph_frame, height=90)
        self.graph.pack(fill="x", padx=10, pady=(2, 10))

        # --- controls ---
        controls = tk.Frame(body, bg=branding.COLOR_BG)
        controls.pack(fill="x", pady=(0, 12))

        self.clean_btn = tk.Button(
            controls, text="Clean RAM Now", command=self._clean_now,
            bg=branding.COLOR_ACCENT_1, fg="white", activebackground=branding.COLOR_ACCENT_2,
            font=(branding.FONT_FAMILY, 10, "bold"), relief="flat", padx=14, pady=8,
            cursor="hand2")
        self.clean_btn.pack(side="left")

        self.auto_var = tk.BooleanVar(value=self.cfg.get("auto_clean", False))
        auto_chk = tk.Checkbutton(
            controls, text="Auto-clean when RAM is high", variable=self.auto_var,
            command=self._toggle_auto, bg=branding.COLOR_BG, fg=branding.COLOR_TEXT,
            selectcolor=branding.COLOR_CARD, activebackground=branding.COLOR_BG,
            font=(branding.FONT_FAMILY, 9))
        auto_chk.pack(side="left", padx=(14, 0))

        startup_row = tk.Frame(body, bg=branding.COLOR_BG)
        startup_row.pack(fill="x", pady=(0, 10))
        self.startup_var = tk.BooleanVar(value=startup.is_enabled())
        tk.Checkbutton(
            startup_row, text="Start with Windows (minimized)", variable=self.startup_var,
            command=self._toggle_startup, bg=branding.COLOR_BG, fg=branding.COLOR_TEXT,
            selectcolor=branding.COLOR_CARD, activebackground=branding.COLOR_BG,
            font=(branding.FONT_FAMILY, 9)).pack(side="left")

        saved_threshold = self.cfg.get("threshold_percent", 85)
        self.threshold_label = tk.Label(startup_row, text=f"Threshold: {saved_threshold}%",
                                         bg=branding.COLOR_BG, fg=branding.COLOR_MUTED,
                                         font=(branding.FONT_FAMILY, 9))
        self.threshold_label.pack(side="right")
        self.threshold_scale = tk.Scale(
            startup_row, from_=60, to=95, orient="horizontal", showvalue=False,
            command=self._on_threshold_change, bg=branding.COLOR_BG,
            fg=branding.COLOR_MUTED, troughcolor=branding.COLOR_CARD,
            highlightthickness=0, length=110)
        self.threshold_scale.set(saved_threshold)
        self.threshold_scale.pack(side="right", padx=(0, 8))

        # --- process list ---
        tk.Label(body, text="Top memory consumers", bg=branding.COLOR_BG,
                  fg=branding.COLOR_MUTED, font=(branding.FONT_FAMILY, 8, "bold"),
                  anchor="w").pack(fill="x")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("MW.Treeview", background=branding.COLOR_CARD,
                         fieldbackground=branding.COLOR_CARD, foreground=branding.COLOR_TEXT,
                         borderwidth=0, rowheight=24)
        style.configure("MW.Treeview.Heading", background=branding.COLOR_BG_ALT,
                         foreground=branding.COLOR_MUTED, borderwidth=0)
        style.map("MW.Treeview", background=[("selected", branding.COLOR_ACCENT_1)])

        self.tree = ttk.Treeview(
            body, columns=("name", "ram", "cpu"), show="headings", height=8, style="MW.Treeview")
        self.tree.heading("name", text="Process")
        self.tree.heading("ram", text="RAM (MB)")
        self.tree.heading("cpu", text="CPU %")
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("ram", width=100, anchor="e")
        self.tree.column("cpu", width=80, anchor="e")
        self.tree.pack(fill="both", expand=True, pady=(4, 10))

        self.status_line = tk.Label(body, text="Watching…", bg=branding.COLOR_BG,
                                     fg=branding.COLOR_MUTED, font=(branding.FONT_FAMILY, 8),
                                     anchor="w")
        self.status_line.pack(fill="x")

        # --- footer ---
        footer = tk.Frame(self.root, bg=branding.COLOR_BG_ALT)
        footer.pack(fill="x", side="bottom")

        footer_row = tk.Frame(footer, bg=branding.COLOR_BG_ALT)
        footer_row.pack(pady=6)

        footer_lbl = tk.Label(
            footer_row, text=f"Made by {branding.AUTHOR}  ·  v{branding.VERSION}  ·  {branding.COPYRIGHT}",
            bg=branding.COLOR_BG_ALT, fg=branding.COLOR_MUTED, font=(branding.FONT_FAMILY, 8),
            cursor="hand2")
        footer_lbl.pack(side="left")
        footer_lbl.bind("<Button-1>", lambda e: webbrowser.open(branding.GITHUB_URL))

        log_lbl = tk.Label(
            footer_row, text="  ·  view log", bg=branding.COLOR_BG_ALT,
            fg=branding.COLOR_ACCENT_2, font=(branding.FONT_FAMILY, 8), cursor="hand2")
        log_lbl.pack(side="left")
        log_lbl.bind("<Button-1>", lambda e: self._open_log())

        about_lbl = tk.Label(
            footer_row, text="  ·  about", bg=branding.COLOR_BG_ALT,
            fg=branding.COLOR_ACCENT_2, font=(branding.FONT_FAMILY, 8), cursor="hand2")
        about_lbl.pack(side="left")
        about_lbl.bind("<Button-1>", lambda e: self._show_about_dialog())

    def _make_card(self, parent, title):
        card = tk.Frame(parent, bg=branding.COLOR_CARD, padx=14, pady=10)
        tk.Label(card, text=title, bg=branding.COLOR_CARD, fg=branding.COLOR_MUTED,
                  font=(branding.FONT_FAMILY, 8, "bold")).pack(anchor="w")
        value_lbl = tk.Label(card, text="--%", bg=branding.COLOR_CARD, fg=branding.COLOR_TEXT,
                              font=(branding.FONT_FAMILY, 24, "bold"))
        value_lbl.pack(anchor="w")
        sub_lbl = tk.Label(card, text="", bg=branding.COLOR_CARD, fg=branding.COLOR_MUTED,
                            font=(branding.FONT_FAMILY, 8))
        sub_lbl.pack(anchor="w")
        return card, value_lbl, sub_lbl

    # ----------------------------------------------------------- events ---
    def _on_stats(self, stats):
        self.root.after(0, self._apply_stats, stats)

    def _apply_stats(self, stats):
        ram_pct = stats["ram_percent"]
        cpu_pct = stats["cpu_percent"]

        self.ram_value_lbl.config(text=f"{ram_pct:.0f}%")
        self.ram_sub_lbl.config(
            text=f"{stats['ram_used_gb']:.1f} / {stats['ram_total_gb']:.1f} GB")
        self.cpu_value_lbl.config(text=f"{cpu_pct:.0f}%")
        self.cpu_sub_lbl.config(text="system-wide")

        self.graph.push(ram_pct)

        if ram_pct >= 90:
            self.status_pill.set_state("Critical", branding.COLOR_BAD)
        elif ram_pct >= 75:
            self.status_pill.set_state("Elevated", branding.COLOR_WARN)
        else:
            self.status_pill.set_state("Optimal", branding.COLOR_GOOD)

        if stats.get("auto_cleaned"):
            report = stats.get("clean_report", {})
            msg = (f"Auto-cleaned — freed ~{report.get('freed_mb', 0):.0f} MB "
                   f"({report.get('trimmed', 0)} processes trimmed)")
            self.status_line.config(text=msg)
            if self.tray_icon:
                try:
                    self.tray_icon.notify(msg, title=branding.APP_NAME)
                except Exception:
                    pass
        else:
            self.status_line.config(text="Watching…")

        # refresh the process table roughly every other tick (cheap enough either way)
        self._refresh_processes()

    def _refresh_processes(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for p in optimizer.get_top_processes(limit=8):
            self.tree.insert("", "end", values=(p["name"], f"{p['ram_mb']:.0f}", f"{p['cpu_percent']:.0f}"))

    def _clean_now(self):
        self.clean_btn.config(state="disabled", text="Cleaning…")
        self.status_line.config(text="Cleaning memory…")

        def work():
            report = optimizer.clean_ram()
            self.root.after(0, self._clean_done, report)

        threading.Thread(target=work, daemon=True).start()

    def _clean_done(self, report):
        self.clean_btn.config(state="normal", text="Clean RAM Now")
        logger.log_clean(report, auto=False)
        if report.get("error"):
            self.status_line.config(text=report["error"])
            return
        msg = f"Freed ~{report['freed_mb']:.0f} MB — {report['trimmed']} processes trimmed"
        if report.get("standby_purged"):
            msg += " — standby list purged"
        self.status_line.config(text=msg)
        if self.tray_icon:
            try:
                self.tray_icon.notify(msg, title=branding.APP_NAME)
            except Exception:
                pass

    def _toggle_auto(self):
        self.watcher.auto_clean = self.auto_var.get()
        logger.log_event(f"auto-clean {'enabled' if self.watcher.auto_clean else 'disabled'} by user")
        self._save_config()

    def _on_threshold_change(self, value):
        v = int(float(value))
        self.watcher.threshold_percent = v
        self.threshold_label.config(text=f"Threshold: {v}%")
        self._save_config()

    def _toggle_startup(self):
        startup.set_enabled(self.startup_var.get())

    def _open_log(self):
        path = logger.get_log_path()
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            else:
                webbrowser.open(f"file://{path}")
        except Exception:
            self.status_line.config(text=f"Log file: {path}")

    def _save_config(self):
        self.cfg.update({
            "auto_clean": self.watcher.auto_clean,
            "threshold_percent": self.watcher.threshold_percent,
            "cooldown_seconds": self.watcher.cooldown_seconds,
            "poll_seconds": self.watcher.poll_seconds,
            "window_geometry": self.root.winfo_geometry(),
        })
        config.save(self.cfg)

    # ------------------------------------------------------------- tray ---
    def _minimize_to_tray(self):
        if not TRAY_AVAILABLE:
            self.root.iconify()
            return
        self.root.withdraw()
        if self.tray_icon:
            return

        image = Image.open(self.icon_png)
        tray_title = f"{branding.APP_NAME} — by {branding.AUTHOR}"
        menu = pystray.Menu(
            pystray.MenuItem("Show MemWatch", self._show_window, default=True),
            pystray.MenuItem("Clean RAM Now", lambda: self._clean_now()),
            pystray.MenuItem("About", self._show_about),
            pystray.MenuItem("Quit", self._quit),
        )
        self.tray_icon = pystray.Icon(branding.APP_NAME, image, tray_title, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def _show_about(self, icon=None, item=None):
        self.root.after(0, self._show_about_dialog)

    def _show_about_dialog(self):
        win = tk.Toplevel(self.root)
        win.title(f"About {branding.APP_NAME}")
        win.configure(bg=branding.COLOR_BG)
        win.resizable(False, False)
        win.geometry("320x220")
        try:
            win.iconbitmap(self.icon_ico)
        except Exception:
            pass

        tk.Label(win, text=branding.APP_NAME, bg=branding.COLOR_BG, fg=branding.COLOR_TEXT,
                 font=(branding.FONT_FAMILY, 16, "bold")).pack(pady=(20, 4))
        tk.Label(win, text=branding.APP_TAGLINE, bg=branding.COLOR_BG, fg=branding.COLOR_MUTED,
                 font=(branding.FONT_FAMILY, 9), wraplength=260, justify="center").pack(pady=(0, 14))
        tk.Label(win, text=f"Made by {branding.AUTHOR}", bg=branding.COLOR_BG,
                 fg=branding.COLOR_ACCENT_2, font=(branding.FONT_FAMILY, 11, "bold")).pack()
        tk.Label(win, text=f"v{branding.VERSION}", bg=branding.COLOR_BG, fg=branding.COLOR_MUTED,
                 font=(branding.FONT_FAMILY, 9)).pack(pady=(2, 10))

        link = tk.Label(win, text=branding.GITHUB_URL, bg=branding.COLOR_BG,
                         fg=branding.COLOR_ACCENT_1, font=(branding.FONT_FAMILY, 9, "underline"),
                         cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open(branding.GITHUB_URL))

        tk.Label(win, text=branding.COPYRIGHT, bg=branding.COLOR_BG, fg=branding.COLOR_MUTED,
                 font=(branding.FONT_FAMILY, 8)).pack(pady=(14, 0))

    def _quit(self, icon=None, item=None):
        self._save_config()
        logger.log_event("MemWatch exiting")
        self.watcher.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)


def main():
    start_minimized = "--minimized" in sys.argv
    root = tk.Tk()
    MemWatchApp(root, start_minimized=start_minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
