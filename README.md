# Cruel Companion

**A passive on-screen assistant for AQW ultra boss fights.** It watches your game window,
recognizes boss mechanics — warning text and glowing telegraph zones — and tells you what to
do with a color-coded alert card and sound cues. Think WeakAuras/DBM, but for AdventureQuest
Worlds.

> **It never plays for you.** No key presses, no mouse movement, no packet injection, no
> automation of any kind. It only observes your screen and displays suggestions — every
> action is yours.

---

## Download & first run (players)

1. Grab the latest `Companion-vX.Y.Z-win64.zip` from
   **[Releases](https://github.com/xyroaqw/cruel-companion/releases)** and unzip it anywhere.
2. Start AQW in the Artix Game Launcher, **windowed** (any size — just don't minimize or
   fully cover it).
3. Double-click **`Companion.exe`**.
   - Windows SmartScreen will warn about an unrecognized app the first time
     (the exe is unsigned): click **More info → Run anyway**.
4. You'll see three things:
   - a **small dark card** in the top-left of your screen — the alert HUD. It's click-through:
     your mouse goes straight to whatever is under it.
   - the **Rule Builder** window — close it if you don't need it (it just hides).
   - a **console window** with status messages — keep it around, it tells you what the tool
     is doing and records every alert it fires.

That's it. When a supported mechanic happens, the card shows the callout
(e.g. **"Staff down — burn Escherion NOW!"**) and you hear a beep pattern:
one beep = info, two = warning, three fast = critical.

**Try it right now:** `/join escherion` and fight. When the staff drops, you'll get the
callout. That fight ships pre-configured as a demo.

---

## How it works

Two independent sensors feed one alert engine:

| Sensor | Sees | Needs |
|---|---|---|
| **Packets** (main source) | Boss warning text, exact HP%, room changes — read from your own network traffic only | [Npcap](https://npcap.com) ("WinPcap API-compatible mode") + run as Administrator |
| **Vision** | Glowing telegraph zones (color detection — client-rendered, invisible to packets) | Nothing — works out of the box |

Text and HP alerts come from packets; glow-zone alerts come from vision. If the packet
layer isn't set up, the tool says so in the console and carries on with zone alerts only.

---

## Adding alerts for any boss

### Simple text alerts — no files needed

Open the **Rule Builder** and create a rule:

- **Message contains**: the boss warning text that marks the mechanic (e.g. `staff is down`)
- **Alert text**: what you want yelled at you (e.g. `Use skill 4 NOW`)
- **Level**: info / warning / critical (controls color + sound)
- **Cooldown**: minimum seconds between repeats

Saved instantly, no restart needed. This covers the most common ultra pattern:
*"when this text appears, press this skill."* (Text rules use the packet layer.)

### Boss packs — text + glowing zones, shareable

Each boss can have one YAML file in `config\bosses\` bundling its **cues** (what glow to
look for) and **rules** (what to call out). Copy `config\bosses\_TEMPLATE.yaml`, follow the
comments, restart Companion. Packs are plain text files — share them with your party.

To calibrate a glow color for a new boss, run **`VisionProbe.exe --watch`** during the
fight: it prints a live coverage % for every cue so you can dial in the color range and
threshold. `VisionProbe.exe --save shot.png` grabs a screenshot to color-pick from.
Full walkthrough inside `_TEMPLATE.yaml`.

### Rule format (exact reference)

Works identically in `config\rules.yaml` and in boss packs. Unknown or mistyped field names
are rejected at startup with an error naming the file and rule — if a rule loads silently,
it's valid.

```yaml
rules:
  - id: my_rule                    # required, unique text
    when:                          # required; all conditions AND together
      message_contains: "staff is down"          # text fragment (case-insensitive), OR:
      # message_contains: ["staff", "counter"]   # a list = fires if ANY fragment matches
      boss_name: "Escherion"       # text, exact monster name        (packet layer)
      zone_equals: "escherion"     # text, exact room name           (packet layer)
      hp_pct_below: 25             # number 0-100                    (packet layer)
      visual_cue: red_glow         # cue id from this pack's cues:   (vision layer)
    then:                          # required
      alert: "Burn NOW!"           # required text shown on the HUD
      level: critical              # info | warning | critical (default info)
    cooldown_seconds: 5            # optional number; min gap between repeats
    fire_once_per_threshold_crossing: true   # optional; fire once, re-arm when condition clears
```

Every `when` field is optional, but use at least one. Cue and rule ids are namespaced by
filename (`ultra_darkon.yaml` → `ultra_darkon:red_glow`), so packs never collide.

### Cue format (exact reference, boss packs only)

```yaml
cues:
  - id: red_glow                   # required, unique within the file
    hsv_lower: [170, 130, 160]     # required [H, S, V] — OpenCV ranges: H 0-179, S/V 0-255
    hsv_upper: [10, 255, 255]      # required; lower H > upper H = wraps around red
    min_coverage_pct: 2.0          # optional; % of region that must match (default 1.0)
    region: [0.05, 0.30, 0.95, 0.95]  # optional [left, top, right, bottom] window fractions
```

A pack with a mistake in it is skipped at startup with a console message saying exactly
which file, which rule, and what's wrong — it never breaks the other packs.

### Not sure what text the boss sends?

Run Companion during the fight and watch its console window — server messages appear there
as they arrive. Whatever it prints is exactly what your `Message contains` rules can match.

---

## Customizing the look

Everything lives in `config\settings.yaml`:

- **`overlay.labels`** — every static text on the HUD. `zone_prefix` labels the current game
  *room* (only shown once packet capture knows one; unrelated to boss glow "zones"). Set
  `title: ""` or `zone_prefix: ""` to hide that row completely.
- **`overlay.theme`** — all colors (panel, accent, alert levels, HP bar) and the font.
- **`overlay.alert_ttl_seconds`** — how long alerts stay on the card.
- **`overlay.x / y`** — where the card sits on screen.
- **`sounds.enabled`** — beeps on/off.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No text/HP alerts | The packet layer needs Npcap installed and Companion run as Administrator — the console says if it's off. |
| Console says *game window not found* | Your client's window title differs. Edit `window_title_contains` in `config\settings.yaml` to match part of your actual window title. |
| No glow-zone alerts | Is the game window visible (not minimized / not covered by other windows)? Zone detection reads actual screen pixels. |
| SmartScreen / antivirus complains | Expected for an unsigned app that reads network traffic. SmartScreen: More info → Run anyway. AV quarantine: restore + add an exclusion for the folder. |
| Alert fires when it shouldn't | Your `Message contains` text is too generic — make the fragment longer/more specific. |

---

## Is this allowed?

Cruel Companion is strictly **observe-and-display**: it reads your screen (and optionally
your own network traffic), and shows you text. It cannot press keys, move your mouse, or
send anything to the game — the code has no pathway for it. That places it in the same
category as overlay/alert addons in other MMOs. Use your own judgment regarding Artix
Entertainment's terms of service; you run it at your own discretion.

---

## For developers

```bash
py -3.13 -m venv .venv
.venv\Scripts\pip install -e .[dev]

.venv\Scripts\pytest tests\                          # unit tests
.venv\Scripts\python tools\selftest_vision.py        # end-to-end vision selftest (spawns a fake game window)
.venv\Scripts\python tools\replay_canned_events.py   # drive the HUD with canned events, no game needed
.venv\Scripts\python -m companion                    # run from source
.venv\Scripts\python tools\make_release.py           # build the release zip (PyInstaller)
```

Architecture in one paragraph: capture threads (packet sniffer in `companion/capture`,
glow-zone screen watcher in `companion/vision`) push normalized events into a queue; the Tk
main thread applies them to `GameState`, evaluates YAML-defined triggers
(`companion/rules`), and renders alerts on a click-through colorkey overlay
(`companion/ui`). Boss packs in `config/bosses/` bundle per-boss vision cues + rules and
are namespaced by filename. The packet parser (`companion/protocol/parser.py`) maps raw
frames to normalized events; its field names come from verifying against your own traffic
(`tools/capture_spike.py`).
