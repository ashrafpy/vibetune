"""CLI entry point for VibeTune.

This is the "ignition key" of VibeTune. When you type `vibetune` in your
terminal, this is the very first file that runs. It finds your Spotify
credentials, sets up the connection, and opens the retro player screen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vibetune import __version__
from vibetune.app import VibeTuneApp
from vibetune.spotify_client import SpotifyClient


def run() -> None:
    """Launch the VibeTune retro terminal Spotify remote.

    Parses CLI arguments, initializes the Spotify client, and starts
    the Textual TUI application.
    """
    parser = argparse.ArgumentParser(
        prog="vibetune",
        description="VibeTune — Retro Terminal Spotify Connect Remote",
    )
    parser.add_argument(
        "--version", action="version", version=f"VibeTune {__version__}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.cwd() / ".env.local",
        help="Path to .env.local credentials file (default: ./.env.local)",
    )
    args = parser.parse_args()

    client = SpotifyClient(env_path=args.config)
    app = VibeTuneApp(spotify_client=client)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"VibeTune error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
