"""Drawing functions for isometric game."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from modules.data_iso import MINI_MAP_HEIGHT, MINI_MAP_WIDTH, SCREEN_HEIGHT, SCREEN_WIDTH, TILE_SIZE
from modules.fonts import FONT_MEDIUM
from modules.geometry import absolute_world_to_iso, get_iso_bounds
from modules.team import team_to_color, team_to_name

if TYPE_CHECKING:
    from collections.abc import Iterable

    from modules.camera.camera_iso import CameraIso
    from modules.fog_of_war import FogOfWarIso
    from modules.game_data import GameDataIso
    from modules.team import Team
    from modules.units import UnitIso


def draw_mini_map(
    screen: pg.Surface,
    camera: CameraIso,
    fog_of_war: FogOfWarIso,
    map_width: int,
    map_height: int,
    map_color: pg.Color,
    buildings: Iterable[UnitIso],
    all_units: Iterable[UnitIso],
    player_allies: frozenset[Team],
) -> pg.Rect:
    mini_map_rect = pg.Rect(
        SCREEN_WIDTH - MINI_MAP_WIDTH,
        SCREEN_HEIGHT - MINI_MAP_HEIGHT,
        MINI_MAP_WIDTH,
        MINI_MAP_HEIGHT,
    )
    mini_map = pg.Surface((MINI_MAP_WIDTH, MINI_MAP_HEIGHT))
    mini_map.fill((0, 0, 0))
    min_x1, max_x1, min_y1, max_y1 = get_iso_bounds(map_w=map_width, map_h=map_height, zoom=1.0)
    span_x1 = max_x1 - min_x1
    span_y1 = max_y1 - min_y1
    mini_zoom = min(MINI_MAP_WIDTH / span_x1, MINI_MAP_HEIGHT / span_y1)
    center_offset_x = (MINI_MAP_WIDTH - span_x1 * mini_zoom) / 2
    center_offset_y = (MINI_MAP_HEIGHT - span_y1 * mini_zoom) / 1
    draw_offset_x = center_offset_x - min_x1 * mini_zoom
    draw_offset_y = center_offset_y - min_y1 * mini_zoom
    tile_size_world = TILE_SIZE
    num_tx = map_width // tile_size_world
    num_ty = map_height // tile_size_world
    for tx in range(num_tx):
        for ty in range(num_ty):
            tile_center_x = (tx + 0.5) * tile_size_world
            tile_center_y = (ty + 0.5) * tile_size_world
            if not fog_of_war.is_explored((tile_center_x, tile_center_y)):
                continue

            c1 = (tx * tile_size_world, ty * tile_size_world)
            c2 = (c1[0] + tile_size_world, c1[1])
            c3 = (c2[0], c2[1] + tile_size_world)
            c4 = (c1[0], c3[1])
            iso_c1 = absolute_world_to_iso(world_pos=c1, zoom=mini_zoom)
            iso_c2 = absolute_world_to_iso(world_pos=c2, zoom=mini_zoom)
            iso_c3 = absolute_world_to_iso(world_pos=c3, zoom=mini_zoom)
            iso_c4 = absolute_world_to_iso(world_pos=c4, zoom=mini_zoom)
            draw_points = [
                (iso_c1[0] + draw_offset_x, iso_c1[1] + draw_offset_y),
                (iso_c2[0] + draw_offset_x, iso_c2[1] + draw_offset_y),
                (iso_c3[0] + draw_offset_x, iso_c3[1] + draw_offset_y),
                (iso_c4[0] + draw_offset_x, iso_c4[1] + draw_offset_y),
            ]
            tile_r = map_color.r
            tile_g = map_color.g
            tile_b = map_color.b
            if not fog_of_war.is_visible((tile_center_x, tile_center_y)):
                avg = (map_color.r + map_color.g + map_color.b) // 3
                tile_r = tile_g = tile_b = avg

            pg.draw.polygon(mini_map, (tile_r, tile_g, tile_b), draw_points)

    for building in buildings:
        if (
            building.health > 0
            and (building.team in player_allies or building.is_seen)
            and fog_of_war.is_explored(building.position)
        ):
            iso_pos = absolute_world_to_iso(world_pos=building.position, zoom=mini_zoom)
            draw_pos = (iso_pos[0] + draw_offset_x, iso_pos[1] + draw_offset_y)
            size = 3
            color = team_to_color[building.team]
            pg.draw.rect(mini_map, color, (draw_pos[0] - size, draw_pos[1] - size, size * 2, size * 2))

    for unit in all_units:
        if unit.health > 0 and (unit.team in player_allies or fog_of_war.is_visible(unit.position)):
            iso_pos = absolute_world_to_iso(world_pos=unit.position, zoom=mini_zoom)
            draw_pos = (iso_pos[0] + draw_offset_x, iso_pos[1] + draw_offset_y)
            color = team_to_color[unit.team]
            pg.draw.circle(mini_map, color, (int(draw_pos[0]), int(draw_pos[1])), 1)

    cam_world_tl = (camera.rect.x, camera.rect.y)
    cam_world_br = (camera.rect.right, camera.rect.bottom)
    cam_corners = [
        cam_world_tl,
        (cam_world_br[0], cam_world_tl[1]),
        cam_world_br,
        (cam_world_tl[0], cam_world_br[1]),
    ]
    iso_cams = [absolute_world_to_iso(world_pos=c, zoom=mini_zoom) for c in cam_corners]
    cam_draw_points = [(ix + draw_offset_x, iy + draw_offset_y) for ix, iy in iso_cams]
    pg.draw.polygon(mini_map, (255, 255, 255), cam_draw_points, 1)
    screen.blit(mini_map, (SCREEN_WIDTH - MINI_MAP_WIDTH, SCREEN_HEIGHT - MINI_MAP_HEIGHT))
    return mini_map_rect


def draw_fitness_panel(screen: pg.Surface, g: GameDataIso) -> None:
    panel_x = 10
    panel_y = 10
    panel_width = 180
    panel_height = 250
    panel_rect = pg.Rect(panel_x, panel_y, panel_width, panel_height)
    panel_surf = pg.Surface((panel_width, panel_height), pg.SRCALPHA)
    panel_surf.fill((40, 40, 40, 128))
    screen.blit(panel_surf, panel_rect.topleft)
    pg.draw.rect(screen, (100, 100, 100), panel_rect, 2)
    y_offset = panel_y + 10
    title_surf = FONT_MEDIUM.render("Fitness", True, (255, 255, 255))
    screen.blit(title_surf, (panel_x + 10, y_offset))
    y_offset += 30
    for team in g.teams:
        hq = g.hqs[team]
        if hq.health <= 0:
            continue

        name = team_to_name[team]
        fitness = g.current_fitness.get(team, 0)
        delta = g.fitness_deltas.get(team, 0)
        name_surf = FONT_MEDIUM.render(f"{name}:", True, team_to_color[team])
        screen.blit(name_surf, (panel_x + 10, y_offset))
        value_surf = FONT_MEDIUM.render(str(fitness), True, (255, 255, 255))
        screen.blit(value_surf, (panel_x + 120, y_offset))
        if delta != 0:
            delta_text = f"{'+' if delta > 0 else ''}{delta}"
            delta_color = (0, 255, 0) if delta > 0 else (255, 0, 0)
            delta_surf = FONT_MEDIUM.render(delta_text, True, delta_color)
            screen.blit(delta_surf, (panel_x + 140, y_offset))

        y_offset += 25
