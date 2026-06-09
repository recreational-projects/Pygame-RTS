"""Functions which require access to buildings/units, specific to 2D game."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame as pg

from modules.data_2d import MAP_HEIGHT as MAP_HEIGHT_2D
from modules.data_2d import MAP_WIDTH as MAP_WIDTH_2D
from modules.unit_stats.unit_stats_2d import get_unit_size

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pygame.typing import Point

    from modules.team import Team
    from modules.units import Unit2d


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
