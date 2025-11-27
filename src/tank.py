from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame as pg

from src.constants import Team
from src.game_object import GameObject

if TYPE_CHECKING:
    from src.camera import Camera


class Tank(GameObject):
    # Override base class(es):
    ATTACK_RANGE = 200
    COST = 500
    IS_MOBILE = True
    POWER_USAGE = 15

    # Class specific:
    UNIT_TARGETING_RANGE = 250
    """Max distance at which a unit can be targeted."""
    ATTACK_COOLDOWN_PERIOD = 50

    def __init__(self, position: pg.typing.SequenceLike, team: Team) -> None:
        super().__init__(position=position, team=team)
        self.base_image = pg.Surface((30, 20), pg.SRCALPHA)
        # Draw tank body (front facing east/right)
        pg.draw.rect(self.base_image, (100, 100, 100), (0, 0, 30, 20))  # Hull
        pg.draw.rect(self.base_image, (80, 80, 80), (2, 2, 26, 16))  # Inner hull
        pg.draw.rect(self.base_image, (50, 50, 50), (0, -2, 30, 4))  # Tracks top
        pg.draw.rect(self.base_image, (50, 50, 50), (0, 18, 30, 4))  # Tracks bottom
        self.barrel_image = pg.Surface((20, 4), pg.SRCALPHA)
        pg.draw.rect(
            self.barrel_image, (70, 70, 70), (0, 0, 20, 4)
        )  # Barrel (extends right)
        self.image = self.base_image
        self.rect = self.image.get_rect(center=position)
        self.speed = 2.5 if team == Team.GDI else 3
        self.health = 200 if team == Team.GDI else 120
        self.max_health = self.health
        self.attack_damage = 20 if team == Team.GDI else 15
        self.angle: float = 0
        self.recoil = 0

    def update(self) -> None:
        super().update()
        if self.target_unit and self.target_unit.health > 0:
            self.target = (
                self.target_unit.position
                if self.distance_to(self.target_unit.position)
                <= Tank.UNIT_TARGETING_RANGE
                else None
            )
            self.target_unit = self.target_unit if self.target else None

        if self.target:
            dx, dy = self.displacement_to(self.target)
            self.angle = math.degrees(
                math.atan2(dy, dx)
            )  # Use dy instead of -dy to fix vertical direction
            self.image = pg.Surface((40, 40), pg.SRCALPHA)
            # Rotate base image to face target (base image faces east, so -angle aligns it correctly)
            rotated_base = pg.transform.rotate(self.base_image, -self.angle)
            self.image.blit(
                source=rotated_base, dest=rotated_base.get_rect(center=(20, 20))
            )
            # Handle barrel with recoil
            barrel_length = 20 - self.recoil * 2
            barrel_image = pg.Surface((barrel_length, 4), pg.SRCALPHA)
            pg.draw.rect(barrel_image, (70, 70, 70), (0, 0, barrel_length, 4))
            # Rotate barrel to match target direction
            rotated_barrel = pg.transform.rotate(
                barrel_image, -self.angle
            )  # Barrel also faces east initially
            self.image.blit(
                source=rotated_barrel, dest=rotated_barrel.get_rect(center=(20, 20))
            )
            if self.recoil > 0:
                self.recoil -= 1

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        surface.blit(source=self.image, dest=camera.to_screen(self.rect.topleft))
        if self.selected:
            pg.draw.circle(
                surface,
                (255, 255, 255),
                camera.rect_to_screen(self.rect).center,
                self.rect.width // 2 + 2,
                2,
            )  # Circular selection

        self.draw_health_bar(surface=surface, camera=camera)
