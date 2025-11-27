from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src import draw_utils
from src.constants import VIEW_DEBUG_MODE_IS_ENABLED, Team
from src.game_objects.game_object import GameObject

if TYPE_CHECKING:
    from src.camera import Camera


class Infantry(GameObject):
    """Basic foot soldier."""

    # Override base class(es):
    ATTACK_RANGE = 50
    COST = 100
    IS_MOBILE = True
    POWER_USAGE = 5

    # Class specific:
    ATTACK_COOLDOWN_PERIOD = 25
    UNIT_TARGETING_RANGE = 200
    """Max distance at which a unit can be targeted."""

    def __init__(self, position: pg.typing.SequenceLike, team: Team) -> None:
        super().__init__(position=position, team=team)
        self.image = pg.Surface((16, 16), pg.SRCALPHA)
        self.rect = self.image.get_rect(center=position)
        self.speed = 3.5 if team == Team.GDI else 4
        self.health = 100 if team == Team.GDI else 60
        self.max_health = self.health
        self.attack_damage = 8

        # Draw infantry as a simple soldier
        pg.draw.circle(self.image, (150, 150, 150), (8, 4), 4)  # Head
        pg.draw.rect(self.image, (100, 100, 100), (6, 8, 4, 8))  # Body
        pg.draw.line(self.image, (80, 80, 80), (8, 16), (8, 20))  # Legs
        pg.draw.line(self.image, (120, 120, 120), (10, 10), (14, 10))  # Gun

    def update(self) -> None:
        super().update()
        if self.target_unit and self.target_unit.health > 0:
            if (
                self.distance_to(self.target_unit.position)
                <= Infantry.UNIT_TARGETING_RANGE
            ):
                self.target = self.target_unit.position
            else:
                self.target = None

            self.target_unit = self.target_unit if self.target else None

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        surface.blit(source=self.image, dest=camera.to_screen(self.rect.topleft))
        if VIEW_DEBUG_MODE_IS_ENABLED:
            draw_utils.debug_outline_rect(
                surface=surface, rect=camera.rect_to_screen(self.rect)
            )
            draw_utils.debug_marker(
                surface=surface, position=camera.to_screen(self.position)
            )

        if self.selected:
            pg.draw.circle(
                surface, (255, 255, 255), camera.rect_to_screen(self.rect).center, 10, 2
            )
        self.draw_health_bar(surface=surface, camera=camera)
