"""Real-time audio spectrum capture via PipeWire/PulseAudio monitor + NumPy FFT.

When VibeTune plays audio locally through `go-librespot`, this module taps the
system's PipeWire/PulseAudio monitor stream using `parec`, applies a Hann-windowed
real FFT (`numpy.fft.rfft`), and bins the magnitudes logarithmically from 60 Hz
to 16 kHz for the 20 FPS retro spectrum visualizer.

When `parec` is unavailable or playback is on a remote Spotify Connect device,
the visualizer falls back seamlessly to its tempo/harmonic synthesizer.
"""

from __future__ import annotations

import atexit
import logging
import shutil
import subprocess
import threading

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
FFT_SIZE = 2048
MIN_FREQ_HZ = 60.0
MAX_FREQ_HZ = 16000.0


def compute_bands_from_samples(
    samples: np.ndarray,
    num_bands: int,
    sample_rate: int = SAMPLE_RATE,
    min_hz: float = MIN_FREQ_HZ,
    max_hz: float = MAX_FREQ_HZ,
) -> list[float]:
    """Compute `num_bands` logarithmically-spaced normalized FFT band heights in [0.0, 1.0]."""
    if num_bands <= 0 or samples.size == 0:
        return []

    n = samples.size
    window = np.hanning(n).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(samples * window)) / (n * 0.5)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    # Logarithmically spaced frequency edges from min_hz to max_hz
    edges = np.geomspace(min_hz, min(max_hz, sample_rate / 2.0 - 1.0), num_bands + 1)

    bands: list[float] = []
    for i in range(num_bands):
        lo_hz = edges[i]
        hi_hz = edges[i + 1]
        lo_idx = int(np.searchsorted(freqs, lo_hz, side="left"))
        hi_idx = int(np.searchsorted(freqs, hi_hz, side="right"))
        if hi_idx <= lo_idx:
            hi_idx = min(spectrum.size, lo_idx + 1)
        mag = float(np.max(spectrum[lo_idx:hi_idx])) if lo_idx < spectrum.size else 0.0
        # Convert linear magnitude to dB in [-60 dB, -6 dB] -> [0.0, 1.0]
        db = 20.0 * np.log10(max(mag, 1e-6))
        norm = (db + 60.0) / 54.0
        # Subtle treble lift so high hats & vocals stay visible alongside bass
        treble_boost = 1.0 + 0.25 * (i / max(1, num_bands - 1))
        bands.append(float(max(0.0, min(1.0, norm * treble_boost))))

    return bands


class LiveAudioSpectrum:
    """Captures live PipeWire/PulseAudio monitor PCM via `parec` and serves FFT bands."""

    def __init__(
        self,
        device: str = "@DEFAULT_MONITOR@",
        sample_rate: int = SAMPLE_RATE,
        fft_size: int = FFT_SIZE,
    ) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self._lock = threading.Lock()
        self._latest_samples: np.ndarray | None = None
        self._has_signal: bool = False
        self._proc: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        atexit.register(self.stop)

    @staticmethod
    def is_available() -> bool:
        """Return True if `parec` is installed on this system."""
        return shutil.which("parec") is not None

    @property
    def is_running(self) -> bool:
        return (
            self._proc is not None
            and self._proc.poll() is None
            and not self._stop_event.is_set()
        )

    def start(self) -> bool:
        """Start the background `parec` capture subprocess and reader thread."""
        if self.is_running:
            return True
        parec_bin = shutil.which("parec")
        if not parec_bin:
            log.debug("parec not found; live FFT spectrum disabled")
            return False

        self._stop_event.clear()
        cmd = [
            parec_bin,
            "--format=float32le",
            f"--rate={self.sample_rate}",
            "--channels=1",
            "--latency-msec=25",
            f"--device={self.device}",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            log.debug("Failed to start parec: %s", exc)
            self._proc = None
            return False

        self._thread = threading.Thread(
            target=self._reader_loop,
            name="vibetune-live-fft",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop `parec` and clear buffered audio samples."""
        self._stop_event.set()
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass
        with self._lock:
            self._latest_samples = None
            self._has_signal = False

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        chunk_bytes = self.fft_size * 4  # float32 = 4 bytes/sample
        buf = bytearray()
        while not self._stop_event.is_set():
            try:
                data = proc.stdout.read(chunk_bytes - len(buf))
            except (OSError, ValueError):
                break
            if not data:
                break
            buf.extend(data)
            if len(buf) >= chunk_bytes:
                samples = np.frombuffer(bytes(buf[:chunk_bytes]), dtype=np.float32).copy()
                del buf[:chunk_bytes]
                rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
                with self._lock:
                    self._latest_samples = samples
                    self._has_signal = rms > 1e-4

    def get_bands(self, num_bands: int) -> list[float] | None:
        """Return latest live FFT band levels in [0.0, 1.0], or None if inactive/silent."""
        if not self.is_running:
            return None
        with self._lock:
            samples = self._latest_samples
            has_signal = self._has_signal
        if samples is None or not has_signal:
            return None
        return compute_bands_from_samples(
            samples,
            num_bands=num_bands,
            sample_rate=self.sample_rate,
        )
