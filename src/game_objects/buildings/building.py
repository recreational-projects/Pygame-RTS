from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import pygame as pg

from src import draw_utils
from src.constants import GDI_COLOR, VIEW_DEBUG_MODE_IS_ENABLED
from src.game_objects.game_object import GameObject
from src.particle import Particle

if TYPE_CHECKING:
    from src.camera import Camera
    from src.constants import Team


class Building(GameObject):
    """Building base class. Stationary."""

    # Class specific:
    CONSTRUCTION_TIME = 50
    SIZE = 60, 60

    def __init__(
        self,
        *,
        position: pg.typing.SequenceLike,
        team: Team,
        color: pg.Color = GDI_COLOR,
        font: pg.Font,
    ) -> None:
        super().__init__(position=position, team=team)
        self.image = pg.Surface(self.SIZE, pg.SRCALPHA)
        self.rect = self.image.get_rect(topleft=position)
        self.font = font
        self.construction_progress = 0
        self.is_explored = False
        """Controls whether AI building is drawn."""

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
        surface.blit(source=self.image, dest=camera.to_screen(self.rect.topleft))
        if VIEW_DEBUG_MODE_IS_ENABLED:
            draw_utils.debug_outline_rect(
                surface=surface, rect=camera.rect_to_screen(self.rect)
            )
            draw_utils.debug_marker(
                surface=surface, position=camera.to_screen(self.position)
            )

        _label = self.font.render(
            text=self.__class__.__name__[0],
            antialias=True,
            color=(255, 255, 255),
        )
        _label_pos = camera.to_screen(self.rect.center) + (-6, 0)
        surface.blit(source=_label, dest=_label_pos)
        self.draw_health_bar(surface=surface, camera=camera)
