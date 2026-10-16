"""Main Textual TUI Application for VibeTune (Terminal Spotify Remote).

In non-tech terms:
This file is the "conductor of the orchestra" for the visual screen.
- It builds the layout: splits your terminal into the top stage (visualizer and
  album cover) and the bottom stage (library list and song table).
- It listens for your keyboard presses (like pressing Space to pause or 'd' to
  switch speakers).
- It runs a heartbeat timer that refreshes the song progress bar every second.
- It pops up the speaker selection window when you press 'd'.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from rich.cells import cell_len, set_cell_size
from rich.style import Style
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget

from vibetune.models import LibraryItem, PlaybackState, TrackItem
from vibetune.spotify_client import SpotifyClient
from vibetune.widgets.library_pane import LibraryPane
from vibetune.widgets.now_playing import NowPlayingDeck
from vibetune.widgets.tracklist_pane import TracklistPane
from vibetune.widgets.visualizer import SpectrumVisualizer


def _fit_cell(text: str, width: int) -> str:
    """Trim text with an ellipsis (…) so it fits neatly into terminal columns without wrapping."""
    clean = " ".join(text.replace("\xa0", " ").splitlines())
    if width <= 0:
        return ""
    if cell_len(clean) > width:
        if width == 1:
            return "…"
        return set_cell_size(clean, width - 1) + "…"
    return set_cell_size(clean, width)


class DeviceSelectorWidget(Widget):
    """Interactive list widget inside the DeviceSelectorModal.
    
    Non-tech summary:
    This draws the menu of your speakers, phones, and computers on screen,
    letting you use the Up/Down arrow keys to highlight the one you want.
    """

    can_focus = True

    def __init__(
        self,
        devices: list[dict[str, Any]],
        active_device_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._devices = devices
        self._active_device_id = active_device_id
        self._selected_idx = 0
        for idx, dev in enumerate(devices):
            if dev.get("id") == active_device_id or dev.get("is_active"):
                self._selected_idx = idx
                break

    def set_devices(self, devices: list[dict[str, Any]], active_device_id: str | None = None) -> None:
        self._devices = devices
        if active_device_id is not None:
            self._active_device_id = active_device_id
        self._selected_idx = 0
        for idx, dev in enumerate(devices):
            if dev.get("id") == self._active_device_id or dev.get("is_active"):
                self._selected_idx = idx
                break
        self.refresh()

    def move_cursor(self, delta: int) -> None:
        if not self._devices:
            return
        self._selected_idx = max(0, min(len(self._devices) - 1, self._selected_idx + delta))
        self.refresh()

    def get_selected_device(self) -> dict[str, Any] | None:
        if 0 <= self._selected_idx < len(self._devices):
            return self._devices[self._selected_idx]
        return None

    def render(self) -> Text:
        out = Text(no_wrap=True)
        out.append(" Select Spotify Connect Target Device\n", style="bold #FFFFFF")
        out.append(" " + ("─" * 50) + "\n", style="#535353")

        if not self._devices:
            out.append("\n   No active Spotify Connect devices found.\n", style="#B3B3B3")
            out.append("   Open Spotify on your phone or speaker and press [r].\n\n", style="#535353")
        else:
            for idx, dev in enumerate(self._devices):
                is_sel = idx == self._selected_idx
                is_act = bool(dev.get("is_active")) or dev.get("id") == self._active_device_id
                name = str(dev.get("name") or "Spotify Device")
                dtype = str(dev.get("type") or "Device")
                vol = dev.get("volume_percent")
                vol_str = f"{vol}%" if vol is not None else ""

                prefix = " > " if is_sel else "   "
                badge = "● ACTIVE" if is_act else f"  {dtype}"
                row_bg = "#282828" if is_sel else None
                fg = "#1DB954" if (is_sel or is_act) else "#FFFFFF"
                meta_fg = "#1DB954" if is_act else "#B3B3B3"

                line = Text(no_wrap=True)
                line.append(prefix, style=Style(color=fg, bgcolor=row_bg, bold=is_sel))
                line.append(_fit_cell(name, 26) + " ", style=Style(color=fg, bgcolor=row_bg, bold=is_sel or is_act))
                line.append(_fit_cell(badge, 12) + " ", style=Style(color=meta_fg, bgcolor=row_bg))
                line.append(f"{vol_str:>4}", style=Style(color="#B3B3B3", bgcolor=row_bg))
                out.append_text(line)
                out.append("\n")

        out.append(" " + ("─" * 50) + "\n", style="#535353")
        out.append(" [↑/↓]", style="bold #1DB954")
        out.append(" Select │ ", style="#B3B3B3")
        out.append("[Enter]", style="bold #1DB954")
        out.append(" Connect │ ", style="#B3B3B3")
        out.append("[r]", style="bold #1DB954")
        out.append(" Refresh │ ", style="#B3B3B3")
        out.append("[Esc]", style="bold #1DB954")
        out.append(" Close", style="#B3B3B3")
        return out


class DeviceSelectorModal(ModalScreen[dict[str, Any] | None]):
    """Retro modal dialog to pick the active Spotify Connect device.
    
    Non-tech summary:
    When you press 'd', this popup box appears in front of the player,
    listing all your speakers and phones. Selecting one transfers the music there!
    """

    def __init__(
        self,
        spotify_client: SpotifyClient,
        active_device_id: str | None = None,
        initial_devices: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self._spotify = spotify_client
        self._active_device_id = active_device_id
        self._initial_devices = initial_devices or []

    def compose(self) -> ComposeResult:
        with Vertical(id="device-modal") as modal:
            modal.border_title = "📱 SPOTIFY CONNECT DEVICES"
            yield DeviceSelectorWidget(
                self._initial_devices,
                active_device_id=self._active_device_id,
                id="device-list-widget",
            )

    @property
    def selector_widget(self) -> DeviceSelectorWidget:
        return self.query_one("#device-list-widget", DeviceSelectorWidget)

    def on_mount(self) -> None:
        self.selector_widget.focus()
        if not self._initial_devices:
            self.run_worker(self._reload_devices(), exclusive=True)

    async def _reload_devices(self) -> None:
        devices = await asyncio.to_thread(self._spotify.get_devices)
        if self.is_mounted:
            self.selector_widget.set_devices(devices, self._active_device_id)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        key = event.key
        char = event.character

        if key == "escape" or char in ("d", "D", "q"):
            self.dismiss(None)
        elif key in ("up", "k"):
            self.selector_widget.move_cursor(-1)
        elif key in ("down", "j"):
            self.selector_widget.move_cursor(1)
        elif char in ("r", "R"):
            self.run_worker(self._reload_devices(), exclusive=True)
        elif key == "enter":
            self.dismiss(self.selector_widget.get_selected_device())


class RetroFooter(Widget):
    """Single-row persistent keybinding legend and status indicator.
    
    Non-tech summary:
    This is the bottom strip that always shows you which keyboard keys do what
    (e.g., Space to pause, Tab to switch sides, / to search).
    """

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._search_mode: bool = False
        self._status_note: str = ""

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()

    def set_search_mode(self, active: bool) -> None:
        self._search_mode = active
        self.refresh()

    def set_status_note(self, note: str) -> None:
        self._status_note = note
        self.refresh()

    def render(self) -> Text:
        avail_w = self.content_size.width if self.content_size.width > 0 else max(30, self.size.width - 2)
        out = Text(" ", no_wrap=True)
        if self._search_mode:
            legend = [
                ("[a-z]", "Query"),
                ("[↑/↓]", "Select"),
                ("[Enter]", "Spotify Search / Play"),
                ("[Esc]", "Cancel"),
            ]
        else:
            legend = [
                ("[Tab]", "Pane"),
                ("[↑/↓]", "Select"),
                ("[Enter]", "Play"),
                ("[←/→]", "±5s"),
                ("[/]", "Search"),
                ("[Space]", "Pause"),
                ("[d]", "Device"),
                ("[q]", "Quit"),
            ]

        for idx, (key_label, desc) in enumerate(legend):
            out.append(key_label, style="bold #1DB954")
            out.append(f" {desc}", style="#FFFFFF")
            if idx < len(legend) - 1:
                out.append(" │ ", style="#535353")

        if self._status_note:
            out.append("  ── ", style="#535353")
            out.append(self._status_note, style="bold #1DB954")

        if cell_len(out.plain) > avail_w:
            out.truncate(avail_w, overflow="ellipsis")
        return out


class VibeTuneApp(App[None]):
    """Retro 2-Deck Terminal Spotify Remote Player.
    
    Non-tech summary:
    The master app window: organizes the visual components, sets the green & black
    retro theme, listens for your keystrokes, and updates playback state.
    """

    CSS_PATH = "styles.tcss"
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        spotify_client: SpotifyClient | None = None,
        enable_polling: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.spotify = spotify_client or SpotifyClient()
        self._enable_polling = enable_polling
        self.playback_state = PlaybackState()
        self.search_mode = False
        self._active_context_uri: str | None = None
        # Cooldown timestamp so background polls never revert optimistic user toggles
        self._suppress_poll_until: float = 0.0
        # Target volume set by user so hardware speakers (e.g. Echo Dot) that round 50% -> 49% don't drift
        self._user_target_volume: int | None = None

    def compose(self) -> ComposeResult:
        """Build the visual layout of the retro player.
        
        Non-tech summary:
        This builds the 4 main rooms on screen:
        1. Top-left: The bouncing music visualizer.
        2. Top-right: Album art cover, song name, and progress bar.
        3. Bottom-left: Your playlists and saved albums list.
        4. Bottom-right: The table of songs and search bar.
        5. Bottom strip: Keyboard shortcuts cheat sheet.
        """
        with Vertical(id="outer-frame") as frame:
            frame.border_title = "VibeTune"
            with Horizontal(id="top-deck"):
                yield SpectrumVisualizer(id="visualizer-pane")
                yield NowPlayingDeck(id="now-playing-pane")
            with Horizontal(id="bottom-deck"):
                yield LibraryPane(id="library-pane")
                yield TracklistPane(id="tracklist-pane")
            yield RetroFooter(id="retro-footer")

    @property
    def visualizer(self) -> SpectrumVisualizer:
        return self.query_one("#visualizer-pane", SpectrumVisualizer)

    @property
    def now_playing(self) -> NowPlayingDeck:
        return self.query_one("#now-playing-pane", NowPlayingDeck)

    @property
    def library_pane(self) -> LibraryPane:
        return self.query_one("#library-pane", LibraryPane)

    @property
    def tracklist_pane(self) -> TracklistPane:
        return self.query_one("#tracklist-pane", TracklistPane)

    @property
    def retro_footer(self) -> RetroFooter:
        return self.query_one("#retro-footer", RetroFooter)

    async def on_mount(self) -> None:
        """Called automatically right after the window opens on screen.
        
        Starts two clocks:
        1. A fast 20 FPS clock (every 0.05s) to animate the visualizer and smooth the scrub bar.
        2. A slower clock (every 2.0s) to ask Spotify if the song changed.
        """
        self.library_pane.focus()
        # 20 FPS timer for visualizer & smooth progress bar interpolation
        self.set_interval(0.05, self._on_animation_tick)
        if self._enable_polling:
            self.set_interval(2.0, self._poll_playback_worker)
            self.run_worker(self._initial_load(), exclusive=False)

    def _mark_user_action(self, cooldown_sec: float = 2.6) -> None:
        """Suppress background playback polling briefly so optimistic UI updates never bounce."""
        self._suppress_poll_until = time.monotonic() + cooldown_sec

    def _on_animation_tick(self) -> None:
        """Advances visualizer animation frames 20 times per second."""
        if not self.is_mounted:
            return
        try:
            self.visualizer.advance_frame(0.05)
            self.now_playing.advance_progress(50)
        except Exception:
            pass

    async def _initial_load(self) -> None:
        """Fetch playlists and current song immediately upon starting up."""
        await self._load_library()
        await self._refresh_playback_state(force=True)

    def _poll_playback_worker(self) -> None:
        if time.monotonic() < self._suppress_poll_until:
            return
        self.run_worker(self._refresh_playback_state(force=False), exclusive=False)

    async def _refresh_playback_state(self, force: bool = False) -> None:
        """Ask Spotify for current track & progress, then update the screen."""
        if not force and time.monotonic() < self._suppress_poll_until:
            return
        state = await asyncio.to_thread(self.spotify.get_playback_state)
        if not force and time.monotonic() < self._suppress_poll_until:
            return
        # Prevent hardware speakers (e.g. Echo Dot) that round 50% -> 49% from drifting by 1%
        if self._user_target_volume is not None:
            if abs(state.volume_percent - self._user_target_volume) <= 2:
                state.volume_percent = self._user_target_volume
            else:
                self._user_target_volume = None
        self.apply_playback_state(state)
        if self.is_mounted and len(self.library_pane.items) <= 1:
            await self._load_library()

    def apply_playback_state(self, state: PlaybackState) -> None:
        self.playback_state = state
        if not self.is_mounted:
            return
        try:
            self.now_playing.update_state(state)
            playing_id = state.track.id if state.track else None
            self.tracklist_pane.set_playing_track(playing_id)

            segments = None
            if state.track:
                _, segments = self.spotify.get_audio_analysis(
                    state.track.id, state.track.duration_ms
                )
            self.visualizer.set_playback_context(
                is_playing=state.is_playing,
                progress_ms=state.progress_ms,
                tempo_bpm=state.tempo_bpm,
                segments=segments,
            )
        except Exception:
            pass

    async def _load_library(self) -> None:
        items = await asyncio.to_thread(self.spotify.get_library_items)
        if not self.is_mounted or not items:
            return
        self.library_pane.set_items(items)
        if not self.tracklist_pane.displayed_tracks:
            first = items[0]
            self.library_pane.set_active_item(first.id)
            self._active_context_uri = first.uri
            await self._stream_library_item_tracks(first)

    @on(LibraryPane.ItemSelected)
    async def _on_library_item_selected(self, event: LibraryPane.ItemSelected) -> None:
        self._active_context_uri = event.item.uri
        self.tracklist_pane.focus()
        self.run_worker(
            self._stream_library_item_tracks(event.item),
            group="track_loader",
            exclusive=True,
        )

    async def _stream_library_item_tracks(self, item: LibraryItem) -> None:
        """Stream all tracks of `item` in batches so large playlists (e.g. 590 tracks) load completely."""
        self.retro_footer.set_status_note(f"Loading {item.name}…")
        iterator = await asyncio.to_thread(self.spotify.iter_library_track_batches, item)
        total_loaded = 0
        first_batch = True

        while True:
            batch = await asyncio.to_thread(lambda: next(iterator, None))
            if not self.is_mounted or batch is None:
                break
            total_loaded += len(batch)
            if first_batch:
                self.tracklist_pane.set_tracklist(item.name, batch)
                first_batch = False
            else:
                self.tracklist_pane.append_tracks(item.name, batch)

            target_str = f"/{item.track_count}" if item.track_count else ""
            self.retro_footer.set_status_note(
                f"Loading {item.name}… ({total_loaded}{target_str})"
            )
            await asyncio.sleep(0.02)

        if first_batch and self.is_mounted:
            self.tracklist_pane.set_tracklist(item.name, [])
        if self.is_mounted:
            self.retro_footer.set_status_note(f"Loaded {total_loaded} tracks")

    @on(TracklistPane.CatalogSearchRequested)
    async def _on_catalog_search_requested(
        self, event: TracklistPane.CatalogSearchRequested
    ) -> None:
        self.retro_footer.set_status_note(f'Searching Spotify for "{event.query}"…')
        results = await asyncio.to_thread(self.spotify.search_tracks, event.query)
        if not self.is_mounted:
            return
        self.tracklist_pane.set_catalog_search_results(event.query, results)
        self.retro_footer.set_status_note(f'Found {len(results)} tracks for "{event.query}"')

    @on(TracklistPane.TrackActivated)
    async def _on_track_activated(self, event: TracklistPane.TrackActivated) -> None:
        self.search_mode = False
        self.retro_footer.set_search_mode(False)

        track = event.track
        uris = [t.uri for t in event.all_tracks]
        self._mark_user_action(3.0)
        self.playback_state.is_playing = True
        self.playback_state.track = track
        self.playback_state.progress_ms = 0
        self.apply_playback_state(self.playback_state)
        self.retro_footer.set_status_note(f"Playing: {track.title}")

        await asyncio.to_thread(
            self.spotify.play_track,
            track,
            track.context_uri or self._active_context_uri,
            uris,
            self.playback_state.device_id,
        )

    def on_key(self, event: events.Key) -> None:
        """Centralized Two-Mode State Machine (Normal Mode vs Search Mode)."""
        if isinstance(self.screen, ModalScreen):
            return
        if self.search_mode:
            self._handle_search_mode_key(event)
        else:
            self._handle_normal_mode_key(event)

    def _handle_search_mode_key(self, event: events.Key) -> None:
        """Handle keyboard typing when in Search Mode ('/' key active).
        
        Non-tech summary:
        When searching, typing letters (a-z, space) narrows down songs in real time.
        Pressing Enter searches Spotify's entire catalog or plays the song.
        Pressing Escape cancels the search and brings back your previous playlist.
        """
        key = event.key
        event.stop()
        event.prevent_default()

        if key == "escape":
            self.search_mode = False
            self.tracklist_pane.exit_search_mode(restore_base=True)
            self.retro_footer.set_search_mode(False)
            self.retro_footer.set_status_note("")
        elif key == "enter":
            self.tracklist_pane.handle_enter()
            if not self.tracklist_pane.search_mode:
                self.search_mode = False
                self.retro_footer.set_search_mode(False)
        elif key == "backspace":
            self.tracklist_pane.backspace_search_char()
        elif key == "left":
            self.tracklist_pane.move_search_cursor(-1)
        elif key == "right":
            self.tracklist_pane.move_search_cursor(1)
        elif key == "up":
            self.tracklist_pane.move_cursor(-1)
        elif key == "down":
            self.tracklist_pane.move_cursor(1)
        elif key == "space":
            self.tracklist_pane.append_search_char(" ")
        elif event.character and len(event.character) == 1 and event.character.isprintable():
            self.tracklist_pane.append_search_char(event.character)

    def _handle_normal_mode_key(self, event: events.Key) -> None:
        """Handle standard hotkeys for browsing and media playback.
        
        Non-tech summary:
        - Tab / F1 / F2: Switch between the playlist menu and the song table.
        - Up / Down: Move up and down the list.
        - Space: Play or pause immediately.
        - n / p: Skip forward or backward.
        - s / r: Toggle shuffle or repeat.
        - + / -: Turn volume up or down.
        - d: Pop up the speaker selector.
        - q: Quit the application.
        """
        key = event.key
        char = event.character

        if key in ("tab", "shift+tab"):
            event.stop()
            event.prevent_default()
            if self.library_pane.has_focus:
                self.tracklist_pane.focus()
            else:
                self.library_pane.focus()
            return

        if key == "f1":
            event.stop()
            self.library_pane.focus()
            return

        if key == "f2":
            event.stop()
            self.tracklist_pane.focus()
            return

        if char == "/" or key == "slash":
            event.stop()
            event.prevent_default()
            self.search_mode = True
            self.tracklist_pane.focus()
            self.tracklist_pane.enter_search_mode()
            self.retro_footer.set_search_mode(True)
            return

        if char == "q":
            event.stop()
            self.exit()
            return

        if key == "up":
            event.stop()
            if self.library_pane.has_focus:
                self.library_pane.move_cursor(-1)
            else:
                self.tracklist_pane.move_cursor(-1)
            return

        if key == "down":
            event.stop()
            if self.library_pane.has_focus:
                self.library_pane.move_cursor(1)
            else:
                self.tracklist_pane.move_cursor(1)
            return

        if key == "enter":
            event.stop()
            if self.library_pane.has_focus:
                self.library_pane.activate_selected()
            else:
                self.tracklist_pane.handle_enter()
            return

        # Media hotkeys: apply instant optimistic UI update (0ms lag) + cooldown lock
        if key == "space" or char == " ":
            event.stop()
            self._mark_user_action()
            prior_state = PlaybackState(**self.playback_state.__dict__)
            self.playback_state.is_playing = not self.playback_state.is_playing
            self.apply_playback_state(self.playback_state)
            self.run_worker(self._toggle_play_pause(prior_state), group="cmd_play", exclusive=True)
            return

        if char == "n":
            event.stop()
            self._mark_user_action(1.5)
            self.retro_footer.set_status_note("⏭ Next track")
            self.run_worker(self._skip_next(), group="cmd_skip", exclusive=True)
            return

        if char == "p":
            event.stop()
            self._mark_user_action(1.5)
            self.retro_footer.set_status_note("⏮ Previous track")
            self.run_worker(self._skip_previous(), group="cmd_skip", exclusive=True)
            return

        if char == "s":
            event.stop()
            self._mark_user_action()
            prior_shuf = self.playback_state.shuffle_state
            self.playback_state.shuffle_state = not prior_shuf
            self.apply_playback_state(self.playback_state)
            self.retro_footer.set_status_note(f"Shuffle: {self.playback_state.shuffle_label}")
            self.run_worker(self._toggle_shuffle(prior_shuf), group="cmd_shuf", exclusive=True)
            return

        if char == "r":
            event.stop()
            self._mark_user_action()
            order = ["off", "context", "track"]
            try:
                next_idx = (order.index(self.playback_state.repeat_state) + 1) % 3
            except ValueError:
                next_idx = 0
            prior_rep = self.playback_state.repeat_state
            self.playback_state.repeat_state = order[next_idx]
            self.apply_playback_state(self.playback_state)
            self.retro_footer.set_status_note(f"Repeat: {self.playback_state.repeat_label}")
            self.run_worker(self._cycle_repeat(prior_rep), group="cmd_rep", exclusive=True)
            return

        if key == "left":
            event.stop()
            self._mark_user_action()
            dur = self.playback_state.track.duration_ms if self.playback_state.track else 300_000
            prior_pos = self.playback_state.progress_ms
            self.playback_state.progress_ms = max(0, min(dur, prior_pos - 5000))
            self.apply_playback_state(self.playback_state)
            self.run_worker(self._seek_to(self.playback_state.progress_ms, dur), group="cmd_seek", exclusive=True)
            return

        if key == "right":
            event.stop()
            self._mark_user_action()
            dur = self.playback_state.track.duration_ms if self.playback_state.track else 300_000
            prior_pos = self.playback_state.progress_ms
            self.playback_state.progress_ms = max(0, min(dur, prior_pos + 5000))
            self.apply_playback_state(self.playback_state)
            self.run_worker(self._seek_to(self.playback_state.progress_ms, dur), group="cmd_seek", exclusive=True)
            return

        if char in ("+", "="):
            event.stop()
            self._mark_user_action(4.0)
            base_vol = (
                self._user_target_volume
                if self._user_target_volume is not None
                else round(self.playback_state.volume_percent / 5) * 5
            )
            target_vol = min(100, base_vol + 5)
            self._user_target_volume = target_vol
            self.playback_state.volume_percent = target_vol
            self.apply_playback_state(self.playback_state)
            self.retro_footer.set_status_note(f"Volume: {target_vol}%")
            self.run_worker(self._set_volume(target_vol), group="cmd_vol", exclusive=True)
            return

        if char in ("-", "_"):
            event.stop()
            self._mark_user_action(4.0)
            base_vol = (
                self._user_target_volume
                if self._user_target_volume is not None
                else round(self.playback_state.volume_percent / 5) * 5
            )
            target_vol = max(0, base_vol - 5)
            self._user_target_volume = target_vol
            self.playback_state.volume_percent = target_vol
            self.apply_playback_state(self.playback_state)
            self.retro_footer.set_status_note(f"Volume: {target_vol}%")
            self.run_worker(self._set_volume(target_vol), group="cmd_vol", exclusive=True)
            return

        if char in ("d", "D"):
            event.stop()
            self.open_device_selector()
            return

    def open_device_selector(self, initial_devices: list[dict[str, Any]] | None = None) -> None:
        """Push the modal dialog allowing the user to pick a Spotify Connect device."""
        modal = DeviceSelectorModal(
            self.spotify,
            active_device_id=self.playback_state.device_id,
            initial_devices=initial_devices,
        )
        self.push_screen(modal, self._on_device_selected)

    def _on_device_selected(self, chosen: dict[str, Any] | None) -> None:
        if not chosen or not chosen.get("id"):
            return
        dev_id = str(chosen["id"])
        dev_name = str(chosen.get("name") or "Spotify Device")
        self._mark_user_action(3.0)
        self.playback_state.device_id = dev_id
        self.playback_state.device_name = dev_name
        if chosen.get("volume_percent") is not None:
            self.playback_state.volume_percent = int(chosen["volume_percent"])
        self.apply_playback_state(self.playback_state)
        self.retro_footer.set_status_note(f"Connected: {dev_name}")
        self.run_worker(
            asyncio.to_thread(self.spotify.transfer_to_device, dev_id, dev_name),
            group="cmd_device",
            exclusive=True,
        )

    async def _toggle_play_pause(self, prior_state: PlaybackState) -> None:
        await asyncio.to_thread(self.spotify.toggle_play_pause, prior_state)

    async def _skip_next(self) -> None:
        await asyncio.to_thread(self.spotify.next_track, self.playback_state.device_id)
        await asyncio.sleep(0.45)
        await self._refresh_playback_state(force=True)

    async def _skip_previous(self) -> None:
        await asyncio.to_thread(self.spotify.previous_track, self.playback_state.device_id)
        await asyncio.sleep(0.45)
        await self._refresh_playback_state(force=True)

    async def _toggle_shuffle(self, prior_shuf: bool) -> None:
        await asyncio.to_thread(
            self.spotify.toggle_shuffle,
            prior_shuf,
            self.playback_state.device_id,
        )

    async def _cycle_repeat(self, prior_rep: str) -> None:
        await asyncio.to_thread(
            self.spotify.cycle_repeat,
            prior_rep,
            self.playback_state.device_id,
        )

    async def _seek_to(self, target_ms: int, dur: int) -> None:
        await asyncio.to_thread(
            self.spotify.seek_relative,
            target_ms,
            0,
            dur,
            self.playback_state.device_id,
        )

    async def _set_volume(self, target_vol: int) -> None:
        await asyncio.to_thread(
            self.spotify.adjust_volume,
            target_vol,
            0,
            self.playback_state.device_id,
        )
