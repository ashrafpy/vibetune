"""Data models for VibeTune playback, library items, and tracks.

Think of this file as a collection of standardized digital index cards.
Instead of passing messy bundles of raw Spotify data around the app, we organize
everything into neat, predictable cards:
1. `TrackItem`: An index card describing a single song (title, singer, duration, album cover).
2. `LibraryItem`: A folder label for your collections (like "Liked Songs", a playlist, or an album).
3. `AudioSegment`: A microscopic slice of musical energy used to bounce the visualizer bars.
4. `PlaybackState`: A real-time status board showing whether music is playing, what song is on,
   which speaker is active, and current volume.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackItem:
    """Represents a single Spotify track in a tracklist or search result.
    
    This card stores all the essential details about one song so VibeTune can
    display it in the song table and show its album cover.
    """

    id: str                         # Spotify's unique ID for the song
    uri: str                        # Spotify's internal link (e.g. spotify:track:...)
    title: str                      # Name of the song (e.g. 'Midnight City')
    artist: str                     # Artist or band names (e.g. 'M83')
    album: str                      # Album name (e.g. 'Hurry Up, We're Dreaming')
    release_year: str               # 4-digit release year (e.g. '2011')
    duration_ms: int                # Length of the song in milliseconds (1 sec = 1,000 ms)
    album_art_url: str | None = None  # Web link to download the album cover picture
    context_uri: str | None = None    # Which playlist/album this song came from

    @property
    def duration_formatted(self) -> str:
        """Converts raw milliseconds into a friendly 'MM:SS' time format (like '03:45')."""
        total_seconds = max(0, self.duration_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"


@dataclass
class LibraryItem:
    """Represents a library entry in Pane 1 (Liked Songs, Playlist, or Album).
    
    This represents an item in your left-hand sidebar menu, such as a playlist
    or your saved albums collection.
    """

    id: str             # Unique ID for the playlist or album
    name: str           # Display name (e.g., 'Discover Weekly' or 'Daily Mix 1')
    item_type: str      # Category: 'liked', 'playlist', or 'album'
    track_count: int    # Total number of songs inside this collection
    uri: str | None = None  # Spotify URI for loading the collection


@dataclass
class AudioSegment:
    """Represents a time slice from Spotify's audio-analysis or synthesized beat map.
    
    Music is broken down into split-second slices. Each slice tells us how loud
    the music is and which musical pitches are hitting, so our retro visualizer
    can dance accurately to the beat.
    """

    start: float        # Timestamp in seconds when this audio slice begins
    duration: float     # How long this slice lasts (in seconds)
    loudness_max: float # Volume in decibels (dB), usually from -60 (whisper) to 0 (loudest)
    pitches: list[float] = field(default_factory=lambda: [0.5] * 12)  # 12 musical notes (C, C#, D, etc.)


@dataclass
class PlaybackState:
    """Snapshot of the active Spotify Connect playback status.
    
    This is the live scoreboard of your music player. Every couple of seconds,
    VibeTune updates this board to know if the song is paused, what time it is at,
    and which speaker the sound is coming out of.
    """

    is_playing: bool = False             # True if music is currently playing; False if paused
    track: TrackItem | None = None       # The song currently loaded (or None if nothing is playing)
    progress_ms: int = 0                 # How far into the song we are, in milliseconds
    volume_percent: int = 75             # Current volume from 0% (mute) to 100% (max)
    shuffle_state: bool = False          # True if shuffle is turned on
    repeat_state: str = "off"            # Repeat mode: 'off', 'context' (loop all), or 'track' (loop one)
    device_id: str | None = None         # ID of the speaker/phone currently playing
    device_name: str = "No Active Device"# Human-friendly name of the speaker/phone
    tempo_bpm: float = 120.0             # Speed of the song in beats per minute
    energy: float = 0.72                 # Spotify energy rating from 0.0 (calm) to 1.0 (energetic)

    @property
    def repeat_label(self) -> str:
        """User-friendly text label for the repeat button ('OFF', 'ALL', or 'TRK')."""
        mapping = {
            "off": "OFF",
            "context": "ALL",
            "track": "TRK",
        }
        return mapping.get(self.repeat_state, "OFF")

    @property
    def shuffle_label(self) -> str:
        """User-friendly text label for the shuffle button ('ON' or 'OFF')."""
        return "ON" if self.shuffle_state else "OFF"
