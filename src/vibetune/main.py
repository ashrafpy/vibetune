"""CLI entry point for VibeTune."""

from __future__ import annotations

from pathlib import Path
from vibetune.app import VibeTuneApp
from vibetune.spotify_client import SpotifyClient


def run() -> None:
    """Launch the VibeTune retro terminal Spotify remote."""
    client = SpotifyClient(env_path=Path.cwd() / ".env.local")
    app = VibeTuneApp(spotify_client=client)
    app.run()


if __name__ == "__main__":
    run()
