"""Cross-platform path, CLI, local REST client, and installer/build smoke tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from vibetune.app import VibeTuneApp
from vibetune.audio_capture import LiveAudioSpectrum
from vibetune.local_player import (
    LocalPlayerClient,
    LocalPlayerConfig,
    find_go_librespot_binary,
)
from vibetune.main import build_parser, run_setup
from vibetune.paths import (
    default_audio_backend,
    get_config_dir,
    get_env_file_path,
    get_player_config_dir,
    get_spotify_cache_path,
    go_librespot_binary_name,
    go_librespot_install_hint,
    go_librespot_search_paths,
)
from vibetune.spotify_client import SpotifyClient
from test_app import FakeSpotifyClient


def test_cross_platform_paths_and_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VIBETUNE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("VIBETUNE_PLAYER_BIN", raising=False)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # Linux defaults
    assert get_config_dir("linux") == fake_home / ".config" / "vibetune"
    assert get_player_config_dir("linux") == fake_home / ".config" / "vibetune" / "player"
    assert get_env_file_path("linux") == fake_home / ".config" / "vibetune" / ".env"
    assert default_audio_backend("linux") == "pulseaudio"
    assert go_librespot_binary_name("linux") == "go-librespot"
    assert "curl" in go_librespot_install_hint("linux").lower()

    # macOS defaults (Application Support when no legacy ~/.config/vibetune exists)
    assert get_config_dir("darwin") == fake_home / "Library" / "Application Support" / "vibetune"
    assert default_audio_backend("darwin") == "audio-toolbox"
    assert go_librespot_binary_name("darwin") == "go-librespot"
    assert "brew install go-librespot" in go_librespot_install_hint("darwin")
    darwin_paths = go_librespot_search_paths("darwin")
    assert Path("/opt/homebrew/bin/go-librespot") in darwin_paths

    # Windows defaults
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert get_config_dir("win32") == tmp_path / "Roaming" / "vibetune"
    assert default_audio_backend("win32") == "wasapi"
    assert go_librespot_binary_name("win32") == "go-librespot.exe"
    assert "powershell" in go_librespot_install_hint("win32").lower()
    win_paths = go_librespot_search_paths("win32")
    assert (tmp_path / "Local" / "vibetune" / "bin" / "go-librespot.exe") in win_paths

    # XDG_CONFIG_HOME & VIBETUNE_CONFIG_DIR overrides
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert get_config_dir("linux") == tmp_path / "xdg" / "vibetune"
    assert get_config_dir("darwin") == tmp_path / "xdg" / "vibetune"

    monkeypatch.setenv("VIBETUNE_CONFIG_DIR", str(tmp_path / "custom_cfg"))
    assert get_config_dir("linux") == tmp_path / "custom_cfg"
    assert get_config_dir("win32") == tmp_path / "custom_cfg"


def test_spotify_cache_path_prefers_local_checkout_else_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIBETUNE_CONFIG_DIR", str(tmp_path / "cfg"))

    empty_cwd = tmp_path / "anywhere"
    empty_cwd.mkdir()
    assert get_spotify_cache_path(cwd=empty_cwd) == tmp_path / "cfg" / "spotify_cache"

    repo_cwd = tmp_path / "repo"
    repo_cwd.mkdir()
    local_cache = repo_cwd / ".spotify_cache"
    local_cache.write_text("{}", encoding="utf-8")
    assert get_spotify_cache_path(cwd=repo_cwd) == local_cache


def test_find_go_librespot_binary_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VIBETUNE_PLAYER_BIN", raising=False)
    monkeypatch.setenv("VIBETUNE_CONFIG_DIR", str(tmp_path / "cfg"))

    # 1. Explicit VIBETUNE_PLAYER_BIN override
    override_bin = tmp_path / "custom-player"
    override_bin.write_text("bin", encoding="utf-8")
    monkeypatch.setenv("VIBETUNE_PLAYER_BIN", str(override_bin))
    assert find_go_librespot_binary("linux") == override_bin
    monkeypatch.delenv("VIBETUNE_PLAYER_BIN", raising=False)

    # 2. Found on PATH
    with patch("shutil.which", return_value="/usr/local/bin/go-librespot"):
        assert find_go_librespot_binary("linux") == Path("/usr/local/bin/go-librespot")

    # 3. Windows .exe fallback under %LOCALAPPDATA%\vibetune\bin
    win_local = tmp_path / "WinLocal"
    win_exe = win_local / "vibetune" / "bin" / "go-librespot.exe"
    win_exe.parent.mkdir(parents=True)
    win_exe.write_text("exe", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(win_local))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")

    with patch("shutil.which", return_value=None):
        assert find_go_librespot_binary("win32") == win_exe


@pytest.mark.parametrize(
    "backend",
    ["pulseaudio", "alsa", "audio-toolbox", "wasapi", "pipe"],
)
def test_local_player_config_accepts_all_platform_backends(
    tmp_path: Path, backend: str
) -> None:
    cfg = LocalPlayerConfig(audio_backend=backend, config_dir=tmp_path)
    yaml_dict = cfg.to_yaml_dict()
    assert yaml_dict["audio_backend"] == backend
    assert yaml_dict["server"]["port"] == 3678


@pytest.mark.asyncio
async def test_local_player_client_rest_endpoints() -> None:
    recorded: list[tuple[str, str, dict[str, object] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        recorded.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path == "/status":
            return httpx.Response(
                200,
                json={
                    "device_id": "vt_dev",
                    "device_name": "VibeTune",
                    "paused": False,
                    "stopped": False,
                    "volume": 80,
                    "volume_steps": 100,
                    "shuffle_context": False,
                    "repeat_context": False,
                    "repeat_track": False,
                    "track": {
                        "uri": "spotify:track:xyz",
                        "name": "Midnight City",
                        "artist_names": ["M83"],
                        "album_name": "Hurry Up",
                        "release_date": "2011-10-18",
                        "duration": 243000,
                        "position": 12000,
                    },
                },
            )
        return httpx.Response(200, json={})

    client = LocalPlayerClient(LocalPlayerConfig())
    client._http = httpx.AsyncClient(
        base_url="http://127.0.0.1:3678",
        transport=httpx.MockTransport(handler),
    )

    try:
        assert await client.is_api_reachable() is True
        state = await client.get_playback_state()
        assert state is not None
        assert state.is_playing is True
        assert state.track is not None
        assert state.track.title == "Midnight City"
        assert state.volume_percent == 80

        assert await client.play("spotify:playlist:1", skip_to_uri="spotify:track:xyz") is True
        assert await client.pause() is True
        assert await client.resume() is True
        assert await client.playpause() is True
        assert await client.next_track() is True
        assert await client.previous_track() is True
        assert await client.seek(15000, relative=False) is True
        assert await client.set_volume(150) is True  # clamped to 100
        assert await client.set_shuffle(True) is True
        assert await client.set_repeat("track") is True
        assert await client.set_repeat("context") is True
        assert await client.set_repeat("off") is True
    finally:
        await client.aclose()

    assert ("POST", "/player/play", {"uri": "spotify:playlist:1", "paused": False, "skip_to_uri": "spotify:track:xyz"}) in recorded
    assert ("POST", "/player/volume", {"volume": 100, "relative": False}) in recorded
    assert ("POST", "/player/seek", {"position": 15000, "relative": False}) in recorded
    assert ("POST", "/player/shuffle", {"shuffle_context": True}) in recorded
    assert ("POST", "/player/repeat_track", {"repeat_track": True}) in recorded
    assert ("POST", "/player/repeat_context", {"repeat_context": True}) in recorded


def test_spotify_client_loads_env_from_global_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"):
        monkeypatch.delenv(key, raising=False)

    cfg_dir = tmp_path / "global_cfg"
    cfg_dir.mkdir()
    (cfg_dir / ".env").write_text(
        "SPOTIPY_CLIENT_ID=global_id_123\n"
        "SPOTIPY_CLIENT_SECRET=global_secret_456\n"
        "SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VIBETUNE_CONFIG_DIR", str(cfg_dir))

    work_dir = tmp_path / "random_workdir"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    client = SpotifyClient()
    assert client.sp is not None or client.auth_error is None
    import os

    assert os.environ.get("SPOTIPY_CLIENT_ID") == "global_id_123"
    assert os.environ.get("SPOTIPY_CLIENT_SECRET") == "global_secret_456"


def test_cli_parser_and_setup_wizard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.audio_backend == "auto"
    assert args.remote_only is False
    assert args.setup is False

    args_win = parser.parse_args(["--audio-backend", "wasapi", "--remote-only"])
    assert args_win.audio_backend == "wasapi"
    assert args_win.remote_only is True

    args_mac = parser.parse_args(["--audio-backend", "audio-toolbox"])
    assert args_mac.audio_backend == "audio-toolbox"

    # Setup wizard writes credentials cleanly
    cfg_dir = tmp_path / "setup_cfg"
    monkeypatch.setenv("VIBETUNE_CONFIG_DIR", str(cfg_dir))
    answers = iter(["my_client_id", "my_client_secret", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    rc = run_setup()
    assert rc == 0
    saved = (cfg_dir / ".env").read_text(encoding="utf-8")
    assert "SPOTIPY_CLIENT_ID=my_client_id" in saved
    assert "SPOTIPY_CLIENT_SECRET=my_client_secret" in saved
    assert "SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback" in saved

    # Empty credentials rejected
    empty_answers = iter(["", "", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(empty_answers))
    assert run_setup(config_path=tmp_path / "bad.env") == 1
    assert not (tmp_path / "bad.env").exists()


def test_live_audio_spectrum_graceful_when_parec_missing() -> None:
    with patch("shutil.which", return_value=None):
        assert LiveAudioSpectrum.is_available() is False
        spec = LiveAudioSpectrum()
        assert spec.start() is False
        assert spec.is_running is False
        assert spec.get_bands(16) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(60, 20), (100, 28), (220, 36)])
async def test_tui_smoke_across_terminal_sizes(size: tuple[int, int]) -> None:
    fake_client = FakeSpotifyClient()
    app = VibeTuneApp(spotify_client=fake_client, enable_polling=True)

    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert app.is_mounted
        assert app.now_playing.render().plain
        assert app.visualizer.render().plain
        assert app.library_pane.render().plain
        assert app.tracklist_pane.render().plain
        assert app.retro_footer.render().plain
