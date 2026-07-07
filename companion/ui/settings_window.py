"""Rule-builder window (tk.Toplevel), dark-themed with ttk. Opens on startup so the user can
manage capture rules without touching the YAML file. Closing the window hides it; clicking
Quit Companion tears down the whole app.

Edits config/rules.yaml only -- boss-pack rules (config/bosses/) are calibrated files, edited
by hand, and survive saves here untouched (see RulesEngine.reload).
"""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from companion.rules.engine import RulesEngine
from companion.rules.schema import (
    Action,
    AlertLevel,
    Condition,
    Trigger,
    load_rules,
    save_rules,
)
from companion.ui.theme import Theme

FIELD_DEFS = [
    ("id",               "Rule ID *",             "unique name, e.g. burn_phase"),
    ("boss_name",        "Boss name",             "packet data — exact monster name"),
    ("zone_equals",      "Zone equals",           "packet data — exact room name"),
    ("hp_pct_below",     "HP % below",            "packet data — e.g. 30"),
    ("message_contains", "Message contains",      "boss/server text; use | for any-of"),
    ("visual_cue",       "Visual cue",            "pack:cue, e.g. ultra_darkon:red_glow"),
    ("alert",            "Alert text *",          "what the HUD shows"),
    ("cooldown_seconds", "Cooldown (s)",          "min seconds between repeats"),
    ("initial_delay_seconds", "Timer: delay (s)", "timer mode: fire this long after fight start"),
    ("repeat_every_seconds",  "Timer: repeat (s)", "timer mode: then repeat every N s (rotation)"),
]


