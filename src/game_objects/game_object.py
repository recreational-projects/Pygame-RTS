from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

if TYPE_CHECKING:
    from src.camera import Camera
    from src.constants import Team
    from src.geometry import Coordinate


class GameObject(pg.sprite.Sprite):
    """Base class for `Unit`, `Building`."""

    ATTACK_RANGE = 0
    COST = 0
    POWER_USAGE = 0

    def __init__(self, *, position: Coordinate, team: Team) -> None:
        super().__init__()
        self.position = position
        self.team = team
        self.image: pg.Surface = pg.Surface((0, 0))  # Nominal, overridden
        self.rect: pg.Rect = pg.Rect(position, (0, 0))  # Nominal, overridden
        self.target: Coordinate | None = None
        self.target_unit: GameObject | None = None
        self.formation_target: Coordinate | None = None
        self.health = 0
        self.max_health = self.health
        self.cooldown_timer = 0
        self.selected = False
        self.under_attack = False

    def displacement_to(self, position: pg.typing.SequenceLike) -> pg.Vector2:
        """Return the displacement to `position`."""
        return position - self.position

    def distance_to(self, position: pg.typing.SequenceLike) -> float:
        """Return the distance to `position`."""
        return self.displacement_to(position).magnitude()

    def draw_health_bar(self, *, surface: pg.Surface, camera: Camera) -> None:
        """Draw health bar if damaged or under attack."""
        health_ratio = self.health / self.max_health
        if not self.under_attack and health_ratio == 1.0:
            return

        color = (0, 255, 0) if health_ratio > 0.5 else (255, 0, 0)
        bar_width = max(10, int(self.rect.width * health_ratio))
        screen_rect = camera.apply(self.rect)
        pg.draw.rect(
            surface,
            (0, 0, 0),
            (screen_rect.x - 1, screen_rect.y - 16, self.rect.width + 2, 10),
        )  # Background
        pg.draw.rect(surface, color, (screen_rect.x, screen_rect.y - 15, bar_width, 8))
        pg.draw.rect(
            surface,
            (255, 255, 255),
            (screen_rect.x, screen_rect.y - 15, self.rect.width, 8),
            1,
        )  # Border

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        self.rect.center = self.position
        surface.blit(self.image, camera.apply(self.rect).topleft)
        self.draw_health_bar(surface=surface, camera=camera)
