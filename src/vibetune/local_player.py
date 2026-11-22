"""Managed go-librespot local playback engine and REST/WebSocket client for VibeTune.

This module turns VibeTune from a remote-only Spotify Connect controller into a
standalone Spotify client with local Linux audio playback (PipeWire/PulseAudio/ALSA):
- `LocalPlayerConfig`: Settings for the local `go-librespot` daemon.
- `LocalPlayerDaemon`: Discovers `go-librespot`, writes its `config.yml`, manages
  subprocess startup/health checks, and guarantees clean shutdown without orphans.
- `LocalPlayerClient`: Async REST + WebSocket client talking to `go-librespot`'s
  local HTTP API (`127.0.0.1:3678`) for zero-latency transport and real-time events.
"""

from __future__ import annotations

import asyncio
import atexit
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import httpx
import yaml

from vibetune.models import PlaybackState, TrackItem
from vibetune.paths import (
    default_audio_backend,
    get_player_config_dir,
    go_librespot_binary_name,
    go_librespot_install_hint,
    go_librespot_search_paths,
)

log = logging.getLogger(__name__)


@dataclass
class LocalPlayerConfig:
    """Configuration for the managed `go-librespot` sidecar process."""

    device_name: str = "VibeTune"
    device_type: str = "computer"
    bitrate: int = 320
    audio_backend: str = field(default_factory=default_audio_backend)
    audio_device: str = "default"
    api_host: str = "127.0.0.1"
    api_port: int = 3678
    config_dir: Path = field(default_factory=get_player_config_dir)
    volume_normalization: bool = True
    initial_volume: int = 75
    zeroconf_enabled: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.api_host}:{self.api_port}/events"

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.yml"

    @property
    def log_path(self) -> Path:
        return self.config_dir / "daemon.log"

    @property
    def state_path(self) -> Path:
        return self.config_dir / "state.json"

    def has_cached_credentials(self) -> bool:
        """Return True if `state.json` already contains saved Spotify credentials."""
        if not self.state_path.is_file():
            return False
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return bool(isinstance(data, dict) and data.get("credentials"))
        except (OSError, ValueError):
            return False

    def to_yaml_dict(self, interactive_auth: bool = False) -> dict[str, Any]:
        """Serialize configuration into a `go-librespot`-compatible dict."""
        cfg: dict[str, Any] = {
            "device_name": self.device_name,
            "device_type": self.device_type,
            "bitrate": int(self.bitrate),
            "audio_backend": self.audio_backend,
            "audio_device": self.audio_device,
            "normalisation_enabled": self.volume_normalization,
            "initial_volume": int(self.initial_volume),
            "zeroconf_enabled": self.zeroconf_enabled,
            "log_level": "info",
            "server": {
                "enabled": True,
                "address": self.api_host,
                "port": int(self.api_port),
            },
        }
        if interactive_auth:
            cfg["credentials"] = {
                "type": "interactive",
                "interactive": {
                    "callback_port": 8889,
                },
            }
        return cfg


def find_go_librespot_binary(platform_name: str | None = None) -> Path | None:
    """Locate the `go-librespot` executable on PATH or common user bin locations."""
    search_paths = go_librespot_search_paths(platform_name)
    # Check explicit VIBETUNE_PLAYER_BIN override first if present
    import os

    if os.environ.get("VIBETUNE_PLAYER_BIN", "").strip() and search_paths:
        if search_paths[0].is_file():
            return search_paths[0]

    bin_name = go_librespot_binary_name(platform_name)
    found = shutil.which(bin_name)
    if not found and bin_name != "go-librespot":
        found = shutil.which("go-librespot")
    if found:
        return Path(found)

    for candidate in search_paths:
        if candidate.is_file():
            return candidate
    return None


