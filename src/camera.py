from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import pygame as pg

from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
)
from src.geometry import Coordinate, mean_vector

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.game_object import GameObject


@dataclass
class Camera:
    PAN_MARGIN: ClassVar[int] = 30

    viewport: pg.Rect

    @property
    def map_offset(self) -> tuple[int, int]:
        return -self.viewport.x, -self.viewport.y

    def update(
        self,
        *,
        selected_units: Sequence[GameObject],
        mouse_pos: pg.typing.SequenceLike,
    ) -> None:
        mouse_pos = Coordinate(mouse_pos)
        if not self.viewport.collidepoint(mouse_pos):
            return

        if selected_units:
            units_center = mean_vector([u.position for u in selected_units])
            x = max(
                self.viewport.width // 2,
                min(MAP_WIDTH - self.viewport.width // 2, round(units_center.x)),
            )
            y = max(
                self.viewport.height // 2,
                min(MAP_HEIGHT - self.viewport.height // 2, round(units_center.y)),
            )
            self.viewport.center = x, y

        else:
            if mouse_pos.x < Camera.PAN_MARGIN and self.viewport.left > 0:
                self.viewport.x -= 10
            elif (
                mouse_pos.x > self.viewport.width - Camera.PAN_MARGIN
                and self.viewport.right < MAP_WIDTH
            ):
                self.viewport.x += 10

            if mouse_pos.y < Camera.PAN_MARGIN and self.viewport.top > 0:
                self.viewport.y -= 10
            elif (
                mouse_pos.y > self.viewport.height - Camera.PAN_MARGIN
                and self.viewport.bottom < MAP_HEIGHT
            ):
                self.viewport.y += 10

        self.viewport.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

    def to_screen(self, world_pos: pg.typing.SequenceLike) -> Coordinate:
        """Translate `world_pos` to screen."""
        return Coordinate(world_pos) + self.map_offset

    def rect_to_screen(self, rect: pg.Rect) -> pg.Rect:
        """Translate world `rect` to screen."""
        return rect.move(self.map_offset)

    def to_world(self, screen_pos: pg.typing.SequenceLike) -> Coordinate:
        """Translate `screen_pos` to world."""
        return Coordinate(screen_pos) - self.map_offset
