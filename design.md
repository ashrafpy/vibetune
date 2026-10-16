# Terminal Spotify Player (TUI) — UI & Design Specification

---

## 1. Executive Architecture & Mental Model

VibeTune employs a **2-Deck Architecture** designed to maximize readability and keyboard ergonomics within compact terminal windows:
* **Top Deck (Display & Media Stage):** Non-focusable status and visualization area split horizontally between a real-time 20 FPS audio spectrum visualizer (left 60%) and an album art/playback control dashboard (right 40%).
* **Bottom Deck (Interactive Navigation):** A 2-column split between Library Navigation (Pane 1, 30%) and Tracklist / Inline Search (Pane 2, 70%).
* **Modal Overlay (Device Selector):** Floating dialog (`d`) for discovering and switching active Spotify Connect playback targets.
* **Footer (Status & Legend):** A single persistent row anchoring active keybindings and contextual indicators.

By keeping the Top Deck display-only and controlled via global hotkeys, the keyboard focus loop remains a clean, two-state toggle between the Library and the Tracklist.

---

## 2. Terminal Wireframe Mockup

### 2.1 Main Application View
```text
┌───────────────────────────────── VIBETUNE ♫ ─────────────────────────────────────────┐
│ ♫ Spectrum Visualizer                                 │ Now Playing & Controls       │
│                                           █   █       │  🬀🬂🬄🬆🬈🬋🬍  Resonance          │
│                                         █ █ █ █ █     │  🬎🬐🬒🬔🬖🬘🬚  HOME               │
│                             █         █ █ █ █ █ █ █   │  🬛🬝🬟🬡🬣🬥🬧  Odyssey (2014)     │
│                         █ █ █ █ █   █ █ █ █ █ █ █ █ █ │  🬨🬪🬬🬮🬰🬲🬴                     │
│                     █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │ [▶] 01:42 ━━━━━●━━━━ 03:32  │
│             █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │ 🔀 [s:ON]  🔁 [r:ALL]  [74%] │
│         ▄ ▄ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │ [p:⏮] [Space:▶] [n:⏭]       │
├────────────────────────────────┬──────────────────────┴──────────────────────────────┤
│ [F1] Library                   │ [F2] Tracklist: Discover Weekly                     │
│                                │      (Press '/' to filter/search)                   │
│ > Liked Songs            (342) │ #   Title               Artist            Duration  │
│   Daily Mix 1             (50) │ ──────────────────────────────────────────────────  │
│ ◉ Random Access Memories  (13) │ 1   Midnight City       M83                  04:03  │
│ ♪ Daft Punk               (10) │ 2  >Resonance           HOME                 03:32  │
│   Synthwave Radio         (80) │ 3   Starboy             The Weeknd           03:50  │
│   Lo-Fi Beats             (65) │ 4   Instant Crush       Daft Punk            05:37  │
│   Coding Focus            (42) │ 5   Nightcall           Kavinsky             04:19  │
│   Release Radar           (30) │ 6   夜に駆ける          YOASOBI              04:21  │
├────────────────────────────────┴─────────────────────────────────────────────────────┤
│ [Tab] Pane │ [↑/↓] Select │ [Enter] Play │ [←/→] ±5s │ [/] Search │ [d] Device │ [q] Quit│
└──────────────────────────────────────────────────────────────────────────────────────┘
◄────────────── 30% ────────────►◄──────────────────── 70% ────────────────────────────►
```

### 2.2 Device Selector Modal View (`d`)
```text
                     ┌─────────── Spotify Connect Devices ───────────┐
                     │                                               │
                     │  ● Living Room Echo Dot  [Speaker]  (ACTIVE)  │
                     │    Pixel 8 Pro           [Smartphone]         │
                     │    Desktop Workstation   [Computer]           │
                     │                                               │
                     │  [↑/↓] Select   [Enter] Switch   [Esc] Close  │
                     └───────────────────────────────────────────────┘
```

---

## 3. Component Breakdown & Geometry

### 3.1 Top Deck: Media & Visualizer Stage (`~35-40%` Viewport Height)

* **Left: Audio Spectrum Visualizer (`60%` Width)**
  * Displays 24–48 logarithmic frequency bands ($60\text{ Hz}$ to $16\text{ kHz}$) using Unicode block glyphs: ` `, `▂`, `▃`, `▄`, `▅`, `▆`, `▇`, `█`.
  * Runs at a steady 20 FPS refresh rate.
  * When track audio features and harmonic segments are retrieved from Spotify's API, the visualizer modulates peak heights and danceability rhythms to match the song's live tempo and energy.
