"""Functions which require access to buildings/units, specific to 2D game."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame as pg

from modules.data_2d import MAP_HEIGHT as MAP_HEIGHT_2D
from modules.data_2d import MAP_WIDTH as MAP_WIDTH_2D
from modules.unit_stats.unit_stats_2d import get_unit_size

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pygame.typing import IntPoint, Point

    from modules.team import Team
    from modules.units_2d import Unit2d


def is_valid_building_position(
    *,
    position: Point,
    team: Team,
    new_building_cls: type,
    buildings: Iterable[Unit2d],
    map_width: int = MAP_WIDTH_2D,
    map_height: int = MAP_HEIGHT_2D,
    building_range: int = 200,
    margin: int = 60,  # Passage margin for units
) -> bool:
    """Validates if a building can be placed at position: checks bounds, overlaps, proximity to friendly buildings.

    :param position: Proposed center position for the building.
    :param team: The team placing the building.
    :param new_building_cls: The class of the building to place.
    :param buildings: List of existing buildings.
    :param map_width: Map width for bounds check.
    :param map_height: Map height for bounds check.
    :param building_range: Max distance to nearest friendly building (HQ requires this).
    :param margin: Minimum distance margin between buildings.
    :return: True if placement is valid.
    """
    width, height = get_unit_size(new_building_cls.__name__)
    temp_rect = pg.Rect(position[0] - width / 2, position[1] - height / 2, width, height)
    if not (
        temp_rect.left >= 0 and temp_rect.right <= map_width and temp_rect.top >= 0 and temp_rect.bottom <= map_height
    ):
        return False

    proposed_center = position
    has_nearby_friendly = False
    for building in buildings:
        if building.team == team and building.health > 0:
            # Dynamic min_dist based on sizes + margin
            half_w_e, half_h_e = building.size[0] / 2, building.size[1] / 2
            min_dist = max(width / 2 + half_w_e, height / 2 + half_h_e) + margin
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
    global_buildings: Iterable[Unit2d],
    global_units: Iterable[Unit2d],
    unit_size: IntPoint = (40, 40),
) -> Point:
    """Finds a nearby free position for spawning units, avoiding overlaps with buildings/units.

    :param target_pos: Preferred target position (e.g., rally point).
    :param global_buildings: List or group of all buildings.
    :param global_units: List or group of all units.
    :param unit_size: Size of the unit to spawn (default: (40, 40)).
    :return: A free position tuple, or target_pos if no free spot found.
    """
    for _ in range(20):
        offset_x = random.uniform(-60, 60)
        offset_y = random.uniform(-60, 60)
        pos_x = target_pos[0] + offset_x
        pos_y = target_pos[1] + offset_y
        unit_rect = pg.Rect(pos_x - unit_size[0] / 2, pos_y - unit_size[1] / 2, unit_size[0], unit_size[1])
        # pyrefly: ignore [missing-attribute]
        overlaps_building = any(b.rect.colliderect(unit_rect) for b in global_buildings if b.health > 0)
        # pyrefly: ignore [missing-attribute]
        overlaps_unit = any(u.rect.colliderect(unit_rect) for u in global_units if u.health > 0 and not u.is_air)
        if not overlaps_building and not overlaps_unit:
            return pos_x, pos_y

    return target_pos
