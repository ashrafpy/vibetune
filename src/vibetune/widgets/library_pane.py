"""Pane 1: Library navigation widget ([F1] Library).

In non-tech terms:
This is the left-hand menu of VibeTune.
- It displays a vertical list of your music folders: "Liked Songs", your playlists,
  saved albums (marked with ◉), and favorite artists (marked with ♪).
- When you use the Up/Down arrow keys and hit Enter, it tells the rest of the app
  to fetch and display that collection's songs in the right-hand table.
"""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size
from rich.style import Style
from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from vibetune.models import LibraryItem


def _fit_cell(text: str, width: int) -> str:
    """Trim text to fit the exact width of the sidebar without spilling over."""
    clean = " ".join(text.replace("\xa0", " ").splitlines())
    if width <= 0:
        return ""
    if cell_len(clean) > width:
        if width == 1:
            return "…"
        return set_cell_size(clean, width - 1) + "…"
    return set_cell_size(clean, width)


class LibraryPane(Widget):
    """Focusable left-hand library navigation pane listing Liked Songs, Playlists, and Albums.
    
    Non-tech summary:
    Manages the highlighted row in the sidebar, scrolling automatically if you have
    more playlists than can fit on screen at once.
    """

    can_focus = True

    class ItemSelected(Message):
        """Posted when the user activates a library item with Enter."""

        def __init__(self, item: LibraryItem) -> None:
            super().__init__()
            self.item = item

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: list[LibraryItem] = []
        self._selected_idx: int = 0
        self._active_item_id: str = "liked_songs"
        self._scroll_offset: int = 0

    def on_resize(self, event: events.Resize) -> None:
        self.refresh()

    @property
    def items(self) -> list[LibraryItem]:
        return self._items

    @property
    def selected_index(self) -> int:
        return self._selected_idx

    def set_items(self, items: list[LibraryItem]) -> None:
        self._items = items
        if self._selected_idx >= len(items):
            self._selected_idx = max(0, len(items) - 1)
        self.refresh()

    def set_active_item(self, item_id: str) -> None:
        self._active_item_id = item_id
        self.refresh()

    def move_cursor(self, delta: int) -> None:
        if not self._items:
            return
        self._selected_idx = max(0, min(len(self._items) - 1, self._selected_idx + delta))
        self.refresh()

    def get_selected_item(self) -> LibraryItem | None:
        if 0 <= self._selected_idx < len(self._items):
            return self._items[self._selected_idx]
        return None

    def activate_selected(self) -> LibraryItem | None:
        item = self.get_selected_item()
        if item:
            self._active_item_id = item.id
            self.post_message(self.ItemSelected(item))
            self.refresh()
        return item

    def render(self) -> Text:
        width = self.content_size.width if self.content_size.width > 0 else max(12, self.size.width - 2)
        height = self.content_size.height if self.content_size.height > 0 else max(4, self.size.height)
        focused = self.has_focus

        out = Text(no_wrap=True)
        header_style = "bold #1DB954" if focused else "bold #FFFFFF"
        out.append(_fit_cell("[F1] Library", width) + "\n", style=header_style)
        out.append("\n")

        list_rows = max(1, height - 2)
        if not self._items:
            out.append(_fit_cell("  Loading library…", width), style="#535353")
            return out

        if self._selected_idx < self._scroll_offset:
            self._scroll_offset = self._selected_idx
        elif self._selected_idx >= self._scroll_offset + list_rows:
            self._scroll_offset = self._selected_idx - list_rows + 1

        visible = self._items[self._scroll_offset : self._scroll_offset + list_rows]

        for rel_idx, item in enumerate(visible):
            abs_idx = self._scroll_offset + rel_idx
            is_selected = abs_idx == self._selected_idx
            is_active = item.id == self._active_item_id

            count_str = f"({item.track_count})"
            prefix = "> " if is_selected else ("• " if is_active else "  ")
            name_cell_width = max(3, width - len(prefix) - len(count_str) - 1)
            name_fitted = _fit_cell(item.name, name_cell_width)

            row_bg = "#282828" if is_selected else None
            if is_selected and focused:
                name_fg = "#1DB954"
                prefix_fg = "#1DB954"
            elif is_active:
                name_fg = "#1DB954"
                prefix_fg = "#1DB954"
            elif is_selected:
                name_fg = "#FFFFFF"
                prefix_fg = "#FFFFFF"
            else:
                name_fg = "#B3B3B3"
                prefix_fg = "#535353"

            line = Text(no_wrap=True)
            line.append(prefix, style=Style(color=prefix_fg, bgcolor=row_bg, bold=is_selected or is_active))
            line.append(name_fitted + " ", style=Style(color=name_fg, bgcolor=row_bg, bold=is_selected or is_active))
            line.append(count_str, style=Style(color="#535353", bgcolor=row_bg))

            out.append_text(line)
            if rel_idx < len(visible) - 1:
                out.append("\n")

        return out