* **Right: Now Playing & Controls (`40%` Width)**
  * **Unicode Sextant Album Art:** Renders high-resolution album covers using $2 \times 3$ Unicode Sextant subpixel partitioning (`U+1FB00`–`U+1FB3B`) with 24-bit TrueColor ANSI escape sequences. Automatically toggles between compact ($12 \times 6$) and standard ($20 \times 10$) cell footprints based on terminal width.
  * **Metadata:** Track title, artist, album name, and release year with automatic overflow truncation.
  * **Progress Bar:** Elapsed runtime, dynamic scrub bar with slider thumb (`●`), total duration, and volume percentage indicator.
  * **Control Cues:** Visual state indicators for Shuffle (`s`), Repeat (`r`), Next (`n`), Previous (`p`), and Play/Pause (`Space`).

### 3.2 Bottom Deck: Interactive Navigation (`~55-60%` Viewport Height)

* **Pane 1: Library (`30%` Width, Focusable via `[F1]` / `Tab`)**
  * Lists playlists, Liked Songs, Saved Albums (`◉`), and Followed Artists (`♪`).
  * Right-aligned track counts rendered in muted grey (`#535353`).
  * Backed by progressive background batch streaming: switching between categories streams content in chunks without UI freezes.
* **Pane 2: Tracklist & Search (`70%` Width, Focusable via `[F2]` / `Tab`)**
  * Tabular display of `#`, `Title`, `Artist`, and `Duration`.
  * **CJK & Wide-Glyph Cell Width Alignment:** Uses `rich.cells.cell_len` and padding calculations to guarantee East Asian characters (Japanese, Chinese, Korean) and South Asian scripts (Bengali, Hindi) align cleanly to column borders without wrapping or breaking table geometry.
  * **Dual-Mode Inline Search Header (`/`):**
    - *Live Filtering:* As characters are entered, the current tracklist filters instantly in memory.
    - *Spotify Catalog Search:* Pressing `Enter` executes a global Spotify catalog search and displays matching tracks directly in the table.
    - *Cancel & Restore:* Pressing `Esc` clears the search buffer and restores the previous playlist cleanly.

### 3.3 Device Selector Modal (`d`)
* Floating modal overlay that queries `/v1/me/player/devices`.
* Displays friendly device names, device types (`Smartphone`, `Speaker`, `Computer`), and highlights the currently active device.
* Selecting a device and pressing `Enter` calls `/v1/me/player` to transfer playback seamlessly.

### 3.4 Footer Strip (`Fixed 1 Row`)
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
               │  d               ──> Open Device Selector Modal        │
               │  /               ──> Transition to Search Mode         │
               └───────────────┬──────────────────────────┬─────────────┘
                               │ Press '/'                │ Press 'd'
                               ▼                          ▼
               ┌─────────────────────────────┐  ┌───────────────────────┐
               │         SEARCH MODE         │  │     DEVICE MODAL      │
               │  Chars     ──> Live Filter  │  │  ↑ / ↓  ──> Navigate  │
               │  Backspace ──> Delete Char  │  │  Enter  ──> Transfer  │
               │  Enter     ──> Catalog Srch │  │  Esc    ──> Close     │
               │  ↑ / ↓     ──> Select Result│  └───────────────────────┘
               │  Esc       ──> Restore List │
               └─────────────────────────────┘
```

---

## 5. Complete Keymap Reference

| Key | Mode / Context | Action |
| :--- | :--- | :--- |
| `Tab` / `Shift+Tab` | Global (Normal) | Toggle focus between Library and Tracklist |
| `F1` | Global (Normal) | Jump focus directly to Library |
| `F2` | Global (Normal) | Jump focus directly to Tracklist |
| `↑` / `↓` | Normal Mode | Navigate active list / table rows |
| `Enter` | Normal Mode | Play selected track or load playlist |
| `Space` | Normal Mode | Toggle Play / Pause |
| `n` | Normal Mode | Skip to next track |
| `p` | Normal Mode | Skip to previous track |
| `s` | Normal Mode | Toggle shuffle mode (`ON` / `OFF`) |
| `r` | Normal Mode | Cycle repeat mode (`OFF` $\to$ `ALL` $\to$ `TRK`) |
| `←` / `→` | Normal Mode | Seek backward / forward 5 seconds |
| `+` / `-` | Normal Mode | Adjust volume up / down by 5% |
| `d` | Normal Mode | Open the Spotify Connect Device Selector modal |
| `/` | Normal Mode | Enter Search Mode (focuses header input) |
| `q` / `Ctrl+C` | Global | Quit player |
| `a-z`, `0-9`, `Space` | Search Mode | Appends characters to query (live filters current list) |
| `Backspace` | Search Mode | Deletes last character of search query |
| `←` / `→` | Search Mode | Move cursor within search text |
| `↑` / `↓` | Search Mode | Navigate through filtered / catalog search results table |
| `Enter` | Search Mode | Search Spotify catalog for query, or play selected result |
| `Esc` | Search Mode | Cancel search and restore previous playlist |

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
