"""Implements TerrainFeature for isometric game."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

from modules.data_iso import TILE_SIZE

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.camera.camera_iso import CameraIso


class TerrainFeature:
    def __init__(self, position: Point, feature_type: str) -> None:
        self.position = Vector2(position)
        self.feature_type = feature_type
        self.rect = pg.Rect(position[0] - 20, position[1] - 20, 40, 40)
        if self.feature_type == "pebbles":
            self.num_pebbles = random.randint(2, 6)
            base_offsets = [(-6, -2), (-3, 0), (0, -4), (4, 1), (2, 5), (-1, 3), (5, -1)]
            self.selected_offsets = random.sample(base_offsets, min(self.num_pebbles, len(base_offsets)))
            self.pebbles = []
            for dx, dy in self.selected_offsets:
                pebble_size = random.uniform(4, 8)
                aspect_ratio = random.uniform(0.5, 1.5)
                pebble_width = pebble_size
                pebble_height = pebble_size * aspect_ratio
                outer_color = (
                    random.randint(140, 160),
                    random.randint(140, 160),
                    random.randint(140, 160),
                )
                inner_color = (
                    random.randint(100, 130),
                    random.randint(100, 130),
                    random.randint(100, 130),
                )
                self.pebbles.append(
                    {
                        "dx": dx,
                        "dy": dy,
                        "width": pebble_width,
                        "height": pebble_height,
                        "outer": outer_color,
                        "inner": inner_color,
                    }
                )

    def draw(self, *, surface: pg.Surface, camera: CameraIso) -> None:
        screen_pos = camera.world_to_iso(self.position, camera.zoom)
        zoom = camera.zoom
        if self.feature_type == "tree":
            trunk_width = int(8 * zoom)
            trunk_height = int(20 * zoom)
            trunk_rect = pg.Rect(screen_pos[0] - trunk_width // 2, screen_pos[1], trunk_width, trunk_height)
            pg.draw.rect(surface, (139, 69, 19), trunk_rect)
            foliage_radius = int(25 * zoom)
            pg.draw.circle(
                surface,
                (0, 128, 0),
                (int(screen_pos[0]), int(screen_pos[1] - 10 * zoom)),
                foliage_radius,
            )
            pg.draw.circle(
                surface,
                (34, 139, 34),
                (int(screen_pos[0] - 10 * zoom), int(screen_pos[1] - 5 * zoom)),
                int(15 * zoom),
            )
            pg.draw.circle(
                surface,
                (34, 139, 34),
                (int(screen_pos[0] + 10 * zoom), int(screen_pos[1] - 5 * zoom)),
                int(15 * zoom),
            )
        elif self.feature_type == "boulder":
            boulder_radius = int(25 * zoom)
            pg.draw.ellipse(
                surface,
                (105, 105, 105),
                (
                    screen_pos[0] - boulder_radius,
                    screen_pos[1] - boulder_radius // 2,
                    boulder_radius * 2,
                    boulder_radius,
                ),
            )
            pg.draw.ellipse(
                surface,
                (70, 70, 70),
                (
                    screen_pos[0] - boulder_radius // 2,
                    screen_pos[1] - boulder_radius // 2,
                    boulder_radius,
                    boulder_radius // 2,
                ),
            )
        elif self.feature_type == "rock":
            rock_width = int(15 * zoom)
            rock_height = int(10 * zoom)
            pg.draw.ellipse(
                surface,
                (128, 128, 128),
                (
                    screen_pos[0] - rock_width // 2,
                    screen_pos[1] - rock_height // 2,
                    rock_width,
                    rock_height,
                ),
            )
            pg.draw.ellipse(
                surface,
                (90, 90, 90),
                (
                    screen_pos[0] - rock_width // 4,
                    screen_pos[1] - rock_height // 4,
                    rock_width // 2,
                    rock_height // 2,
                ),
            )
        elif self.feature_type == "bush":
            bush_radius = int(18 * zoom)
            pg.draw.circle(surface, (0, 100, 0), (int(screen_pos[0]), int(screen_pos[1])), bush_radius)
            pg.draw.circle(
                surface,
                (34, 139, 34),
                (int(screen_pos[0] - 8 * zoom), int(screen_pos[1] - 5 * zoom)),
                int(12 * zoom),
            )
            pg.draw.circle(
                surface,
                (0, 120, 0),
                (int(screen_pos[0] + 6 * zoom), int(screen_pos[1] + 3 * zoom)),
                int(10 * zoom),
            )
            pg.draw.line(
                surface,
                (139, 69, 19),
                screen_pos,
                (screen_pos[0], screen_pos[1] + 5 * zoom),
                int(2 * zoom),
            )
        elif self.feature_type == "twigs":
            twig_length = int(12 * zoom)
            twig_width = int(2 * zoom)
            pg.draw.line(
                surface,
                (101, 67, 33),
                screen_pos,
                (screen_pos[0] + twig_length, screen_pos[1]),
                twig_width,
            )
            pg.draw.line(
                surface,
                (101, 67, 33),
                (screen_pos[0] + twig_length // 2, screen_pos[1]),
                (screen_pos[0] + twig_length // 2 - 5 * zoom, screen_pos[1] - 8 * zoom),
                twig_width,
            )
            pg.draw.line(
                surface,
                (101, 67, 33),
                (screen_pos[0] + twig_length // 2, screen_pos[1]),
                (screen_pos[0] + twig_length // 2 + 6 * zoom, screen_pos[1] + 4 * zoom),
                twig_width,
            )
            pg.draw.circle(
                surface,
                (0, 100, 0),
                (int(screen_pos[0] + 3 * zoom), int(screen_pos[1] - 2 * zoom)),
                int(3 * zoom),
            )
        elif self.feature_type == "pebbles":
            for pebble in self.pebbles:
                px = screen_pos[0] + pebble["dx"] * zoom
                py = screen_pos[1] + pebble["dy"] * zoom
                pebble_width = int(pebble["width"] * zoom)
                pebble_height = int(pebble["height"] * zoom)
                pg.draw.ellipse(
                    surface,
                    pebble["outer"],
                    (px - pebble_width // 2, py - pebble_height // 2, pebble_width, pebble_height),
                )
                inner_width = pebble_width // 2
                inner_height = pebble_height // 2
                pg.draw.ellipse(
                    surface,
                    pebble["inner"],
                    (px - inner_width // 2, py - inner_height // 2, inner_width, inner_height),
                )


def generate_terrain_features(*, map_name: str, map_width: int, map_height: int) -> list[TerrainFeature]:
    features = []
    num_tiles = (map_width // TILE_SIZE) * (map_height // TILE_SIZE)
    tree_density = 0.02 if map_name == "Forest" else 0.005
    boulder_density = 0.01
    rock_density = 0.03
    bush_density = 0.025 if "Forest" in map_name else 0.01
    twig_density = 0.015 if "Forest" in map_name or "Woodland" in map_name else 0.005
    pebble_density = 0.04 if "Desert" in map_name or "Riverbed" in map_name else 0.02
    num_trees = int(num_tiles * tree_density)
    num_boulders = int(num_tiles * boulder_density)
    num_rocks = int(num_tiles * rock_density)
    num_bushes = int(num_tiles * bush_density)
    num_twigs = int(num_tiles * twig_density)
    num_pebbles = int(num_tiles * pebble_density)

    def add_feature(*, ftype: str, count: int) -> None:
        for _ in range(count):
            attempts = 0
            while attempts < 10:
                x = random.randint(0, map_width)
                y = random.randint(0, map_height)
                new_rect = pg.Rect(x - 20, y - 20, 40, 40)
                if all(
                    not new_rect.colliderect(f.rect.inflate(10, 10) if f.feature_type == ftype else f.rect)
                    for f in features
                ):
                    features.append(TerrainFeature((x, y), ftype))
                    break
                attempts += 1

    add_feature(ftype="tree", count=num_trees)
    add_feature(ftype="boulder", count=num_boulders)
    add_feature(ftype="rock", count=num_rocks)
    add_feature(ftype="bush", count=num_bushes)
    add_feature(ftype="twigs", count=num_twigs)
    add_feature(ftype="pebbles", count=num_pebbles)
    return features
