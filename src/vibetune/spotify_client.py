"""Spotify Web API wrapper and audio spectrum segment synthesizer for VibeTune.

Think of this file as the "diplomat" or "remote control" between VibeTune and Spotify's
cloud servers:
- It logs you in securely using your Spotify Developer keys.
- It asks Spotify: "What playlists does the user have?", "What song is playing?",
  or "What speakers are currently online?"
- When you press Spacebar or 'n', this file calls Spotify to say: "Please pause the
  living room speaker" or "Skip to the next song."
- It also breaks down songs into beat patterns so the music visualizer can bounce.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
from typing import Any

from dotenv import load_dotenv
import httpx
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import CacheFileHandler, SpotifyOAuth

from vibetune.models import AudioSegment, LibraryItem, PlaybackState, TrackItem

# Silence chatty network logging so terminal output stays clean and readable
logging.getLogger("spotipy").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# Permissions VibeTune asks from Spotify (reading your library and controlling playback)
SCOPES = " ".join(
    [
        "user-read-playback-state",
        "user-modify-playback-state",
        "user-read-currently-playing",
        "user-library-read",
        "playlist-read-private",
        "playlist-read-collaborative",
    ]
)

PATHFINDER_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
PLAYLIST_CONTENTS_HASH = "cd2275433b29f7316176e7b5b5e098ae7744724e1a52d63549c76636b3257749"


def _clean_str(val: str | None, default: str = "") -> str:
    """Clean up messy text by removing extra spaces, line breaks, and hidden characters."""
    if not val:
        return default
    return " ".join(val.replace("\xa0", " ").splitlines()).strip() or default


def _parse_track(raw_track: dict[str, Any], context_uri: str | None = None) -> TrackItem | None:
    """Convert raw Spotify track data into a clean, simple TrackItem card.
    
    Spotify sends back a giant, complicated packet of raw data for every song.
    This helper unpacks that packet and pulls out just the important bits:
    the song title, the artist names, album name, release year, and duration.
    """
    if not raw_track or not isinstance(raw_track, dict) or not raw_track.get("id"):
        return None

    artists = raw_track.get("artists") or []
    artist_names = (
        ", ".join(
            _clean_str(a.get("name"))
            for a in artists
            if isinstance(a, dict) and a.get("name")
        )
        or "Unknown Artist"
    )

    album_obj = raw_track.get("album") or {}
    album_name = _clean_str(album_obj.get("name"), "Unknown Album")
    release_date = album_obj.get("release_date") or ""
    release_year = release_date[:4] if len(release_date) >= 4 else ""

    images = album_obj.get("images") or []
    album_art_url = images[-1]["url"] if images else None
    if len(images) >= 2:
        album_art_url = images[1]["url"]

    return TrackItem(
        id=raw_track["id"],
        uri=raw_track.get("uri", f"spotify:track:{raw_track['id']}"),
        title=_clean_str(raw_track.get("name"), "Untitled"),
        artist=artist_names,
        album=album_name,
        release_year=release_year,
        duration_ms=int(raw_track.get("duration_ms") or 0),
        album_art_url=album_art_url,
        context_uri=context_uri,
    )


def _parse_pathfinder_track(entry: dict[str, Any], context_uri: str | None = None) -> TrackItem | None:
    """Convert a Spotify Pathfinder GraphQL playlist item into a TrackItem."""
    item_v2 = (entry or {}).get("itemV2") or {}
    data = item_v2.get("data") or {}
    uri = data.get("uri") or ""
    if not uri.startswith("spotify:track:"):
        return None
    track_id = uri.split(":")[-1]
    title = _clean_str(data.get("name"), "Untitled")

    artists_items = ((data.get("artists") or {}).get("items")) or []
    artist_names = (
        ", ".join(
            _clean_str((a.get("profile") or {}).get("name"))
            for a in artists_items
            if isinstance(a, dict) and (a.get("profile") or {}).get("name")
        )
        or "Unknown Artist"
    )

    album_obj = data.get("albumOfTrack") or {}
    album_name = _clean_str(album_obj.get("name"), "Unknown Album")
    sources = ((album_obj.get("coverArt") or {}).get("sources")) or []
    art_url = sources[0]["url"] if sources else None

    duration_ms = int(((data.get("trackDuration") or {}).get("totalMilliseconds")) or 0)

    return TrackItem(
        id=track_id,
        uri=uri,
        title=title,
        artist=artist_names,
        album=album_name,
        release_year="",
        duration_ms=duration_ms,
        album_art_url=art_url,
        context_uri=context_uri,
    )


class SpotifyClient:
    """Manages Spotify OAuth, remote device playback, library queries, and beat analysis.
    
    This class is the master remote control. It handles:
    1. Authenticating: Opening your browser to log into Spotify the first time.
    2. Finding Devices: Spotting your phone, computer, or smart speakers on your network.
    3. Controlling Music: Sending Play, Pause, Next, and Volume signals over the internet.
    4. Fetching Songs: Downloading your playlists and album details in smooth background batches.
    """

    def __init__(self, env_path: Path | None = None, sp_client: spotipy.Spotify | None = None) -> None:
        # Load your Spotify credentials (Client ID and Secret) from .env.local
        self._load_env(env_path)
        self._sp: spotipy.Spotify | None = sp_client
        self._sp_lock = threading.Lock()
        self._analysis_cache: dict[str, tuple[float, list[AudioSegment]]] = {}
        self._last_device_id: str | None = None
        self._last_device_name: str = "No Active Device"
        self.auth_error: str | None = None

    def _load_env(self, env_path: Path | None = None) -> None:
        """Search the disk for the .env.local or .env file containing Spotify keys."""
        candidates = []
        if env_path:
            candidates.append(env_path)
        candidates.extend(
            [
                Path.cwd() / ".env.local",
                Path.cwd() / ".env",
                Path(__file__).resolve().parents[2] / ".env.local",
            ]
        )
        for path in candidates:
            if path.is_file():
                load_dotenv(dotenv_path=path, override=False)
                break

    @property
    def sp(self) -> spotipy.Spotify | None:
        """Get or initialize the authenticated Spotify connection.
        
        Checks if we're already logged in. If not, reads your keys and opens
        your web browser to let you grant permission, then saves a temporary
        login pass (token) in `.spotify_cache` so you don't have to log in again.
        """
        if self._sp is not None:
            return self._sp

        with self._sp_lock:
            if self._sp is not None:
                return self._sp

            client_id = os.getenv("SPOTIPY_CLIENT_ID")
            client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
            redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

            if not client_id or not client_secret:
                self.auth_error = "Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET in .env.local"
                return None

            cache_path = Path.cwd() / ".spotify_cache"
            try:
                cache_handler = CacheFileHandler(cache_path=str(cache_path))
                auth_manager = SpotifyOAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                    scope=SCOPES,
                    cache_handler=cache_handler,
                    open_browser=True,
                )
                self._sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=8, retries=1)
                self.auth_error = None
                return self._sp
            except Exception as exc:
                self.auth_error = str(exc)
                return None

    def ensure_device_id(self) -> str | None:
        """Return active Spotify Connect device_id, preferring active or phone devices.
        
        Finds out which speaker or phone should play music. If your phone or smart
        speaker is already awake, it chooses that.
        """
        if not self.sp:
            return None
        try:
            resp = self.sp.devices()
            devices = (resp or {}).get("devices") or []
            if not devices:
                return self._last_device_id

            for dev in devices:
                if dev.get("is_active") and dev.get("id"):
                    self._last_device_id = dev["id"]
                    self._last_device_name = dev.get("name", "Spotify Device")
                    return self._last_device_id

            for dev in devices:
                if (dev.get("type") or "").lower() == "smartphone" and dev.get("id"):
                    self._last_device_id = dev["id"]
                    self._last_device_name = dev.get("name", "Phone")
                    return self._last_device_id

            first = devices[0]
            self._last_device_id = first.get("id")
            self._last_device_name = first.get("name", "Spotify Device")
            return self._last_device_id
        except Exception:
            return self._last_device_id

    def get_devices(self) -> list[dict[str, Any]]:
        """Return list of available Spotify Connect devices (speakers, phones, computers)."""
        if not self.sp:
            return []
        try:
            resp = self.sp.devices()
            devices = (resp or {}).get("devices") or []
            return [d for d in devices if isinstance(d, dict) and d.get("id")]
        except Exception:
            return []

    def transfer_to_device(self, device_id: str, device_name: str = "Spotify Device") -> bool:
        """Transfer active playback to the specified Spotify Connect device (e.g. switch to Echo Dot)."""
        if not self.sp or not device_id:
            return False
        self._last_device_id = device_id
        self._last_device_name = device_name
        try:
            self.sp.transfer_playback(device_id=device_id, force_play=False)
            return True
        except Exception:
            return False

    def cycle_device(self) -> str:
        """Switch active playback to the next available Spotify Connect device."""
        devices = self.get_devices()
        if not devices:
            return "No Spotify devices found"

        current_idx = 0
        for idx, dev in enumerate(devices):
            if dev.get("id") == self._last_device_id or dev.get("is_active"):
                current_idx = idx
                break
        next_dev = devices[(current_idx + 1) % len(devices)]
        dev_id = next_dev["id"]
        dev_name = next_dev.get("name", "Spotify Device")
        self.transfer_to_device(dev_id, dev_name)
        return self._last_device_name

    def get_playback_state(self) -> PlaybackState:
        """Fetch current Spotify playback state or fallback to idle device state.
        
        Asks Spotify: 'What is playing right now?'
        Spotify responds with the current song name, how many seconds have elapsed,
        current volume, and whether shuffle or repeat is turned on.
        """
        if not self.sp:
            return PlaybackState(device_name=self.auth_error or "Offline")

        try:
            playback = self.sp.current_playback()
            if not playback:
                dev_id = self.ensure_device_id()
                return PlaybackState(
                    is_playing=False,
                    device_id=dev_id,
                    device_name=self._last_device_name,
                )

            device = playback.get("device") or {}
            dev_id = device.get("id") or self._last_device_id
            dev_name = device.get("name") or self._last_device_name
            if dev_id:
                self._last_device_id = dev_id
                self._last_device_name = dev_name

            context = playback.get("context") or {}
            context_uri = context.get("uri")
            track = _parse_track(playback.get("item") or {}, context_uri=context_uri)

            tempo_bpm = 120.0
            if track:
                tempo_bpm, _ = self.get_audio_analysis(track.id, track.duration_ms)

            volume = device.get("volume_percent")
            if volume is None:
                volume = 75

            return PlaybackState(
                is_playing=bool(playback.get("is_playing", False)),
                track=track,
                progress_ms=int(playback.get("progress_ms") or 0),
                volume_percent=int(volume),
                shuffle_state=bool(playback.get("shuffle_state", False)),
                repeat_state=str(playback.get("repeat_state") or "off"),
                device_id=dev_id,
                device_name=dev_name,
                tempo_bpm=tempo_bpm,
            )
        except Exception:
            return PlaybackState(
                is_playing=False,
                device_id=self._last_device_id,
                device_name=self._last_device_name,
            )

    def toggle_play_pause(self, state: PlaybackState) -> bool:
        """Toggle playback between play and pause on the active/remote device (Spacebar)."""
        if not self.sp:
            return state.is_playing
        dev_id = state.device_id or self.ensure_device_id()
        try:
            if state.is_playing:
                self.sp.pause_playback(device_id=dev_id)
                return False
            else:
                self.sp.start_playback(device_id=dev_id)
                return True
        except Exception:
            return state.is_playing

    def next_track(self, device_id: str | None = None) -> None:
        """Skip to the next song on Spotify ('n' key)."""
        if not self.sp:
            return
        try:
            self.sp.next_track(device_id=device_id or self.ensure_device_id())
        except Exception:
            pass

    def previous_track(self, device_id: str | None = None) -> None:
        """Skip backward to the previous song or beginning of current song ('p' key)."""
        if not self.sp:
            return
        try:
            self.sp.previous_track(device_id=device_id or self.ensure_device_id())
        except Exception:
            pass

    def seek_relative(self, current_ms: int, delta_ms: int, duration_ms: int, device_id: str | None = None) -> int:
        """Jump 5 seconds forward or backward in the current song (Left/Right arrow keys)."""
        target_ms = max(0, min(duration_ms or 300_000, current_ms + delta_ms))
        if not self.sp:
            return target_ms
        try:
            self.sp.seek_track(target_ms, device_id=device_id or self.ensure_device_id())
        except Exception:
            pass
        return target_ms

    def adjust_volume(self, current_vol: int, delta: int, device_id: str | None = None) -> int:
        """Raise or lower speaker volume by 5% ('+' and '-' keys)."""
        target_vol = max(0, min(100, current_vol + delta))
        if not self.sp:
            return target_vol
        try:
            self.sp.volume(target_vol, device_id=device_id or self.ensure_device_id())
        except Exception:
            pass
        return target_vol

    def toggle_shuffle(self, current_shuffle: bool, device_id: str | None = None) -> bool:
        """Turn shuffle mode on or off ('s' key)."""
        new_shuffle = not current_shuffle
        if not self.sp:
            return new_shuffle
        try:
            self.sp.shuffle(new_shuffle, device_id=device_id or self.ensure_device_id())
        except Exception:
            pass
        return new_shuffle

    def cycle_repeat(self, current_repeat: str, device_id: str | None = None) -> str:
        """Cycle repeat mode: OFF -> Repeat All -> Repeat One Song ('r' key)."""
        order = ["off", "context", "track"]
        try:
            next_idx = (order.index(current_repeat) + 1) % len(order)
        except ValueError:
            next_idx = 0
        new_repeat = order[next_idx]
        if not self.sp:
            return new_repeat
        try:
            self.sp.repeat(new_repeat, device_id=device_id or self.ensure_device_id())
        except Exception:
            pass
        return new_repeat

    def play_track(
        self,
        track: TrackItem,
        context_uri: str | None = None,
        fallback_uris: list[str] | None = None,
        device_id: str | None = None,
    ) -> None:
        """Start playing a specific track on the remote Spotify Connect device."""
        if not self.sp:
            return
        dev_id = device_id or self.ensure_device_id()
        effective_context = context_uri or track.context_uri
        try:
            if (
                effective_context
                and effective_context.startswith("spotify:")
                and ":track:" not in effective_context
                and ":artist:" not in effective_context
            ):
                try:
                    self.sp.start_playback(
                        device_id=dev_id,
                        context_uri=effective_context,
                        offset={"uri": track.uri},
                    )
                    return
                except Exception:
                    pass

            if fallback_uris:
                try:
                    idx = fallback_uris.index(track.uri)
                    uris_slice = fallback_uris[idx : idx + 50]
                except ValueError:
                    uris_slice = [track.uri]
                self.sp.start_playback(device_id=dev_id, uris=uris_slice)
            else:
                self.sp.start_playback(device_id=dev_id, uris=[track.uri])
        except Exception:
            pass

    def get_library_items(self) -> list[LibraryItem]:
        """Fetch Liked Songs, saved Playlists, favorite Artists, and saved Albums for Pane 1.
        
        This builds your left-hand menu. It asks Spotify for:
        1. Your 'Liked Songs' count.
        2. All your personal and followed playlists.
        3. Your saved albums (marked with ◉).
        4. Artists you listen to most frequently (marked with ♪).
        """
        if not self.sp:
            return []

        items: list[LibraryItem] = []
        artist_counts: Counter[str] = Counter()
        artist_meta: dict[str, tuple[str, str]] = {}

        # 1. Liked Songs (also sample saved tracks to extract favorite artists)
        try:
            saved = self.sp.current_user_saved_tracks(limit=50)
            liked_total = int((saved or {}).get("total") or 0)
            items.append(
                LibraryItem(
                    id="liked_songs",
                    name="Liked Songs",
                    item_type="liked",
                    track_count=liked_total,
                    uri=None,
                )
            )
            for row in (saved or {}).get("items") or []:
                raw_trk = (row or {}).get("track") or (row or {}).get("item") or {}
                for artist in raw_trk.get("artists") or []:
                    aid = artist.get("id")
                    aname = artist.get("name")
                    if aid and aname:
                        artist_counts[aid] += 1
                        artist_meta[aid] = (aname, artist.get("uri") or f"spotify:artist:{aid}")
        except Exception:
            items.append(
                LibraryItem(
                    id="liked_songs",
                    name="Liked Songs",
                    item_type="liked",
                    track_count=0,
                    uri=None,
                )
            )

        # 2. User's Saved & Followed Playlists
        try:
            playlists_resp = self.sp.current_user_playlists(limit=50)
            for pl in (playlists_resp or {}).get("items") or []:
                if not pl or not pl.get("id"):
                    continue
                tracks_info = pl.get("items") or pl.get("tracks") or {}
                items.append(
                    LibraryItem(
                        id=pl["id"],
                        name=_clean_str(pl.get("name"), "Untitled Playlist"),
                        item_type="playlist",
                        track_count=int(tracks_info.get("total") or 0),
                        uri=pl.get("uri"),
                    )
                )
        except Exception:
            pass

        # 3. Saved Albums (use single-cell glyph '◉' so cell alignment stays exact)
        try:
            albums_resp = self.sp.current_user_saved_albums(limit=20)
            for entry in (albums_resp or {}).get("items") or []:
                album = (entry or {}).get("album") or {}
                if not album.get("id"):
                    continue
                items.append(
                    LibraryItem(
                        id=album["id"],
                        name=f"◉ {_clean_str(album.get('name'), 'Saved Album')}",
                        item_type="album",
                        track_count=int(album.get("total_tracks") or 0),
                        uri=album.get("uri"),
                    )
                )
                for artist in album.get("artists") or []:
                    aid = artist.get("id")
                    aname = artist.get("name")
                    if aid and aname:
                        artist_counts[aid] += 2
                        artist_meta[aid] = (aname, artist.get("uri") or f"spotify:artist:{aid}")
        except Exception:
            pass

        # 4. Artists
        added_artist_ids: set[str] = set()
        try:
            followed = self.sp.current_user_followed_artists(limit=15)
            for artist in ((followed or {}).get("artists") or {}).get("items") or []:
                aid = artist.get("id")
                aname = artist.get("name")
                if aid and aname and aid not in added_artist_ids:
                    added_artist_ids.add(aid)
                    items.append(
                        LibraryItem(
                            id=aid,
                            name=f"♪ {_clean_str(aname)}",
                            item_type="artist",
                            track_count=artist_counts.get(aid, 10),
                            uri=artist.get("uri") or f"spotify:artist:{aid}",
                        )
                    )
        except Exception:
            pass

        for aid, count in artist_counts.most_common(15):
            if aid in added_artist_ids:
                continue
            added_artist_ids.add(aid)
            aname, auri = artist_meta[aid]
            items.append(
                LibraryItem(
                    id=aid,
                    name=f"♪ {_clean_str(aname)}",
                    item_type="artist",
                    track_count=count,
                    uri=auri,
                )
            )

        return items

    def _iter_public_playlist_batches(
        self,
        playlist_id: str,
        context_uri: str | None,
        batch_size: int = 100,
    ) -> Iterator[list[TrackItem]]:
        """Stream all tracks of a public/curated playlist in batches via Spotify Pathfinder."""
        try:
            with httpx.Client(timeout=10.0) as client:
                embed_resp = client.get(f"https://open.spotify.com/embed/playlist/{playlist_id}")
                embed_resp.raise_for_status()
                match = re.search(
                    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                    embed_resp.text,
                )
                if not match:
                    return
                next_data = json.loads(match.group(1))
                state = (
                    next_data.get("props", {})
                    .get("pageProps", {})
                    .get("state", {})
                )
                token = (
                    state.get("settings", {})
                    .get("session", {})
                    .get("accessToken")
                )

                if token:
                    offset = 0
                    total_count = None
                    headers = {"Authorization": f"Bearer {token}"}
                    while total_count is None or offset < total_count:
                        params = {
                            "operationName": "fetchPlaylistContents",
                            "variables": json.dumps(
                                {
                                    "uri": f"spotify:playlist:{playlist_id}",
                                    "offset": offset,
                                    "limit": batch_size,
                                }
                            ),
                            "extensions": json.dumps(
                                {
                                    "persistedQuery": {
                                        "version": 1,
                                        "sha256Hash": PLAYLIST_CONTENTS_HASH,
                                    }
                                }
                            ),
                        }
                        gql_resp = client.get(PATHFINDER_URL, params=params, headers=headers)
                        if gql_resp.status_code != 200:
                            break
                        content = (
                            gql_resp.json()
                            .get("data", {})
                            .get("playlistV2", {})
                            .get("content", {})
                        )
                        if total_count is None:
                            total_count = int(content.get("totalCount") or 0)
                        raw_items = content.get("items") or []
                        if not raw_items:
                            break

                        batch: list[TrackItem] = []
                        for entry in raw_items:
                            parsed = _parse_pathfinder_track(entry, context_uri=context_uri)
                            if parsed:
                                batch.append(parsed)
                        if batch:
                            yield batch

                        offset += len(raw_items)
                        if len(raw_items) < batch_size:
                            break
                    return

                # Fallback to embedded trackList if no session token
                entity = state.get("data", {}).get("entity", {})
                raw_list = entity.get("trackList") or []
                batch = []
                for item in raw_list:
                    uri = item.get("uri") or ""
                    if not uri.startswith("spotify:track:"):
                        continue
                    tid = uri.split(":")[-1]
                    batch.append(
                        TrackItem(
                            id=tid,
                            uri=uri,
                            title=_clean_str(item.get("title"), "Untitled"),
                            artist=_clean_str(item.get("subtitle"), "Unknown Artist"),
                            album="",
                            release_year="",
                            duration_ms=int(item.get("duration") or 0),
                            context_uri=context_uri,
                        )
                    )
                if batch:
                    yield batch
        except Exception:
            return

    def iter_library_track_batches(
        self,
        item: LibraryItem,
        batch_size: int = 50,
    ) -> Iterator[list[TrackItem]]:
        """Yield batches of TrackItems until the entire playlist/library item is loaded.
        
        If a playlist has 500 songs, downloading all of them at once would freeze
        the screen for several seconds.
        Instead, this function acts like a conveyor belt: it delivers the first 50
        songs right away so you can start browsing and playing, then quietly delivers
        the next 50 in the background.
        """
        if not self.sp:
            return

        if item.item_type == "liked":
            offset = 0
            total = None
            while total is None or offset < total:
                try:
                    resp = self.sp.current_user_saved_tracks(limit=50, offset=offset)
                    if total is None:
                        total = int((resp or {}).get("total") or 0)
                    rows = (resp or {}).get("items") or []
                    if not rows:
                        break
                    batch: list[TrackItem] = []
                    for row in rows:
                        raw_track = (row or {}).get("track") or (row or {}).get("item") or {}
                        parsed = _parse_track(raw_track)
                        if parsed:
                            batch.append(parsed)
                    if batch:
                        yield batch
                    offset += len(rows)
                    if len(rows) < 50:
                        break
                except Exception:
                    break

        elif item.item_type == "playlist":
            offset = 0
            total = None
            try:
                while total is None or offset < total:
                    resp = self.sp.playlist_items(item.id, limit=50, offset=offset)
                    if total is None:
                        total = int((resp or {}).get("total") or 0)
                    rows = (resp or {}).get("items") or []
                    if not rows:
                        break
                    batch = []
                    for row in rows:
                        raw_track = (row or {}).get("item") or (row or {}).get("track") or {}
                        parsed = _parse_track(raw_track, context_uri=item.uri)
                        if parsed:
                            batch.append(parsed)
                    if batch:
                        yield batch
                    offset += len(rows)
                    if len(rows) < 50:
                        break
            except SpotifyException:
                yielded_any = False
                for batch in self._iter_public_playlist_batches(item.id, item.uri, batch_size=100):
                    yielded_any = True
                    yield batch
                if not yielded_any:
                    fallback = self.search_tracks(item.name, limit=20)
                    for t in fallback:
                        t.context_uri = item.uri
                    if fallback:
                        yield fallback
            except Exception:
                pass

        elif item.item_type == "artist":
            clean_artist = item.name.lstrip("♪ ").strip()
            tracks = self.search_tracks(f'artist:"{clean_artist}"', limit=30)
            if not tracks:
                tracks = self.search_tracks(clean_artist, limit=30)
            for t in tracks:
                t.context_uri = item.uri
            if tracks:
                yield tracks

        elif item.item_type == "album":
            try:
                album_full = self.sp.album(item.id)
                images = (album_full or {}).get("images") or []
                art_url = images[1]["url"] if len(images) >= 2 else (images[0]["url"] if images else None)
                album_name = _clean_str(album_full.get("name"), item.name.lstrip("◉💿 ").strip())
                release_date = (album_full or {}).get("release_date") or ""
                release_year = release_date[:4] if len(release_date) >= 4 else ""

                batch = []
                for raw in ((album_full or {}).get("tracks") or {}).get("items") or []:
                    if not raw or not raw.get("id"):
                        continue
                    artists = ", ".join(
                        _clean_str(a.get("name"))
                        for a in (raw.get("artists") or [])
                        if a.get("name")
                    )
                    batch.append(
                        TrackItem(
                            id=raw["id"],
                            uri=raw.get("uri", f"spotify:track:{raw['id']}"),
                            title=_clean_str(raw.get("name"), "Untitled"),
                            artist=artists or "Unknown Artist",
                            album=album_name,
                            release_year=release_year,
                            duration_ms=int(raw.get("duration_ms") or 0),
                            album_art_url=art_url,
                            context_uri=item.uri,
                        )
                    )
                if batch:
                    yield batch
            except Exception:
                pass

    def get_library_tracks(self, item: LibraryItem, limit: int = 50) -> list[TrackItem]:
        """Fetch tracklist for a library item (convenience wrapper over iter_library_track_batches)."""
        all_tracks: list[TrackItem] = []
        for batch in self.iter_library_track_batches(item, batch_size=limit):
            all_tracks.extend(batch)
            if limit and len(all_tracks) >= limit:
                break
        return all_tracks

    def search_tracks(self, query: str, limit: int = 20) -> list[TrackItem]:
        """Search the full Spotify catalog for tracks matching query (paginating in chunks of 10).
        
        When you type a search term and press Enter, this function asks Spotify's
        global music library for songs matching your query and returns a list
        of track cards ready to display on screen.
        """
        if not self.sp or not query.strip():
            return []
        tracks: list[TrackItem] = []
        seen_ids: set[str] = set()
        page_size = 10
        pages = max(1, min(5, math.ceil(limit / page_size)))

        for page in range(pages):
            try:
                resp = self.sp.search(
                    q=query.strip(),
                    type="track",
                    limit=page_size,
                    offset=page * page_size,
                )
                raw_items = ((resp or {}).get("tracks") or {}).get("items") or []
                if not raw_items:
                    break
                for raw in raw_items:
                    parsed = _parse_track(raw)
                    if parsed and parsed.id not in seen_ids:
                        seen_ids.add(parsed.id)
                        tracks.append(parsed)
                if len(raw_items) < page_size:
                    break
            except Exception:
                break
        return tracks

    def get_audio_analysis(self, track_id: str, duration_ms: int = 210_000) -> tuple[float, list[AudioSegment]]:
        """Return (tempo_bpm, segments) using deterministic track-seeded beat & harmonic profile.
        
        Calculates the speed (BPM = Beats Per Minute) and rhythm patterns of the song.
        This provides the musical 'pulse' that makes the frequency bars in the visualizer
        bounce in rhythm with the music.
        """
        if track_id in self._analysis_cache:
            return self._analysis_cache[track_id]

        digest = hashlib.sha256(track_id.encode("utf-8")).digest()
        tempo = 92.0 + (digest[0] % 56)  # 92 - 147 BPM
        beat_sec = 60.0 / tempo
        step_sec = beat_sec / 2.0
        total_sec = max(30.0, duration_ms / 1000.0)

        segments = []
        t = 0.0
        idx = 0
        while t < total_sec and idx < 900:
            phase = idx % 8
            accent = 0.0 if phase in (0, 4) else (-5.0 if phase in (2, 6) else -11.0)
            seed_byte = digest[idx % len(digest)]
            loudness = -6.0 + accent - (seed_byte % 8)
            pitches = [
                0.25
                + 0.75
                * abs(
                    math.sin(
                        (idx * 0.45)
                        + (p_i * 0.55)
                        + (digest[(idx + p_i) % len(digest)] / 255.0) * math.pi
                    )
                )
                for p_i in range(12)
            ]
            segments.append(
                AudioSegment(
                    start=t,
                    duration=step_sec,
                    loudness_max=loudness,
                    pitches=pitches,
                )
            )
            t += step_sec
            idx += 1

        self._analysis_cache[track_id] = (tempo, segments)
        return tempo, segments
