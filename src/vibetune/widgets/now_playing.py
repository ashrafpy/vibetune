"""Now Playing & Controls dashboard widget with responsive high-res 2x3 Sextant album art.

This file builds the top-right corner of VibeTune:
- It downloads the album cover picture from Spotify and performs a clever trick:
  terminals usually can only show text letters, but this code cuts each character
  cell into 6 tiny subpixels (2 wide by 3 tall) using special Unicode 'Sextant'
  characters. This lets it paint full-color album covers in your terminal!
- It also displays the song title, artist, album name, year, and volume.
- It draws the timeline bar (progress bar) that moves forward as the song plays.
"""

from __future__ import annotations

from io import BytesIO
import httpx
from PIL import Image, ImageEnhance
from rich.cells import cell_len, set_cell_size
from rich.style import Style
from rich.text import Text
from textual import events
from textual.widget import Widget

from vibetune.models import PlaybackState

# Full Top-Deck art size (wide mode): 14 cols x 7 rows = 28x21 subpixels
WIDE_ART_WIDTH = 14
WIDE_ART_ROWS = 7

# Compact tile art size (narrow tile mode): 9 cols x 4 rows = 18x12 subpixels
COMPACT_ART_WIDTH = 9
COMPACT_ART_ROWS = 4

# Default exported constants for unit tests
ART_CELL_WIDTH = WIDE_ART_WIDTH
ART_CELL_ROWS = WIDE_ART_ROWS


def _build_sextant_table() -> tuple[str, ...]:
    """Precompute the 64 Unicode Sextant characters (U+1FB00 to U+1FB3B)."""
    table: list[str] = []
    code = 0x1FB00
    for mask in range(64):
        if mask == 0:
            ch = " "
        elif mask == 0b010101:
            ch = "▌"
        elif mask == 0b101010:
            ch = "▐"
        elif mask == 0b111111:
            ch = "█"
        else:
            ch = chr(code)
            code += 1
        table.append(ch)
    return tuple(table)


SEXTANT_CHARS = _build_sextant_table()


def _fit_cell(text: str, width: int) -> str:
    """Trim or pad text to fit exact character width in the terminal."""
    clean = " ".join(text.replace("\xa0", " ").splitlines())
    if width <= 0:
        return ""
    if cell_len(clean) > width:
        if width == 1:
            return "…"
        return set_cell_size(clean, width - 1) + "…"
    return set_cell_size(clean, width)


def _crop_text_line(line: Text, max_cells: int) -> Text:
    """Ensure a Rich Text line never exceeds `max_cells` terminal columns."""
    if max_cells <= 0:
        return Text("", no_wrap=True)
    plain_cells = cell_len(line.plain)
    if plain_cells <= max_cells:
        return line
    cropped = line.copy()
    cropped.truncate(max_cells, overflow="ellipsis")
    return cropped


