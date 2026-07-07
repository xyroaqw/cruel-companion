"""Frame Inspector: a live view of every packet frame the sniffer receives, so you can
discover the protocol yourself -- fight a boss, type part of an on-screen message into the
filter, and see whether (and in which frame) it crosses the wire. Read-only; it only observes.

Runs on the Tk main thread, draining the FrameTap on a timer (like the overlay drains its
bridge). Polls even while hidden so the tap's bounded queue never backs up.
"""

import json
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import ttk

from companion.capture.frame_tap import FrameTap
from companion.ui.theme import Theme

RING = 4000            # frames kept in memory for filtering / saving
MAX_LINES = 500        # lines shown in the view at once
POLL_MS = 250


class FrameInspector:
    def __init__(self, root: tk.Tk, tap: FrameTap, save_dir: Path, theme: Theme | None = None):
        self._tap = tap
        self._save_dir = save_dir
        self._theme = theme or Theme()
        self._frames: deque[tuple[float, str, str]] = deque(maxlen=RING)  # (ts, dir, raw)
        self._last_filter = ""
        self._built = False

        self._win = tk.Toplevel(root)
        self._win.title("Companion — Frame Inspector")
        self._win.geometry("820x520")
        self._win.configure(bg=self._theme.panel_bg)
        self._win.protocol("WM_DELETE_WINDOW", self._win.withdraw)
        self._win.withdraw()  # created hidden; opened from the Rule Builder

        self._build_ui()
        root.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------

    def show(self) -> None:
        self._win.deiconify()
        self._win.lift()
        self._win.focus_force()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = self._theme
        field_bg = "#1d1f28"
        bar = tk.Frame(self._win, bg=t.panel_bg)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(bar, text="Filter:", bg=t.panel_bg, fg=t.text,
                 font=(t.font_family, 9)).pack(side="left")
        self._filter_var = tk.StringVar()
        entry = tk.Entry(bar, textvariable=self._filter_var, width=26, bg=field_bg,
                         fg=t.text, insertbackground=t.text, relief="flat")
        entry.pack(side="left", padx=(6, 12), ipady=3)
        entry.bind("<KeyRelease>", lambda _e: self._rebuild())

        self._hide_noise = tk.BooleanVar(value=True)
        tk.Checkbutton(
            bar, text="Hide vitals spam (ct)", variable=self._hide_noise,
            command=self._rebuild, bg=t.panel_bg, fg=t.text, selectcolor=field_bg,
            activebackground=t.panel_bg, activeforeground=t.text, font=(t.font_family, 9),
        ).pack(side="left")

        self._paused = tk.BooleanVar(value=False)
        tk.Checkbutton(
            bar, text="Pause", variable=self._paused, bg=t.panel_bg, fg=t.text,
            selectcolor=field_bg, activebackground=t.panel_bg, activeforeground=t.text,
            font=(t.font_family, 9),
        ).pack(side="left", padx=(8, 0))

        tk.Button(bar, text="Save to file", command=self._save, bg=field_bg, fg=t.text,
                  relief="flat", font=(t.font_family, 9)).pack(side="right")
        tk.Button(bar, text="Clear", command=self._clear, bg=field_bg, fg=t.text,
                  relief="flat", font=(t.font_family, 9)).pack(side="right", padx=(0, 8))

        self._status = tk.Label(self._win, text="", bg=t.panel_bg, fg=t.muted,
                                font=(t.font_family, 8), anchor="w")
        self._status.pack(fill="x", padx=10)

        wrap = tk.Frame(self._win, bg=t.panel_bg)
        wrap.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self._text = tk.Text(wrap, bg="#0e0f14", fg="#cdd2e0", insertbackground=t.text,
                             font=("Consolas", 9), relief="flat", wrap="none", state="disabled")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        self._text.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self._text.tag_configure("match", foreground=t.accent)
        self._text.tag_configure("hint", foreground=t.muted)

        hint = ("Tip: run as Administrator so capture is active, fight the boss, then type part "
                "of the on-screen message (e.g. Abyss) above. If it appears here, it's in the "
                "packets and a Message-contains rule can match it.")
        self._text.configure(state="normal")
        self._text.insert("end", hint + "\n", "hint")
        self._text.configure(state="disabled")

    # ------------------------------------------------------------------

    def _poll(self) -> None:
        new = self._tap.drain()
        if new:
            self._frames.extend(new)
            if not self._paused.get() and self._win.state() != "withdrawn":
                self._append(new)
        self._status.configure(
            text=f"{len(self._frames)} frames buffered"
            + (f"  ·  filter: {self._last_filter!r}" if self._last_filter else "")
        )
        self._win.after(POLL_MS, self._poll)

    def _passes(self, raw: str, needle: str) -> bool:
        if self._hide_noise.get() and _is_vitals_noise(raw):
            return False
        return needle in raw.lower() if needle else True

    def _append(self, rows: list[tuple[float, str, str]]) -> None:
        needle = self._filter_var.get().strip().lower()
        lines = [_format(ts, direction, raw) for ts, direction, raw in rows
                 if self._passes(raw, needle)]
        if not lines:
            return
        self._text.configure(state="normal")
        for line in lines:
            self._text.insert("end", line + "\n", "match" if needle else "")
        # Trim to the last MAX_LINES to keep the widget light.
        excess = int(self._text.index("end-1c").split(".")[0]) - MAX_LINES
        if excess > 0:
            self._text.delete("1.0", f"{excess + 1}.0")
        self._text.see("end")
        self._text.configure(state="disabled")

    def _rebuild(self) -> None:
        self._last_filter = self._filter_var.get().strip().lower()
        needle = self._last_filter
        rows = [r for r in self._frames if self._passes(r[2], needle)][-MAX_LINES:]
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        for ts, direction, raw in rows:
            self._text.insert("end", _format(ts, direction, raw) + "\n",
                              "match" if needle else "")
        self._text.see("end")
        self._text.configure(state="disabled")

    def _clear(self) -> None:
        self._frames.clear()
        self._rebuild()

    def _save(self) -> None:
        self._save_dir.mkdir(parents=True, exist_ok=True)
        path = self._save_dir / f"frames-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            for ts, direction, raw in self._frames:
                fh.write(json.dumps({"ts": ts, "dir": direction, "frame": raw}) + "\n")
        self._status.configure(text=f"Saved {len(self._frames)} frames -> {path}")


