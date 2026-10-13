"""Data models for VibeTune playback, library items, and tracks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackItem:
    """Represents a single Spotify track in a tracklist or search result."""

    id: str
    uri: str
    title: str
    artist: str
    album: str
    release_year: str
    duration_ms: int
    album_art_url: str | None = None
    context_uri: str | None = None

    @property
    def duration_formatted(self) -> str:
        total_seconds = max(0, self.duration_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"


@dataclass
class LibraryItem:
    """Represents a library entry in Pane 1 (Liked Songs, Playlist, or Album)."""

    id: str
    name: str
    item_type: str  # "liked", "playlist", "album"
    track_count: int
    uri: str | None = None


@dataclass
class AudioSegment:
    """Represents a time slice from Spotify's audio-analysis or synthesized beat map."""

    start: float
    duration: float
    loudness_max: float  # dB typically -60 to 0
    pitches: list[float] = field(default_factory=lambda: [0.5] * 12)


@dataclass
class PlaybackState:
    """Snapshot of the active Spotify Connect playback status."""

    is_playing: bool = False
    track: TrackItem | None = None
    progress_ms: int = 0
    volume_percent: int = 75
    shuffle_state: bool = False
    repeat_state: str = "off"  # "off", "context" (ALL), "track" (TRACK)
    device_id: str | None = None
    device_name: str = "No Active Device"
    tempo_bpm: float = 120.0
    energy: float = 0.72

    @property
    def repeat_label(self) -> str:
        mapping = {
            "off": "OFF",
            "context": "ALL",
            "track": "TRK",
        }
        return mapping.get(self.repeat_state, "OFF")

    @property
    def shuffle_label(self) -> str:
        return "ON" if self.shuffle_state else "OFF"
