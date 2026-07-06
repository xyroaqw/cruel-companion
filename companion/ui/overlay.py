"""Always-on-top, click-through, transparent HUD. All GameState mutation and rule evaluation
happen here on the Tk main thread, inside the poll loop -- capture-side threads only ever push
normalized events into the EventBridge (see queue_bridge.py). Single-writer, no locks needed.

Rendering: one Canvas drawing a compact rounded card (Tk canvas doesn't antialias, so the
rounded corners stay fringe-free against the colorkey background). The card resizes to its
content, hides entirely when there is nothing to show, and only redraws when the content
model actually changed -- not every poll tick.
"""

import time
import tkinter as tk
from tkinter import font as tkfont

from companion.protocol.events import MessageEvent
from companion.rules.engine import FiredAlert, RulesEngine
from companion.state.game_state import GameState
from companion.ui.clickthrough_win32 import make_window_clickthrough
from companion.ui.queue_bridge import EventBridge
from companion.ui.theme import Theme

TRANSPARENT_KEY = "magenta"

PAD = 10          # card inner padding
STRIPE_W = 3      # accent stripe width
ROW_GAP = 4
MIN_CARD_W = 190
MAX_CARD_W = 340
HP_BAR_W = 52
HP_BAR_H = 5


class OverlayHUD:
    def __init__(
        self,
        bridge: EventBridge,
        state: GameState,
        engine: RulesEngine,
        x: int = 40,
        y: int = 40,
        poll_ms: int = 75,
        max_alert_feed: int = 6,
        clickthrough: bool = True,
        transparent: bool = True,
        root: tk.Tk | None = None,
        sound_player=None,
        theme: Theme | None = None,
        alert_ttl_seconds: float = 8.0,
    ):
        self._bridge = bridge
        self._state = state
        self._engine = engine
        self._poll_ms = poll_ms
        self._max_alert_feed = max_alert_feed
        self._sound_player = sound_player
        self._theme = theme or Theme()
        self._alert_ttl = alert_ttl_seconds

        # (expires_at_monotonic, text, color) -- newest last
        self._alerts: list[tuple[float, str, str]] = []
        self._last_model: object = None
        self._hidden = False

        self._owns_root = root is None
        self.root = root if root is not None else tk.Tk()
        self._build_window(x, y, clickthrough, transparent)

    def _build_window(self, x: int, y: int, clickthrough: bool, transparent: bool) -> None:
        self._x = x
        self._y = y

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_KEY)

        family = self._theme.font_family
        self._font_title = tkfont.Font(family=family, size=10, weight="bold")
        self._font_row = tkfont.Font(family=family, size=9)
        self._font_alert = tkfont.Font(family=family, size=10, weight="bold")

        self._canvas = tk.Canvas(
            self.root, bg=TRANSPARENT_KEY, highlightthickness=0, bd=0
        )
        self._canvas.pack(fill="both", expand=True)

        # Fixed initial size rather than relying on Tk's auto-computed content size -- that
        # comes back unreliable (near-zero) under PyInstaller's bundled Tcl/Tk. The redraw
        # resizes to real content immediately afterwards.
        self.root.geometry(f"{MIN_CARD_W}x60+{self._x}+{self._y}")

        # -transparentcolor must be applied last, after all widgets are created and laid out --
        # setting it before the window has real content makes the whole layered window (not
        # just the colorkey background) render blank on Windows.
        if transparent:
            self.root.attributes("-transparentcolor", TRANSPARENT_KEY)

        if clickthrough:
            self.root.update_idletasks()
            make_window_clickthrough(self.root.winfo_id())

    def start(self) -> None:
        self.root.after(self._poll_ms, self._poll)

    def run(self) -> None:
        self.start()
        if self._owns_root:
            self.root.mainloop()

    def _poll(self) -> None:
        # Whatever goes wrong in a single tick (a bad rule, a rendering hiccup), the poll
        # loop must survive -- a dead loop means a silently frozen HUD mid-fight.
        try:
            self._tick()
        except Exception as exc:
            print(f"[overlay] tick error (HUD continues): {exc!r}")
        self.root.after(self._poll_ms, self._poll)

    def _tick(self) -> None:
        for event in self._bridge.drain():
            # Echo server messages: this console record is how users discover the exact
            # text their 'Message contains' rules can match.
            if isinstance(event, MessageEvent):
                print(f"[msg] {event.text}")
            self._state.apply(event)

        for alert in self._engine.evaluate(self._state.snapshot()):
            self.render_alert(alert)
            # Console echo doubles as a post-fight record -- the HUD feed only keeps the
            # last few alerts.
            print(f"[alert] {alert.level.value.upper()}: {alert.message} ({alert.trigger_id})")
            if self._sound_player is not None:
                self._sound_player.play(alert.level)

        now = time.monotonic()
        self._alerts = [a for a in self._alerts if a[0] > now][-self._max_alert_feed :]

        model = self._build_model()
        if model != self._last_model:
            self._last_model = model
            self._redraw(model)

    def render_alert(self, alert: FiredAlert) -> None:
        self._alerts.append(
            (
                time.monotonic() + self._alert_ttl,
                alert.message,
                self._theme.level_color(alert.level),
            )
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _build_model(self) -> tuple:
        """Everything the card displays, as plain data -- compared between polls so the
        canvas only redraws on real changes."""
        t = self._theme
        snap = self._state.snapshot()

        rows: list[tuple] = []
        if t.title:
            rows.append(("title", t.title))
        if t.zone_prefix:
            rows.append(("zone", f"{t.zone_prefix}: {snap.zone or t.zone_unknown}"))
        for actor in snap.monsters():
            rows.append(("monster", actor.display_name, actor.hp_pct))
        for _expires, text, color in self._alerts:
            rows.append(("alert", text, color))
        return tuple(rows)

    def _redraw(self, model: tuple) -> None:
        if not model:
            if not self._hidden:
                self.root.withdraw()
                self._hidden = True
            return
        if self._hidden:
            self.root.deiconify()
            self._hidden = False

        t = self._theme
        c = self._canvas

        # Measure content to size the card.
        width = MIN_CARD_W
        for row in model:
            if row[0] == "title":
                w = self._font_title.measure(row[1])
            elif row[0] == "monster":
                w = self._font_row.measure(row[1]) + HP_BAR_W + 42
            else:
                font = self._font_alert if row[0] == "alert" else self._font_row
                w = font.measure(row[1])
            width = max(width, w + 2 * PAD + STRIPE_W + 8)
        width = min(width, MAX_CARD_W)

        row_heights = []
        for row in model:
            if row[0] == "title":
                row_heights.append(self._font_title.metrics("linespace") + 2)
            elif row[0] == "alert":
                row_heights.append(self._font_alert.metrics("linespace") + 1)
            else:
                row_heights.append(self._font_row.metrics("linespace") + 1)
        height = 2 * PAD + sum(row_heights) + ROW_GAP * (len(model) - 1)

        c.delete("all")
        self.root.geometry(f"{width}x{height}+{self._x}+{self._y}")
        c.configure(width=width, height=height)

        self._rounded_rect(0, 0, width - 1, height - 1, 9, fill=t.panel_bg, outline=t.border)
        # Accent stripe down the left edge.
        c.create_rectangle(
            0, 8, STRIPE_W, height - 9, fill=t.accent, outline=t.accent
        )

        text_x = PAD + STRIPE_W + 4
        y = PAD
        for row, row_h in zip(model, row_heights):
            kind = row[0]
            if kind == "title":
                c.create_text(
                    text_x, y, text=row[1], anchor="nw", fill=t.accent, font=self._font_title
                )
            elif kind == "zone":
                c.create_text(
                    text_x, y, text=row[1], anchor="nw", fill=t.muted, font=self._font_row
                )
            elif kind == "monster":
                _, name, hp_pct = row
                name = self._truncate(name, self._font_row, width - HP_BAR_W - 48 - text_x)
                c.create_text(
                    text_x, y, text=name, anchor="nw", fill=t.text, font=self._font_row
                )
                bar_x = width - PAD - HP_BAR_W - 30
                bar_y = y + (row_h - HP_BAR_H) // 2
                pct_text = f"{hp_pct:.0f}%" if hp_pct is not None else t.hp_unknown
                c.create_rectangle(
                    bar_x, bar_y, bar_x + HP_BAR_W, bar_y + HP_BAR_H,
                    fill=t.border, outline="",
                )
                if hp_pct is not None:
                    fill_w = max(int(HP_BAR_W * hp_pct / 100.0), 1)
                    c.create_rectangle(
                        bar_x, bar_y, bar_x + fill_w, bar_y + HP_BAR_H,
                        fill=t.hp_color(hp_pct), outline="",
                    )
                c.create_text(
                    width - PAD, y, text=pct_text, anchor="ne", fill=t.muted,
                    font=self._font_row,
                )
            elif kind == "alert":
                _, text, color = row
                text = self._truncate(text, self._font_alert, width - PAD - text_x)
                c.create_text(
                    text_x, y, text=text, anchor="nw", fill=color, font=self._font_alert
                )
            y += row_h + ROW_GAP

    def _rounded_rect(self, x0, y0, x1, y1, r, **kwargs):
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
            x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return self._canvas.create_polygon(points, smooth=True, **kwargs)

    @staticmethod
    def _truncate(text: str, font: tkfont.Font, max_px: int) -> str:
        if font.measure(text) <= max_px:
            return text
        while text and font.measure(text + "…") > max_px:
            text = text[:-1]
        return text + "…"
