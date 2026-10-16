# VibeTune — Product Specification

## 1. Product Vision & Overview

**VibeTune** is a lightweight, keyboard-driven terminal Spotify Connect remote player designed specifically for Linux tiling window manager environments (e.g., i3, bspwm, sway, Hyprland).

Unlike heavy official or Electron-based desktop clients that consume significant RAM and CPU, VibeTune operates strictly as a **remote control** using the Spotify Web API. It streams track metadata, library content, and album art directly to the terminal, delegating all actual audio decoding and playback to any active Spotify Connect device (such as a smartphone, smart speaker, tablet, or headless daemon like `spotifyd`).

---

## 2. Target Audience & Problem Statement

### 2.1 Target Audience
- **Linux & Tiling Window Manager Power Users:** Developers and sysadmins who work primarily within terminal emulators and want immediate media control without context-switching to browser tabs or bulky GUI apps.
- **Minimalists & Resource-Conscious Users:** Users running resource-constrained hardware (laptops on battery, older machines) where running an Electron or heavy Chromium-based app is undesirable.
- **Audio Enthusiasts with Multi-Device Setups:** Users who stream music on high-fidelity smart speakers, AV receivers, or phones, but want desktop-side control without picking up handheld devices.

### 2.2 Key Problems Solved
| Problem with Existing Players | How VibeTune Solves It |
| :--- | :--- |
| **Heavy Memory Footprint** | Operates as a pure remote terminal interface with zero local audio decoding. |
| **Mouse-Heavy Navigation** | 100% keyboard-navigable with Vim/tmux-inspired bindings (`Tab`, `F1`/`F2`, `/`, `Space`, `n`/`p`, `d`). |
| **Poor Terminal Aesthetics** | Delivers rich retro aesthetics with TrueColor 24-bit $2 \times 3$ Unicode Sextant album art and a 20 FPS frequency-synced visualizer. |
| **Slow Library Loading** | Uses background batch streaming to load massive playlists and library sections progressively without freezing navigation. |

---

## 3. Core Features & Capabilities

### 3.1 Featherweight Spotify Connect Remote
- Communicates directly with the Spotify Web API (`/v1/me/player/*`).
- Does not decode or stream raw audio locally, maintaining sub-second launch times and low CPU/memory overhead.
- Supports volume adjustment (`+` / `-`), seeking (`←` / `→`), play/pause (`Space`), track skipping (`n` / `p`), shuffle toggle (`s`), and repeat modes (`r`).

### 3.2 Spotify Connect Device Picker (`d`)
- Dedicated modal dialog (`DeviceModal`) invoked via the `d` key.
- Discovers and lists all available Spotify Connect endpoints on the local network/account (active speaker highlighted in Spotify Green `#1DB954`).
- Instantly transfers active playback to the chosen device with optimistic feedback.

### 3.3 Two-Deck Retro Terminal UI
- **Top Deck (Media & Visualizer Stage):**
  - **Left (60%):** 20 FPS spectrum visualizer featuring animated logarithmic frequency bars (`▂▃▄▅▆▇█`) synchronized with track tempo and harmonic beat segments.
  - **Right (40%):** High-resolution album cover artwork rendered using Unicode Sextant characters (`U+1FB00`–`U+1FB3B`), paired with track metadata, elapsed/total time scrub bar, and status indicators.
- **Bottom Deck (Interactive Navigation):**
  - **Library Pane (`[F1]`, 30%):** Lists Liked Songs, Daily Mixes, Saved Playlists, Saved Albums (`◉`), and Followed Artists (`♪`).
  - **Tracklist Pane (`[F2]`, 70%):** Table view displaying track numbers, titles, artists, and durations. Features CJK and wide-glyph cell alignment so non-Latin scripts (Japanese, Chinese, Korean, Bengali) never misalign columns.
- **Footer Strip:** Persistent single-row keymap legend showing context-sensitive keyboard commands.

### 3.4 Progressive Batch Streaming
- Asynchronously streams tracks in chunks (50 items per batch) via background worker threads.
- Users can immediately view and navigate the first batch of tracks while remaining items continue to stream in the background without locking the UI.

### 3.5 Dual-Mode Search (`/`)
- **Mode 1 (Live Filter):** Typing in the search input dynamically filters songs in the currently active playlist.
- **Mode 2 (Global Catalog Search):** Pressing `Enter` executes a Spotify catalog search across all tracks, instantly populating the tracklist with global search results.
- Pressing `Esc` discards search results and cleanly restores the previous playlist view.

---

## 4. User Journeys & Interaction Flows

### 4.1 First-Time Setup & Authentication
1. User configures Spotify Developer App credentials in `.env.local`.
2. On first launch (`uv run vibetune`), VibeTune checks for a cached OAuth token in `.spotify_cache`.
3. If no token exists, VibeTune automatically launches the system web browser to the Spotify authorization page.
4. Spotify redirects to the local callback (`http://127.0.0.1:8888/callback`), storing the refreshed OAuth token for seamless subsequent startups.

### 4.2 Playback on Connect Devices
1. User opens VibeTune in a terminal window.
2. If playback is currently idle or on another device, pressing `d` brings up the Device Selector.
3. User selects their target device (e.g., Living Room Speaker, Phone, Echo Dot) with arrow keys and presses `Enter`.
4. Playback transfers seamlessly; album art, track details, and the spectrum visualizer immediately begin animating.

### 4.3 Navigating Libraries & Discovering Tracks
1. Press `F1` or `Tab` to navigate the left Library pane.
2. Browse playlists, saved albums, or followed artists and hit `Enter` to load the tracklist.
3. The first batch of tracks displays immediately; background streaming completes large collections seamlessly.
4. Press `F2` or `Tab` to focus the Tracklist pane, navigate with arrow keys, and press `Enter` to begin playback.
5. Press `/` at any point to search or filter songs on the fly.

---

## 5. System Requirements & Non-Goals

### 5.1 System Requirements
- **Operating System:** Linux (primary), macOS, or Unix-like environments.
- **Python Version:** $\ge 3.11$ (managed via [uv](https://docs.astral.sh/uv/)).
- **Account:** Active Spotify Premium account (required by Spotify Web API for remote playback endpoints).
- **Terminal Emulator:** Terminal supporting 24-bit TrueColor and Unicode 13+ glyphs (e.g., Ptyxis, Kitty, WezTerm, Ghostty, Alacritty, Foot, GNOME Terminal).

### 5.2 Non-Goals & Explicit Boundaries
- **No Local Audio Decoding:** VibeTune will not implement local audio decoding, soundcard interfacing, or proprietary DRM decryption. It is purely a remote control.
- **No Heavy GUI / Mouse Requirement:** While Textual allows mouse clicks, the core product promise is complete, frictionless keyboard control.
- **No Offline Mode:** Requires an active internet connection to communicate with Spotify Web API endpoints.

---

## 6. Future Roadmap
- **Customizable Color Schemes:** User-defined terminal themes (Nord, Gruvbox, Catppuccin, Tokyo Night) via configuration file.
- **Local Audio Loopback Mode:** Optional visualizer mode reading live frequency data from local PulseAudio/PipeWire monitors when a local sink is playing.
- **Smart Queue Management:** Dedicated modal or pane to reorder, add, and remove upcoming tracks in the Spotify playback queue.
- **Global Media Key Integration:** Optional D-Bus / MPRIS2 daemon listener allowing desktop media keys to control VibeTune in the background.
