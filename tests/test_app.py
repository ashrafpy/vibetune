"""Automated unit and Textual Pilot tests for VibeTune TUI."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from PIL import Image
import pytest

from vibetune.app import DeviceSelectorModal, VibeTuneApp
from vibetune.models import LibraryItem, PlaybackState, TrackItem
from vibetune.spotify_client import SpotifyClient
from vibetune.widgets.now_playing import render_sextant_art


class FakeSpotifyClient(SpotifyClient):
    """In-memory mock SpotifyClient for deterministic TUI testing."""

    def __init__(self) -> None:
        super().__init__(sp_client=None)
        self.tracks_liked = [
            TrackItem(
                id="trk_1",
                uri="spotify:track:trk_1",
                title="Midnight City",
                artist="M83",
                album="Hurry Up, We're Dreaming",
                release_year="2011",
                duration_ms=243_000,
            ),
            TrackItem(
                id="trk_2",
                uri="spotify:track:trk_2",
                title="Resonance",
                artist="HOME",
                album="Odyssey",
                release_year="2014",
                duration_ms=212_000,
            ),
            TrackItem(
                id="trk_3",
                uri="spotify:track:trk_3",
                title="Nightcall",
                artist="Kavinsky",
                album="OutRun",
                release_year="2013",
                duration_ms=259_000,
            ),
        ]
        self.tracks_synth = [
            TrackItem(
                id="trk_4",
                uri="spotify:track:trk_4",
                title="Tech Noir",
                artist="GUNSHIP",
                album="GUNSHIP",
                release_year="2015",
                duration_ms=297_000,
                context_uri="spotify:playlist:pl_synth",
            ),
        ]
        self.catalog_results = [
            TrackItem(
                id="cat_1",
                uri="spotify:track:cat_1",
                title="Instant Crush",
                artist="Daft Punk",
                album="Random Access Memories",
                release_year="2013",
                duration_ms=337_000,
            ),
        ]
        self.devices_list: list[dict[str, Any]] = [
            {
                "id": "dev_phone",
                "name": "Pixel 9 (Earbuds)",
                "type": "Smartphone",
                "is_active": True,
                "volume_percent": 75,
            },
            {
                "id": "dev_echo",
                "name": "Ashraful's Echo Dot",
                "type": "Speaker",
                "is_active": False,
                "volume_percent": 50,
            },
        ]
        self.state = PlaybackState(
            is_playing=True,
            track=self.tracks_liked[1],
            progress_ms=102_000,
            volume_percent=75,
            shuffle_state=True,
            repeat_state="context",
            device_id="dev_phone",
            device_name="Pixel 9 (Earbuds)",
            tempo_bpm=110.0,
        )
        self.played_tracks: list[TrackItem] = []
        self.next_calls = 0
        self.prev_calls = 0
        self.search_queries: list[str] = []
        self.transferred_to: list[str] = []

    def get_devices(self) -> list[dict[str, Any]]:
        return list(self.devices_list)

    def transfer_to_device(self, device_id: str, device_name: str = "Spotify Device") -> bool:
        self.transferred_to.append(device_id)
        self.state.device_id = device_id
        self.state.device_name = device_name
        return True

    def get_playback_state(self) -> PlaybackState:
        return self.state

    def get_library_items(self) -> list[LibraryItem]:
        return [
            LibraryItem("liked_songs", "Liked Songs", "liked", 342, None),
            LibraryItem("pl_synth", "Synthwave Radio", "playlist", 80, "spotify:playlist:pl_synth"),
        ]

    def get_library_tracks(self, item: LibraryItem, limit: int = 50) -> list[TrackItem]:
        if item.id == "pl_synth":
            return list(self.tracks_synth)
        return list(self.tracks_liked)

    def iter_library_track_batches(self, item: LibraryItem, batch_size: int = 50):
        yield self.get_library_tracks(item, limit=batch_size)

    def search_tracks(self, query: str, limit: int = 30) -> list[TrackItem]:
        self.search_queries.append(query)
        return list(self.catalog_results)

    def toggle_play_pause(self, state: PlaybackState) -> bool:
        self.state.is_playing = not state.is_playing
        return self.state.is_playing

    def next_track(self, device_id: str | None = None) -> None:
        self.next_calls += 1

    def previous_track(self, device_id: str | None = None) -> None:
        self.prev_calls += 1

    def toggle_shuffle(self, current_shuffle: bool, device_id: str | None = None) -> bool:
        self.state.shuffle_state = not current_shuffle
        return self.state.shuffle_state

    def cycle_repeat(self, current_repeat: str, device_id: str | None = None) -> str:
        order = ["off", "context", "track"]
        self.state.repeat_state = order[(order.index(current_repeat) + 1) % 3]
        return self.state.repeat_state

    def seek_relative(self, current_ms: int, delta_ms: int, duration_ms: int, device_id: str | None = None) -> int:
        self.state.progress_ms = max(0, min(duration_ms, current_ms + delta_ms))
        return self.state.progress_ms

    def adjust_volume(self, current_vol: int, delta: int, device_id: str | None = None) -> int:
        self.state.volume_percent = max(0, min(100, current_vol + delta))
        return self.state.volume_percent

    def play_track(
        self,
        track: TrackItem,
        context_uri: str | None = None,
        fallback_uris: list[str] | None = None,
        device_id: str | None = None,
    ) -> None:
        self.played_tracks.append(track)
        self.state.track = track
        self.state.is_playing = True
        self.state.progress_ms = 0


def test_sextant_album_art_renderer() -> None:
    img = Image.new("RGB", (64, 64), color=(29, 185, 84))
    buf = BytesIO()
    img.save(buf, format="PNG")
    rows = render_sextant_art(buf.getvalue(), width=14, height_rows=7)
    assert len(rows) == 7
    for row in rows:
        assert len(row.plain) == 14


@pytest.mark.asyncio
async def test_navigation_controls_device_modal_and_fullscreen() -> None:
    fake_client = FakeSpotifyClient()
    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    # Test with wide fullscreen size (220 cols) to verify visualizer scales past 48 bands
    async with app.run_test(size=(220, 36)) as pilot:
        await pilot.pause()

        outer = app.query_one("#outer-frame")
        assert outer.border_title == "VibeTune"

        # Spectrum visualizer should scale across the wide 60% pane (> 60 bands)
        assert app.visualizer._active_band_count() > 55

        # Verify initial mount & focus on LibraryPane
        assert app.library_pane.has_focus
        assert len(app.library_pane.items) == 2
        assert len(app.tracklist_pane.displayed_tracks) == 3

        # Press Tab to move focus to TracklistPane, F1 back to LibraryPane
        await pilot.press("tab")
        assert app.tracklist_pane.has_focus
        await pilot.press("f1")
        assert app.library_pane.has_focus

        # Navigate down in LibraryPane to "Synthwave Radio" and press Enter
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert app.tracklist_pane.has_focus
        assert len(app.tracklist_pane.displayed_tracks) == 1
        assert app.tracklist_pane.displayed_tracks[0].title == "Tech Noir"

        # Media hotkeys in Normal Mode (0ms optimistic update)
        await pilot.press("space")
        assert app.playback_state.is_playing is False

        await pilot.press("s")
        assert app.playback_state.shuffle_state is False

        await pilot.press("r")
        assert app.playback_state.repeat_state == "track"

        await pilot.press("+")
        assert app.playback_state.volume_percent == 80

        await pilot.press("right")
        assert app.playback_state.progress_ms >= 107_000

        # Open Device Selector Modal with 'd', select second device ("Ashraful's Echo Dot"), press Enter
        await pilot.press("d")
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert isinstance(app.screen, DeviceSelectorModal)
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, DeviceSelectorModal)
        assert app.playback_state.device_name == "Ashraful's Echo Dot"
        assert fake_client.transferred_to == ["dev_echo"]


@pytest.mark.asyncio
async def test_search_mode_live_filter_and_catalog_search() -> None:
    fake_client = FakeSpotifyClient()
    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    async with app.run_test(size=(100, 28)) as pilot:
        await pilot.pause()

        # Enter search mode with '/'
        await pilot.press("/")
        assert app.search_mode is True
        assert app.tracklist_pane.search_mode is True

        # Typing 'r', 'e', 's' filters live to "Resonance" without triggering Repeat or Shuffle!
        await pilot.press("r", "e", "s")
        assert app.tracklist_pane.search_query == "res"
        assert len(app.tracklist_pane.displayed_tracks) == 1
        assert app.tracklist_pane.displayed_tracks[0].title == "Resonance"

        # Pressing Esc cancels search and restores all 3 tracks
        await pilot.press("escape")
        assert app.search_mode is False
        assert len(app.tracklist_pane.displayed_tracks) == 3

        # Re-enter search mode, type "daft punk", press Enter to query Spotify catalog
        await pilot.press("/")
        for ch in "daft punk":
            await pilot.press("space" if ch == " " else ch)
        assert app.tracklist_pane.search_query == "daft punk"

        await pilot.press("enter")
        await pilot.pause()
        assert fake_client.search_queries == ["daft punk"]
        assert len(app.tracklist_pane.displayed_tracks) == 1
        assert app.tracklist_pane.displayed_tracks[0].title == "Instant Crush"

        # Press Enter again to play the selected catalog result and exit search mode
        await pilot.press("enter")
        await pilot.pause()
        assert app.search_mode is False
        assert len(fake_client.played_tracks) == 1
        assert fake_client.played_tracks[0].title == "Instant Crush"

def test_hour_long_track_duration_format() -> None:
    """TrackItem.duration_formatted handles hour+ durations correctly."""
    # Exactly 1 hour
    track_1h = TrackItem(
        id="t1", uri="spotify:track:t1", title="Long Mix",
        artist="DJ", album="Set", release_year="2024", duration_ms=3_600_000,
    )
    assert track_1h.duration_formatted == "1:00:00"

    # 1 hour, 2 minutes, 3 seconds
    track_long = TrackItem(
        id="t2", uri="spotify:track:t2", title="Podcast Episode",
        artist="Host", album="Show", release_year="2024", duration_ms=3_723_000,
    )
    assert track_long.duration_formatted == "1:02:03"

    # Under 1 hour stays as MM:SS
    track_short = TrackItem(
        id="t3", uri="spotify:track:t3", title="Short Song",
        artist="Band", album="LP", release_year="2024", duration_ms=195_000,
    )
    assert track_short.duration_formatted == "03:15"


class EmptyFakeSpotifyClient(SpotifyClient):
    """Mock SpotifyClient that returns empty collections for edge-case testing."""

    def __init__(self) -> None:
        super().__init__(sp_client=None)
        self.state = PlaybackState()

    def get_devices(self) -> list[dict[str, Any]]:
        return []

    def get_playback_state(self) -> PlaybackState:
        return self.state

    def get_library_items(self) -> list[LibraryItem]:
        return []

    def iter_library_track_batches(self, item: LibraryItem, batch_size: int = 50):
        return iter([])

    def search_tracks(self, query: str, limit: int = 30) -> list[TrackItem]:
        return []


@pytest.mark.asyncio
async def test_empty_library_displays_gracefully() -> None:
    """App launches and renders without crash when the library is empty."""
    fake_client = EmptyFakeSpotifyClient()
    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    async with app.run_test(size=(100, 28)) as pilot:
        await pilot.pause()

        # App should mount and render without errors
        outer = app.query_one("#outer-frame")
        assert outer.border_title == "VibeTune"

        # Library pane should be empty but focused
        assert app.library_pane.has_focus
        assert len(app.library_pane.items) == 0

        # Tracklist should be empty
        assert len(app.tracklist_pane.displayed_tracks) == 0


@pytest.mark.asyncio
async def test_device_modal_with_no_devices() -> None:
    """Device selector modal handles empty device list gracefully."""
    fake_client = EmptyFakeSpotifyClient()
    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    async with app.run_test(size=(100, 28)) as pilot:
        await pilot.pause()

        # Open device modal
        await pilot.press("d")
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert isinstance(app.screen, DeviceSelectorModal)

        # Dismiss it with Escape — should not crash
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DeviceSelectorModal)


@pytest.mark.asyncio
async def test_search_mode_with_empty_tracklist() -> None:
    """Search mode works even when tracklist is empty (catalog search still available)."""
    fake_client = FakeSpotifyClient()
    # Override library to return an empty item
    original_get_library = fake_client.get_library_items
    fake_client.get_library_items = lambda: [
        LibraryItem("empty_pl", "Empty Playlist", "playlist", 0, "spotify:playlist:empty"),
    ]
    fake_client.iter_library_track_batches = lambda item, batch_size=50: iter([])

    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    async with app.run_test(size=(100, 28)) as pilot:
        await pilot.pause()

        # Select the empty playlist
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.tracklist_pane.displayed_tracks) == 0

        # Enter search mode — should not crash on empty list
        await pilot.press("/")
        assert app.search_mode is True

        # Escape back out
        await pilot.press("escape")
        assert app.search_mode is False


@pytest.mark.asyncio
async def test_terminal_resize_preserves_state() -> None:
    """Resizing the terminal preserves playback state and cursor position."""
    fake_client = FakeSpotifyClient()
    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    async with app.run_test(size=(100, 28)) as pilot:
        await pilot.pause()

        # Navigate down in tracklist
        await pilot.press("tab")
        await pilot.press("down")

        # Record state before resize
        playing_before = app.playback_state.is_playing
        track_before = app.playback_state.track

        # Resize to a much smaller terminal
        await pilot.resize_terminal(40, 20)
        await pilot.pause()

        # State should be preserved
        assert app.playback_state.is_playing == playing_before
        assert app.playback_state.track == track_before

        # Resize back to large
        await pilot.resize_terminal(120, 36)
        await pilot.pause()

        # Still intact
        assert app.playback_state.is_playing == playing_before
        assert app.playback_state.track == track_before
