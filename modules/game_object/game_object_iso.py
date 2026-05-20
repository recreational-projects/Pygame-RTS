from __future__ import annotations

import random
from abc import ABC
from typing import TYPE_CHECKING

import pygame as pg

from modules.data_iso import MAP_HEIGHT, MAP_WIDTH, PLASMA_BURN_DURATION, PLASMA_BURN_PARTICLE_COUNT
from modules.game_object.game_object import _GameObject
from modules.particles import PlasmaBurnParticle
from modules.team import team_to_color
from modules.typing import ensure_rect, is_rect

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.camera.camera_iso import CameraIso
    from modules.team import Team


class GameObjectIso(_GameObject, ABC):
    """Abstract base for isometric entities."""

    def __init__(self, position: Point, team: Team) -> None:
        super().__init__(position, team)
        # self.body_angle = 0
        self.plasma_burn_particles: list[PlasmaBurnParticle] = []
        self.map_width = MAP_WIDTH
        self.map_height = MAP_HEIGHT
        # pyrefly: ignore [missing-override-decorator]
        self.image = pg.Surface((32, 32))
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            # pyrefly: ignore [missing-override-decorator]
            self.rect = self.image.get_rect(center=position)

    def distance_to(self, other_pos: Point) -> float:
        return self.position.distance_to(other_pos)

    def draw_health_bar(self, screen: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        hovered = False
        ensure_rect(self.rect)
        if mouse_pos is not None:  # TODO: type guard - not sure why needed
            if not is_rect(self.rect):  # TODO: not sure why `ensure_rect` is insufficient here
                raise TypeError("self.rect` is unexpected non-`Rect` type")

            screen_rect = camera.get_screen_rect(self.rect)
            if screen_rect.collidepoint(mouse_pos):
                hovered = True

        show = True
        if hasattr(self, "is_building") and self.is_building:  # TODO: fix root cause
            if self.health >= self.max_health:
                show = False

        elif not (self.under_attack or hovered):
            show = False

        if not show:
            return

        screen_pos = camera.world_to_iso(self.position, camera.zoom)
        health_ratio = self.health / self.max_health
        color = (0, 255, 0) if health_ratio > 0.5 else (255, 0, 0)
        bar_width = 25
        bar_height = 4
        bar_x = screen_pos[0] - bar_width / 2
        ensure_rect(self.rect)
        if not is_rect(self.rect):  # TODO: not sure why `ensure_rect` is insufficient here
            raise TypeError("self.rect` is unexpected non-`Rect` type")

        bar_y = screen_pos[1] - (self.rect.height / 2 * camera.zoom) - bar_height - 2
        pg.draw.rect(screen, (0, 0, 0), (bar_x - 1, bar_y - 1, bar_width + 2, bar_height + 2))
        pg.draw.rect(screen, color, (bar_x, bar_y, bar_width * health_ratio, bar_height))
        pg.draw.rect(screen, (255, 255, 255), (bar_x, bar_y, bar_width, bar_height), 1)

    def take_damage(self, damage: int) -> bool:
        self.health -= damage
        self.under_attack = True
        self.under_attack_timer = 120
        if self.health < self.max_health * 0.7 and random.random() < 0.3:
            color = team_to_color[self.team]
            for _ in range(PLASMA_BURN_PARTICLE_COUNT):
                self.plasma_burn_particles.append(PlasmaBurnParticle(self.position, self, color, PLASMA_BURN_DURATION))

        return self.health <= 0
