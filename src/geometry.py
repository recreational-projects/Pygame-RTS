from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

import pygame as pg

from src.constants import BUILDING_CONSTRUCTION_RANGE, TILE_SIZE

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.building import Building
    from src.constants import Team

Coordinate = pg.Vector2


def _is_within_building_range(
    *, position: pg.typing.SequenceLike, team: Team, buildings: Iterable[Building]
) -> bool:
    """Return whether `position` is within construction range of team's building."""
    pos = Coordinate(position)
    return any(
        building.team == team
        and building.health > 0
        and pos.distance_to(building.position) < BUILDING_CONSTRUCTION_RANGE
        for building in buildings
    )


def _collides_with_building(
    *,
    position: pg.typing.SequenceLike,
    new_building_cls: type[Building],
    buildings: Iterable[Building],
) -> bool:
    """Return whether pending building at `position` collides with existing building."""
    new_rect = pg.Rect(position, new_building_cls.SIZE)
    return any(
        building.health > 0 and new_rect.colliderect(building.rect)
        for building in buildings
    )


def is_valid_building_position(
    *,
    position: pg.typing.SequenceLike,
    new_building_cls: type[Building],
    team: Team,
    buildings: Iterable[Building],
) -> bool:
    return _is_within_building_range(
        position=position,
        team=team,
        buildings=buildings,
    ) and not _collides_with_building(
        position=position,
        new_building_cls=new_building_cls,
        buildings=buildings,
    )


def snap_to_grid(position: pg.typing.SequenceLike) -> Coordinate:
    """Return minimum (top left) point of tile containing `position`."""
    pos = Coordinate(position)
    return Coordinate(pos.x // TILE_SIZE * TILE_SIZE, pos.y // TILE_SIZE * TILE_SIZE)


def calculate_formation_positions(
    *,
    center: pg.typing.SequenceLike,
    target: pg.typing.SequenceLike | None,
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
