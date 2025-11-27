from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src.constants import MAP_HEIGHT, MAP_WIDTH
from src.geometry import Coordinate

if TYPE_CHECKING:
    from src.camera import Camera
    from src.constants import Team

ARRIVAL_RADIUS = 5


class GameObject(pg.sprite.Sprite):
    ATTACK_RANGE = 0
    COST = 0
    IS_MOBILE = False
    """Override for mobile classes."""
    POWER_USAGE = 0

    def __init__(self, *, position: pg.typing.SequenceLike, team: Team) -> None:
        super().__init__()
        self.rect: pg.Rect = pg.Rect(position, (0, 0))  # Nominal, overridden
        self.image: pg.Surface = pg.Surface(position)
        self.team = team
        self.target: Coordinate | None = None
        self.target_unit: GameObject | None = None
        self.formation_target: Coordinate | None = None
        self.speed: float = 0
        self.health = 0
        self.max_health = self.health
        self.cooldown_timer = 0
        self.selected = False
        self.under_attack = False

    @property
    def position(self) -> Coordinate:
        return Coordinate(self.rect.center)

    def displacement_to(self, position: pg.typing.SequenceLike) -> pg.Vector2:
        """Return the displacement to `position`."""
        return position - self.position

    def distance_to(self, position: pg.typing.SequenceLike) -> float:
        """Return the distance to `position`."""
        return (position - self.position).magnitude()

    def move_toward(self) -> None:
        """Only relevant for mobile classes."""
        if not self.IS_MOBILE:
            raise TypeError(
                f"Can't move unit of non-mobile class {self.__class__.__name__}"
            )

        if self.target and self.target_unit and self.target_unit.health > 0:
            dist = self.distance_to(self.target)
            if dist > self.ATTACK_RANGE:
                if dist > ARRIVAL_RADIUS:
                    dx, dy = self.displacement_to(self.target)
                    self.rect.x += self.speed * dx / dist
                    self.rect.y += self.speed * dy / dist
                self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))
            else:
                self.target = None

        elif self.formation_target:
            dist = self.distance_to(self.formation_target)
            if dist > ARRIVAL_RADIUS:
                dx, dy = self.displacement_to(self.formation_target)
                self.rect.x += self.speed * dx / dist
                self.rect.y += self.speed * dy / dist
            self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

        elif self.target:
            dist = self.distance_to(self.target)
            if dist > ARRIVAL_RADIUS:
                dx, dy = self.displacement_to(self.target)
                self.rect.x += self.speed * dx / dist
                self.rect.y += self.speed * dy / dist
            self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        if self.IS_MOBILE:
            self.move_toward()

        if self.cooldown_timer > 0:
            self.cooldown_timer -= 1

    def draw_health_bar(self, *, surface: pg.Surface, camera: Camera) -> None:
        health_ratio = self.health / self.max_health
        if not self.under_attack and health_ratio == 1.0:
            return

        color = (0, 255, 0) if health_ratio > 0.5 else (255, 0, 0)
        bar_width = max(10, int(self.rect.width * health_ratio))
        screen_rect = camera.rect_to_screen(self.rect)
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
