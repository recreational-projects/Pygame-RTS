from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src import draw_utils
from src.constants import VIEW_DEBUG_MODE_IS_ENABLED
from src.geometry import Coordinate

if TYPE_CHECKING:
    from src.camera import Camera


class IronField(pg.sprite.Sprite):
    """Stationary resource node for harvesters."""

    def __init__(
        self, *, x: float, y: float, font: pg.Font, resources: int = 5000
    ) -> None:
        super().__init__()
        self.image: pg.Surface = pg.Surface((40, 40), pg.SRCALPHA)
        pg.draw.polygon(
            self.image, (0, 200, 0), [(0, 20), (20, 0), (40, 20), (20, 40)]
        )  # Diamond shape for crystal
        self.rect: pg.Rect = self.image.get_rect(topleft=(x, y))
        self.font = font
        self.resources = resources
        self.regen_timer = 500

    @property
    def position(self) -> Coordinate:
        return Coordinate(self.rect.center)

    def update(self) -> None:
        if self.regen_timer > 0:
            self.regen_timer -= 1
        else:
            self.resources = min(5000, self.resources + 15)
            self.regen_timer = 500
        self.image.set_alpha(int(255 * self.resources / 5000))

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        _blit_pos = camera.to_screen(self.rect.topleft)
        surface.blit(source=self.image, dest=_blit_pos)
        if VIEW_DEBUG_MODE_IS_ENABLED:
            draw_utils.debug_outline_rect(
                surface=surface, rect=camera.rect_to_screen(self.rect)
            )
            draw_utils.debug_marker(
                surface=surface, position=camera.to_screen(self.position)
            )

        _label = self.font.render(
            text=f"{self.resources}", antialias=True, color=(255, 255, 255)
        )
        _label_pos = _blit_pos + (0, -20)
        surface.blit(source=_label, dest=_label_pos)