def _is_vitals_noise(raw: str) -> bool:
    """A ct frame with no aura entries -- the high-volume HP/MP ticks worth hiding by default."""
    if '"cmd":"ct"' not in raw.replace(" ", ""):
        return False
    return "aura" not in raw


def _format(ts: float, direction: str, raw: str) -> str:
    stamp = time.strftime("%H:%M:%S", time.localtime(ts))
    arrow = "<-" if direction == "inbound" else "->"
    return f"{stamp} {arrow} {_summarize(raw)}"


def _summarize(raw: str) -> str:
    t = raw.strip()
    if t.startswith("%"):
        parts = [p for p in t.split("%") if p]
        return "pkt %" + "/".join(parts[:3]) + ("  " + t[:100] if len(parts) > 3 else "")
    try:
        obj = json.loads(t)
    except Exception:
        return t[:140]
    body = obj.get("b") if isinstance(obj, dict) else None
    o = body.get("o") if isinstance(body, dict) else None
    if isinstance(o, dict):
        cmd = o.get("cmd", "?")
        auras = _aura_names(o)
        extra = f"  auras=[{', '.join(auras)}]" if auras else ""
        return f"xt {cmd}{extra}"
    return f"({obj.get('t', '?')}) {t[:120]}" if isinstance(obj, dict) else t[:140]


def _aura_names(o: dict) -> list[str]:
    names = []
    a = o.get("a")
    if isinstance(a, list):
        for entry in a:
            if not isinstance(entry, dict) or not str(entry.get("cmd", "")).startswith("aura"):
                continue
            auras = entry.get("auras") or ([entry.get("aura")] if entry.get("aura") else [])
            for au in auras:
                if isinstance(au, dict) and au.get("nam"):
                    names.append(au["nam"])
    return names
