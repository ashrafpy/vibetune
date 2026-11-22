# VibeTune ♫

**VibeTune** is a lightweight, cross-platform, retro-styled terminal Spotify Connect remote & local player built with Python, [Textual](https://textual.textualize.io/), and [Spotipy](https://spotipy.readthedocs.io/).

Designed for Linux tiling window managers, macOS, and Windows Terminal, VibeTune sits comfortably in a small terminal tile (or scales up to full screen) so you can browse your playlists, search the Spotify catalog, and control playback locally or on your phone, earbuds, or smart speakers without ever picking up your phone or running a heavy desktop client.

<img width="1048" height="601" alt="Screenshot From 2026-10-14 04-11-41 (Edited)" src="https://github.com/user-attachments/assets/b2690165-7cf3-4e8c-b1c7-bbafe493cc61" />

---

## Features

- **Standalone Local Playback + Spotify Connect Remote:** Automatically manages a lightweight `go-librespot` local audio engine (PipeWire/PulseAudio/ALSA) with zero-latency local REST/WebSocket control, while still letting you switch to phones or smart speakers via `d` (or run `--remote-only`).
- **Responsive 2-Deck Retro UI:** Adapts seamlessly from compact tiling window manager panes to ultrawide fullscreen terminals.
- **High-Res Unicode Sextant Album Art:** Renders 24-bit TrueColor album covers using $2 \times 3$ Unicode Sextant subpixel partitioning (`U+1FB00`–`U+1FB3B`) with automatic compact/wide breakpoints.
- **20 FPS Real-Time Audio Spectrum Visualizer:** Smooth logarithmic frequency bar animation (`▂▃▄▅▆▇█`) driven by live PipeWire/PulseAudio FFT (`[LIVE]`) during local playback, with automatic fallback to tempo/harmonic synthesis on remote devices.
- **Progressive Batch Streaming:** Streams large playlists (500+ tracks), Liked Songs, Saved Albums (`◉`), and Favorite Artists (`♪`) in background batches without blocking navigation.
- **Dual-Mode Inline Search (`/`):** Filters the active tracklist live as you type, and searches the full Spotify catalog on `Enter` without intrusive popups.
- **Interactive Device Picker (`d`):** Modal selector to switch active playback between your phone, speakers, and computer on the fly.
- **CJK & Wide-Glyph Aware:** Strict terminal cell-width alignment (`rich.cells`) ensures Japanese, Chinese, Korean, Bengali, and symbol titles never misalign columns or wrap lines.

---

## Prerequisites

- **OS:** Linux, macOS, or Windows (Windows Terminal recommended on Windows)
- **Python** $\ge 3.11$ (installed automatically by the one-line installer via `uv`)
- A **Spotify Premium** account (required by Spotify's Web API for playback control)
- A **Terminal Emulator** with 24-bit TrueColor and Unicode 13+ support (e.g., Ptyxis, Kitty, WezTerm, Ghostty, Alacritty, Foot, iTerm2, Windows Terminal)

---

## Quick Install

Install `vibetune` globally in one command (installs [`uv`](https://docs.astral.sh/uv/) if needed, installs the `vibetune` CLI, and sets up the optional `go-librespot` local audio engine):

### Linux & macOS (`curl`)
```sh
curl -fsSL https://raw.githubusercontent.com/ashrafpy/vibetune/main/install.sh | sh
```

### Windows PowerShell (`irm` / `iex`)
```powershell
irm https://raw.githubusercontent.com/ashrafpy/vibetune/main/install.ps1 | iex
```

> **Installer options:** Set `VIBETUNE_NO_PLAYER=1` to skip installing `go-librespot` (remote-only mode), or `VIBETUNE_REF=<branch-or-tag>` to install a specific branch/release.

### Quick Start After Installing
1. Create a Spotify app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) with Redirect URI `http://127.0.0.1:8888/callback` and **Web API** checked.
2. Save your Spotify API credentials globally:
   ```sh
   vibetune --setup
   ```
3. *(Optional)* Authenticate the local playback engine once:
   ```sh
   vibetune --auth-player
   ```
4. Run VibeTune from any directory:
   ```sh
   vibetune                  # Standalone local playback + Connect remote
   vibetune --remote-only    # Pure Spotify Connect remote mode
   ```

### Platform Support Matrix

| OS | Default Audio Backend | Local Engine (`go-librespot`) | Spectrum Visualizer |
| :--- | :--- | :--- | :--- |
| **Linux** | `pulseaudio` (PipeWire/PulseAudio) or `alsa` | Auto-installed by `install.sh` | Live FFT (`parec`) + synthesized fallback |
| **macOS** | `audio-toolbox` | Installed via `brew install go-librespot` | Tempo & harmonic synthesized |
| **Windows** | `wasapi` | Auto-installed by `install.ps1` | Tempo & harmonic synthesized |

---

## Manual / Developer Setup

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

### 3. Optional: Authenticate Local Playback Engine (`go-librespot`)
For standalone local audio playback directly from VibeTune (enabled by default; gracefully falls back to remote-only mode if not installed):
```bash
# Authenticate go-librespot once via OAuth
uv run vibetune --auth-player
```

### 4. Run from Source
```bash
uv run vibetune                  # Standalone local playback + live FFT visualizer
uv run vibetune --remote-only    # Pure Spotify Connect remote mode
```
On your first run, VibeTune will open your browser to authorize with Spotify and automatically save the token for future sessions.

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
├── .github/workflows/ci.yml      # Cross-platform CI (Linux, macOS, Windows)
├── install.sh                    # One-line curl installer (Linux & macOS)
├── install.ps1                   # One-line PowerShell irm/iex installer (Windows)
├── pyproject.toml                # Project metadata & dependencies (uv / hatchling)
├── product_spec.md               # Product vision, user flows & functional specifications
├── design.md                     # UI/TUI layout, keymap state machine & color tokens
├── src/vibetune/
│   ├── app.py                    # Main Textual App, Device Modal & Input State Machine
│   ├── audio_capture.py          # Live PipeWire/PulseAudio FFT capture (Linux)
│   ├── local_player.py           # Managed go-librespot daemon & REST/WebSocket client
│   ├── main.py                   # CLI entry point (`vibetune`, `--setup`, `--auth-player`)
│   ├── models.py                 # Dataclasses for tracks, library items & playback state
│   ├── paths.py                  # Cross-platform config, cache & binary lookup helpers
│   ├── spotify_client.py         # Spotipy OAuth, device control, batch streaming & search
│   ├── styles.tcss               # Retro Spotify Green (#1DB954) & #121212 stylesheet
│   └── widgets/
│       ├── _helpers.py           # Shared text-formatting utilities (fit_cell)
│       ├── visualizer.py         # 20 FPS logarithmic spectrum visualizer
│       ├── now_playing.py        # Responsive 2x3 Sextant TrueColor album art & controls
│       ├── library_pane.py       # [F1] Library navigation pane
│       └── tracklist_pane.py     # [F2] Tracklist table & inline header search
└── tests/
    ├── conftest.py               # Shared test fixtures and helpers
    ├── test_app.py               # Automated pytest + Textual Pilot test suite
    ├── test_cross_platform.py    # Cross-platform path, CLI, REST & smoke tests
    └── test_local_player.py      # Local playback & FFT spectrum unit/integration tests
```

---

## License

Released under the [MIT License](LICENSE).
