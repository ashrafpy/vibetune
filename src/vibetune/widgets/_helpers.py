"""Shared text-formatting utilities for VibeTune TUI widgets."""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size


def fit_cell(text: str, width: int) -> str:
    """Pad or truncate ``text`` to exact terminal display-cell ``width``.

    Handles CJK, emoji, and other wide glyphs so columns remain
    perfectly straight and never wrap to ruin the layout.
    """
    clean = " ".join(text.replace("\xa0", " ").splitlines())
    if width <= 0:
        return ""
    if cell_len(clean) > width:
        if width == 1:
            return "…"
        return set_cell_size(clean, width - 1) + "…"
    return set_cell_size(clean, width)
