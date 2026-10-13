# Terminal Spotify Player (TUI) — UI & Design Specification

---

## 1. Executive Architecture & Mental Model

The player uses a **2-Deck Architecture**:
* **Top Deck (Display & Media Stage):** Non-focusable status and visualization area split horizontally between a real-time audio spectrum visualizer (left 60%) and an album art/playback control dashboard (right 40%).
* **Bottom Deck (Interactive Navigation):** A 2-column split between Library Navigation (Pane 1) and Tracklist/Search (Pane 2).
* **Footer (Status & Legend):** A single persistent row anchoring active keybindings and contextual indicators.

By keeping the Top Deck display-only and controlled via global hotkeys, the keyboard focus loop remains a clean, two-state toggle between the Library and the Tracklist.

---

## 2. Complete Terminal Wireframe Mockup

```text
┌───────────────────────────────── SPOTIFY-TUI ────────────────────────────────────────┐
│ ♫ Spectrum Visualizer                                 │ Now Playing & Controls       │
│                                           █   █       │  ▄▄▄▄▄▄▄▄▄▄▄  Resonance      │
│                                         █ █ █ █ █     │  █ ▄▄▄ ▄▄▄ █  HOME           │
│                             █         █ █ █ █ █ █ █   │  █ █ █ █ █ █  Odyssey (2014) │
│                         █ █ █ █ █   █ █ █ █ █ █ █ █ █ │  ▀▀▀▀▀▀▀▀▀▀▀                 │
│                     █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │ [▶] 01:42 ━━━━━●━━━━ 03:32  │
│             █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │ 🔀 [s:ON]  🔁 [r:ALL]  [74%] │
│         ▄ ▄ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │ [p:⏮] [Space:▶] [n:⏭]       │
├────────────────────────────────┬──────────────────────┴──────────────────────────────┤
│ [F1] Library                   │ [F2] Tracklist: Discover Weekly                     │
│                                │      (Press '/' to filter/search)                   │
│ > Liked Songs            (342) │ #   Title               Artist            Duration  │
│   Daily Mix 1             (50) │ ──────────────────────────────────────────────────  │
│   Synthwave Radio         (80) │ 1   Midnight City       M83                  04:03  │
│   Lo-Fi Beats             (65) │ 2  >Resonance           HOME                 03:32  │
│   Coding Focus            (42) │ 3   Starboy             The Weeknd           03:50  │
│   Release Radar           (30) │ 4   Instant Crush       Daft Punk            05:37  │
│   Post-Rock Essentials    (25) │ 5   Nightcall           Kavinsky             04:19  │
│   Ambient Space           (40) │ 6   Genesis             Grimes               04:15  │
├────────────────────────────────┴─────────────────────────────────────────────────────┤
│ [Tab] Pane │ [↑/↓] Select │ [Enter] Play │ [←/→] ±5s │ [/] Search │ [Space] Pause │ [q] Quit │
└──────────────────────────────────────────────────────────────────────────────────────┘
◄────────────── 30% ────────────►◄──────────────────── 70% ────────────────────────────►
```

---

## 3. Component Breakdown & Geometry

### 3.1 Top Deck: Media & Visualizer Stage (`~35-40%` Viewport Height)

* **Left: Audio Spectrum Visualizer (`60%` Width)**
  * Displays 24–48 logarithmic frequency bands ($60\text{ Hz}$ to $16\text{ kHz}$) using Unicode block glyphs: ` `, `▂`, `▃`, `▄`, `▅`, `▆`, `▇`, `█`.
  * Fed either via local audio loopback (PulseAudio/PipeWire/ALSA) or interpolated from Spotify's `/v1/audio-analysis` segments.
* **Right: Now Playing & Controls (`40%` Width)**
  * **Album Art:** $1:1$ square rendered via Unicode half-blocks (`▀`, `▄`) with 24-bit TrueColor or Kitty/Sixel graphics protocol.
  * **Metadata:** Song title, artist, album, and release year.
  * **Progress Bar:** Elapsed runtime, dynamic scrub bar with slider thumb (`●`), total duration, and volume percentage.
  * **Control Cues:** Visual state indicators for Shuffle (`s`), Repeat (`r`), Next (`n`), Previous (`p`), and Play/Pause (`Space`).

### 3.2 Bottom Deck: Interactive Navigation (`~55-60%` Viewport Height)

