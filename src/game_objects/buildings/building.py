from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import pygame as pg

from src.constants import COLORS, Team
from src.game_object import GameObject
from src.particle import Particle

if TYPE_CHECKING:
    from src.camera import Camera


class Building(GameObject):
    # Class specific:
    CONSTRUCTION_TIME = 50
    SIZE = 60, 60

    def __init__(
        self,
        *,
        position: pg.typing.SequenceLike,
        team: Team,
        font: pg.Font,
    ) -> None:
        super().__init__(position=position, team=team)
        self.color = COLORS[team]
        self.image = pg.Surface(self.SIZE, pg.SRCALPHA)
        self.rect = self.image.get_rect(topleft=position)
        self.font = font
        self.construction_progress = 0
        self.is_explored = False
        """Controls whether AI building is drawn."""

        # Add details to building
        pg.draw.rect(self.image, self.color, ((0, 0), self.SIZE))  # Base
        # Clamp color values to prevent negative values
        inner_color = (
            max(0, self.color.r - 50),
            max(0, self.color.g - 50),
            max(0, self.color.b - 50),
        )
        pg.draw.rect(
            self.image, inner_color, ((5, 5), (self.SIZE[0] - 10, self.SIZE[1] - 10))
        )  # Inner
        for i in range(10, self.SIZE[0] - 10, 20):
            pg.draw.rect(self.image, (200, 200, 200), (i, 10, 10, 10))  # Windows

    def update(self, particles: pg.sprite.Group[Any], *args, **kwargs) -> None:
        """Update the building, including removal at zero health."""
        if self.construction_progress < self.CONSTRUCTION_TIME:
            self.construction_progress += 1
            self.image.set_alpha(
                int(255 * self.construction_progress / self.CONSTRUCTION_TIME)
            )
        super().update(*args, **kwargs)
        if self.health <= 0:
            for _ in range(15):
                particles.add(
                    Particle(
                        self.position,
                        random.uniform(-3, 3),
                        random.uniform(-3, 3),
                        random.randint(6, 12),
                        pg.Color(200, 100, 100),
                        30,
                    )
                )
            self.kill()

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        """Draw the building, and label with first letter of class."""
        surface.blit(self.image, camera.apply(self.rect).topleft)
        cls_label = self.__class__.__name__[0]
        cls_label_offset = -5, -2
        surface.blit(
            self.font.render(
                text=f"{cls_label}", antialias=True, color=(255, 255, 255)
            ),
            camera.apply(self.rect).center + cls_label_offset,
        )
        self.draw_health_bar(surface=surface, camera=camera)
