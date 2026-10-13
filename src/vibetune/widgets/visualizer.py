"""Real-time retro audio spectrum visualizer widget for the Top Deck."""

from __future__ import annotations

import math
from rich.text import Text
from textual import events
from textual.widget import Widget

from vibetune.models import AudioSegment

BLOCKS = (" ", "▂", "▃", "▄", "▅", "▆", "▇", "█")
MAX_BANDS = 160


class SpectrumVisualizer(Widget):
    """Non-focusable logarithmic spectrum visualizer that scales across any window/fullscreen width."""

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._is_playing: bool = False
        self._tempo_bpm: float = 120.0
        self._progress_sec: float = 0.0
        self._segments: list[AudioSegment] = []
        self._levels: list[float] = [0.05] * MAX_BANDS
        self._peaks: list[float] = [0.08] * MAX_BANDS

    def _active_band_count(self) -> int:
        width = max(16, self.size.width - 2)
        return max(12, min(MAX_BANDS, width // 2))

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()

    def set_playback_context(
        self,
        is_playing: bool,
        progress_ms: int,
        tempo_bpm: float = 120.0,
        segments: list[AudioSegment] | None = None,
    ) -> None:
        self._is_playing = is_playing
        self._progress_sec = max(0.0, progress_ms / 1000.0)
        self._tempo_bpm = max(60.0, min(200.0, tempo_bpm or 120.0))
        if segments is not None:
            self._segments = segments
        self.refresh()

    def advance_frame(self, dt: float) -> None:
        """Advance visualizer physics and bar smoothing at ~20 FPS."""
        if self._is_playing:
            self._progress_sec += dt

        num_bands = self._active_band_count()
        target_levels = self._compute_targets(num_bands, self._progress_sec)

        for i in range(num_bands):
            target = target_levels[i]
            current = self._levels[i]
            if target > current:
                self._levels[i] = current + (target - current) * min(1.0, dt * 16.0)
            else:
                self._levels[i] = max(0.03, current - dt * 1.45)

            if self._levels[i] >= self._peaks[i]:
                self._peaks[i] = self._levels[i]
            else:
                self._peaks[i] = max(self._levels[i], self._peaks[i] - dt * 0.55)

        self.refresh()

    def _find_active_segment(self, t_sec: float) -> AudioSegment | None:
        if not self._segments:
            return None
        lo, hi = 0, len(self._segments) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            seg = self._segments[mid]
            if seg.start <= t_sec < seg.start + seg.duration:
                return seg
            elif t_sec < seg.start:
                hi = mid - 1
            else:
                lo = mid + 1
        return self._segments[min(len(self._segments) - 1, max(0, lo))]

    def _compute_targets(self, num_bands: int, t_sec: float) -> list[float]:
        if not self._is_playing:
            return [0.04] * num_bands

        seg = self._find_active_segment(t_sec)
        beat_freq = (self._tempo_bpm / 60.0) * math.pi * 2.0
        beat_pulse = 0.5 + 0.5 * math.sin(t_sec * beat_freq)
        sub_pulse = 0.5 + 0.5 * math.cos(t_sec * beat_freq * 0.5)

        if seg:
            loudness_norm = max(0.25, min(1.0, (seg.loudness_max + 35.0) / 35.0))
            pitches = seg.pitches if len(seg.pitches) >= 12 else [0.5] * 12
        else:
            loudness_norm = 0.78
            pitches = [
                0.4 + 0.6 * abs(math.sin(t_sec * 2.3 + idx * 0.6))
                for idx in range(12)
            ]

        targets: list[float] = []
        for b in range(num_bands):
            norm_x = b / max(1, num_bands - 1)
            envelope = math.sin(norm_x * math.pi) ** 0.65
            pitch_idx = int(norm_x * 11.99)
            pitch_val = pitches[pitch_idx]

            harmonic_wave = 0.5 + 0.5 * math.sin(t_sec * (3.5 + (b % 7) * 0.9) + b * 0.45)
            bass_boost = (1.0 - norm_x * 0.5) * (0.28 * beat_pulse + 0.14 * sub_pulse)

            level = loudness_norm * envelope * (0.48 * pitch_val + 0.34 * harmonic_wave + bass_boost)
            targets.append(max(0.06, min(1.0, level)))

        return targets

    def render(self) -> Text:
        height = max(4, self.size.height)
        chart_rows = max(2, height - 1)
        num_bands = self._active_band_count()

        out = Text(no_wrap=True)
        out.append(" ♫ Spectrum Visualizer\n", style="bold #FFFFFF")

        levels = self._levels[:num_bands]

        for row in range(chart_rows):
            row_from_bottom = chart_rows - 1 - row
            row_bottom_thresh = row_from_bottom / chart_rows
            row_top_thresh = (row_from_bottom + 1) / chart_rows

            line = Text(" ", no_wrap=True)
            for b_idx, level in enumerate(levels):
                if level <= row_bottom_thresh:
                    glyph = " "
                elif level >= row_top_thresh:
                    glyph = "█"
                else:
                    frac = (level - row_bottom_thresh) / max(1e-6, row_top_thresh - row_bottom_thresh)
                    glyph_idx = max(1, min(7, int(frac * 8)))
                    glyph = BLOCKS[glyph_idx]

                if row_from_bottom >= chart_rows - 1 and glyph != " ":
                    color = "#45F082"
                elif row_from_bottom >= chart_rows // 2:
                    color = "#1DB954"
                else:
                    color = "#179944"

                line.append(glyph, style=color)
                if b_idx < num_bands - 1:
                    line.append(" ")

            out.append_text(line)
            if row < chart_rows - 1:
                out.append("\n")

        return out
