"""Geometry functions that don't access game state."""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

import pygame as pg

from src.constants import TILE_SIZE

if TYPE_CHECKING:
    from collections.abc import Iterable


Coordinate = pg.Vector2


def snap_to_grid(position: pg.typing.Point) -> Coordinate:
    """Return minimum (top left) point of tile containing `position`."""
    pos = Coordinate(position)
    return Coordinate(pos.x // TILE_SIZE * TILE_SIZE, pos.y // TILE_SIZE * TILE_SIZE)


def calculate_formation_positions(
    *,
    center: pg.typing.Point,
    target: pg.typing.Point | None,
    num_units: int,
    direction: float | None = None,
) -> list[Coordinate]:
    if num_units == 0:
        return []
    max_cols, max_rows = 5, 4
    spacing = 20
    positions = []
    if direction is None and target:
        d = Coordinate(target) - center
        angle = math.atan2(d.y, d.x) if d.x != 0 or d.y != 0 else 0
    else:
        angle = direction if direction is not None else 0

    cos_a, sin_a = math.cos(angle), math.sin(angle)
    for i in range(min(num_units, max_cols * max_rows)):
        row = i // max_cols
        col = i % max_cols
        offset_x = (col - (max_cols - 1) / 2) * spacing
        offset_y = (row - (max_rows - 1) / 2) * spacing
        rotated_x = offset_x * cos_a - offset_y * sin_a
        rotated_y = offset_x * sin_a + offset_y * cos_a
        positions.append(Coordinate(center[0] + rotated_x, center[1] + rotated_y))

    return positions


def mean_vector(vecs: Iterable[pg.Vector2]) -> pg.Vector2:
    """Return mean vector of `vecs`."""
    return pg.Vector2(fmean(vec.x for vec in vecs), fmean(vec.y for vec in vecs))
