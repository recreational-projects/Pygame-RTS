"""Implements Particles."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, override

import pygame as pg
from pygame.math import Vector2

from modules.team import team_to_color

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.camera.camera_2d import Camera2d
    from modules.camera.camera_iso import CameraIso
    from modules.game_object.game_object_2d import GameObject2d
    from modules.game_object.game_object_iso import GameObjectIso
    from modules.team import Team


PARTICLES_PER_EXPLOSION_ISO = 3
PARTICLES_PER_EXPLOSION_2D = 20


def create_explosion_2d(
    *,
    position: Point,
    particles: pg.sprite.Group[GenericParticle],
    team: Team,
    count: int = PARTICLES_PER_EXPLOSION_2D,
) -> None:
    """Spawns a burst of particles at position with team color.

    :param position: Explosion center (x, y).
    :param particles: Particle group to add to.
    :param team: Team for particle color.
    :param count: Number of particles (default: PARTICLES_PER_EXPLOSION).
    """
    # Spawns a burst of particles at position with team color.
    color = team_to_color[team]
    for _ in range(count):
        vx = random.uniform(-3, 3)
        vy = random.uniform(-3, 3)
        size = random.randint(2, 4)
        lifetime = random.randint(3, 7)
        particles.add(GenericParticle(position, vx, vy, size, color, lifetime))


def create_explosion_iso(
    *,
    position: Point,
    particles: pg.sprite.Group[GenericParticle],
    team: Team,
    count: int = PARTICLES_PER_EXPLOSION_ISO,
) -> None:
    color = team_to_color[team]
    for _ in range(count):
        vx = random.uniform(-3, 3)
        vy = random.uniform(-3, 3)
        size = random.randint(1, 2)
        lifetime = random.randint(1, 3)
        particles.add(GenericParticle(position, vx, vy, size, color, lifetime))


class GenericParticle(pg.sprite.Sprite):
    """Base particle: circular sprite with velocity, fading alpha over lifetime.

    Used for explosion effects.
    """

    def __init__(self, pos: Point, vx: float, vy: float, size: int, color: pg.Color, lifetime: int) -> None:
        """:param pos: Initial position.
        :param vx: Initial x velocity.
        :param vy: Initial y velocity.
        :param size: Particle size in pixels.
        :param color: Pygame Color for the particle.
        :param lifetime: Lifetime in frames (scaled by 10).
        """
        # Base particle: circular sprite with velocity, fading alpha over lifetime.
        super().__init__()
        self.position = Vector2(pos)
        self.vx = vx
        self.vy = vy
        self.size = size
        self.color = color
        self.lifetime = lifetime * 10
        self.age = 0
        # pyrefly: ignore [missing-override-decorator]
        self.image = pg.Surface((size, size), pg.SRCALPHA)
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            pg.draw.circle(self.image, color, (size // 2, size // 2), size // 2)
            # pyrefly: ignore [missing-override-decorator]
            self.rect = self.image.get_rect(center=self.position)

    @override
    def update(self, *args: Any, **kwargs: Any) -> None:
        """Updates position, age, and alpha; kills when lifetime exceeded."""
        self.position.x += self.vx
        self.position.y += self.vy
        self.age += 1
        alpha = int(255 * (1 - self.age / self.lifetime))
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            self.image.set_alpha(alpha)

        if self.rect is not None:  # TODO: type guard - not sure why this can be None
            self.rect.center = self.position

        if self.age >= self.lifetime:
            self.kill()

    def draw_2d(self, surface: pg.Surface, camera: Camera2d) -> None:
        """Draws scaled and positioned particle if on-screen.

        :param surface: Surface to draw on.
        :param camera: Camera2d for transformation.
        """
        if self.rect is not None and isinstance(
            self.rect, pg.Rect
        ):  # TODO: type guard - not sure why this can be None | FRect
            screen_rect = camera.get_screen_rect(self.rect)
            if not screen_rect.colliderect((0, 0, camera.width, camera.height)):
                return

        screen_pos = camera.world_to_screen(self.position)
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            scaled_size = (
                int(self.image.get_width() * camera.zoom),
                int(self.image.get_height() * camera.zoom),
            )
            if scaled_size[0] > 0 and scaled_size[1] > 0:
                scaled_image = pg.transform.smoothscale(self.image, scaled_size)
                offset_x = scaled_size[0] / 2
                offset_y = scaled_size[1] / 2
                blit_pos = (screen_pos[0] - offset_x, screen_pos[1] - offset_y)
                surface.blit(scaled_image, blit_pos)

    def draw_iso(self, surface: pg.Surface, camera: CameraIso) -> None:
        if self.rect is not None and isinstance(
            self.rect, pg.Rect
        ):  # TODO: type guard - not sure why this can be None | FRect
            screen_rect = camera.get_screen_rect(self.rect)
            if not screen_rect.colliderect((0, 0, camera.width, camera.height)):
                return

        screen_pos = camera.world_to_iso(self.position, camera.zoom)
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            scaled_size = (
                int(self.image.get_width() * camera.zoom),
                int(self.image.get_height() * camera.zoom),
            )
            if scaled_size[0] > 0 and scaled_size[1] > 0:
                scaled_image = pg.transform.smoothscale(self.image, scaled_size)
                offset_x = scaled_size[0] / 2
                offset_y = scaled_size[1] / 2
                blit_pos = (screen_pos[0] - offset_x, screen_pos[1] - offset_y)
                surface.blit(scaled_image, blit_pos)


class PlasmaBurnParticle(GenericParticle):
    """Attached particle that follows an entity, offset and rotated with it.

    Used for damage burn effects on entities.
    """

    def __init__(self, pos: Point, entity: GameObject2d | GameObjectIso, color: pg.Color, lifetime: int) -> None:
        """:param pos: Initial position (unused, as it follows entity).
        :param entity: Entity to attach to.
        :param color: Pygame Color for the particle.
        :param lifetime: Lifetime in seconds (scaled by 30).
        """
        super().__init__(pos, 0, 0, 4, color, lifetime)
        self.entity = entity
        self.offset = Vector2(random.uniform(-20, 20), random.uniform(-10, 10))
        self.initial_lifetime = lifetime * 30

    @override
    def update(self, *args: Any, **kwargs: Any) -> None:
        """Updates position relative to entity, fades over time."""
        # Updates position relative to entity, fades over time.
        body_angle = getattr(self.entity, "body_angle", 0)
        rotated_offset = self.offset.rotate_rad(-body_angle)
        self.position = self.entity.position + rotated_offset
        self.age += 1
        alpha = int(255 * (1 - self.age / self.initial_lifetime))
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            self.image.set_alpha(alpha)

        if self.rect is not None:  # TODO: type guard - not sure why this can be None
            self.rect.center = self.position

        if self.age >= self.initial_lifetime:
            self.kill()
