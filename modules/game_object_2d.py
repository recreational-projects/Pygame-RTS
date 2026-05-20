from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

from modules.data_2d import PLASMA_BURN_DURATION, PLASMA_BURN_PARTICLE_COUNT
from modules.particles import PlasmaBurnParticle
from modules.team import team_to_color
from modules.typing import ensure_rect, is_rect

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.camera.camera_2d import Camera2d
    from modules.team import Team


class GameObject(pg.sprite.Sprite, ABC):
    """Abstract base for all entities (units and buildings).

    Provides common properties like position, health, selection, drawing.
    """

    def __init__(self, position: Point, team: Team) -> None:
        """Base entity: position, team, health, selection, plasma particles, basic image/rect.

        :param position: Initial position (x, y).
        :param team: Team enum.
        """
        # Base entity: position, team, health, selection, plasma particles, basic image/rect.
        super().__init__()
        self.position = Vector2(position)
        self.team = team
        self.health = 100
        self.max_health = 100
        self.under_attack = False
        self.under_attack_timer = 0
        self.selected = False
        self.is_seen = False
        self.body_angle: float = 0
        self.plasma_burn_particles: list[PlasmaBurnParticle] = []
        self.image = pg.Surface((32, 32))

        if self.rect is None:
            return  # TODO: HQ requires this

        if self.image is not None:  # TODO: type guard - not sure why these can be None
            self.rect = self.image.get_rect(center=position)

    def distance_to(self, other_pos: Point) -> float:
        """Euclidean distance to another position.

        :param other_pos: Target position (x, y).
        :return: Distance in pixels.
        """
        # Euclidean distance to another position.
        return self.position.distance_to(other_pos)

    def draw(self, surface: pg.Surface, camera: Camera2d, mouse_pos: Point | None = None) -> None:
        """Base draw: scales image, handles rotation if needed, selection circle, health bar, particles.

        :param surface: Surface to draw on.
        :param camera: Camera2d for transformation.
        :param mouse_pos: Optional for hover.
        """
        ensure_rect(self.rect)
        if not is_rect(self.rect):  # TODO: not sure why `ensure_rect` is insufficient here
            raise TypeError("self.rect` is unexpected non-`Rect` type")

        screen_rect = camera.get_screen_rect(self.rect)
        if not screen_rect.colliderect((0, 0, camera.width, camera.height)):
            return

        screen_pos = camera.world_to_screen(self.position)
        zoom = camera.zoom

        if self.image is not None:  # TODO: type guard - not sure why this can be None
            scaled_size = (int(self.image.get_width() * zoom), int(self.image.get_height() * zoom))
            if scaled_size[0] > 0 and scaled_size[1] > 0:
                scaled_image = pg.transform.smoothscale(self.image, scaled_size)
                offset_x = scaled_size[0] / 2
                offset_y = scaled_size[1] / 2
                blit_pos = (screen_pos[0] - offset_x, screen_pos[1] - offset_y)
                surface.blit(scaled_image, blit_pos)

        ensure_rect(self.rect)
        if not is_rect(self.rect):  # TODO: not sure why `ensure_rect` is insufficient here
            raise TypeError("self.rect` is unexpected non-`Rect` type")

        if self.selected:
            ensure_rect(self.rect)
            radius = max(self.rect.width, self.rect.height) / 2 * zoom + 3
            pg.draw.circle(
                surface,
                (255, 255, 0),
                (int(screen_pos[0]), int(screen_pos[1])),
                int(radius),
                int(2 * zoom),
            )

        for particle in self.plasma_burn_particles:
            particle.draw_2d(surface, camera)

    def draw_health_bar(self, screen: pg.Surface, camera: Camera2d, mouse_pos: Point | None = None) -> None:
        """Draws health bar above entity if under attack, hovered, or building with damage.

        :param screen: Surface to draw on.
        :param camera: Camera2d for positioning.
        :param mouse_pos: Mouse position for hover detection.
        """
        # Draws health bar above entity if under attack, hovered, or building with damage.
        hovered = False
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
        else:
            if not (self.under_attack or hovered):
                show = False

        if not show:
            return

        screen_pos = camera.world_to_screen(self.position)
        health_ratio = self.health / self.max_health
        color = (0, 255, 0) if health_ratio > 0.5 else (255, 0, 0)
        bar_width = 25
        bar_height = 4
        bar_x = screen_pos[0] - bar_width / 2
        if not isinstance(self.rect, pg.Rect):
            raise TypeError("self.rect` is unexpected non-`Rect` type")

        bar_y = screen_pos[1] - (self.rect.height / 2 * camera.zoom) - bar_height - 2
        pg.draw.rect(screen, (0, 0, 0), (bar_x - 1, bar_y - 1, bar_width + 2, bar_height + 2))
        pg.draw.rect(screen, color, (bar_x, bar_y, bar_width * health_ratio, bar_height))
        pg.draw.rect(screen, (255, 255, 255), (bar_x, bar_y, bar_width, bar_height), 1)

    def take_damage(self, damage: int) -> bool:
        """Applies damage, sets attack flag, spawns plasma burn particles if low health.

        :param damage: Damage amount.
        :return: True if entity is destroyed (health <= 0).
        """
        # Applies damage, sets attack flag, spawns plasma burn particles if low health.
        self.health -= damage
        self.under_attack = True
        self.under_attack_timer = 120
        if self.health < self.max_health * 0.7 and random.random() < 0.3:
            color = team_to_color[self.team]
            for _ in range(PLASMA_BURN_PARTICLE_COUNT):
                self.plasma_burn_particles.append(PlasmaBurnParticle(self.position, self, color, PLASMA_BURN_DURATION))

        return self.health <= 0

    @abstractmethod
    def update(self) -> None:
        """Abstract update method for entity-specific logic."""