* **Pane 1: Library (`30%` Width, Focusable)**
  * Lists Liked Songs, Daily Mixes, Saved Playlists, and Saved Albums.
  * Right-aligned track counts rendered in muted grey (`#535353`).
* **Pane 2: Tracklist & Search (`70%` Width, Focusable)**
  * Tabular display of `#`, `Title`, `Artist`, and `Duration`.
  * **Inline Header Search:** Pressing `/` transforms the pane header into an active text input (`[F2] 🔍 Search: <query>_`). Submitting queries populates search results directly into the table without modal popups.

### 3.3 Footer Strip (`Fixed 1 Row`)

* Persistent global key legend showing available navigation and media control hotkeys.

---

## 4. Input Modes & Interaction State Machine

```text
               ┌────────────────────────────────────────────────────────┐
               │                      NORMAL MODE                       │
               │  Tab / Shift+Tab ──> Toggle Pane Focus (Library ↔ Tracks)│
               │  F1 / F2         ──> Direct Pane Jump                  │
               │  ↑ / ↓           ──> Navigate List Items               │
               │  Enter           ──> Play Track / Open Playlist        │
               │  ← / →           ──> Seek Audio (-5s / +5s)            │
               │  + / -           ──> Volume (-5% / +5%)                │
               │  Space           ──> Play / Pause                      │
               │  n / p           ──> Next / Previous Track             │
               │  s / r           ──> Toggle Shuffle / Cycle Repeat     │
               │  /               ──> Transition to Search Mode         │
               └───────────────────────────┬────────────────────────────┘
                                           │ Press '/'
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │                      SEARCH MODE                       │
               │  All Chars (a-z) ──> Appended to Search Query Buffer   │
               │  Space           ──> Inserts Space ' ' into query      │
               │  Backspace       ──> Removes Last Character            │
               │  ← / →           ──> Move Text Cursor inside Query     │
               │  ↑ / ↓           ──> Select Search Results Below       │
               │  Enter           ──> Play Selected Result & Exit Mode  │
               │  Esc             ──> Discard Search & Exit Mode        │
               └────────────────────────────────────────────────────────┘
```

---

## 5. Complete Keymap Reference

| Key | Mode / Context | Action |
| :--- | :--- | :--- |
| `Tab` / `Shift+Tab` | Global (Normal) | Toggle focus between Library and Tracklist |
| `F1` | Global (Normal) | Jump focus to Library |
| `F2` | Global (Normal) | Jump focus to Tracklist |
| `↑` / `↓` | Normal Mode | Navigate active list / table rows |
| `Enter` | Normal Mode | Play selected track or load playlist |
| `Space` | Normal Mode | Toggle Play / Pause |
| `n` | Normal Mode | Skip to next track |
| `p` | Normal Mode | Skip to previous track |
| `s` | Normal Mode | Toggle shuffle mode (`ON` / `OFF`) |
| `r` | Normal Mode | Cycle repeat mode (`OFF` $\to$ `ALL` $\to$ `TRACK`) |
| `←` / `→` | Normal Mode | Seek backward / forward 5 seconds |
| `+` / `-` | Normal Mode | Adjust volume up / down by 5% |
| `/` | Normal Mode | Enter Search Mode (focuses header input) |
| `q` / `Ctrl+C` | Global | Quit player |
| `a-z`, `0-9`, `Space` | Search Mode | Appends characters to search query |
| `Backspace` | Search Mode | Deletes last character of search query |
| `←` / `→` | Search Mode | Move cursor within search text |
| `↑` / `↓` | Search Mode | Navigate through live search results table |
| `Enter` | Search Mode | Submit / Play selected result & exit to Normal Mode |
| `Esc` | Search Mode | Cancel search & exit to Normal Mode |

---

## 6. Theming & Color Tokens

| Token | Palette Value | Role |
| :--- | :--- | :--- |
| **Accent / Focus** | `#1DB954` (Spotify Green) | Focused pane borders, active row highlight, progress thumb |
| **Active Row BG** | `#282828` | Background of currently highlighted table/list item |
| **Primary Text** | `#FFFFFF` | Track titles, column headers, active elapsed time |
| **Secondary Text** | `#B3B3B3` | Artists, album names, unselected durations |
| **Subtle / Border** | `#535353` | Inactive pane borders, table dividers, empty scrub track |
| **Background** | `#121212` (or Terminal Default) | Main application canvas |