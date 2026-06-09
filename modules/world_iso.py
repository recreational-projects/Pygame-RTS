"""Functions which require access to buildings/units, specific to isometric game."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame as pg

from modules.data_iso import MAP_HEIGHT, MAP_WIDTH
from modules.unit_stats.unit_stats_iso import get_unit_size

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pygame.typing import IntPoint, Point

    from modules.team import Team
    from modules.units_iso import UnitIso


def is_valid_building_position(
    *,
    position: Point,
    team: Team | None,
    new_building_cls: type,
    buildings: Iterable[UnitIso],
    map_width: int = MAP_WIDTH,
    map_height: int = MAP_HEIGHT,
    building_range: int = 200,
    margin: int = 60,
) -> bool:
    width, height = get_unit_size(new_building_cls.__name__)
    half_w_n, half_h_n = width / 2, height / 2
    temp_rect = pg.Rect(position[0] - half_w_n, position[1] - half_h_n, width, height)
    if not (
        temp_rect.left >= 0 and temp_rect.right <= map_width and temp_rect.top >= 0 and temp_rect.bottom <= map_height
    ):
        return False

    proposed_center = position
    has_nearby_friendly = False
    for building in buildings:
        if building.team == team and building.health > 0:
            half_w_e, half_h_e = building.size[0] / 2, building.size[1] / 2
            min_dist = max(half_w_n + half_w_e, half_h_n + half_h_e) + margin
            dist = math.hypot(proposed_center[0] - building.position.x, proposed_center[1] - building.position.y)
            if dist < min_dist:
                return False

            if dist <= building_range:
                has_nearby_friendly = True

        # pyrefly: ignore [missing-attribute]
        if building.health > 0 and building.rect.colliderect(temp_rect):
            return False

    return has_nearby_friendly or new_building_cls.__name__ == "Headquarters"


def find_free_spawn_position(
    *,
    target_pos: Point,
    global_buildings: Iterable[UnitIso],
    global_units: Iterable[UnitIso],
    unit_size: IntPoint = (40, 40),
    map_width: int = MAP_WIDTH,
    map_height: int = MAP_HEIGHT,
) -> Point:
    for _ in range(20):
        offset_x = random.uniform(-60, 60)
        offset_y = random.uniform(-60, 60)
        pos_x = max(0, min(target_pos[0] + offset_x, map_width))
        pos_y = max(0, min(target_pos[1] + offset_y, map_height))
        unit_rect = pg.Rect(pos_x - unit_size[0] / 2, pos_y - unit_size[1] / 2, unit_size[0], unit_size[1])
        # pyrefly: ignore [missing-attribute]
        overlaps_building = any(b.rect.colliderect(unit_rect) for b in global_buildings if b.health > 0)
        # pyrefly: ignore [missing-attribute]
        overlaps_unit = any(u.rect.colliderect(unit_rect) for u in global_units if u.health > 0 and not u.is_air)
        if not overlaps_building and not overlaps_unit:
            return pos_x, pos_y

    return max(0, min(target_pos[0], map_width)), max(0, min(target_pos[1], map_height))
