# VibeTune ♫

**VibeTune** is a lightweight, retro-styled terminal Spotify Connect remote player built with Python, [Textual](https://textual.textualize.io/), and [Spotipy](https://spotipy.readthedocs.io/).

Designed for Linux tiling window managers, VibeTune sits comfortably in a small terminal tile (or scales up to full screen) so you can browse your playlists, search the Spotify catalog, and control playback on your phone, earbuds, or smart speakers without ever picking up your phone or running a heavy desktop client.

```text
┌───────────────────────────────────── VibeTune ───────────────────────────────────────┐
│ ♫ Spectrum Visualizer                         │ Now Playing & Controls               │
│                                     █   █     │  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄  Resonance           │
│                                   █ █ █ █ █   │  █ ▄▄▄▄  ▄▄▄▄ █  HOME                │
│                       █         █ █ █ █ █ █ █ │  █ █  █  █  █ █  Odyssey (2014)      │
│                   █ █ █ █ █   █ █ █ █ █ █ █ █ │  █ ▀▀▀▀▀▀▀▀▀▀ █  ◈ Pixel 9 (Earbuds) │
│               █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │  █            █  [▶] 01:42 ━━●━━ 03:32│
│       █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │  █            █  🔀 [s:ON] 🔁 [r:ALL] │
│   ▄ ▄ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ █ │  ▀▀▀▀▀▀▀▀▀▀▀▀▀▀  [p:⏮] [Space:⏸] [n:⏭]│
├──────────────────────────┬────────────────────┴──────────────────────────────────────┤
│ [F1] Library             │ [F2] Tracklist: 80's Retro Wave                           │
│                          │      (Press '/' to filter/search)                         │
│ > Liked Songs       (48) │ #    Title                     Artist            Duration │
│   80's Retro Wave  (590) │ ───────────────────────────────────────────────────────── │
│   Reels playlist     (6) │ 1    Running in the Night      FM-84, Ollie Wri…    04:30 │
│   2000s Bangla Un…  (64) │ 2   >Resonance                 HOME                 03:32 │
│   ◉ Die For You      (1) │ 3    Midnight City             M83                  04:03 │
│   ♪ Kaaktaal         (4) │ 4    Nightcall                 Kavinsky             04:19 │
│   ♪ Linkin Park      (2) │ 5    Tech Noir                 GUNSHIP              04:57 │
├──────────────────────────┴───────────────────────────────────────────────────────────┤
│ [Tab] Pane │ [↑/↓] Select │ [Enter] Play │ [←/→] ±5s │ [/] Search │ [Space] Pause │ [d] Device │ [q] Quit │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Featherweight Spotify Connect Remote:** Controls playback on your phone, desktop, or smart speaker (Echo Dot, Sonos, etc.) via the Spotify Web API with zero local audio decoding overhead.
- **Responsive 2-Deck Retro UI:** Adapts seamlessly from compact tiling window manager panes to ultrawide fullscreen terminals.
- **High-Res Unicode Sextant Album Art:** Renders 24-bit TrueColor album covers using $2 \times 3$ Unicode Sextant subpixel partitioning (`U+1FB00`–`U+1FB3B`) with automatic compact/wide breakpoints.
- **20 FPS Audio Spectrum Visualizer:** Smooth logarithmic frequency bar animation using Unicode block glyphs (`▂▃▄▅▆▇█`) synced to track tempo and harmonic segments.
- **Progressive Batch Streaming:** Streams large playlists (500+ tracks), Liked Songs, Saved Albums (`◉`), and Favorite Artists (`♪`) in background batches without blocking navigation.
- **Dual-Mode Inline Search (`/`):** Filters the active tracklist live as you type, and searches the full Spotify catalog on `Enter` without intrusive popups.
- **Interactive Device Picker (`d`):** Modal selector to switch active playback between your phone, speakers, and computer on the fly.
- **CJK & Wide-Glyph Aware:** Strict terminal cell-width alignment (`rich.cells`) ensures Japanese, Chinese, Korean, Bengali, and symbol titles never misalign columns or wrap lines.

---

## Prerequisites

- **Python** $\ge 3.11$
- **[uv](https://docs.astral.sh/uv/)** (recommended Python package & environment manager)
- A **Spotify Premium** account (required by Spotify's Web API for remote playback control)
- A **Terminal Emulator** with 24-bit TrueColor and Unicode 13+ support (e.g., Ptyxis, Kitty, WezTerm, Ghostty, Alacritty, Foot, GNOME Terminal)

---

## Setup & Installation

### 1. Create a Spotify Developer App
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in.
2. Click **Create app**.
3. Fill in any **App name** (e.g., `VibeTune`) and **App description**.
4. Add the following **Redirect URI**:
   ```text
   http://127.0.0.1:8888/callback
   ```
5. Check **Web API** under APIs used and save.
6. Open your app's **Settings** and copy your **Client ID** and **Client Secret**.

### 2. Clone & Configure Environment
```bash
git clone https://github.com/ashrafpy/vibetune.git
cd vibetune
cp .env.example .env.local
```

Edit `.env.local` and paste your Spotify credentials:
```ini
SPOTIPY_CLIENT_ID=your_spotify_client_id_here
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

### 3. Run VibeTune
```bash
uv run vibetune
```
On your first run, VibeTune will open your browser to authorize with Spotify and automatically save the token in `.spotify_cache` for future sessions.

---

## Keybindings Reference

### Normal Mode
| Key | Action |
| :--- | :--- |
| `Tab` / `Shift+Tab` | Toggle focus between **Library** (`[F1]`) and **Tracklist** (`[F2]`) |
| `F1` / `F2` | Jump focus directly to **Library** or **Tracklist** |
| `↑` / `↓` | Navigate rows in the focused pane |
| `Enter` | Load selected Library playlist/artist/album, or play selected track |
| `Space` | Toggle Play / Pause (instant optimistic update) |
| `n` / `p` | Skip to Next / Previous track |
| `s` | Toggle Shuffle (`ON` / `OFF`) |
| `r` | Cycle Repeat mode (`OFF` $\to$ `ALL` $\to$ `TRK`) |
| `←` / `→` | Seek audio backward / forward by $5\text{ s}$ |
| `+` / `-` | Adjust volume up / down by $5\%$ |
| `d` | Open the **Spotify Connect Device Selector** modal |
| `/` | Enter inline **Search Mode** in the Tracklist header |
| `q` / `Ctrl+C` | Quit VibeTune |

### Search Mode (`/`)
| Key | Action |
| :--- | :--- |
| `a-z`, `0-9`, `Space` | Type into the search query (live-filters current playlist) |
| `Backspace` | Delete character before cursor |
| `←` / `→` | Move text cursor within search query |
| `Enter` | Search full **Spotify Catalog** for query, or play highlighted result |
| `↑` / `↓` | Navigate through filtered or catalog search results |
| `Esc` | Cancel search and restore the previous playlist |

---

## Development & Testing

Run the automated test suite (unit tests + Textual Pilot integration tests):
```bash
uv run --extra dev pytest -v
```

### Project Structure
```text
vibetune/
├── .env.example                  # Environment variable template
├── pyproject.toml                # Project metadata & dependencies (uv / hatchling)
├── spotify_tui_design_specification.md
├── src/vibetune/
│   ├── app.py                    # Main Textual App, Device Modal & Input State Machine
│   ├── main.py                   # CLI entry point (`vibetune`)
│   ├── models.py                 # Dataclasses for tracks, library items & playback state
│   ├── spotify_client.py         # Spotipy OAuth, device control, batch streaming & search
│   ├── styles.tcss               # Retro Spotify Green (#1DB954) & #121212 stylesheet
│   └── widgets/
│       ├── visualizer.py         # 20 FPS logarithmic spectrum visualizer
│       ├── now_playing.py        # Responsive 2x3 Sextant TrueColor album art & controls
│       ├── library_pane.py       # [F1] Library navigation pane
│       └── tracklist_pane.py     # [F2] Tracklist table & inline header search
└── tests/
    └── test_app.py               # Automated pytest + Textual Pilot test suite
```

---

## License

Released under the [MIT License](LICENSE).
