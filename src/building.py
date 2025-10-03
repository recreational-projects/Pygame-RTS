from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pygame as pg

from src.constants import GDI_COLOR
from src.game_object import GameObject
from src.particle import Particle

if TYPE_CHECKING:
    from CondaRTS import Team
    from src.camera import Camera


class Building(GameObject):
    SIZE = 60, 60
    CONSTRUCTION_TIME = 50

    def __init__(
        self,
        *,
        x: float,
        y: float,
        team: Team,
        color: pg.Color = GDI_COLOR,
    ) -> None:
        super().__init__(x=x, y=y, team=team)
        self.image = pg.Surface(self.SIZE, pg.SRCALPHA)
        self.rect = self.image.get_rect(topleft=(x, y))
        self.construction_progress = 0
        self.is_seen = False

        # Add details to building
        pg.draw.rect(self.image, color, ((0, 0), self.SIZE))  # Base
        # Clamp color values to prevent negative values
        inner_color = (
            max(0, color[0] - 50),
            max(0, color[1] - 50),
            max(0, color[2] - 50),
        )
        pg.draw.rect(
            self.image, inner_color, ((5, 5), (self.SIZE[0] - 10, self.SIZE[1] - 10))
        )  # Inner
        for i in range(10, self.SIZE[0] - 10, 20):
            pg.draw.rect(self.image, (200, 200, 200), (i, 10, 10, 10))  # Windows

    def update(self, particles: pg.sprite.Group[Particle], *args, **kwargs) -> None:
        """Update the `Building`.

        Parameters
        ----------
        particles:
            `sprite.Group` to which new particles will be added.
        """

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
                        self.rect.centerx,
                        self.rect.centery,
                        random.uniform(-3, 3),
                        random.uniform(-3, 3),
                        random.randint(6, 12),
                        pg.Color(200, 100, 100),
                        30,
                    )
                )
            self.kill()

    def draw(self, screen: pg.Surface, camera: Camera) -> None:
        screen.blit(self.image, camera.apply(self.rect).topleft)
        self.draw_health_bar(screen, camera)
