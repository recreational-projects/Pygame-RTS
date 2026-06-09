"""Modular drawing functions for 2d units and buildings."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

from modules.data_2d import MINI_MAP_HEIGHT, MINI_MAP_WIDTH, SCREEN_HEIGHT, SCREEN_WIDTH, TILE_SIZE
from modules.team import team_to_color

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pygame.typing import ColorLike, Point

    from modules.camera.camera_2d import Camera2d
    from modules.fog_of_war import FogOfWar2d
    from modules.team import Team
    from modules.units_2d import Unit2d


def _create_infantry_image(size: Point, team_color: ColorLike) -> pg.Surface:
    """Creates a simple pixel-art style image for an Infantry unit.

    Draws head, eyes, helmet, body, arms, legs, and weapon using basic shapes.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn infantry image.
    """
    image = pg.Surface(size, pg.SRCALPHA)
    pg.draw.circle(image, (150, 150, 150), (8, 4), 4)  # Head
    pg.draw.circle(image, (0, 0, 0), (7, 3), 1)  # Left eye
    pg.draw.circle(image, (0, 0, 0), (9, 3), 1)  # Right eye
    pg.draw.rect(image, team_color, (6, 2, 4, 2))  # Helmet top
    pg.draw.rect(image, (100, 100, 100), (6, 8, 4, 8))  # Body
    pg.draw.line(image, (120, 120, 120), (6, 10), (2, 12), 2)  # Left arm
    pg.draw.line(image, (120, 120, 120), (10, 10), (14, 12), 2)  # Right arm
    pg.draw.line(image, team_color, (14, 10), (18, 8), 2)  # Rifle barrel
    pg.draw.rect(image, team_color, (18, 7, 3, 2))  # Rifle body
    pg.draw.line(image, (80, 80, 80), (7, 16), (7, 20), 2)  # Left leg
    pg.draw.line(image, (80, 80, 80), (9, 16), (9, 20), 2)  # Right leg
    return image


def _create_grenadier_image(size: Point, team_color: ColorLike) -> pg.Surface:
    """Creates a simple pixel-art style image for a Grenadier unit.

    Similar to Infantry but with grenade launcher details.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn grenadier image.
    """
    image = pg.Surface(size, pg.SRCALPHA)
    pg.draw.circle(image, (150, 150, 150), (8, 4), 4)  # Head
    pg.draw.circle(image, (0, 0, 0), (7, 3), 1)  # Left eye
    pg.draw.circle(image, (0, 0, 0), (9, 3), 1)  # Right eye
    pg.draw.rect(image, team_color, (6, 2, 4, 2))  # Helmet top
    pg.draw.rect(image, (100, 100, 100), (6, 8, 4, 8))  # Body
    pg.draw.line(image, (120, 120, 120), (6, 10), (2, 12), 2)  # Left arm
    pg.draw.line(image, (120, 120, 120), (10, 10), (14, 12), 2)  # Right arm
    pg.draw.line(image, (200, 100, 100), (14, 10), (18, 12), 2)  # Grenade launcher barrel
    pg.draw.circle(image, (200, 0, 0), (18, 12), 3)  # Grenade tip
    pg.draw.circle(image, (150, 0, 0), (12, 10), 2)  # Grenade chamber
    pg.draw.line(image, (80, 80, 80), (7, 16), (7, 20), 2)  # Left leg
    pg.draw.line(image, (80, 80, 80), (9, 16), (9, 20), 2)  # Right leg
    return image


def _create_tank_surfaces(team: Team) -> tuple[pg.Surface, pg.Surface, pg.Surface]:
    """Creates separate surfaces for tank body, turret, and barrel for modular rotation.

    :param team: The team enum for color selection.
    :return: Tuple of (body_surf, turret_surf, barrel_surf) Pygame Surfaces.
    """
    _team_color = team_to_color[team]
    body_surf = pg.Surface((30, 20), pg.SRCALPHA)
    pg.draw.rect(body_surf, (50, 50, 50), (0, 0, 30, 3), width=2)  # Top track
    pg.draw.rect(body_surf, (50, 50, 50), (0, 17, 30, 3), width=2)  # Bottom track
    pg.draw.rect(body_surf, _team_color, (2, 3, 26, 14), width=2)  # Hull outline
    pg.draw.line(body_surf, _team_color, (0, 3), (30, 3), width=2)  # Hull top
    pg.draw.circle(body_surf, (60, 60, 60), (5, 10), 1, width=1)  # Left wheel hub
    pg.draw.circle(body_surf, (60, 60, 60), (25, 10), 1, width=1)  # Right wheel hub
    turret_surf = pg.Surface((12, 12), pg.SRCALPHA)
    pg.draw.circle(turret_surf, _team_color, (6, 6), 6, width=2)  # Turret circle
    barrel_surf = pg.Surface((20, 6), pg.SRCALPHA)
    pg.draw.line(barrel_surf, _team_color, (0, 3), (20, 3), width=3)  # Barrel
    pg.draw.line(barrel_surf, (90, 90, 90), (20, 2), (20, 4), width=1)  # Muzzle brake
    return body_surf, turret_surf, barrel_surf


def _draw_tank(
    obj,  # pyrefly: ignore [implicit-any-parameter]
    surface: pg.Surface,
    camera: Camera2d,
    mouse_pos: Point | None = None,
) -> None:
    """Custom draw method for Tank: scales, rotates, and blits body, turret, and barrel independently.
    Handles selection circle and health bar.

    :param obj: The Tank instance.
    :param surface: The Pygame surface to draw on.
    :param camera: The Camera2d instance for world-to-screen transformation.
    :param mouse_pos: Optional mouse position for hover effects.
    """
    if obj.health <= 0:
        return
    screen_pos = camera.world_to_screen(obj.position)
    zoom = camera.zoom
    body_scaled = pg.transform.smoothscale(obj.body_surf, (int(30 * zoom), int(20 * zoom)))
    rotated_body = pg.transform.rotate(body_scaled, -math.degrees(obj.body_angle))
    body_rect = rotated_body.get_rect(center=screen_pos)
    surface.blit(rotated_body, body_rect.topleft)
    turret_scaled = pg.transform.smoothscale(obj.turret_surf, (int(12 * zoom), int(12 * zoom)))
    rotated_turret = pg.transform.rotate(turret_scaled, -math.degrees(obj.turret_angle))
    turret_rect = rotated_turret.get_rect()
    offset_rot = obj.turret_offset.rotate_rad(obj.body_angle) * zoom
    turret_center = Vector2(body_rect.center) + offset_rot
    turret_rect.center = turret_center
    surface.blit(rotated_turret, turret_rect.topleft)
    barrel_scaled = pg.transform.smoothscale(obj.barrel_surf, (int(20 * zoom), int(6 * zoom)))
    rotated_barrel = pg.transform.rotate(barrel_scaled, -math.degrees(obj.turret_angle))
    barrel_rect = rotated_barrel.get_rect()
    barrel_offset_rot = obj.barrel_offset.rotate_rad(obj.turret_angle) * zoom
    barrel_center = Vector2(turret_center) + barrel_offset_rot
    barrel_rect.center = barrel_center
    surface.blit(rotated_barrel, barrel_rect.topleft)
    if obj.selected:
        radius = 15 * zoom + 3
        pg.draw.circle(
            surface,
            (255, 255, 0),
            (int(screen_pos[0]), int(screen_pos[1])),
            int(radius),
            int(2 * zoom),
        )
    obj.draw_health_bar_if_needed(surface=surface, camera=camera, mouse_pos=mouse_pos)
    for particle in obj.plasma_burn_particles:
        particle.draw_2d(surface, camera)


def _create_machinegunvehicle_surfaces(team: Team) -> tuple[pg.Surface, pg.Surface, pg.Surface]:
    """Creates surfaces for MachineGunVehicle: body with wheels, turret, and MG barrel.

    :param team: The team enum for color selection.
    :return: Tuple of (body_surf, turret_surf, barrel_surf) Pygame Surfaces.
    """
    _team_color = team_to_color[team]
    body_surf = pg.Surface((35, 25), pg.SRCALPHA)
    pg.draw.rect(body_surf, _team_color, (0, 5, 35, 15), width=2)  # Hull
    wheel_positions = [5, 15, 25]
    for px in wheel_positions:
        pg.draw.circle(body_surf, (50, 50, 50), (px, 5), 3, width=2)  # Top wheels
        pg.draw.circle(body_surf, (50, 50, 50), (px, 20), 3, width=2)  # Bottom wheels
    pg.draw.line(body_surf, _team_color, (0, 5), (35, 5), width=2)  # Hull top
    for px in wheel_positions:
        pg.draw.circle(body_surf, (40, 40, 40), (px, 5), 1, width=1)  # Wheel hubs top
        pg.draw.circle(body_surf, (40, 40, 40), (px, 20), 1, width=1)  # Wheel hubs bottom
    turret_surf = pg.Surface((8, 8), pg.SRCALPHA)
    pg.draw.rect(turret_surf, _team_color, (0, 0, 8, 8), width=2)  # Turret
    barrel_surf = pg.Surface((25, 2), pg.SRCALPHA)
    pg.draw.line(barrel_surf, _team_color, (0, 1), (25, 1), width=2)  # MG barrel
    return body_surf, turret_surf, barrel_surf


def _draw_machinegunvehicle(
    obj,  # pyrefly: ignore [implicit-any-parameter]
    surface: pg.Surface,
    camera: Camera2d,
    mouse_pos: Point | None = None,
) -> None:
    """Custom draw for MachineGunVehicle, similar to Tank.

    :param obj: The MachineGunVehicle instance.
    :param surface: The Pygame surface to draw on.
    :param camera: The Camera2d instance for world-to-screen transformation.
    :param mouse_pos: Optional mouse position for hover effects.
    """
    if obj.health <= 0:
        return
    screen_pos = camera.world_to_screen(obj.position)
    zoom = camera.zoom
    body_scaled = pg.transform.smoothscale(obj.body_surf, (int(35 * zoom), int(25 * zoom)))
    rotated_body = pg.transform.rotate(body_scaled, -math.degrees(obj.body_angle))
    body_rect = rotated_body.get_rect(center=screen_pos)
    surface.blit(rotated_body, body_rect.topleft)
    turret_scaled = pg.transform.smoothscale(obj.turret_surf, (int(8 * zoom), int(8 * zoom)))
    rotated_turret = pg.transform.rotate(turret_scaled, -math.degrees(obj.turret_angle))
    turret_rect = rotated_turret.get_rect()
    offset_rot = obj.turret_offset.rotate_rad(obj.body_angle) * zoom
    turret_center = Vector2(body_rect.center) + offset_rot
    turret_rect.center = turret_center
    surface.blit(rotated_turret, turret_rect.topleft)
    barrel_scaled = pg.transform.smoothscale(obj.barrel_surf, (int(25 * zoom), int(2 * zoom)))
    rotated_barrel = pg.transform.rotate(barrel_scaled, -math.degrees(obj.turret_angle))
    barrel_rect = rotated_barrel.get_rect()
    barrel_offset_rot = obj.barrel_offset.rotate_rad(obj.turret_angle) * zoom
    barrel_center = Vector2(turret_center) + barrel_offset_rot
    barrel_rect.center = barrel_center
    surface.blit(rotated_barrel, barrel_rect.topleft)
    if obj.selected:
        radius = 17.5 * zoom + 3
        pg.draw.circle(
            surface,
            (255, 255, 0),
            (int(screen_pos[0]), int(screen_pos[1])),
            int(radius),
            int(2 * zoom),
        )
    obj.draw_health_bar_if_needed(surface=surface, camera=camera, mouse_pos=mouse_pos)
    for particle in obj.plasma_burn_particles:
        particle.draw_2d(surface, camera)


def _create_rocketartillery_surfaces(team: Team) -> tuple[pg.Surface, pg.Surface, pg.Surface]:
    """Surfaces for RocketArtillery: body with tracks, rectangular turret, triple rocket barrels.

    :param team: The team enum for color selection.
    :return: Tuple of (body_surf, turret_surf, barrel_surf) Pygame Surfaces.
    """
    _team_color = team_to_color[team]
    body_surf = pg.Surface((40, 25), pg.SRCALPHA)
    pg.draw.rect(body_surf, _team_color, (0, 5, 40, 15), width=2)  # Hull
    pg.draw.rect(body_surf, (50, 50, 50), (0, 0, 40, 5), width=2)  # Top track
    pg.draw.rect(body_surf, (50, 50, 50), (0, 20, 40, 5), width=2)  # Bottom track
    pg.draw.line(body_surf, _team_color, (0, 5), (40, 5), width=2)  # Hull top
    pg.draw.circle(body_surf, (40, 40, 40), (8, 12.5), 3, width=2)  # Left wheel
    pg.draw.circle(body_surf, (40, 40, 40), (32, 12.5), 3, width=2)  # Right wheel
    turret_surf = pg.Surface((12, 12), pg.SRCALPHA)
    pg.draw.rect(turret_surf, _team_color, (0, 0, 12, 12), width=2)  # Turret
    barrel_surf = pg.Surface((30, 8), pg.SRCALPHA)
    for i in range(3):
        pg.draw.line(barrel_surf, _team_color, (i * 10, 4), (i * 10 + 20, 4), width=2)  # Three rocket tubes
    return body_surf, turret_surf, barrel_surf


def _draw_rocketartillery(
    obj,  # pyrefly: ignore [implicit-any-parameter]
    surface: pg.Surface,
    camera: Camera2d,
    mouse_pos: Point | None = None,
) -> None:
    """Custom draw for RocketArtillery, analogous to previous vehicle draws.

    :param obj: The RocketArtillery instance.
    :param surface: The Pygame surface to draw on.
    :param camera: The Camera2d instance for world-to-screen transformation.
    :param mouse_pos: Optional mouse position for hover effects.
    """
    if obj.health <= 0:
        return
    screen_pos = camera.world_to_screen(obj.position)
    zoom = camera.zoom
    body_scaled = pg.transform.smoothscale(obj.body_surf, (int(40 * zoom), int(25 * zoom)))
    rotated_body = pg.transform.rotate(body_scaled, -math.degrees(obj.body_angle))
    body_rect = rotated_body.get_rect(center=screen_pos)
    surface.blit(rotated_body, body_rect.topleft)
    turret_scaled = pg.transform.smoothscale(obj.turret_surf, (int(12 * zoom), int(12 * zoom)))
    rotated_turret = pg.transform.rotate(turret_scaled, -math.degrees(obj.turret_angle))
    turret_rect = rotated_turret.get_rect()
    offset_rot = obj.turret_offset.rotate_rad(obj.body_angle) * zoom
    turret_center = Vector2(body_rect.center) + offset_rot
    turret_rect.center = turret_center
    surface.blit(rotated_turret, turret_rect.topleft)
    barrel_scaled = pg.transform.smoothscale(obj.barrel_surf, (int(30 * zoom), int(8 * zoom)))
    rotated_barrel = pg.transform.rotate(barrel_scaled, -math.degrees(obj.turret_angle))
    barrel_rect = rotated_barrel.get_rect()
    barrel_offset_rot = obj.barrel_offset.rotate_rad(obj.turret_angle) * zoom
    barrel_center = Vector2(turret_center) + barrel_offset_rot
    barrel_rect.center = barrel_center
    surface.blit(rotated_barrel, barrel_rect.topleft)
    if obj.selected:
        radius = 20 * zoom + 3
        pg.draw.circle(
            surface,
            (255, 255, 0),
            (int(screen_pos[0]), int(screen_pos[1])),
            int(radius),
            int(2 * zoom),
        )
    obj.draw_health_bar_if_needed(surface=surface, camera=camera, mouse_pos=mouse_pos)
    for particle in obj.plasma_burn_particles:
        particle.draw_2d(surface, camera)


def _create_attackhelicopter_surfaces(team: Team) -> tuple[pg.Surface, pg.Surface, pg.Surface]:
    """Surfaces for AttackHelicopter: fuselage, cockpit, tail rotor, skids, turret, and missile pod.

    :param team: The team enum for color selection.
    :return: Tuple of (body_surf, turret_surf, barrel_surf) Pygame Surfaces.
    """
    _team_color = team_to_color[team]
    body_surf = pg.Surface((25, 15), pg.SRCALPHA)
    pg.draw.ellipse(body_surf, _team_color, (0, 2, 25, 11), width=2)  # Fuselage outline
    pg.draw.ellipse(body_surf, (80, 80, 80), (2, 4, 21, 7), width=2)  # Cockpit
    pg.draw.ellipse(body_surf, (150, 200, 255), (18, 3, 6, 5), width=2)  # Canopy
    pg.draw.line(body_surf, (90, 90, 90), (0, 7), (-5, 7), width=2)  # Tail boom
    pg.draw.circle(body_surf, _team_color, (-5, 7), 2, width=2)  # Tail rotor
    pg.draw.circle(body_surf, (60, 60, 60), (12, 7), 3, width=2)  # Main rotor hub
    pg.draw.line(body_surf, _team_color, (0, 0), (25, 0), width=2)  # Rotor spine
    pg.draw.line(body_surf, _team_color, (5, 12), (9, 12), width=2)  # Left skid
    pg.draw.line(body_surf, _team_color, (16, 12), (20, 12), width=2)  # Right skid
    turret_surf = pg.Surface((8, 6), pg.SRCALPHA)
    pg.draw.rect(turret_surf, _team_color, (0, 0, 8, 6), width=2)  # Turret
    barrel_surf = pg.Surface((12, 2), pg.SRCALPHA)
    pg.draw.line(barrel_surf, _team_color, (0, 1), (12, 1), width=2)  # Missile pod
    return body_surf, turret_surf, barrel_surf


def _draw_attackhelicopter(
    obj,  # pyrefly: ignore [implicit-any-parameter]
    surface: pg.Surface,
    camera: Camera2d,
    mouse_pos: Point | None = None,
) -> None:
    """Custom draw for AttackHelicopter: adjusts Y for fly_height, draws main rotor blades.

    :param obj: The AttackHelicopter instance.
    :param surface: The Pygame surface to draw on.
    :param camera: The Camera2d instance for world-to-screen transformation.
    :param mouse_pos: Optional mouse position for hover effects.
    """
    if obj.health <= 0:
        return
    _team_color = team_to_color[obj.team]
    fly_screen_pos = camera.world_to_screen((obj.position.x, obj.position.y - obj.fly_height))
    zoom = camera.zoom
    body_scaled = pg.transform.smoothscale(obj.body_surf, (int(25 * zoom), int(15 * zoom)))
    rotated_body = pg.transform.rotate(body_scaled, -math.degrees(obj.body_angle))
    body_rect = rotated_body.get_rect(center=fly_screen_pos)
    surface.blit(rotated_body, body_rect.topleft)
    turret_scaled = pg.transform.smoothscale(obj.turret_surf, (int(8 * zoom), int(6 * zoom)))
    rotated_turret = pg.transform.rotate(turret_scaled, -math.degrees(obj.turret_angle))
    turret_rect = rotated_turret.get_rect()
    offset_rot = obj.turret_offset.rotate_rad(obj.body_angle) * zoom
    turret_center = Vector2(body_rect.center) + offset_rot
    turret_rect.center = turret_center
    surface.blit(rotated_turret, turret_rect.topleft)
    barrel_scaled = pg.transform.smoothscale(obj.barrel_surf, (int(12 * zoom), int(2 * zoom)))
    rotated_barrel = pg.transform.rotate(barrel_scaled, -math.degrees(obj.turret_angle))
    barrel_rect = rotated_barrel.get_rect()
    barrel_offset_rot = obj.barrel_offset.rotate_rad(obj.turret_angle) * zoom
    barrel_center = Vector2(turret_center) + barrel_offset_rot
    barrel_rect.center = barrel_center
    surface.blit(rotated_barrel, barrel_rect.topleft)
    rotor_size = int(20 * zoom)
    pg.draw.circle(
        surface,
        _team_color,
        (int(fly_screen_pos[0]), int(fly_screen_pos[1])),
        rotor_size // 2,
        int(2 * zoom),
    )  # Rotor blades
    if obj.selected:
        radius = 12.5 * zoom + 3
        pg.draw.circle(
            surface,
            (255, 255, 0),
            (int(fly_screen_pos[0]), int(fly_screen_pos[1])),
            int(radius),
            int(2 * zoom),
        )
    obj.draw_health_bar_if_needed(surface=surface, camera=camera, mouse_pos=mouse_pos)
    for particle in obj.plasma_burn_particles:
        particle.draw_2d(surface, camera)


def _create_headquarters_image(size: Point, team: Team) -> pg.Surface:
    """Static building image for Headquarters: multi-story with windows, antenna, flag.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn headquarters image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((80, 80, 80))  # Base gray
    pg.draw.rect(
        image,
        (100, 100, 100),
        (
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(40 * scale_factor),
            int(35 * scale_factor),
        ),
    )  # Main structure
    pg.draw.rect(
        image,
        _team_color,
        (
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(40 * scale_factor),
            int(10 * scale_factor),
        ),
    )  # Roof
    for i in range(3):
        win_x = int(7.5 * scale_factor + i * 7.5 * scale_factor)
        win_y = int(15 * scale_factor + (i % 2) * 7.5 * scale_factor)
        pg.draw.rect(
            image, (100, 150, 255), (win_x, win_y, int(4 * scale_factor), int(3 * scale_factor))
        )  # Left windows
        pg.draw.rect(
            image,
            (100, 150, 255),
            (
                int(38.5 * scale_factor - (i % 2) * 4 * scale_factor),
                win_y,
                int(4 * scale_factor),
                int(3 * scale_factor),
            ),
        )  # Right windows
    pg.draw.rect(
        image,
        (50, 50, 50),
        (
            int(20 * scale_factor),
            int(40 * scale_factor),
            int(10 * scale_factor),
            int(10 * scale_factor),
        ),
    )  # Door
    pg.draw.line(
        image,
        (30, 30, 30),
        (int(20 * scale_factor), int(40 * scale_factor)),
        (int(30 * scale_factor), int(50 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Antenna base
    pg.draw.line(
        image,
        _team_color,
        (int(25 * scale_factor), int(5 * scale_factor)),
        (int(25 * scale_factor), 0),
        int(1 * scale_factor),
    )  # Flagpole
    pg.draw.circle(
        image, _team_color, (int(25 * scale_factor), int(25 * scale_factor)), int(5 * scale_factor)
    )  # Central emblem
    pg.draw.arc(
        image,
        (40, 40, 40),
        (
            int(20 * scale_factor),
            int(20 * scale_factor),
            int(10 * scale_factor),
            int(10 * scale_factor),
        ),
        0,
        math.pi,
        int(1 * scale_factor),
    )  # Arc detail
    pg.draw.rect(
        image,
        (60, 60, 60),
        (
            int(10 * scale_factor),
            int(42.5 * scale_factor),
            int(5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Left door panel
    pg.draw.rect(
        image,
        (60, 60, 60),
        (
            int(35 * scale_factor),
            int(42.5 * scale_factor),
            int(5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Right door panel
    return image


def _create_barracks_image(size: Point, team: Team) -> pg.Surface:
    """Barracks: sloped roof, windows, door with gate details.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn barracks image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((100, 100, 100))  # Base
    pg.draw.rect(
        image,
        (120, 120, 120),
        (
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
            int(35 * scale_factor),
            int(30 * scale_factor),
        ),
    )  # Walls
    pg.draw.polygon(
        image,
        (90, 90, 90),
        [
            (0, int(2.5 * scale_factor)),
            (int(40 * scale_factor), int(2.5 * scale_factor)),
            (int(30 * scale_factor), 0),
            (int(10 * scale_factor), 0),
        ],
    )  # Roof
    for i in range(2):
        win_y = int(10 * scale_factor + i * 6 * scale_factor)
        pg.draw.rect(
            image,
            (100, 150, 255),
            (int(7.5 * scale_factor), win_y, int(4 * scale_factor), int(3 * scale_factor)),
        )  # Left windows
        pg.draw.rect(
            image,
            (100, 150, 255),
            (int(28.5 * scale_factor), win_y, int(4 * scale_factor), int(3 * scale_factor)),
        )  # Right windows
    pg.draw.rect(
        image,
        (60, 60, 60),
        (
            int(15 * scale_factor),
            int(32.5 * scale_factor),
            int(10 * scale_factor),
            int(7.5 * scale_factor),
        ),
    )  # Door
    pg.draw.line(
        image,
        (40, 40, 40),
        (int(15 * scale_factor), int(32.5 * scale_factor)),
        (int(25 * scale_factor), int(40 * scale_factor)),
        int(1 * scale_factor),
    )  # Left gate arm
    pg.draw.line(
        image,
        (40, 40, 40),
        (int(25 * scale_factor), int(32.5 * scale_factor)),
        (int(35 * scale_factor), int(40 * scale_factor)),
        int(1 * scale_factor),
    )  # Right gate arm
    pg.draw.rect(
        image,
        (70, 70, 70),
        (
            int(35 * scale_factor),
            int(5 * scale_factor),
            int(2.5 * scale_factor),
            int(5 * scale_factor),
        ),
    )  # Chimney
    pg.draw.rect(
        image,
        (50, 50, 50),
        (
            int(36 * scale_factor),
            int(2.5 * scale_factor),
            int(0.5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Chimney smoke
    pg.draw.line(
        image,
        _team_color,
        (int(2.5 * scale_factor), int(2.5 * scale_factor)),
        (0, 0),
        int(1.5 * scale_factor),
    )  # Team accent
    return image


def _create_warfactory_image(size: Point, team: Team) -> pg.Surface:
    """WarFactory: industrial building with smokestack, windows, conveyor details.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn war factory image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((150, 150, 150))  # Base
    pg.draw.rect(
        image,
        (130, 130, 130),
        (
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(40 * scale_factor),
            int(25 * scale_factor),
        ),
    )  # Main walls
    pg.draw.rect(image, (140, 140, 140), (0, 0, int(50 * scale_factor), int(40 * scale_factor)))  # Foundation
    pg.draw.rect(
        image,
        (110, 110, 110),
        (int(42.5 * scale_factor), 0, int(7.5 * scale_factor), int(15 * scale_factor)),
    )  # Smokestack base
    pg.draw.rect(
        image,
        (200, 200, 200),
        (
            int(43.5 * scale_factor),
            int(1 * scale_factor),
            int(5.5 * scale_factor),
            int(13 * scale_factor),
        ),
    )  # Smokestack
    pg.draw.circle(
        image,
        (100, 150, 255),
        (int(46 * scale_factor), int(9 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Stack light
    for y in [10, 20]:
        pg.draw.rect(
            image,
            (100, 150, 255),
            (
                int(10 * scale_factor),
                int(y * scale_factor),
                int(6 * scale_factor),
                int(4 * scale_factor),
            ),
        )  # Left windows
        pg.draw.rect(
            image,
            (100, 150, 255),
            (
                int(34 * scale_factor),
                int(y * scale_factor),
                int(6 * scale_factor),
                int(4 * scale_factor),
            ),
        )  # Right windows
    pg.draw.rect(
        image,
        (70, 70, 70),
        (
            int(20 * scale_factor),
            int(30 * scale_factor),
            int(10 * scale_factor),
            int(10 * scale_factor),
        ),
    )  # Door
    pg.draw.line(
        image,
        (50, 50, 50),
        (int(20 * scale_factor), int(30 * scale_factor)),
        (int(30 * scale_factor), int(40 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Left conveyor
    pg.draw.line(
        image,
        (50, 50, 50),
        (int(30 * scale_factor), int(30 * scale_factor)),
        (int(40 * scale_factor), int(40 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Right conveyor
    pg.draw.line(
        image,
        (90, 90, 90),
        (int(5 * scale_factor), int(35 * scale_factor)),
        (int(45 * scale_factor), int(35 * scale_factor)),
        int(1 * scale_factor),
    )  # Conveyor belt
    pg.draw.rect(
        image,
        _team_color,
        (
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Team logo
    return image


def _create_hangar_image(size: Point, team: Team) -> pg.Surface:
    """Hangar: arched roof, control tower, doors for aircraft.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn hangar image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((120, 120, 120))  # Base
    pg.draw.rect(
        image,
        (140, 140, 140),
        (
            int(2.5 * scale_factor),
            int(5 * scale_factor),
            int(40 * scale_factor),
            int(25 * scale_factor),
        ),
    )  # Walls
    pg.draw.polygon(
        image,
        (100, 100, 100),
        [
            (0, int(5 * scale_factor)),
            (int(45 * scale_factor), int(5 * scale_factor)),
            (int(35 * scale_factor), 0),
            (int(10 * scale_factor), 0),
        ],
    )  # Roof
    pg.draw.rect(
        image,
        (80, 80, 80),
        (
            int(20 * scale_factor),
            int(30 * scale_factor),
            int(5 * scale_factor),
            int(5 * scale_factor),
        ),
    )  # Door
    pg.draw.line(
        image,
        (60, 60, 60),
        (int(20 * scale_factor), int(30 * scale_factor)),
        (int(25 * scale_factor), int(35 * scale_factor)),
        int(1 * scale_factor),
    )  # Left door arm
    pg.draw.line(
        image,
        (60, 60, 60),
        (int(25 * scale_factor), int(30 * scale_factor)),
        (int(30 * scale_factor), int(35 * scale_factor)),
        int(1 * scale_factor),
    )  # Right door arm
    pg.draw.rect(
        image,
        (110, 110, 110),
        (
            int(40 * scale_factor),
            int(2.5 * scale_factor),
            int(5 * scale_factor),
            int(12.5 * scale_factor),
        ),
    )  # Tower
    pg.draw.circle(
        image,
        (100, 150, 255),
        (int(42.5 * scale_factor), int(7.5 * scale_factor)),
        int(1 * scale_factor),
    )  # Tower light
    pg.draw.rect(
        image,
        _team_color,
        (
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
            int(40 * scale_factor),
            int(1.5 * scale_factor),
        ),
    )  # Team stripe
    return image


def _create_powerplant_image(size: Point, team: Team) -> pg.Surface:
    """PowerPlant: cooling towers, windows, exhaust pipes.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn power plant image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((200, 180, 100))  # Base yellow
    pg.draw.rect(
        image,
        (220, 200, 120),
        (
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(30 * scale_factor),
            int(25 * scale_factor),
        ),
    )  # Main building
    pg.draw.rect(
        image,
        (150, 150, 150),
        (
            int(32.5 * scale_factor),
            int(2.5 * scale_factor),
            int(5 * scale_factor),
            int(12.5 * scale_factor),
        ),
    )  # Left tower
    pg.draw.rect(
        image,
        (150, 150, 150),
        (
            int(32.5 * scale_factor),
            int(20 * scale_factor),
            int(5 * scale_factor),
            int(12.5 * scale_factor),
        ),
    )  # Right tower
    pg.draw.rect(
        image,
        (100, 100, 100),
        (
            int(33.5 * scale_factor),
            int(3.5 * scale_factor),
            int(3 * scale_factor),
            int(11.5 * scale_factor),
        ),
    )  # Left tower vent
    pg.draw.rect(
        image,
        (100, 100, 100),
        (
            int(33.5 * scale_factor),
            int(21 * scale_factor),
            int(3 * scale_factor),
            int(11.5 * scale_factor),
        ),
    )  # Right tower vent
    pg.draw.rect(
        image,
        (120, 120, 120),
        (int(34 * scale_factor), 0, int(2 * scale_factor), int(2.5 * scale_factor)),
    )  # Left exhaust
    pg.draw.rect(
        image,
        (120, 120, 120),
        (
            int(34 * scale_factor),
            int(17.5 * scale_factor),
            int(2 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Right exhaust
    for i in range(2):
        win_y = int(10 * scale_factor + i * 5 * scale_factor)
        pg.draw.rect(
            image,
            (255, 255, 150),
            (int(10 * scale_factor), win_y, int(4 * scale_factor), int(3 * scale_factor)),
        )  # Left windows
        pg.draw.rect(
            image,
            (255, 255, 150),
            (int(26 * scale_factor), win_y, int(4 * scale_factor), int(3 * scale_factor)),
        )  # Right windows
    pg.draw.rect(
        image,
        (120, 120, 120),
        (
            int(17.5 * scale_factor),
            int(30 * scale_factor),
            int(5 * scale_factor),
            int(10 * scale_factor),
        ),
    )  # Door
    pg.draw.line(
        image,
        (140, 140, 140),
        (int(35 * scale_factor), int(15 * scale_factor)),
        (int(40 * scale_factor), int(15 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Left pipe
    pg.draw.line(
        image,
        (140, 140, 140),
        (int(35 * scale_factor), int(25 * scale_factor)),
        (int(40 * scale_factor), int(25 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Right pipe
    pg.draw.rect(image, _team_color, (0, 0, int(40 * scale_factor), int(1.5 * scale_factor)))  # Team stripe
    return image


def _create_oilderrick_image(size: Point, team: Team) -> pg.Surface:
    """OilDerrick: derrick structure, platform, pump jack.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn oil derrick image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((139, 120, 80))  # Desert base
    pg.draw.rect(
        image,
        (100, 80, 60),
        (
            int(10 * scale_factor),
            int(10 * scale_factor),
            int(10 * scale_factor),
            int(25 * scale_factor),
        ),
    )  # Platform
    pg.draw.line(
        image,
        (80, 80, 80),
        (int(15 * scale_factor), int(12.5 * scale_factor)),
        (int(22.5 * scale_factor), int(7.5 * scale_factor)),
        int(2 * scale_factor),
    )  # Derrick leg left
    pg.draw.line(
        image,
        (60, 60, 60),
        (int(22.5 * scale_factor), int(7.5 * scale_factor)),
        (int(22.5 * scale_factor), int(15 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Derrick beam
    pg.draw.circle(
        image,
        (60, 60, 60),
        (int(22.5 * scale_factor), int(7.5 * scale_factor)),
        int(2.5 * scale_factor),
    )  # Derrick top
    pg.draw.rect(
        image,
        (120, 100, 80),
        (
            int(5 * scale_factor),
            int(35 * scale_factor),
            int(20 * scale_factor),
            int(5 * scale_factor),
        ),
    )  # Pump base
    pg.draw.rect(
        image,
        _team_color,
        (
            int(12.5 * scale_factor),
            int(37.5 * scale_factor),
            int(5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Pump head
    pg.draw.line(
        image,
        (90, 70, 50),
        (int(5 * scale_factor), int(35 * scale_factor)),
        (int(5 * scale_factor), int(10 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Left support
    pg.draw.line(
        image,
        (90, 70, 50),
        (int(25 * scale_factor), int(35 * scale_factor)),
        (int(25 * scale_factor), int(10 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Right support
    pg.draw.rect(
        image,
        (70, 50, 30),
        (
            int(20 * scale_factor),
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(5 * scale_factor),
        ),
    )  # Engine
    return image


def _create_refinery_image(size: Point, team: Team) -> pg.Surface:
    """Refinery: tanks, pipes, distillation tower.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn refinery image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((100, 50, 0))  # Brown base
    pg.draw.ellipse(
        image,
        (120, 80, 40),
        (
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(25 * scale_factor),
            int(30 * scale_factor),
        ),
    )  # Left tank
    pg.draw.ellipse(
        image,
        (120, 80, 40),
        (
            int(30 * scale_factor),
            int(5 * scale_factor),
            int(25 * scale_factor),
            int(30 * scale_factor),
        ),
    )  # Right tank
    pg.draw.circle(
        image,
        (140, 100, 60),
        (int(17.5 * scale_factor), int(20 * scale_factor)),
        int(2.5 * scale_factor),
    )  # Left valve
    pg.draw.circle(
        image,
        (140, 100, 60),
        (int(42.5 * scale_factor), int(20 * scale_factor)),
        int(2.5 * scale_factor),
    )  # Right valve
    pg.draw.rect(
        image,
        (80, 80, 80),
        (
            int(27.5 * scale_factor),
            int(17.5 * scale_factor),
            int(5 * scale_factor),
            int(5 * scale_factor),
        ),
    )  # Pump
    pg.draw.rect(
        image,
        (60, 60, 60),
        (
            int(50 * scale_factor),
            int(10 * scale_factor),
            int(10 * scale_factor),
            int(20 * scale_factor),
        ),
    )  # Tower base
    pg.draw.rect(
        image,
        (80, 80, 80),
        (
            int(51 * scale_factor),
            int(11 * scale_factor),
            int(8 * scale_factor),
            int(18 * scale_factor),
        ),
    )  # Tower
    pg.draw.line(
        image,
        (50, 50, 50),
        (int(30 * scale_factor), int(20 * scale_factor)),
        (int(50 * scale_factor), int(20 * scale_factor)),
        int(2 * scale_factor),
    )  # Top pipe
    pg.draw.line(
        image,
        (50, 50, 50),
        (int(30 * scale_factor), int(25 * scale_factor)),
        (int(50 * scale_factor), int(25 * scale_factor)),
        int(2 * scale_factor),
    )  # Bottom pipe
    pg.draw.rect(image, _team_color, (0, 0, int(60 * scale_factor), int(2.5 * scale_factor)))  # Team stripe
    return image


def _create_shalefracker_image(size: Point, team: Team) -> pg.Surface:
    """ShaleFracker: drilling rig with piston and wellhead.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn shale fracker image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((80, 60, 40))  # Earth base
    pg.draw.rect(
        image,
        (100, 80, 60),
        (
            int(5 * scale_factor),
            int(5 * scale_factor),
            int(25 * scale_factor),
            int(25 * scale_factor),
        ),
    )  # Rig base
    pg.draw.rect(
        image,
        (120, 100, 80),
        (
            int(10 * scale_factor),
            int(30 * scale_factor),
            int(15 * scale_factor),
            int(5 * scale_factor),
        ),
    )  # Platform
    pg.draw.line(
        image,
        (60, 40, 20),
        (int(17.5 * scale_factor), int(5 * scale_factor)),
        (int(17.5 * scale_factor), int(30 * scale_factor)),
        int(4 * scale_factor),
    )  # Drill pipe
    pg.draw.polygon(
        image,
        (40, 20, 0),
        [
            (int(16.5 * scale_factor), int(32.5 * scale_factor)),
            (int(17.5 * scale_factor), int(35 * scale_factor)),
            (int(18.5 * scale_factor), int(32.5 * scale_factor)),
        ],
    )  # Drill bit
    pg.draw.line(
        image,
        (90, 70, 50),
        (int(5 * scale_factor), int(30 * scale_factor)),
        (int(5 * scale_factor), int(5 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Left leg
    pg.draw.line(
        image,
        (90, 70, 50),
        (int(30 * scale_factor), int(30 * scale_factor)),
        (int(30 * scale_factor), int(5 * scale_factor)),
        int(1.5 * scale_factor),
    )  # Right leg
    pg.draw.rect(
        image,
        _team_color,
        (
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Team logo
    return image


def _create_blackmarket_image(size: Point, team: Team) -> pg.Surface:
    """BlackMarket: tent-like structure with stalls and signage.

    :param size: Tuple of (width, height) for the surface.
    :param team: The team enum for color selection.
    :return: A Pygame Surface with the drawn black market image.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    scaled_size = (int(size[0] * scale_factor), int(size[1] * scale_factor))
    image = pg.Surface(scaled_size)
    image.fill((40, 40, 80))  # Blue base
    pg.draw.polygon(
        image,
        (60, 60, 100),
        [
            (int(5 * scale_factor), int(10 * scale_factor)),
            (int(17.5 * scale_factor), int(2.5 * scale_factor)),
            (int(30 * scale_factor), int(10 * scale_factor)),
        ],
    )  # Left tent
    pg.draw.line(
        image,
        (50, 50, 90),
        (int(5 * scale_factor), int(10 * scale_factor)),
        (int(30 * scale_factor), int(10 * scale_factor)),
        int(1 * scale_factor),
    )  # Tent base
    pg.draw.polygon(
        image,
        (60, 60, 100),
        [
            (int(5 * scale_factor), int(20 * scale_factor)),
            (int(17.5 * scale_factor), int(12.5 * scale_factor)),
            (int(30 * scale_factor), int(20 * scale_factor)),
        ],
    )  # Right tent
    pg.draw.line(
        image,
        (50, 50, 90),
        (int(5 * scale_factor), int(20 * scale_factor)),
        (int(30 * scale_factor), int(20 * scale_factor)),
        int(1 * scale_factor),
    )  # Tent base
    pg.draw.rect(
        image,
        (80, 60, 40),
        (
            int(32.5 * scale_factor),
            int(5 * scale_factor),
            int(10 * scale_factor),
            int(7.5 * scale_factor),
        ),
    )  # Stall left
    pg.draw.rect(
        image,
        (80, 60, 40),
        (
            int(32.5 * scale_factor),
            int(15 * scale_factor),
            int(10 * scale_factor),
            int(7.5 * scale_factor),
        ),
    )  # Stall right
    pg.draw.line(
        image,
        (70, 50, 30),
        (int(32.5 * scale_factor), int(7.5 * scale_factor)),
        (int(42.5 * scale_factor), int(7.5 * scale_factor)),
        int(0.5 * scale_factor),
    )  # Stall shelf left
    pg.draw.line(
        image,
        (70, 50, 30),
        (int(32.5 * scale_factor), int(17.5 * scale_factor)),
        (int(42.5 * scale_factor), int(17.5 * scale_factor)),
        int(0.5 * scale_factor),
    )  # Stall shelf right
    pg.draw.rect(
        image,
        (70, 70, 70),
        (
            int(10 * scale_factor),
            int(22.5 * scale_factor),
            int(10 * scale_factor),
            int(7.5 * scale_factor),
        ),
    )  # Counter
    pg.draw.rect(image, _team_color, (0, 0, int(45 * scale_factor), int(1.5 * scale_factor)))  # Team stripe
    return image


def _create_turret_surfaces(team: Team) -> tuple[pg.Surface, pg.Surface, pg.Surface]:
    """Turret: base platform, rotating turret, gun barrel.

    :param team: The team enum for color selection.
    :return: Tuple of (body_surf, turret_surf, barrel_surf) Pygame Surfaces.
    """
    _team_color = team_to_color[team]
    scale_factor = 0.8
    body_surf = pg.Surface((int(30 * scale_factor), int(30 * scale_factor)), pg.SRCALPHA)
    pg.draw.rect(
        body_surf,
        (100, 100, 100),
        (
            int(7.5 * scale_factor),
            int(17.5 * scale_factor),
            int(15 * scale_factor),
            int(12.5 * scale_factor),
        ),
    )  # Base
    pg.draw.rect(
        body_surf,
        (80, 80, 80),
        (
            int(8.5 * scale_factor),
            int(18.5 * scale_factor),
            int(13 * scale_factor),
            int(10.5 * scale_factor),
        ),
    )  # Pedestal
    pg.draw.circle(
        body_surf,
        (60, 60, 60),
        (int(10 * scale_factor), int(27.5 * scale_factor)),
        int(1 * scale_factor),
    )  # Left foot
    pg.draw.circle(
        body_surf,
        (60, 60, 60),
        (int(20 * scale_factor), int(27.5 * scale_factor)),
        int(1 * scale_factor),
    )  # Right foot
    pg.draw.rect(
        body_surf,
        (120, 120, 120),
        (
            int(12.5 * scale_factor),
            int(25 * scale_factor),
            int(5 * scale_factor),
            int(2.5 * scale_factor),
        ),
    )  # Foot detail
    turret_surf = pg.Surface((int(10 * scale_factor), int(10 * scale_factor)), pg.SRCALPHA)
    pg.draw.circle(
        turret_surf,
        _team_color,
        (int(5 * scale_factor), int(5 * scale_factor)),
        int(5 * scale_factor),
    )  # Turret outer
    pg.draw.circle(
        turret_surf,
        (120, 120, 120),
        (int(5 * scale_factor), int(5 * scale_factor)),
        int(4 * scale_factor),
    )  # Inner ring
    pg.draw.circle(
        turret_surf,
        (100, 150, 255),
        (int(5 * scale_factor), int(6 * scale_factor)),
        int(1 * scale_factor),
    )  # Sight
    barrel_surf = pg.Surface((int(10 * scale_factor), int(2.5 * scale_factor)), pg.SRCALPHA)
    pg.draw.rect(barrel_surf, _team_color, (0, 0, int(10 * scale_factor), int(2.5 * scale_factor)))  # Barrel
    pg.draw.rect(
        barrel_surf,
        (90, 90, 90),
        (
            int(9 * scale_factor),
            int(1 * scale_factor),
            int(1 * scale_factor),
            int(0.5 * scale_factor),
        ),
    )  # Muzzle
    return body_surf, turret_surf, barrel_surf


def _draw_turret(
    obj,  # pyrefly: ignore [implicit-any-parameter]
    surface: pg.Surface,
    camera: Camera2d,
    mouse_pos: Point | None = None,
) -> None:
    """Custom draw for Turret: no body rotation (static building), turret and barrel rotate.

    :param obj: The Turret instance.
    :param surface: The Pygame surface to draw on.
    :param camera: The Camera2d instance for world-to-screen transformation.
    :param mouse_pos: Optional mouse position for hover effects.
    """
    # Custom draw for Turret: no body rotation (static building), turret and barrel rotate.
    if obj.health <= 0:
        return
    screen_pos = camera.world_to_screen(obj.position)
    zoom = camera.zoom
    body_scaled = pg.transform.smoothscale(obj.body_surf, (int(30 * zoom * 0.8), int(30 * zoom * 0.8)))
    body_rect = body_scaled.get_rect(center=screen_pos)
    surface.blit(body_scaled, body_rect.topleft)
    turret_scaled = pg.transform.smoothscale(obj.turret_surf, (int(10 * zoom * 0.8), int(10 * zoom * 0.8)))
    rotated_turret = pg.transform.rotate(turret_scaled, -math.degrees(obj.turret_angle))
    turret_rect = rotated_turret.get_rect()
    offset_rot = obj.turret_offset.rotate_rad(obj.body_angle) * zoom
    turret_center = Vector2(body_rect.center) + offset_rot
    turret_rect.center = turret_center
    surface.blit(rotated_turret, turret_rect.topleft)
    barrel_scaled = pg.transform.smoothscale(obj.barrel_surf, (int(10 * zoom * 0.8), int(2.5 * zoom * 0.8)))
    rotated_barrel = pg.transform.rotate(barrel_scaled, -math.degrees(obj.turret_angle))
    barrel_rect = rotated_barrel.get_rect()
    barrel_offset_rot = obj.barrel_offset.rotate_rad(obj.turret_angle) * zoom
    barrel_center = Vector2(turret_center) + barrel_offset_rot
    barrel_rect.center = barrel_center
    surface.blit(rotated_barrel, barrel_rect.topleft)
    if obj.selected:
        screen_rect = camera.get_screen_rect(obj.rect)
        pg.draw.rect(surface, (255, 255, 0), screen_rect, int(3 * zoom))

    obj.draw_health_bar_if_needed(surface=surface, camera=camera, mouse_pos=mouse_pos)
    for particle in obj.plasma_burn_particles:
        particle.draw_2d(surface, camera)


# Drawing recipe dictionary for simple rotated units
SIMPLE_DRAW_RECIPES = {
    "Infantry": _create_infantry_image,
    "Grenadier": _create_grenadier_image,
}

# Complex draw mappings
COMPLEX_DRAW_RECIPES = {
    "Tank": (_create_tank_surfaces, _draw_tank),
    "MachineGunVehicle": (_create_machinegunvehicle_surfaces, _draw_machinegunvehicle),
    "RocketArtillery": (_create_rocketartillery_surfaces, _draw_rocketartillery),
    "AttackHelicopter": (_create_attackhelicopter_surfaces, _draw_attackhelicopter),
    "Turret": (_create_turret_surfaces, _draw_turret),
}

# Static image recipes for buildings
BUILDING_DRAW_RECIPES = {
    "Headquarters": _create_headquarters_image,
    "Barracks": _create_barracks_image,
    "WarFactory": _create_warfactory_image,
    "Hangar": _create_hangar_image,
    "PowerPlant": _create_powerplant_image,
    "OilDerrick": _create_oilderrick_image,
    "Refinery": _create_refinery_image,
    "ShaleFracker": _create_shalefracker_image,
    "BlackMarket": _create_blackmarket_image,
}


def draw_mini_map(
    *,
    screen: pg.Surface,
    camera: Camera2d,
    fog_of_war: FogOfWar2d,
    map_width: int,
    map_height: int,
    map_color: pg.Color,
    buildings: Iterable[Unit2d],
    all_units: Iterable[Unit2d],
    player_allies: frozenset[Team],
) -> pg.Rect:
    """Renders scaled top-down map with terrain variation, entities, camera view outline.

    :param screen: Main screen.
    :param camera: Camera2d.
    :param fog_of_war: FogOfWar instance.
    :param map_width: Map width.
    :param map_height: Map height.
    :param map_color: Base map color tuple.
    :param buildings: Building group.
    :param all_units: Unit group.
    :param player_allies: Allied teams for visibility.
    :return: Minimap Rect.
    """
    # Renders scaled top-down map with terrain variation, entities, camera view outline.
    mini_map_rect = pg.Rect(
        SCREEN_WIDTH - MINI_MAP_WIDTH,
        SCREEN_HEIGHT - MINI_MAP_HEIGHT,
        MINI_MAP_WIDTH,
        MINI_MAP_HEIGHT,
    )
    mini_map = pg.Surface((MINI_MAP_WIDTH, MINI_MAP_HEIGHT))
    mini_map.fill((0, 0, 0))

    num_tx = map_width // TILE_SIZE
    num_ty = map_height // TILE_SIZE
    scale_x = MINI_MAP_WIDTH / map_width
    scale_y = MINI_MAP_HEIGHT / map_height
    tile_mw = TILE_SIZE * scale_x
    tile_mh = TILE_SIZE * scale_y

    for tx in range(num_tx):
        mx = tx * TILE_SIZE * scale_x
        tile_center_x = (tx + 0.5) * TILE_SIZE
        for ty in range(num_ty):
            tile_center_y = (ty + 0.5) * TILE_SIZE
            if not fog_of_war.is_explored((tile_center_x, tile_center_y)):
                continue
            my = ty * TILE_SIZE * scale_y
            var_r = ((tx * 17 + ty * 31) % 41) - 20
            var_g = ((tx * 23 + ty * 37) % 41) - 20
            var_b = ((tx * 29 + ty * 41) % 41) - 20
            tile_r = max(0, min(255, map_color.r + var_r))
            tile_g = max(0, min(255, map_color.g + var_g))
            tile_b = max(0, min(255, map_color.b + var_b))
            if not fog_of_war.is_visible((tile_center_x, tile_center_y)):
                avg = (tile_r + tile_g + tile_b) // 3
                tile_r = tile_g = tile_b = avg
            pg.draw.rect(mini_map, (tile_r, tile_g, tile_b), (mx, my, tile_mw, tile_mh))
            crater_seed = (tx * 123 + ty * 456) % 100
            if crater_seed < 5:
                cx = mx + tile_mw / 2
                cy = my + tile_mh / 2
                cr = tile_mw / 4
                dark_r = max(0, tile_r - 40)
                dark_g = max(0, tile_g - 40)
                dark_b = max(0, tile_b - 40)
                pg.draw.circle(mini_map, (dark_r, dark_g, dark_b), (int(cx), int(cy)), int(cr))

    for building in buildings:
        if (
            building.health > 0
            and (building.team in player_allies or building.is_seen)
            and fog_of_war.is_explored(building.position)
        ):
            color = team_to_color[building.team]
            x = int(building.position.x * scale_x)
            y = int(building.position.y * scale_y)
            pg.draw.rect(mini_map, color, (x - 2, y - 2, 5, 5))

    for unit in all_units:
        if unit.health > 0 and (unit.team in player_allies or fog_of_war.is_visible(unit.position)):
            color = team_to_color[unit.team]
            x = int(unit.position.x * scale_x)
            y = int(unit.position.y * scale_y)
            pg.draw.circle(mini_map, color, (x, y), 2)

    cam_rect = pg.Rect(
        camera.rect.x * scale_x,
        camera.rect.y * scale_y,
        camera.rect.width * scale_x,
        camera.rect.height * scale_y,
    )
    pg.draw.rect(mini_map, (255, 255, 255), cam_rect, 1)

    screen.blit(mini_map, (SCREEN_WIDTH - MINI_MAP_WIDTH, SCREEN_HEIGHT - MINI_MAP_HEIGHT))
    return mini_map_rect
