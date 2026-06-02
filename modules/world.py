"""Functions which require access to buildings/units."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.spatial_hash import SpatialHash2d, SpatialHashIso


# pyrefly: ignore [implicit-any-type-argument]
def handle_unit_collisions(*, all_units: list, unit_hash: SpatialHash2d | SpatialHashIso) -> None:
    """
    Resolves overlaps between ground units using simple repulsion.

    :param all_units: List of all units.
    :param unit_hash: SpatialHash for nearby queries.
    """
    for unit in all_units:
        if unit.health <= 0 or unit.is_air:
            continue

        nearby = unit_hash.query(unit.position, max(unit.rect.width, unit.rect.height))
        for other in nearby:
            if other is unit or other.health <= 0 or other.is_air or id(other) <= id(unit):
                continue

            if unit.rect.colliderect(other.rect):
                dx = other.position.x - unit.position.x
                dy = other.position.y - unit.position.y
                dist = math.hypot(dx, dy)
                if dist > 0:
                    r1 = max(unit.rect.width, unit.rect.height) / 2
                    r2 = max(other.rect.width, other.rect.height) / 2
                    overlap = max(0, r1 + r2 - dist)
                    if overlap > 0:
                        push = overlap * 0.5
                        direction_x = dx / dist
                        direction_y = dy / dist
                        unit.position.x -= direction_x * push
                        unit.position.y -= direction_y * push
                        other.position.x += direction_x * push
                        other.position.y += direction_y * push


# pyrefly: ignore [implicit-any-type-argument]
def handle_unit_building_collisions(*, all_units: list, building_hash: SpatialHash2d | SpatialHashIso) -> None:
    """
    Pushes units away from building overlaps.

    :param all_units: List of units.
    :param building_hash: SpatialHash for buildings.
    """
    for unit in [u for u in all_units if u.health > 0 and not u.is_air]:
        nearby_builds = building_hash.query(unit.position, max(unit.rect.width, unit.rect.height) + 50)
        for building in [b for b in nearby_builds if b.health > 0]:
            if unit.rect.colliderect(building.rect):
                dx = building.position.x - unit.position.x
                dy = building.position.y - unit.position.y
                dist = math.hypot(dx, dy)
                if dist > 0:
                    r1 = max(unit.rect.width, unit.rect.height) / 2
                    r2 = max(building.rect.width, building.rect.height) / 2
                    overlap = max(0, r1 + r2 - dist)
                    if overlap > 0:
                        direction_x = dx / dist
                        direction_y = dy / dist
                        unit.position.x -= direction_x * overlap
                        unit.position.y -= direction_y * overlap
