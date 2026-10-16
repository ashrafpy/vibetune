"""Pane 2: Tracklist & Inline Header Search widget ([F2] Tracklist).

In non-tech terms:
This is the main song table on the right side of the screen.
- It lists all the songs in the currently selected playlist with columns for
  track number, song title, artist, and duration.
- It keeps foreign characters (like Japanese, Korean, Arabic, or Bengali) neatly
  aligned so columns never get crooked or broken.
- When you press '/', the top of this table becomes a live search bar:
  1. Typing letters filters the current playlist instantly.
  2. Pressing Enter searches the entire Spotify global music catalog.
  3. Pressing Escape restores your previous playlist.
- When you press Enter on a song, music begins playing on your speakers!
"""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from rich.style import Style
from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from vibetune.models import TrackItem


def _fit_cell(text: str, width: int) -> str:
    """Pad or truncate `text` to exact terminal display cell `width` (handles CJK & wide glyphs).
    
    Non-tech summary:
    In terminals, characters like Japanese kanji or emojis take up two spaces instead
    of one. This function measures the real visual space on screen to make sure
    columns remain perfectly straight and never wrap around to ruin the layout.
    """
    clean = " ".join(text.replace("\xa0", " ").splitlines())
    if width <= 0:
        return ""
    if cell_len(clean) > width:
        if width == 1:
            return "…"
        return set_cell_size(clean, width - 1) + "…"
    return set_cell_size(clean, width)