def status_to_playback_state(
    status: dict[str, Any],
    default_device_name: str = "VibeTune",
) -> PlaybackState:
    """Convert a `go-librespot` `GET /status` JSON payload into a `PlaybackState`."""
    raw_track = status.get("track") or {}
    track: TrackItem | None = None
    uri = str(raw_track.get("uri") or "")
    if uri:
        track_id = uri.split(":")[-1] if ":" in uri else uri
        artists_raw = raw_track.get("artist_names") or []
        if isinstance(artists_raw, list) and artists_raw:
            artist = ", ".join(str(a) for a in artists_raw if a)
        else:
            artist = str(raw_track.get("artist") or "Unknown Artist")

        release_date = str(raw_track.get("release_date") or "")
        release_year = release_date[:4] if len(release_date) >= 4 else ""
        art_url = raw_track.get("album_cover_url") or None

        track = TrackItem(
            id=track_id,
            uri=uri,
            title=str(raw_track.get("name") or "Untitled"),
            artist=artist,
            album=str(raw_track.get("album_name") or "Unknown Album"),
            release_year=release_year,
            duration_ms=int(raw_track.get("duration") or 0),
            album_art_url=art_url,
            context_uri=status.get("context_uri") or None,
        )

    paused = bool(status.get("paused", True))
    stopped = bool(status.get("stopped", False))
    is_playing = bool(track is not None and not paused and not stopped)

    repeat_track = bool(status.get("repeat_track", False))
    repeat_context = bool(status.get("repeat_context", False))
    if repeat_track:
        repeat_state: str = "track"
    elif repeat_context:
        repeat_state = "context"
    else:
        repeat_state = "off"

    vol_raw = status.get("volume")
    vol_steps = int(status.get("volume_steps") or 100)
    if vol_raw is None:
        volume_percent = 75
    elif vol_steps > 0 and vol_steps != 100:
        volume_percent = max(0, min(100, round((int(vol_raw) / vol_steps) * 100)))
    else:
        volume_percent = max(0, min(100, int(vol_raw)))

    position_ms = int(raw_track.get("position") or status.get("position") or 0)
    device_name = str(status.get("device_name") or default_device_name)
    device_id = str(status.get("device_id") or "vibetune_local")

    return PlaybackState(
        is_playing=is_playing,
        track=track,
        progress_ms=max(0, position_ms),
        volume_percent=volume_percent,
        supports_volume=True,
        shuffle_state=bool(status.get("shuffle_context", False)),
        repeat_state=repeat_state,  # type: ignore[arg-type]  # validated to be Literal value above
        device_id=device_id,
        device_name=device_name,
        is_local_device=True,
    )


