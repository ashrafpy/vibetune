"""CLI entry point for VibeTune.

In non-tech terms:
This is the "ignition key" of VibeTune. When you type `vibetune` in your
terminal, this is the very first file that runs. It finds your Spotify
credentials, sets up the connection, and opens the retro player screen.
"""

from __future__ import annotations

from pathlib import Path
from vibetune.app import VibeTuneApp
from vibetune.spotify_client import SpotifyClient


def run() -> None:
    """Launch the VibeTune retro terminal Spotify remote.
    
    Step 1: Read your Spotify secret keys from the `.env.local` file.
    Step 2: Start up the graphical terminal interface (the 'App').
    Step 3: Keep the player running until you press 'q' or close the terminal.
    """
    # Look for your Spotify password/keys in .env.local in the current folder
    client = SpotifyClient(env_path=Path.cwd() / ".env.local")
    
    # Create the terminal window with our Spotify connection
    app = VibeTuneApp(spotify_client=client)
    
    # Hand over control to Textual to draw the UI and listen for keypresses
    app.run()


if __name__ == "__main__":
    # If this file is run directly by Python, start the app!
    run()

