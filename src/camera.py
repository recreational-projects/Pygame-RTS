from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING

import pygame as pg

from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from src.geometry import Coordinate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.game_object import GameObject


@dataclass(kw_only=True)
class Camera:
    rect: pg.Rect = dataclass_field(init=False)

    def __post_init__(self) -> None:
        self.rect = pg.Rect(0, 0, SCREEN_WIDTH - 200, SCREEN_HEIGHT)

    def update(
        self,
        selected_units: Sequence[GameObject],
        mouse_pos: pg.typing.SequenceLike,
        interface_rect: pg.Rect,
    ) -> None:
        mouse_coord = Coordinate(mouse_pos)
        if interface_rect.collidepoint(mouse_coord) or mouse_coord.y > SCREEN_HEIGHT:
            return
        if selected_units:
            avg_x = sum(unit.position.x for unit in selected_units) / len(
                selected_units
            )
            avg_y = sum(unit.position.y for unit in selected_units) / len(
                selected_units
            )
            self.rect.center = (
                max(
                    self.rect.width // 2,
                    min(MAP_WIDTH - self.rect.width // 2, int(avg_x)),
                ),
                max(
                    self.rect.height // 2,
                    min(MAP_HEIGHT - self.rect.height // 2, int(avg_y)),
                ),
            )
        else:
            if mouse_coord.x < 30 and self.rect.left > 0:
                self.rect.x -= 10
            elif mouse_coord.x > SCREEN_WIDTH - 230 and self.rect.right < MAP_WIDTH:
                self.rect.x += 10
            if mouse_coord.y < 30 and self.rect.top > 0:
                self.rect.y -= 10
            elif mouse_coord.y > SCREEN_HEIGHT - 30 and self.rect.bottom < MAP_HEIGHT:
                self.rect.y += 10
        self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

    def apply(self, rect: pg.Rect) -> pg.Rect:
        return pg.Rect(
            rect.x - self.rect.x, rect.y - self.rect.y, rect.width, rect.height
        )

    def screen_to_world(self, screen_pos: pg.typing.SequenceLike) -> Coordinate:
        screen_coord = Coordinate(screen_pos)
        map_area_y = int(min(screen_coord.y, SCREEN_HEIGHT))
        return Coordinate(
            max(0, min(MAP_WIDTH, int(screen_coord.x) + self.rect.x)),
            max(0, min(MAP_HEIGHT, map_area_y + self.rect.y)),
        )