class LocalPlayerClient:
    """Async REST & WebSocket client for a running `go-librespot` daemon."""

    def __init__(self, config: LocalPlayerConfig) -> None:
        self.config = config
        self._http: httpx.AsyncClient | None = None

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=3.0,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def is_api_reachable(self) -> bool:
        """Return True if `go-librespot`'s HTTP server is listening (200 active or 204 standby)."""
        try:
            resp = await self._get_http().get("/status")
            return resp.status_code in (200, 204)
        except httpx.HTTPError:
            return False

    async def get_status(self) -> dict[str, Any] | None:
        try:
            resp = await self._get_http().get("/status")
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.debug("Local player /status failed: %s", exc)
        return None

    async def get_playback_state(self) -> PlaybackState | None:
        status = await self.get_status()
        if not status:
            return None
        return status_to_playback_state(status, default_device_name=self.config.device_name)

    async def _post(self, path: str, payload: dict[str, Any] | None = None) -> bool:
        try:
            resp = await self._get_http().post(path, json=payload)
            return 200 <= resp.status_code < 300
        except httpx.HTTPError as exc:
            log.debug("Local player POST %s failed: %s", path, exc)
            return False

    async def play(
        self,
        uri: str,
        skip_to_uri: str | None = None,
        paused: bool = False,
    ) -> bool:
        payload: dict[str, Any] = {"uri": uri, "paused": paused}
        if skip_to_uri:
            payload["skip_to_uri"] = skip_to_uri
        return await self._post("/player/play", payload)

    async def pause(self) -> bool:
        return await self._post("/player/pause")

    async def resume(self) -> bool:
        return await self._post("/player/resume")

    async def playpause(self) -> bool:
        return await self._post("/player/playpause")

    async def next_track(self) -> bool:
        return await self._post("/player/next")

    async def previous_track(self) -> bool:
        return await self._post("/player/prev")

    async def seek(self, position_ms: int, relative: bool = False) -> bool:
        return await self._post(
            "/player/seek",
            {"position": int(position_ms), "relative": relative},
        )

    async def set_volume(self, volume_percent: int) -> bool:
        vol = max(0, min(100, int(volume_percent)))
        return await self._post("/player/volume", {"volume": vol, "relative": False})

    async def set_shuffle(self, enabled: bool) -> bool:
        return await self._post("/player/shuffle", {"shuffle_context": bool(enabled)})

    async def set_repeat(self, repeat_state: str) -> bool:
        if repeat_state == "track":
            ok1 = await self._post("/player/repeat_context", {"repeat_context": False})
            ok2 = await self._post("/player/repeat_track", {"repeat_track": True})
            return ok1 or ok2
        if repeat_state == "context":
            ok1 = await self._post("/player/repeat_track", {"repeat_track": False})
            ok2 = await self._post("/player/repeat_context", {"repeat_context": True})
            return ok1 or ok2
        ok1 = await self._post("/player/repeat_track", {"repeat_track": False})
        ok2 = await self._post("/player/repeat_context", {"repeat_context": False})
        return ok1 or ok2

    async def iter_events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed JSON events from `go-librespot`'s `/events` WebSocket."""
        import websockets

        backoff = 0.5
        while True:
            try:
                async with websockets.connect(self.config.ws_url, open_timeout=3.0) as ws:
                    backoff = 0.5
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="ignore")
                        try:
                            event = json.loads(raw)
                            if isinstance(event, dict):
                                yield event
                        except json.JSONDecodeError:
                            continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("Local player WS disconnected (%s), retrying in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(5.0, backoff * 1.5)


class LocalPlayerDaemon:
    """Manages the lifecycle of the `go-librespot` background audio process."""

    def __init__(self, config: LocalPlayerConfig | None = None) -> None:
        self.config = config or LocalPlayerConfig()
        self.client = LocalPlayerClient(self.config)
        self._process: asyncio.subprocess.Process | None = None
        self._log_file: Any = None
        self._started: bool = False
        self.last_error: str | None = None
        atexit.register(self._cleanup_sync)

    @property
    def is_running(self) -> bool:
        return (
            self._started
            and self._process is not None
            and self._process.returncode is None
        )

    def write_config(self, interactive_auth: bool = False) -> Path:
        """Write `config.yml` for `go-librespot` into `config_dir`."""
        self.config.config_dir.mkdir(parents=True, exist_ok=True)
        cfg_data = self.config.to_yaml_dict(interactive_auth=interactive_auth)
        self.config.config_path.write_text(
            yaml.safe_dump(cfg_data, sort_keys=False),
            encoding="utf-8",
        )
        return self.config.config_path

    def run_interactive_auth(self) -> int:
        """Run `go-librespot` in the foreground so the user can complete OAuth login."""
        binary = find_go_librespot_binary()
        if not binary:
            self.last_error = go_librespot_install_hint()
            return 127
        self.write_config(interactive_auth=True)
        proc = subprocess.run(
            [str(binary), "--config_dir", str(self.config.config_dir)],
            check=False,
        )
        # Restore standard config after interactive auth finishes
        self.write_config(interactive_auth=False)
        return proc.returncode

    async def start(self, timeout_sec: float = 5.0) -> bool:
        """Start `go-librespot` if not already running and wait for its HTTP API."""
        if self.is_running:
            return True

        # If an external/already-running daemon is serving on our port, reuse it
        if await self.client.is_api_reachable():
            self._started = True
            self.last_error = None
            return True

        binary = find_go_librespot_binary()
        if not binary:
            self.last_error = "go-librespot not found (running in remote-only mode)"
            log.info(self.last_error)
            return False

        # Enable credential auto-login when state.json already has cached OAuth credentials
        self.write_config(interactive_auth=self.config.has_cached_credentials())
        self._log_file = open(self.config.log_path, "a", encoding="utf-8")

        try:
            spawn_kwargs: dict[str, Any] = {
                "stdout": self._log_file,
                "stderr": self._log_file,
            }
            if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                spawn_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._process = await asyncio.create_subprocess_exec(
                str(binary),
                "--config_dir",
                str(self.config.config_dir),
                **spawn_kwargs,
            )
        except OSError as exc:
            self.last_error = f"Failed to launch go-librespot: {exc}"
            self._close_log_file()
            return False

        # Poll local HTTP API until ready or process exits
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            if self._process.returncode is not None:
                self.last_error = (
                    f"go-librespot exited early (code {self._process.returncode}); "
                    f"run `vibetune --auth-player` or check {self.config.log_path}"
                )
                self._close_log_file()
                return False
            status = await self.client.get_status()
            if status is not None:
                self._started = True
                self.last_error = None
                return True
            await asyncio.sleep(0.15)

        # Process is still alive (e.g. waiting for Zeroconf / first Connect handshake)
        if self._process.returncode is None:
            self._started = True
            self.last_error = None
            return True

        self.last_error = "Timed out waiting for go-librespot"
        await self.stop()
        return False

    async def stop(self) -> None:
        """Gracefully stop the managed `go-librespot` subprocess."""
        self._started = False
        await self.client.aclose()
        proc = self._process
        self._process = None
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            except (ProcessLookupError, OSError):
                pass
        self._close_log_file()

    def _cleanup_sync(self) -> None:
        """Synchronous `atexit` safety net to prevent orphaned `go-librespot` processes."""
        proc = self._process
        self._process = None
        self._started = False
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except (ProcessLookupError, OSError):
                pass
        self._close_log_file()

    def _close_log_file(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None