class TracklistPane(Widget):
    """Focusable right-hand tracklist table with inline header search.
    
    Non-tech summary:
    Manages the song table, scrolling, live searching, and track selection.
    """

    can_focus = True

    class TrackActivated(Message):
        """Posted when a track is chosen for playback."""

        def __init__(self, track: TrackItem, all_tracks: list[TrackItem]) -> None:
            super().__init__()
            self.track = track
            self.all_tracks = all_tracks

    class CatalogSearchRequested(Message):
        """Posted when the user presses Enter on a search query to search Spotify's full catalog."""

        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title: str = "Liked Songs"
        self._base_tracks: list[TrackItem] = []
        self._displayed_tracks: list[TrackItem] = []
        self._selected_idx: int = 0
        self._scroll_offset: int = 0
        self._playing_track_id: str | None = None

        # Search mode state
        self._search_mode: bool = False
        self._search_query: str = ""
        self._cursor_pos: int = 0
        self._result_navigated: bool = False
        self._catalog_searched_query: str | None = None

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()

    @property
    def search_mode(self) -> bool:
        return self._search_mode

    @property
    def search_query(self) -> str:
        return self._search_query

    @property
    def displayed_tracks(self) -> list[TrackItem]:
        return self._displayed_tracks

    @property
    def selected_index(self) -> int:
        return self._selected_idx

    def set_tracklist(self, title: str, tracks: list[TrackItem]) -> None:
        """Load the initial batch of a playlist or album tracklist into Pane 2."""
        self._title = title
        self._base_tracks = list(tracks)
        if not self._search_mode:
            self._displayed_tracks = list(tracks)
            self._selected_idx = 0
            self._scroll_offset = 0
        self.refresh()

    def append_tracks(self, title: str, batch: list[TrackItem]) -> None:
        """Append a streamed batch of tracks without resetting cursor or scroll offset."""
        if self._title != title or not batch:
            return
        self._base_tracks.extend(batch)
        if not self._search_mode:
            self._displayed_tracks.extend(batch)
        elif not self._catalog_searched_query:
            q = self._search_query.strip().lower()
            if not q:
                self._displayed_tracks.extend(batch)
            else:
                self._displayed_tracks.extend(
                    t
                    for t in batch
                    if q in t.title.lower() or q in t.artist.lower() or q in t.album.lower()
                )
        self.refresh()

    def set_catalog_search_results(self, query: str, tracks: list[TrackItem]) -> None:
        """Populate table with full Spotify catalog search results."""
        self._displayed_tracks = list(tracks)
        self._selected_idx = 0
        self._scroll_offset = 0
        self._catalog_searched_query = query
        self._result_navigated = True
        self.refresh()

    def set_playing_track(self, track_id: str | None) -> None:
        if self._playing_track_id != track_id:
            self._playing_track_id = track_id
            self.refresh()

    def enter_search_mode(self) -> None:
        self._search_mode = True
        self._search_query = ""
        self._cursor_pos = 0
        self._result_navigated = False
        self._catalog_searched_query = None
        self._displayed_tracks = list(self._base_tracks)
        self._selected_idx = 0
        self._scroll_offset = 0
        self.refresh()

    def exit_search_mode(self, restore_base: bool = False) -> None:
        self._search_mode = False
        self._result_navigated = False
        if restore_base:
            self._search_query = ""
            self._cursor_pos = 0
            self._catalog_searched_query = None
            self._displayed_tracks = list(self._base_tracks)
            self._selected_idx = 0
            self._scroll_offset = 0
        self.refresh()

    def append_search_char(self, ch: str) -> None:
        if not self._search_mode:
            return
        self._search_query = (
            self._search_query[: self._cursor_pos]
            + ch
            + self._search_query[self._cursor_pos :]
        )
        self._cursor_pos += len(ch)
        self._result_navigated = False
        self._catalog_searched_query = None
        self._apply_live_filter()

    def backspace_search_char(self) -> None:
        if not self._search_mode or self._cursor_pos <= 0:
            return
        self._search_query = (
            self._search_query[: self._cursor_pos - 1]
            + self._search_query[self._cursor_pos :]
        )
        self._cursor_pos -= 1
        self._result_navigated = False
        self._catalog_searched_query = None
        self._apply_live_filter()

    def move_search_cursor(self, delta: int) -> None:
        if not self._search_mode:
            return
        self._cursor_pos = max(0, min(len(self._search_query), self._cursor_pos + delta))
        self.refresh()

    def _apply_live_filter(self) -> None:
        q = self._search_query.strip().lower()
        if not q:
            self._displayed_tracks = list(self._base_tracks)
        else:
            self._displayed_tracks = [
                t
                for t in self._base_tracks
                if q in t.title.lower() or q in t.artist.lower() or q in t.album.lower()
            ]
        self._selected_idx = 0
        self._scroll_offset = 0
        self.refresh()

    def move_cursor(self, delta: int) -> None:
        if not self._displayed_tracks:
            return
        if self._search_mode:
            self._result_navigated = True
        self._selected_idx = max(
            0, min(len(self._displayed_tracks) - 1, self._selected_idx + delta)
        )
        self.refresh()

    def get_selected_track(self) -> TrackItem | None:
        if 0 <= self._selected_idx < len(self._displayed_tracks):
            return self._displayed_tracks[self._selected_idx]
        return None

    def handle_enter(self) -> None:
        """Handle Enter in either Normal Mode or Search Mode."""
        if self._search_mode:
            q = self._search_query.strip()
            if q and not self._result_navigated and self._catalog_searched_query != q:
                self.post_message(self.CatalogSearchRequested(q))
                return

            selected = self.get_selected_track()
            if selected:
                self._title = f'Search: "{q}"' if q else self._title
                self.exit_search_mode(restore_base=False)
                self.post_message(self.TrackActivated(selected, list(self._displayed_tracks)))
            elif q:
                self.post_message(self.CatalogSearchRequested(q))
            return

        selected = self.get_selected_track()
        if selected:
            self.post_message(self.TrackActivated(selected, list(self._displayed_tracks)))

    def render(self) -> Text:
        width = self.content_size.width if self.content_size.width > 0 else max(24, self.size.width - 2)
        height = self.content_size.height if self.content_size.height > 0 else max(6, self.size.height)
        focused = self.has_focus

        out = Text(no_wrap=True)
        # Row 0 & Row 1: Header + Subheader / Search Input (strictly fitted to width so headers never wrap!)
        if self._search_mode:
            out.append("[F2] 🔍 Search: ", style="bold #1DB954")
            before = self._search_query[: self._cursor_pos]
            at_cursor = (
                self._search_query[self._cursor_pos]
                if self._cursor_pos < len(self._search_query)
                else " "
            )
            after = (
                self._search_query[self._cursor_pos + 1 :]
                if self._cursor_pos < len(self._search_query)
                else ""
            )
            out.append(before, style="bold #FFFFFF")
            out.append(at_cursor, style=Style(color="#121212", bgcolor="#1DB954", bold=True))
            out.append(after, style="bold #FFFFFF")
            out.append("\n")
            if self._catalog_searched_query:
                sub = f'     (Catalog: "{self._catalog_searched_query}" │ Enter: Play │ Esc: Back)'
            else:
                sub = "     (Enter: Search Spotify │ ↑↓: Select │ Esc: Cancel)"
            out.append(_fit_cell(sub, width) + "\n", style="#1DB954")
        else:
            header_style = "bold #1DB954" if focused else "bold #FFFFFF"
            out.append(_fit_cell(f"[F2] Tracklist: {self._title}", width) + "\n", style=header_style)
            out.append(_fit_cell("     (Press '/' to filter/search)", width) + "\n", style="#B3B3B3")

        # Column widths strictly bounded by `width`:
        # Total row width = idx_w + title_w + 2 + artist_w + 1 + dur_w == width
        idx_w = 4 if width < 48 else 5
        dur_w = 6 if width < 56 else 8
        dur_label = "Time" if dur_w == 6 else "Duration"
        remaining = max(8, width - idx_w - dur_w - 3)
        title_w = max(4, int(remaining * 0.56))
        artist_w = max(4, remaining - title_w)

        # Row 2: Column Headers
        col_hdr = (
            f"{_fit_cell('#', idx_w)}"
            f"{_fit_cell('Title', title_w)}  "
            f"{_fit_cell('Artist', artist_w)} "
            f"{dur_label:>{dur_w}}\n"
        )
        out.append(col_hdr, style="bold #FFFFFF")

        # Row 3: Horizontal Divider
        out.append(("─" * max(8, width)) + "\n", style="#535353")

        # Rows 4+: Track items
        table_rows = max(1, height - 4)
        if not self._displayed_tracks:
            msg = (
                "  No local matches — press Enter to search Spotify…"
                if self._search_mode and self._search_query.strip()
                else "  No tracks loaded."
            )
            out.append(_fit_cell(msg, width), style="#B3B3B3")
            return out

        if self._selected_idx < self._scroll_offset:
            self._scroll_offset = self._selected_idx
        elif self._selected_idx >= self._scroll_offset + table_rows:
            self._scroll_offset = self._selected_idx - table_rows + 1

        visible = self._displayed_tracks[self._scroll_offset : self._scroll_offset + table_rows]

        for rel_i, track in enumerate(visible):
            abs_i = self._scroll_offset + rel_i
            is_selected = abs_i == self._selected_idx
            is_playing = self._playing_track_id is not None and track.id == self._playing_track_id

            num_str = f"{abs_i + 1}"
            marker = ">" if is_playing else " "
            idx_cell = f"{num_str[: idx_w - 1]:<{idx_w - 1}}{marker}"

            t_str = _fit_cell(track.title, title_w)
            a_str = _fit_cell(track.artist, artist_w)
            d_str = f"{track.duration_formatted:>{dur_w}}"

            row_bg = "#282828" if is_selected else None
            if is_playing:
                title_fg = "#1DB954"
                idx_fg = "#1DB954"
            elif is_selected and (focused or self._search_mode):
                title_fg = "#1DB954"
                idx_fg = "#1DB954"
            else:
                title_fg = "#FFFFFF"
                idx_fg = "#B3B3B3"

            artist_fg = "#1DB954" if is_playing else "#B3B3B3"
            dur_fg = "#FFFFFF" if is_selected else "#B3B3B3"

            line = Text(no_wrap=True)
            line.append(idx_cell, style=Style(color=idx_fg, bgcolor=row_bg, bold=is_playing or is_selected))
            line.append(t_str + "  ", style=Style(color=title_fg, bgcolor=row_bg, bold=is_playing or is_selected))
            line.append(a_str + " ", style=Style(color=artist_fg, bgcolor=row_bg))
            line.append(d_str, style=Style(color=dur_fg, bgcolor=row_bg))

            out.append_text(line)
            if rel_i < len(visible) - 1:
                out.append("\n")

        return out
