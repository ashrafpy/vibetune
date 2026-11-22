"""Cross-platform configuration, cache, and binary lookup helpers for VibeTune."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def _resolve_platform(platform_name: str | None = None) -> str:
    return (platform_name or sys.platform).lower()


def get_config_dir(platform_name: str | None = None) -> Path:
    """Return the user configuration directory for VibeTune on the current OS."""
    override = os.environ.get("VIBETUNE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    plat = _resolve_platform(platform_name)
    if plat.startswith("win"):
        appdata = os.environ.get("APPDATA", "").strip()
        base = Path(appdata) if appdata else (Path.home() / "AppData" / "Roaming")
        return base / "vibetune"

    if plat == "darwin":
        xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg:
            return Path(xdg).expanduser() / "vibetune"
        legacy_xdg = Path.home() / ".config" / "vibetune"
        if legacy_xdg.exists():
            return legacy_xdg
        return Path.home() / "Library" / "Application Support" / "vibetune"

    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else (Path.home() / ".config")
    return base / "vibetune"


def get_player_config_dir(platform_name: str | None = None) -> Path:
    """Return the configuration directory for the managed `go-librespot` daemon."""
    return get_config_dir(platform_name) / "player"


def get_env_file_path(platform_name: str | None = None) -> Path:
    """Return the default user `.env` file path for Spotify API credentials."""
    return get_config_dir(platform_name) / ".env"


def get_spotify_cache_path(
    cwd: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Return the Spotipy OAuth token cache path, preserving local dev checkouts."""
    local_cache = (cwd or Path.cwd()) / ".spotify_cache"
    if local_cache.is_file():
        return local_cache
    return get_config_dir(platform_name) / "spotify_cache"


def default_audio_backend(platform_name: str | None = None) -> str:
    """Return the default `go-librespot` audio backend for the active OS."""
    plat = _resolve_platform(platform_name)
    if plat.startswith("win"):
        return "wasapi"
    if plat == "darwin":
        return "audio-toolbox"
    return "pulseaudio"


def go_librespot_binary_name(platform_name: str | None = None) -> str:
    """Return the executable filename for `go-librespot` on the active OS."""
    plat = _resolve_platform(platform_name)
    return "go-librespot.exe" if plat.startswith("win") else "go-librespot"


def go_librespot_search_paths(platform_name: str | None = None) -> list[Path]:
    """Return ordered fallback paths where `go-librespot` may be installed."""
    plat = _resolve_platform(platform_name)
    paths: list[Path] = []

    env_bin = os.environ.get("VIBETUNE_PLAYER_BIN", "").strip()
    if env_bin:
        paths.append(Path(env_bin).expanduser())

    if plat.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        local_base = (
            Path(local_appdata)
            if local_appdata
            else (Path.home() / "AppData" / "Local")
        )
        paths.extend(
            [
                Path.home() / ".local" / "bin" / "go-librespot.exe",
                local_base / "vibetune" / "bin" / "go-librespot.exe",
                get_config_dir(plat) / "bin" / "go-librespot.exe",
            ]
        )
        return paths

    if plat == "darwin":
        paths.extend(
            [
                Path.home() / ".local" / "bin" / "go-librespot",
                Path("/opt/homebrew/bin/go-librespot"),
                Path("/usr/local/bin/go-librespot"),
                get_config_dir(plat) / "bin" / "go-librespot",
            ]
        )
        return paths

    paths.extend(
        [
            Path.home() / ".local" / "bin" / "go-librespot",
            Path("/usr/local/bin/go-librespot"),
            Path("/usr/bin/go-librespot"),
            get_config_dir(plat) / "bin" / "go-librespot",
        ]
    )
    return paths


def go_librespot_install_hint(platform_name: str | None = None) -> str:
    """Return a concise OS-specific hint for installing `go-librespot`."""
    plat = _resolve_platform(platform_name)
    if plat == "darwin":
        return (
            "go-librespot not found. Install via `brew install go-librespot` "
            "or place the binary in ~/.local/bin/go-librespot."
        )
    if plat.startswith("win"):
        return (
            "go-librespot.exe not found. Re-run the Windows PowerShell installer "
            "or place go-librespot.exe in %USERPROFILE%\\.local\\bin."
        )
    return (
        "go-librespot not found. Re-run the curl installer, install via your "
        "package manager (e.g. `yay -S go-librespot-bin`), or place it in ~/.local/bin/go-librespot."
    )
