"""CLI entry point for VibeTune.

This is the "ignition key" of VibeTune. When you type `vibetune` in your
terminal, this is the very first file that runs. It finds your Spotify
credentials, optionally launches the embedded `go-librespot` local audio
engine + real-time FFT spectrum capture, and opens the retro player screen.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from vibetune import __version__
from vibetune.app import VibeTuneApp
from vibetune.audio_capture import LiveAudioSpectrum
from vibetune.local_player import LocalPlayerConfig, LocalPlayerDaemon
from vibetune.paths import default_audio_backend, get_env_file_path
from vibetune.spotify_client import SpotifyClient


def _configure_stdio() -> None:
    """Ensure UTF-8 stdio encoding so Unicode/emoji output never fails on Windows codepages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for VibeTune."""
    parser = argparse.ArgumentParser(
        prog="vibetune",
        description="VibeTune — Retro Terminal Spotify Client & Connect Remote",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"VibeTune {__version__}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to .env credentials file (default: ./.env.local, ./.env, or user config dir)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Interactive wizard to save your Spotify Developer API credentials",
    )
    parser.add_argument(
        "--remote-only",
        action="store_true",
        help="Disable the embedded local audio engine and run purely as a Spotify Connect remote",
    )
    parser.add_argument(
        "--auth-player",
        action="store_true",
        help="Run interactive go-librespot OAuth login in the terminal and exit",
    )
    parser.add_argument(
        "--device-name",
        default="VibeTune",
        help="Spotify Connect device name for the local audio engine (default: VibeTune)",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        choices=(96, 160, 320),
        default=320,
        help="Audio streaming bitrate in kbps for local playback (default: 320)",
    )
    parser.add_argument(
        "--audio-backend",
        choices=("auto", "pulseaudio", "alsa", "audio-toolbox", "wasapi", "pipe"),
        default="auto",
        help=(
            "Audio backend for go-librespot "
            "(default: auto -> pulseaudio on Linux, audio-toolbox on macOS, wasapi on Windows)"
        ),
    )
    parser.add_argument(
        "--no-live-fft",
        action="store_true",
        help=(
            "Disable real-time PipeWire/PulseAudio FFT capture on Linux and use "
            "synthesized visualizer (automatic on macOS/Windows)"
        ),
    )
    return parser


def run_setup(config_path: Path | None = None) -> int:
    """Prompt the user for Spotify API credentials and save them to the config file."""
    target = config_path or get_env_file_path()
    default_redirect = "http://127.0.0.1:8888/callback"

    print("VibeTune Setup — Spotify Developer App Credentials")
    print("Create an app at: https://developer.spotify.com/dashboard")
    print(f"Redirect URI to register in your Spotify app: {default_redirect}\n")

    try:
        client_id = input("SPOTIPY_CLIENT_ID: ").strip()
        client_secret = input("SPOTIPY_CLIENT_SECRET: ").strip()
        redirect_uri = input(f"SPOTIPY_REDIRECT_URI [{default_redirect}]: ").strip() or default_redirect
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.", file=sys.stderr)
        return 1

    if not client_id or not client_secret:
        print("Error: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET are required.", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "# VibeTune Spotify Developer App credentials\n"
        f"SPOTIPY_CLIENT_ID={client_id}\n"
        f"SPOTIPY_CLIENT_SECRET={client_secret}\n"
        f"SPOTIPY_REDIRECT_URI={redirect_uri}\n"
    )
    target.write_text(content, encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass

    print(f"\nSaved Spotify credentials to: {target}")
    print("Next steps:")
    print("  1. (Optional) Authenticate local audio playback: vibetune --auth-player")
    print("  2. Launch VibeTune: vibetune")
    return 0


def run(argv: list[str] | None = None) -> None:
    """Launch the VibeTune retro terminal Spotify client.

    Parses CLI arguments, initializes the Spotify client and optional local
    `go-librespot` playback engine, and starts the Textual TUI application.
    """
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.setup:
        sys.exit(run_setup(config_path=args.config))

    audio_backend = (
        default_audio_backend()
        if args.audio_backend == "auto"
        else args.audio_backend
    )

    local_config = LocalPlayerConfig(
        device_name=args.device_name,
        bitrate=args.bitrate,
        audio_backend=audio_backend,
    )

    if args.auth_player:
        daemon = LocalPlayerDaemon(config=local_config)
        rc = daemon.run_interactive_auth()
        if daemon.last_error:
            print(f"VibeTune error: {daemon.last_error}", file=sys.stderr)
        sys.exit(rc)

    local_daemon: LocalPlayerDaemon | None = None
    audio_spectrum: LiveAudioSpectrum | None = None
    if not args.remote_only:
        local_daemon = LocalPlayerDaemon(config=local_config)
        if not args.no_live_fft:
            audio_spectrum = LiveAudioSpectrum()

    client = SpotifyClient(
        env_path=args.config,
        preferred_device_name=None if args.remote_only else args.device_name,
    )
    app = VibeTuneApp(
        spotify_client=client,
        local_player=local_daemon,
        audio_spectrum=audio_spectrum,
    )

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"VibeTune error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