def render_halfblock_art(
    image_bytes: bytes,
    width: int = WIDE_ART_WIDTH,
    height_rows: int = WIDE_ART_ROWS,
) -> list[Text]:
    """Render high-res album art into `width x height_rows` cells using 2x3 Unicode Sextants."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    sub_w = width * 2
    sub_h = height_rows * 3
    img = img.resize((sub_w, sub_h), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.16)
    img = ImageEnhance.Sharpness(img).enhance(1.30)
    pixels = img.load()

    rows: list[Text] = []
    for r in range(height_rows):
        line = Text(no_wrap=True)
        y0 = r * 3
        for c in range(width):
            x0 = c * 2
            pts = [
                pixels[x0, y0],          # 0: TL
                pixels[x0 + 1, y0],      # 1: TR
                pixels[x0, y0 + 1],      # 2: ML
                pixels[x0 + 1, y0 + 1],  # 3: MR
                pixels[x0, y0 + 2],      # 4: BL
                pixels[x0 + 1, y0 + 2],  # 5: BR
            ]

            mr = sum(p[0] for p in pts) / 6.0
            mg = sum(p[1] for p in pts) / 6.0
            mb = sum(p[2] for p in pts) / 6.0

            best_dist = -1.0
            vr, vg, vb = 1.0, 1.0, 1.0
            for pr, pg, pb in pts:
                dr, dg, db = pr - mr, pg - mg, pb - mb
                d = dr * dr + dg * dg + db * db
                if d > best_dist:
                    best_dist = d
                    vr, vg, vb = dr, dg, db

            if best_dist < 4.0:
                ir, ig, ib = int(mr), int(mg), int(mb)
                c_hex = f"#{ir:02x}{ig:02x}{ib:02x}"
                line.append("█", style=Style(color=c_hex, bgcolor=c_hex))
                continue

            mask = 0
            fg_pts: list[tuple[int, int, int]] = []
            bg_pts: list[tuple[int, int, int]] = []
            for bit_idx, p in enumerate(pts):
                proj = (p[0] - mr) * vr + (p[1] - mg) * vg + (p[2] - mb) * vb
                if proj >= 0.0:
                    mask |= 1 << bit_idx
                    fg_pts.append(p)
                else:
                    bg_pts.append(p)

            if not fg_pts:
                fg_pts = [pts[0]]
                mask = 1
            elif not bg_pts:
                bg_pts = [pts[-1]]
                mask = 0b011111

            nf = len(fg_pts)
            nb = len(bg_pts)
            fr = sum(p[0] for p in fg_pts) // nf
            fg = sum(p[1] for p in fg_pts) // nf
            fb = sum(p[2] for p in fg_pts) // nf

            br = sum(p[0] for p in bg_pts) // nb
            bg = sum(p[1] for p in bg_pts) // nb
            bb = sum(p[2] for p in bg_pts) // nb

            glyph = SEXTANT_CHARS[mask]
            style = Style(
                color=f"#{fr:02x}{fg:02x}{fb:02x}",
                bgcolor=f"#{br:02x}{bg:02x}{bb:02x}",
            )
            line.append(glyph, style=style)
        rows.append(line)
    return rows


def default_retro_art(
    width: int = WIDE_ART_WIDTH,
    height_rows: int = WIDE_ART_ROWS,
) -> list[Text]:
    """Fallback retro vinyl disc art at the requested (width, height_rows) dimensions."""
    sub_w = width * 2
    sub_h = height_rows * 3
    img = Image.new("RGB", (sub_w, sub_h), color=(20, 20, 20))
    px = img.load()
    cx, cy = (sub_w - 1) / 2.0, (sub_h - 1) / 2.0
    max_r = min(cx, cy)
    for y in range(sub_h):
        for x in range(sub_w):
            dx = (x - cx) / max(1.0, cx)
            dy = (y - cy) / max(1.0, cy)
            norm_d = (dx * dx + dy * dy) ** 0.5
            if x in (0, sub_w - 1) or y in (0, sub_h - 1):
                px[x, y] = (29, 185, 84)
            elif 0.80 <= norm_d <= 0.94:
                px[x, y] = (29, 185, 84)
            elif 0.50 <= norm_d <= 0.62:
                px[x, y] = (45, 95, 65)
            elif 0.18 <= norm_d <= 0.34:
                px[x, y] = (29, 185, 84)
            elif norm_d < 0.18:
                px[x, y] = (18, 18, 18)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return render_halfblock_art(buf.getvalue(), width=width, height_rows=height_rows)


def _format_ms(ms: int) -> str:
    total_sec = max(0, ms // 1000)
    minutes, seconds = divmod(total_sec, 60)
    return f"{minutes:02d}:{seconds:02d}"


class NowPlayingDeck(Widget):
    """Responsive Top Deck widget that adapts Album Art & Controls to both small tiles and fullscreen."""

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state: PlaybackState = PlaybackState()
        self._loaded_art_url: str | None = None
        self._raw_art_cache: dict[str, bytes] = {}
        self._rendered_cache: dict[tuple[str, int, int], list[Text]] = {}

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()

    def update_state(self, state: PlaybackState) -> None:
        self._state = state
        art_url = state.track.album_art_url if state.track else None
        if not art_url:
            self._loaded_art_url = None
        elif art_url in self._raw_art_cache:
            self._loaded_art_url = art_url
        elif art_url != self._loaded_art_url:
            self._loaded_art_url = art_url
            self.run_worker(self._fetch_album_art(art_url), exclusive=True)
        self.refresh()

    def advance_progress(self, dt_ms: int) -> None:
        if self._state.is_playing and self._state.track:
            self._state.progress_ms = min(
                self._state.track.duration_ms,
                self._state.progress_ms + dt_ms,
            )
            self.refresh()

    async def _fetch_album_art(self, url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                self._raw_art_cache[url] = resp.content
                if self._loaded_art_url == url:
                    self.refresh()
        except Exception:
            if self._loaded_art_url == url:
                self.refresh()

    def _get_art_lines(self, width: int, height_rows: int) -> list[Text]:
        url = self._loaded_art_url
        if url and url in self._raw_art_cache:
            key = (url, width, height_rows)
            if key not in self._rendered_cache:
                try:
                    self._rendered_cache[key] = render_halfblock_art(
                        self._raw_art_cache[url],
                        width=width,
                        height_rows=height_rows,
                    )
                except Exception:
                    self._rendered_cache[key] = default_retro_art(width, height_rows)
            return self._rendered_cache[key]
        return default_retro_art(width, height_rows)

    def _build_scrub_line(self, avail_w: int, is_playing: bool, progress_ms: int, duration_ms: int) -> Text:
        play_icon = "▶" if is_playing else "⏸"
        elapsed_str = _format_ms(progress_ms)
        total_str = _format_ms(duration_ms)
        # Prefix "[▶] 05:58 " is 10 chars, suffix " 07:14" is 6 chars -> 16 chars
        bar_width = max(4, min(26, avail_w - 16))
        ratio = (progress_ms / duration_ms) if duration_ms > 0 else 0.0
        thumb_pos = min(bar_width - 1, max(0, int(ratio * (bar_width - 1))))

        line = Text(no_wrap=True)
        line.append("[", style="#535353")
        line.append(play_icon, style="bold #1DB954" if is_playing else "#B3B3B3")
        line.append(f"] {elapsed_str} ", style="bold #FFFFFF")
        if thumb_pos > 0:
            line.append("━" * thumb_pos, style="#1DB954")
        line.append("●", style="bold #1DB954")
        remaining = bar_width - 1 - thumb_pos
        if remaining > 0:
            line.append("━" * remaining, style="#535353")
        line.append(f" {total_str}", style="#B3B3B3")
        return _crop_text_line(line, avail_w)

    def _build_modes_line(self, avail_w: int, state: PlaybackState) -> Text:
        shuf_style = "bold #1DB954" if state.shuffle_state else "#B3B3B3"
        rep_style = "bold #1DB954" if state.repeat_state != "off" else "#B3B3B3"
        line = Text(no_wrap=True)
        if avail_w >= 26:
            line.append("🔀 ")
            line.append(f"[s:{state.shuffle_label}]", style=shuf_style)
            line.append(" 🔁 ")
            line.append(f"[r:{state.repeat_label}]", style=rep_style)
            line.append(f" [{state.volume_percent}%]", style="bold #FFFFFF")
        else:
            line.append(f"[s:{state.shuffle_label}] ", style=shuf_style)
            line.append(f"[r:{state.repeat_label}] ", style=rep_style)
            line.append(f"[{state.volume_percent}%]", style="bold #FFFFFF")
        return _crop_text_line(line, avail_w)

    def _build_ctrl_line(self, avail_w: int, is_playing: bool) -> Text:
        line = Text(no_wrap=True)
        line.append("[p:⏮]", style="#B3B3B3")
        line.append(" ")
        line.append(
            f"[Space:{'⏸' if is_playing else '▶'}]",
            style="bold #1DB954" if is_playing else "#FFFFFF",
        )
        line.append(" ")
        line.append("[n:⏭]", style="#B3B3B3")
        if avail_w >= 25:
            line.append(" ")
            line.append("[d:📱]", style="#1DB954")
        return _crop_text_line(line, avail_w)

    def render(self) -> Text:
        # Strictly respect actual widget content width so lines NEVER wrap in small tiles
        avail_w = self.content_size.width if self.content_size.width > 0 else max(20, self.size.width - 2)
        state = self._state
        track = state.track

        if track:
            title_str = track.title
            artist_str = track.artist
            album_str = (
                f"{track.album} ({track.release_year})"
                if track.release_year
                else track.album
            )
            duration_ms = max(1, track.duration_ms)
            progress_ms = min(duration_ms, max(0, state.progress_ms))
        else:
            title_str = "Ready to Vibe"
            artist_str = "Select a track or press Space"
            album_str = f"Device: {state.device_name}"
            duration_ms = 0
            progress_ms = 0

        out = Text(no_wrap=True)
        out.append(_fit_cell("Now Playing & Controls", avail_w) + "\n", style="bold #FFFFFF")

        # Responsive breakpoint:
        # - Wide mode (avail_w >= 44): 14x7 Sextant art (28x21 subpixels) on left + 7 lines on right
        # - Compact tile mode (avail_w < 44): 9x4 Sextant art (18x12 subpixels) + 4 metadata lines on right,
        #   and full-width scrub bar / modes / controls on rows 5..7 below the art!
        if avail_w >= 44:
            art_w, art_h = WIDE_ART_WIDTH, WIDE_ART_ROWS
            art = self._get_art_lines(art_w, art_h)
            right_w = max(8, avail_w - art_w - 2)

            right_lines = [
                Text(_fit_cell(title_str, right_w), style="bold #FFFFFF", no_wrap=True),
                Text(_fit_cell(artist_str, right_w), style="#B3B3B3", no_wrap=True),
                Text(_fit_cell(album_str, right_w), style="#B3B3B3", no_wrap=True),
                Text(
                    _fit_cell(f"◈ {state.device_name}", right_w),
                    style="#1DB954" if state.device_id else "#535353",
                    no_wrap=True,
                ),
                self._build_scrub_line(right_w, state.is_playing, progress_ms, duration_ms),
                self._build_modes_line(right_w, state),
                self._build_ctrl_line(right_w, state.is_playing),
            ]

            for i in range(art_h):
                out.append_text(art[i])
                out.append("  ")
                out.append_text(right_lines[i])
                if i < art_h - 1:
                    out.append("\n")
        else:
            art_w, art_h = COMPACT_ART_WIDTH, COMPACT_ART_ROWS
            art = self._get_art_lines(art_w, art_h)
            meta_w = max(4, avail_w - art_w - 2)

            meta_lines = [
                Text(_fit_cell(title_str, meta_w), style="bold #FFFFFF", no_wrap=True),
                Text(_fit_cell(artist_str, meta_w), style="#B3B3B3", no_wrap=True),
                Text(_fit_cell(album_str, meta_w), style="#B3B3B3", no_wrap=True),
                Text(
                    _fit_cell(f"◈ {state.device_name}", meta_w),
                    style="#1DB954" if state.device_id else "#535353",
                    no_wrap=True,
                ),
            ]

            for i in range(art_h):
                out.append_text(art[i])
                out.append("  ")
                out.append_text(meta_lines[i])
                out.append("\n")

            out.append_text(self._build_scrub_line(avail_w, state.is_playing, progress_ms, duration_ms))
            out.append("\n")
            out.append_text(self._build_modes_line(avail_w, state))
            out.append("\n")
            out.append_text(self._build_ctrl_line(avail_w, state.is_playing))

        return out
