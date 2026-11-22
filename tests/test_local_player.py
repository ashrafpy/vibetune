"""Unit and integration tests for VibeTune local playback (`go-librespot`) and live FFT spectrum."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import yaml

from vibetune.app import DeviceSelectorModal, VibeTuneApp
from vibetune.audio_capture import compute_bands_from_samples
from vibetune.local_player import (
    LocalPlayerConfig,
    LocalPlayerDaemon,
    status_to_playback_state,
)
from vibetune.models import PlaybackState, TrackItem
from vibetune.widgets.visualizer import SpectrumVisualizer
from test_app import FakeSpotifyClient


def test_local_player_config_yaml_generation(tmp_path: Path) -> None:
    cfg = LocalPlayerConfig(
        device_name="VibeTune Test",
        bitrate=320,
        audio_backend="pulseaudio",
        api_port=3679,
        config_dir=tmp_path,
    )
    daemon = LocalPlayerDaemon(config=cfg)
    path = daemon.write_config(interactive_auth=False)
    assert path == tmp_path / "config.yml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["device_name"] == "VibeTune Test"
    assert loaded["bitrate"] == 320
    assert loaded["audio_backend"] == "pulseaudio"
    assert loaded["server"]["enabled"] is True
    assert loaded["server"]["port"] == 3679
    assert "credentials" not in loaded

    daemon.write_config(interactive_auth=True)
    loaded_auth = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded_auth["credentials"]["type"] == "interactive"


def test_status_to_playback_state_conversion() -> None:
    status = {
        "device_id": "local_dev_1",
        "device_name": "VibeTune",
        "paused": False,
        "stopped": False,
        "volume": 32,
        "volume_steps": 64,
        "shuffle_context": True,
        "repeat_context": True,
        "repeat_track": False,
        "context_uri": "spotify:playlist:pl_1",
        "track": {
            "uri": "spotify:track:abc123",
            "name": "Nightcall",
            "artist_names": ["Kavinsky"],
            "album_name": "OutRun",
            "release_date": "2013-02-22",
            "duration": 258000,
            "position": 45000,
            "album_cover_url": "https://example.com/art.jpg",
        },
    }
    state = status_to_playback_state(status)
    assert state.is_local_device is True
    assert state.is_playing is True
    assert state.supports_volume is True
    assert state.volume_percent == 50
    assert state.shuffle_state is True
    assert state.repeat_state == "context"
    assert state.progress_ms == 45000
    assert state.track is not None
    assert state.track.id == "abc123"
    assert state.track.title == "Nightcall"
    assert state.track.artist == "Kavinsky"
    assert state.track.release_year == "2013"


@pytest.mark.asyncio
async def test_local_daemon_missing_binary_fallback(tmp_path: Path) -> None:
    cfg = LocalPlayerConfig(config_dir=tmp_path)
    daemon = LocalPlayerDaemon(config=cfg)
    daemon.client.is_api_reachable = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with patch("vibetune.local_player.find_go_librespot_binary", return_value=None):
        ok = await daemon.start(timeout_sec=0.5)

    assert ok is False
    assert daemon.is_running is False
    assert daemon.last_error is not None
    assert "go-librespot" in daemon.last_error
    await daemon.stop()


@pytest.mark.asyncio
async def test_local_daemon_start_and_clean_stop(tmp_path: Path) -> None:
    cfg = LocalPlayerConfig(config_dir=tmp_path)
    daemon = LocalPlayerDaemon(config=cfg)

    fake_proc = MagicMock()
    fake_proc.returncode = None
    fake_proc.terminate = MagicMock()
    fake_proc.kill = MagicMock()
    fake_proc.wait = AsyncMock(return_value=0)

    daemon.client.is_api_reachable = AsyncMock(return_value=False)  # type: ignore[method-assign]
    daemon.client.get_status = AsyncMock(return_value={"paused": True})  # type: ignore[method-assign]

    with (
        patch("vibetune.local_player.find_go_librespot_binary", return_value=Path("/usr/bin/go-librespot")),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)),
    ):
        ok = await daemon.start(timeout_sec=1.0)
        assert ok is True
        assert daemon.is_running is True

        await daemon.stop()
        assert daemon.is_running is False
        fake_proc.terminate.assert_called_once()


def test_fft_compute_bands_distinguishes_bass_and_treble() -> None:
    sample_rate = 44100
    t = np.arange(2048, dtype=np.float32) / sample_rate

    bass_wave = 0.8 * np.sin(2.0 * np.pi * 120.0 * t).astype(np.float32)
    treble_wave = 0.8 * np.sin(2.0 * np.pi * 8000.0 * t).astype(np.float32)

    bass_bands = compute_bands_from_samples(bass_wave, num_bands=24, sample_rate=sample_rate)
    treble_bands = compute_bands_from_samples(treble_wave, num_bands=24, sample_rate=sample_rate)

    assert len(bass_bands) == 24
    assert len(treble_bands) == 24
    # Bass energy should dominate the lower third of bands
    assert max(bass_bands[:8]) > 0.6
    assert max(bass_bands[:8]) > max(bass_bands[16:]) + 0.3
    # Treble energy should dominate the upper third of bands
    assert max(treble_bands[16:]) > 0.6
    assert max(treble_bands[16:]) > max(treble_bands[:8]) + 0.3


class FakeLiveSpectrum:
    """In-memory FFT spectrum provider for testing Visualizer & App integration."""

    def __init__(self, bands_value: float = 0.75) -> None:
        self.bands_value = bands_value
        self.is_running = False
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> bool:
        self.start_calls += 1
        self.is_running = True
        return True

    def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False

    def get_bands(self, num_bands: int) -> list[float] | None:
        if not self.is_running:
            return None
        return [self.bands_value] * num_bands


def test_visualizer_live_fft_mode_badge_and_fallback() -> None:
    viz = SpectrumVisualizer()
    provider = FakeLiveSpectrum(bands_value=0.8)
    provider.start()

    viz.set_live_spectrum_provider(provider)
    viz.set_live_mode(True)
    viz.set_playback_context(is_playing=True, progress_ms=5000, tempo_bpm=120.0)
    viz.advance_frame(0.05)

    rendered_live = viz.render().plain
    assert "[LIVE]" in rendered_live

    viz.set_live_mode(False)
    viz.advance_frame(0.05)
    rendered_synth = viz.render().plain
    assert "[LIVE]" not in rendered_synth


class FakeLocalClient:
    """In-memory mock of LocalPlayerClient for VibeTuneApp integration tests."""

    def __init__(self, state: PlaybackState) -> None:
        self.state = state
        self.calls: list[tuple[str, Any]] = []

    async def get_playback_state(self) -> PlaybackState | None:
        return self.state

    async def play(self, uri: str, skip_to_uri: str | None = None, paused: bool = False) -> bool:
        self.calls.append(("play", (uri, skip_to_uri)))
        self.state.is_playing = not paused
        return True

    async def pause(self) -> bool:
        self.calls.append(("pause", None))
        self.state.is_playing = False
        return True

    async def resume(self) -> bool:
        self.calls.append(("resume", None))
        self.state.is_playing = True
        return True

    async def next_track(self) -> bool:
        self.calls.append(("next", None))
        return True

    async def previous_track(self) -> bool:
        self.calls.append(("prev", None))
        return True

    async def seek(self, position_ms: int, relative: bool = False) -> bool:
        self.calls.append(("seek", position_ms))
        self.state.progress_ms = position_ms
        return True

    async def set_volume(self, volume_percent: int) -> bool:
        self.calls.append(("volume", volume_percent))
        self.state.volume_percent = volume_percent
        return True

    async def set_shuffle(self, enabled: bool) -> bool:
        self.calls.append(("shuffle", enabled))
        self.state.shuffle_state = enabled
        return True

    async def set_repeat(self, repeat_state: str) -> bool:
        self.calls.append(("repeat", repeat_state))
        self.state.repeat_state = repeat_state  # type: ignore[assignment]
        return True

    async def iter_events(self) -> AsyncIterator[dict[str, Any]]:
        if False:
            yield {}
        await asyncio.sleep(60)

    async def aclose(self) -> None:
        return None


class FakeLocalDaemon:
    """In-memory mock of LocalPlayerDaemon for VibeTuneApp integration tests."""

    def __init__(self, state: PlaybackState, should_start: bool = True) -> None:
        self.config = LocalPlayerConfig(device_name="VibeTune")
        self.client = FakeLocalClient(state)
        self.should_start = should_start
        self.is_running = False
        self.stop_calls = 0
        self.last_error: str | None = (
            None if should_start else "go-librespot not found (running in remote-only mode)"
        )

    async def start(self, timeout_sec: float = 5.0) -> bool:
        if not self.should_start:
            return False
        self.is_running = True
        return True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False


@pytest.mark.asyncio
async def test_vibetune_app_local_playback_routing_and_device_switch() -> None:
    fake_spotify = FakeSpotifyClient()
    fake_spotify.devices_list = [
        {
            "id": "vibetune_local",
            "name": "VibeTune",
            "type": "Computer",
            "is_active": True,
            "supports_volume": True,
            "volume_percent": 75,
        },
        {
            "id": "dev_echo",
            "name": "Living Room Echo Dot",
            "type": "Speaker",
            "is_active": False,
            "supports_volume": True,
            "volume_percent": 50,
        },
    ]

    local_track = TrackItem(
        id="trk_local",
        uri="spotify:track:trk_local",
        title="Resonance",
        artist="HOME",
        album="Odyssey",
        release_year="2014",
        duration_ms=212_000,
    )
    local_state = PlaybackState(
        is_playing=True,
        track=local_track,
        progress_ms=30_000,
        volume_percent=75,
        supports_volume=True,
        device_id="vibetune_local",
        device_name="VibeTune",
        is_local_device=True,
    )
    fake_daemon = FakeLocalDaemon(local_state, should_start=True)
    fake_fft = FakeLiveSpectrum()

    app = VibeTuneApp(
        spotify_client=fake_spotify,
        enable_polling=True,
        local_player=fake_daemon,  # type: ignore[arg-type]
        audio_spectrum=fake_fft,  # type: ignore[arg-type]
    )

    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()

        # Local engine booted, active, and live FFT capture started
        assert app._local_engine_ready is True
        assert app.playback_state.is_local_device is True
        assert fake_fft.is_running is True

        # Press Space -> routes to local client pause()
        await pilot.press("space")
        await pilot.pause()
        assert ("pause", None) in fake_daemon.client.calls

        # Press '+' -> routes to local client set_volume(80)
        await pilot.press("+")
        await pilot.pause()
        assert ("volume", 80) in fake_daemon.client.calls

        # Switch to remote Echo Dot via 'd' -> disables local mode and stops live FFT
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, DeviceSelectorModal)
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        assert app.playback_state.device_name == "Living Room Echo Dot"
        assert app.playback_state.is_local_device is False
        assert fake_fft.is_running is False
        assert "dev_echo" in fake_spotify.transferred_to

    # Clean shutdown stops local daemon
    assert fake_daemon.stop_calls >= 1


@pytest.mark.asyncio
async def test_vibetune_app_graceful_fallback_when_local_engine_missing() -> None:
    fake_spotify = FakeSpotifyClient()
    fake_daemon = FakeLocalDaemon(PlaybackState(), should_start=False)

    app = VibeTuneApp(
        spotify_client=fake_spotify,
        enable_polling=True,
        local_player=fake_daemon,  # type: ignore[arg-type]
    )

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert app._local_engine_ready is False
        assert app.playback_state.is_local_device is False
        assert "go-librespot" in app.retro_footer._status_note
