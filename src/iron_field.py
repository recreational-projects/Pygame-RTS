from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src.geometry import Coordinate

if TYPE_CHECKING:
    from src.camera import Camera


class IronField(pg.sprite.Sprite):
    """Resource node for harvesters."""

    SIZE = 40

    def __init__(
        self, *, position: pg.typing.SequenceLike, font: pg.Font, resources: int = 5000
    ) -> None:
        super().__init__()
        self.position = Coordinate(position)
        self.image: pg.Surface = pg.Surface(
            (IronField.SIZE, IronField.SIZE), pg.SRCALPHA
        )
        pg.draw.polygon(
            self.image, (0, 200, 0), [(0, 20), (20, 0), (40, 20), (20, 40)]
        )  # Diamond shape for crystal
        self.rect: pg.Rect = self.image.get_rect(topleft=self.position)
        self.font = font
        self.resources = resources
        self.regen_timer = 500

    def update(self) -> None:
        if self.regen_timer > 0:
            self.regen_timer -= 1
        else:
            self.resources = min(5000, self.resources + 15)
            self.regen_timer = 500
        self.image.set_alpha(int(255 * self.resources / 5000))

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        surface.blit(self.image, camera.apply(self.rect).topleft)
        surface.blit(
            self.font.render(
                text=f"{self.resources}", antialias=True, color=(255, 255, 255)
            ),
            (camera.apply(self.rect).x, camera.apply(self.rect).y - 20),
        )