class SettingsWindow:
    def __init__(
        self,
        root: tk.Tk,
        rules_path: Path,
        engine: RulesEngine,
        theme: Theme | None = None,
        on_open_inspector=None,
    ):
        self._root = root
        self._rules_path = rules_path
        self._engine = engine
        self._theme = theme or Theme()
        self._on_open_inspector = on_open_inspector
        self._triggers: list[Trigger] = []

        self._win = tk.Toplevel(root)
        self._win.title("Companion — Rule Builder")
        self._win.geometry("760x480")
        self._win.minsize(680, 420)
        self._win.configure(bg=self._theme.panel_bg)
        # Closing the window just hides it rather than destroying the Toplevel so it can be
        # shown again without rebuilding all the widgets.
        self._win.protocol("WM_DELETE_WINDOW", self._win.withdraw)

        self._init_style()
        self._build_ui()
        self._reload_list()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def show(self) -> None:
        self._win.deiconify()
        self._win.lift()
        self._win.focus_force()

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _init_style(self) -> None:
        t = self._theme
        self._field_bg = "#1d1f28"

        style = ttk.Style(self._win)
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=t.panel_bg)
        style.configure(
            "Dark.TLabel", background=t.panel_bg, foreground=t.text,
            font=(t.font_family, 10),
        )
        style.configure(
            "Muted.TLabel", background=t.panel_bg, foreground=t.muted,
            font=(t.font_family, 9),
        )
        style.configure(
            "Header.TLabel", background=t.panel_bg, foreground=t.accent,
            font=(t.font_family, 11, "bold"),
        )
        style.configure(
            "Dark.TEntry",
            fieldbackground=self._field_bg, foreground=t.text, insertcolor=t.text,
            bordercolor=t.border, lightcolor=t.border, darkcolor=t.border,
            padding=5,
        )
        style.map("Dark.TEntry", bordercolor=[("focus", t.accent)])
        style.configure(
            "Accent.TButton",
            background=t.accent, foreground="#ffffff", borderwidth=0,
            focusthickness=0, padding=(14, 7), font=(t.font_family, 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#9078ff")])
        style.configure(
            "Ghost.TButton",
            background=self._field_bg, foreground=t.text, borderwidth=1,
            bordercolor=t.border, focusthickness=0, padding=(10, 5),
            font=(t.font_family, 9),
        )
        style.map("Ghost.TButton", background=[("active", "#262935")])
        style.configure(
            "Danger.TButton",
            background=self._field_bg, foreground=t.critical, borderwidth=1,
            bordercolor=t.border, focusthickness=0, padding=(10, 5),
            font=(t.font_family, 9),
        )
        style.map("Danger.TButton", background=[("active", "#2e222a")])
        style.configure(
            "Dark.Treeview",
            background=self._field_bg, fieldbackground=self._field_bg,
            foreground=t.text, borderwidth=0, rowheight=26,
            font=(t.font_family, 9),
        )
        style.map(
            "Dark.Treeview",
            background=[("selected", t.accent)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Dark.Treeview.Heading",
            background=t.panel_bg, foreground=t.muted, borderwidth=0,
            font=(t.font_family, 9, "bold"),
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=self._field_bg, background=self._field_bg,
            foreground=t.text, bordercolor=t.border, arrowcolor=t.muted,
            lightcolor=t.border, darkcolor=t.border, padding=4,
        )
        style.configure(
            "Dark.TCheckbutton",
            background=t.panel_bg, foreground=t.text, focuscolor=t.panel_bg,
            font=(t.font_family, 9),
        )
        style.map(
            "Dark.TCheckbutton",
            background=[("active", t.panel_bg)],
            indicatorcolor=[("selected", t.accent)],
        )
        # Combobox dropdown list colors are plain-Tk options, not ttk styles.
        self._win.option_add("*TCombobox*Listbox.background", self._field_bg)
        self._win.option_add("*TCombobox*Listbox.foreground", t.text)
        self._win.option_add("*TCombobox*Listbox.selectBackground", t.accent)
        self._win.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = self._theme
        outer = ttk.Frame(self._win, style="Dark.TFrame", padding=14)
        outer.pack(fill="both", expand=True)

        # ── Left panel: rule table ─────────────────────────────────────
        left = ttk.Frame(outer, style="Dark.TFrame")
        left.pack(side="left", fill="y")

        ttk.Label(left, text="Rules", style="Header.TLabel").pack(anchor="w", pady=(0, 8))

        table_wrap = ttk.Frame(left, style="Dark.TFrame")
        table_wrap.pack(fill="y", expand=True)

        self._tree = ttk.Treeview(
            table_wrap,
            columns=("level",),
            show="tree headings",
            style="Dark.Treeview",
            selectmode="browse",
            height=12,
        )
        self._tree.heading("#0", text="ID", anchor="w")
        self._tree.heading("level", text="Level", anchor="w")
        self._tree.column("#0", width=170, stretch=True)
        self._tree.column("level", width=70, stretch=False)

        sb = ttk.Scrollbar(table_wrap, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        btns = ttk.Frame(left, style="Dark.TFrame")
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="＋ New", style="Ghost.TButton", command=self._new_rule).pack(
            side="left"
        )
        ttk.Button(
            btns, text="Delete", style="Danger.TButton", command=self._delete_rule
        ).pack(side="left", padx=(8, 0))

        # ── Divider ────────────────────────────────────────────────────
        divider = tk.Frame(outer, width=1, bg=t.border)
        divider.pack(side="left", fill="y", padx=16)

        # ── Right panel: form ──────────────────────────────────────────
        right = ttk.Frame(outer, style="Dark.TFrame")
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(right, text="Edit Rule", style="Header.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )

        self._entries: dict[str, ttk.Entry] = {}
        for row, (key, label, hint) in enumerate(FIELD_DEFS, start=1):
            ttk.Label(right, text=label, style="Dark.TLabel").grid(
                row=row, column=0, sticky="e", pady=3, padx=(0, 10)
            )
            entry = ttk.Entry(right, style="Dark.TEntry", width=26, font=(t.font_family, 10))
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            ttk.Label(right, text=hint, style="Muted.TLabel").grid(
                row=row, column=2, sticky="w", padx=(10, 0)
            )
            self._entries[key] = entry

        right.columnconfigure(1, weight=1)

        lrow = len(FIELD_DEFS) + 1
        ttk.Label(right, text="Level", style="Dark.TLabel").grid(
            row=lrow, column=0, sticky="e", pady=3, padx=(0, 10)
        )
        self._level_var = tk.StringVar(value="info")
        ttk.Combobox(
            right,
            textvariable=self._level_var,
            values=["info", "warning", "critical"],
            state="readonly",
            style="Dark.TCombobox",
            width=12,
        ).grid(row=lrow, column=1, sticky="w", pady=3)

        crow = lrow + 1
        self._fire_once_var = tk.BooleanVar()
        ttk.Checkbutton(
            right,
            text="Fire once per threshold crossing (re-arms when condition clears)",
            variable=self._fire_once_var,
            style="Dark.TCheckbutton",
        ).grid(row=crow, column=0, columnspan=3, sticky="w", pady=(8, 4))

        brow = crow + 1
        actions = ttk.Frame(right, style="Dark.TFrame")
        actions.grid(row=brow, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(
            actions, text="Save Rule", style="Accent.TButton", command=self._save_rule
        ).pack(side="left")
        if self._on_open_inspector is not None:
            ttk.Button(
                actions, text="Frame Inspector", style="Ghost.TButton",
                command=self._on_open_inspector,
            ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions, text="Quit Companion", style="Danger.TButton", command=self._quit
        ).pack(side="right")

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _reload_list(self) -> None:
        try:
            self._triggers = load_rules(self._rules_path)
        except Exception as exc:
            messagebox.showerror("Rules load error", str(exc), parent=self._win)
            self._triggers = []

        self._tree.delete(*self._tree.get_children())
        for t in self._triggers:
            self._tree.insert("", "end", iid=t.id, text=t.id, values=(t.then.level.value,))

    def _on_select(self, _event=None) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        trigger = next((t for t in self._triggers if t.id == selected[0]), None)
        if trigger is not None:
            self._populate_form(trigger)

    # ------------------------------------------------------------------
    # Form helpers
    # ------------------------------------------------------------------

    def _populate_form(self, t: Trigger) -> None:
        def _set(key: str, val: object) -> None:
            self._entries[key].delete(0, "end")
            if val is not None:
                self._entries[key].insert(0, str(val))

        _set("id", t.id)
        _set("boss_name", t.when.boss_name)
        _set("zone_equals", t.when.zone_equals)
        _set("hp_pct_below", t.when.hp_pct_below)
        mc = t.when.message_contains
        _set("message_contains", " | ".join(mc) if isinstance(mc, tuple) else mc)
        _set("visual_cue", t.when.visual_cue)
        _set("alert", t.then.alert)
        _set("cooldown_seconds", t.cooldown_seconds if t.cooldown_seconds else "")
        _set("initial_delay_seconds", t.initial_delay_seconds if t.initial_delay_seconds else "")
        _set("repeat_every_seconds", t.repeat_every_seconds if t.repeat_every_seconds else "")
        self._level_var.set(t.then.level.value)
        self._fire_once_var.set(t.fire_once_per_threshold_crossing)

    def _clear_form(self) -> None:
        for e in self._entries.values():
            e.delete(0, "end")
        self._level_var.set("info")
        self._fire_once_var.set(False)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _new_rule(self) -> None:
        self._tree.selection_remove(self._tree.selection())
        self._clear_form()
        self._entries["id"].focus_set()

    def _delete_rule(self) -> None:
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning("No selection", "Select a rule to delete.", parent=self._win)
            return
        rule_id = selected[0]
        if not messagebox.askyesno("Delete rule", f"Delete rule '{rule_id}'?", parent=self._win):
            return
        self._triggers = [t for t in self._triggers if t.id != rule_id]
        self._persist()
        self._reload_list()
        self._clear_form()

    def _save_rule(self) -> None:
        rule_id = self._entries["id"].get().strip()
        alert_text = self._entries["alert"].get().strip()

        if not rule_id:
            messagebox.showerror("Validation error", "Rule ID is required.", parent=self._win)
            return
        if not alert_text:
            messagebox.showerror("Validation error", "Alert text is required.", parent=self._win)
            return

        hp_raw = self._entries["hp_pct_below"].get().strip()
        hp_pct_below: float | None = None
        if hp_raw:
            try:
                hp_pct_below = float(hp_raw)
            except ValueError:
                messagebox.showerror(
                    "Validation error", "HP % below must be a number (e.g. 30).", parent=self._win
                )
                return

        numbers: dict[str, float] = {}
        for key, label in (
            ("cooldown_seconds", "Cooldown"),
            ("initial_delay_seconds", "Timer delay"),
            ("repeat_every_seconds", "Timer repeat"),
        ):
            raw = self._entries[key].get().strip()
            if not raw:
                numbers[key] = 0.0
                continue
            try:
                numbers[key] = float(raw)
            except ValueError:
                messagebox.showerror(
                    "Validation error", f"{label} must be a number (e.g. 5).", parent=self._win
                )
                return

        mc_raw = self._entries["message_contains"].get().strip()
        message_contains: str | tuple[str, ...] | None = None
        if mc_raw:
            fragments = tuple(p.strip() for p in mc_raw.split("|") if p.strip())
            message_contains = fragments if len(fragments) > 1 else fragments[0]

        trigger = Trigger(
            id=rule_id,
            when=Condition(
                boss_name=self._entries["boss_name"].get().strip() or None,
                zone_equals=self._entries["zone_equals"].get().strip() or None,
                hp_pct_below=hp_pct_below,
                message_contains=message_contains,
                visual_cue=self._entries["visual_cue"].get().strip() or None,
            ),
            then=Action(alert=alert_text, level=AlertLevel(self._level_var.get())),
            cooldown_seconds=numbers["cooldown_seconds"],
            fire_once_per_threshold_crossing=self._fire_once_var.get(),
            initial_delay_seconds=numbers["initial_delay_seconds"],
            repeat_every_seconds=numbers["repeat_every_seconds"],
        )

        # Upsert: replace if the id already exists, otherwise append
        existing_idx = next(
            (i for i, t in enumerate(self._triggers) if t.id == rule_id), None
        )
        if existing_idx is not None:
            self._triggers[existing_idx] = trigger
        else:
            self._triggers.append(trigger)

        self._persist()
        self._reload_list()

        if rule_id in self._tree.get_children():
            self._tree.selection_set(rule_id)
            self._tree.see(rule_id)

    def _persist(self) -> None:
        try:
            save_rules(self._triggers, self._rules_path)
            self._engine.reload(self._triggers)
        except Exception as exc:
            messagebox.showerror("Save error", str(exc), parent=self._win)

    def _quit(self) -> None:
        if messagebox.askyesno("Quit Companion", "Stop Companion?", parent=self._win):
            self._root.destroy()
