"""Shape drawing functions."""

from __future__ import annotations

import pygame as pg

from src.constants import DEBUG_COLOR


def draw_progress_bar(
    *,
    surface: pg.Surface,
    bar_color: pg.Color,
    rect: pg.Rect,
    progress: float,
) -> None:
    """Draw a fixed-width progress bar."""
    if progress < 0 or progress > 1:
        raise ValueError("Progress should be between 0 and 1 inclusive")

    inner_rect = pg.Rect(
        (rect.left + 1, rect.top + 1),
        (rect.width - 2, rect.height - 2),
    )
    bar = pg.Rect(
        (inner_rect.left + 1, inner_rect.top + 1),
        (int(progress * inner_rect.width - 2), inner_rect.height - 2),
    )
    pg.draw.rect(surface=surface, color=pg.Color("black"), rect=rect)
    pg.draw.rect(surface=surface, color=pg.Color("white"), rect=inner_rect, width=1)
    pg.draw.rect(surface=surface, color=bar_color, rect=bar)


def debug_outline_rect(*, surface: pg.Surface, rect: pg.typing.RectLike) -> None:
    """Draw outline of `rect` on `surface`. Used for visual debugging."""
    pg.draw.rect(surface=surface, color=DEBUG_COLOR, rect=rect, width=1)


def debug_marker(*, surface: pg.Surface, position: pg.typing.SequenceLike) -> None:
    """Draw marker at `position` on `surface`. Used for visual debugging."""
    pg.draw.circle(surface=surface, color=DEBUG_COLOR, center=position, radius=5)
