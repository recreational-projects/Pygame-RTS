from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src import draw_utils
from src.constants import VIEW_DEBUG_MODE_IS_ENABLED
from src.geometry import Coordinate

if TYPE_CHECKING:
    from src.camera import Camera


class Particle(pg.sprite.Sprite):
    """For effects like explosions or muzzle flash."""

    def __init__(
        self,
        position: pg.typing.SequenceLike,
        vx: float,
        vy: float,
        size: int,
        color: pg.Color,
        lifetime: int,
    ) -> None:
        super().__init__()
        self.image: pg.Surface = pg.Surface((size, size), pg.SRCALPHA)
        pg.draw.circle(self.image, color, (size // 2, size // 2), size // 2)
        self.rect: pg.Rect = self.image.get_rect(center=position)
        self.vx, self.vy = vx, vy
        self.lifetime = lifetime
        self.alpha = 255
        self.initial_lifetime = lifetime

    @property
    def position(self) -> Coordinate:
        return Coordinate(self.rect.center)

    def update(self) -> None:
        self.rect.x += self.vx
        self.rect.y += self.vy
        self.lifetime -= 1
        if self.lifetime <= 0:
            self.kill()
        else:
            self.alpha = int(255 * self.lifetime / self.initial_lifetime)
            self.image.set_alpha(self.alpha)

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        surface.blit(source=self.image, dest=camera.to_screen(self.rect.topleft))
        if VIEW_DEBUG_MODE_IS_ENABLED:
            draw_utils.debug_outline_rect(
                surface=surface, rect=camera.rect_to_screen(self.rect)
            )
            draw_utils.debug_marker(
                surface=surface, position=camera.to_screen(self.position)
            )
