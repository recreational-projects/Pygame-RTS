"""Implements GameManager for isometric game."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

import pygame as pg
from pygame.math import Vector2

from modules.ai import AiIso
from modules.camera.camera_iso import CameraIso
from modules.data import Palette
from modules.data_iso import (
    CONSOLE_HEIGHT,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAPS,
    MINI_MAP_HEIGHT,
    MINI_MAP_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    STARTING_POSITIONS_EDGE_OFFSET,
    TILE_SIZE,
)
from modules.draw_iso import draw_fitness_panel, draw_mini_map
from modules.fog_of_war import FogOfWarIso
from modules.game_data import GameDataIso
from modules.game_state import GameState
from modules.geometry import calculate_formation_positions_iso, get_starting_positions, snap_to_grid
from modules.production_interface import ProductionInterfaceIso
from modules.screens import VictoryScreen
from modules.spatial_hash import SpatialHashIso
from modules.team import Team, team_to_name
from modules.terrain_feature_iso import generate_terrain_features
from modules.unit_stats.unit_stats_iso import get_unit_cost, get_unit_size
from modules.units.units_iso import Headquarters, Infantry
from modules.world import handle_unit_building_collisions, handle_unit_collisions
from modules.world_iso import (
    find_free_spawn_position,
    is_valid_building_position,
)

from .game_manager_generic import _GameManagerGeneric

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from pygame.typing import IntPoint, Point

    from modules.units import UnitIso


def _handle_minimap_click(*, game_data: GameDataIso, mouse_pos: IntPoint, mini_x: int, mini_y: int) -> None:
    local_x = mouse_pos[0] - mini_x
    local_y = mouse_pos[1] - mini_y
    g = game_data
    scale_x = g.map_width / MINI_MAP_WIDTH
    scale_y = g.map_height / MINI_MAP_HEIGHT
    world_x = local_x * scale_x
    world_y = local_y * scale_y
    g.camera.rect.centerx = world_x
    g.camera.rect.centery = world_y
    g.camera.clamp()
    if not g.spectator_mode:
        if g.player_hq is None:
            raise ValueError("`player_hq` cannot be `None`")  # TODO: typeguard

        for unit in g.player_units:
            unit.selected = False

        g.selected_units.empty()
        if g.selected_building:
            g.selected_building.selected = False

        g.selected_building = None
        g.selecting = False
        if g.interface:
            g.interface.update_producer(g.player_hq)


def _handle_mouse_1_click_non_spectator_mode(*, game_data: GameDataIso, mouse_pos: IntPoint, world_pos: Point) -> None:
    if game_data is None:
        raise ValueError("`game_data` cannot be `None`")  # TODO: typeguard

    g = game_data
    if g.interface is None or g.player_hq is None or g.player_team is None:
        raise ValueError("Unexpected condition")

    result = g.interface.handle_click(mouse_pos)
    if result:
        if isinstance(result, tuple) and result[0] == "sell":
            building_to_sell = result[1]
            if building_to_sell in g.global_buildings:
                g.global_buildings.remove(building_to_sell)
                g.player_hq.credits += building_to_sell.cost // 2
                if g.selected_building == building_to_sell:
                    g.selected_building = None
                    g.interface.update_producer(g.player_hq)

        return

    if g.interface.placing_cls is not None and not g.interface_rect.collidepoint(mouse_pos):
        snapped = snap_to_grid(pos=world_pos, grid_size=TILE_SIZE)
        buildings_list = list(g.global_buildings)
        unit_type_str = g.interface.placing_cls.__name__
        cost = get_unit_cost(unit_type_str)

        if g.player_hq.credits >= cost and is_valid_building_position(
            position=snapped,
            team=g.player_team,
            new_building_cls=g.interface.placing_cls,
            buildings=buildings_list,
            map_width=g.map_width,
            map_height=g.map_height,
        ):
            building = g.interface.placing_cls(snapped, g.player_team, hq=g.player_hq)
            building.map_width = g.map_width
            building.map_height = g.map_height
            g.global_buildings.add(building)
            g.player_hq.credits -= cost
            g.interface.placing_cls = None
        else:
            g.interface.placing_cls = None

        return

    clicked_building = next(
        (
            b
            for b in g.global_buildings
            if b.team == g.player_team
            # pyrefly: ignore [bad-argument-type]
            and g.camera.get_screen_rect(b.rect).collidepoint(mouse_pos)
        ),
        None,
    )
    if clicked_building:
        if g.selected_building and g.selected_building != clicked_building:
            g.selected_building.selected = False

        clicked_building.selected = True
        g.selected_building = clicked_building
        for unit in g.player_units:
            unit.selected = False

        g.selected_units.empty()
        g.interface.update_producer(clicked_building)

    else:
        if g.selected_building:
            g.selected_building.selected = False

        g.selected_building = None
        g.interface.update_producer(g.player_hq)
        g.selecting = True
        g.select_start = mouse_pos
        g.select_rect = pg.Rect(mouse_pos, (0, 0))


def _handle_mouse_2_click_non_spectator_mode(*, game_data: GameDataIso, mouse_pos: IntPoint, world_pos: Point) -> None:
    if game_data is None:
        raise ValueError("`game_data` cannot be `None`")

    g = game_data
    if g.interface is None:
        raise ValueError("`interface` cannot be `None`")

    if g.interface.placing_cls is not None:
        g.interface.placing_cls = None

    elif g.selected_building and hasattr(g.selected_building, "rally_point"):
        g.selected_building.rally_point = Vector2(world_pos)

    elif g.selected_units:
        clicked_enemy = None
        unit_list = list(g.global_units)
        building_list = [b for b in g.global_buildings if b.health > 0]
        for u in unit_list:
            # pyrefly: ignore [bad-argument-type]
            screen_rect = g.camera.get_screen_rect(u.rect)
            if screen_rect.collidepoint(mouse_pos) and u.team not in g.player_allies and u.health > 0:
                clicked_enemy = u
                break

        if not clicked_enemy:
            for b in building_list:
                # pyrefly: ignore [bad-argument-type]
                screen_rect = g.camera.get_screen_rect(b.rect)
                if screen_rect.collidepoint(mouse_pos) and b.team not in g.player_allies and b.health > 0:
                    clicked_enemy = b
                    break

        if clicked_enemy:
            for unit in g.selected_units:
                unit.attack_target = clicked_enemy
                if clicked_enemy.is_building:
                    chase_pos = unit.get_chase_position_for_building(clicked_enemy)
                    unit.move_target = chase_pos if chase_pos is not None else None
                    unit.path = []
                else:
                    unit.move_target = clicked_enemy.position
                    unit.path = []

        else:
            formation_positions = calculate_formation_positions_iso(
                center=world_pos, target=world_pos, num_units=len(g.selected_units)
            )
            for unit, pos in zip(g.selected_units, formation_positions):
                unit.move_target = pos
                unit.path = []
                unit.attack_target = None
                unit.formation_target = pos


def _handle_mouse_1_release_while_selecting(*, game_data: GameDataIso, mouse_pos: IntPoint) -> None:
    if game_data is None:
        raise ValueError("`game_data` cannot be `None`")

    g = game_data
    if g.interface is None or g.player_hq is None:
        raise ValueError("Unexpected condition")

    g.selecting = False
    for unit in g.player_units:
        unit.selected = False

    g.selected_units.empty()
    if g.selected_building:
        g.selected_building.selected = False

    g.selected_building = None

    g.interface.update_producer(g.player_hq)
    if g.select_start:
        world_start = g.camera.screen_to_world(g.select_start)
        world_end = g.camera.screen_to_world(mouse_pos)
        world_rect = pg.Rect(
            min(world_start[0], world_end[0]),
            min(world_start[1], world_end[1]),
            abs(world_end[0] - world_start[0]),
            abs(world_end[1] - world_start[1]),
        )
        for unit in g.player_units:
            # pyrefly: ignore [bad-argument-type]
            if world_rect.colliderect(unit.rect):
                unit.selected = True
                g.selected_units.add(unit)


@dataclass(kw_only=True)
class GameManagerIso(_GameManagerGeneric):
    """GameManager for isometric game."""

    game_data: GameDataIso = field(init=False)

    @override
    def _run_game(self) -> None:
        if self.game_data is None:
            raise ValueError("`self.game_data` cannot be `None`")

        g = self.game_data
        while self.running and self.state == GameState.PLAYING:
            self._handle_events()
            g.camera.update(
                selected_units=g.selected_units.sprites() if not g.spectator_mode else [],
                mouse_pos=pg.mouse.get_pos(),
                interface_rect=g.interface_rect,
                keys=pg.key.get_pressed(),
            )
            unit_list = list(g.global_units)
            building_list = [b for b in g.global_buildings if b.health > 0]
            for unit in [u for u in unit_list if not u.is_building]:
                unit.update(particles=g.particles, global_buildings=list(g.global_buildings), projectiles=g.projectiles)

            for building in building_list:
                building_team = building.team
                friendly_units_for_build = g.unit_groups.get(building_team, pg.sprite.Group())
                building.update(
                    particles=g.particles,
                    friendly_units=friendly_units_for_build,
                    all_units=g.global_units,
                    global_buildings=g.global_buildings,
                    projectiles=g.projectiles,
                )

            g.projectiles.update()
            g.particles.update()
            unit_hash = SpatialHashIso(250)
            for u in unit_list:
                unit_hash.add(u)

            building_hash = SpatialHashIso(250)
            for b in building_list:
                building_hash.add(b)

            handle_unit_collisions(all_units=unit_list, unit_hash=unit_hash)
            handle_unit_building_collisions(all_units=unit_list, building_hash=building_hash)
            for unit in unit_list:
                # pyrefly: ignore [missing-attribute]
                unit.rect.center = unit.position

            for team in g.teams:
                g.handle_attacks(
                    team=team,
                    unit_hash=unit_hash,
                    building_hash=building_hash,
                    allied_teams=g.alliances[team],
                )

            g.handle_projectiles()
            g.cleanup_dead_entities()
            g.tile_timer += 1
            if g.tile_timer >= 60:
                g.tile_timer = 0
                alive_hqs_pos = {team: hq.position for team, hq in g.hqs.items() if hq.health > 0}
                if alive_hqs_pos:
                    for tx in range(g.num_tx):
                        tile_x = tx * TILE_SIZE + TILE_SIZE / 2
                        for ty in range(g.num_ty):
                            tile_y = ty * TILE_SIZE + TILE_SIZE / 2
                            min_dist = float("inf")
                            nearest_team = None
                            for team, pos in alive_hqs_pos.items():
                                dist = math.hypot(tile_x - pos.x, tile_y - pos.y)
                                if dist < min_dist:
                                    min_dist = dist
                                    nearest_team = team

                            g.tile_ownership[tx][ty] = nearest_team

                    for team, hq in g.hqs.items():
                        if hq.health > 0:
                            count = sum(
                                1
                                for tx in range(g.num_tx)
                                for ty in range(g.num_ty)
                                if g.tile_ownership[tx][ty] == team
                            )
                            income = count * 0.050
                            hq.credits += income
                            if "credits_earned" in hq.game_stats:
                                hq.game_stats["credits_earned"] += income

            for ai in g.ais:
                their_team = ai.hq.team
                friendly_units_list = g.unit_groups[their_team].sprites()
                friendly_buildings_list = [b for b in building_list if b.team == their_team]
                enemy_units_list = [
                    u
                    for team, ug in g.unit_groups.items()
                    if team not in ai.allies
                    for u in ug.sprites()
                    if u.health > 0
                ]
                enemy_buildings_list = [b for b in building_list if b.team not in ai.allies]
                ai.update(
                    friendly_units=friendly_units_list,
                    friendly_buildings=friendly_buildings_list,
                    enemy_units=enemy_units_list,
                    enemy_buildings=enemy_buildings_list,
                    all_buildings=g.global_buildings,
                    map_width=g.map_width,
                    map_height=g.map_height,
                )

            g.current_fitness = {}
            g.fitness_deltas = {}
            for team in g.teams:
                hq = g.hqs[team]
                if hq.health > 0:
                    game_stats = hq.game_stats
                    fitness = (
                        game_stats.get("units_destroyed", 0) * 10
                        + game_stats.get("buildings_destroyed", 0) * 20
                        - game_stats.get("units_lost", 0) * 5
                        - game_stats.get("buildings_lost", 0) * 10
                        + game_stats.get("credits_earned", 0) // 50
                    )
                    g.current_fitness[team] = fitness
                    prev = g.previous_fitness.get(team, 0)
                    delta = fitness - prev
                    g.fitness_deltas[team] = delta
                    g.previous_fitness[team] = fitness

            if not g.spectator_mode:
                ally_units = [u for team in g.player_allies for u in g.unit_groups[team].sprites()]
                ally_buildings = [b for b in g.global_buildings.sprites() if b.team in g.player_allies]
                g.fog_of_war.update_visibility(ally_units, ally_buildings, g.global_buildings.sprites())
            else:
                g.fog_of_war.update_visibility([], [], g.global_buildings.sprites())

            alive_hqs = [hq for hq in g.hqs.values() if hq.health > 0]
            all_stats = {team_to_name[team]: hq.game_stats for team, hq in g.hqs.items()}
            if g.player_hq and g.player_hq.health <= 0:
                self.state = GameState.DEFEAT
                self.victory_screen = VictoryScreen(
                    is_victory=False,
                    all_stats=all_stats,
                    player_team=g.player_team,
                    screen_size=self.screen.size,
                )

            elif len(alive_hqs) <= 1:
                if len(alive_hqs) == 0:
                    is_player_victory = None if g.spectator_mode else False
                    self.state = GameState.VICTORY if g.spectator_mode else GameState.DEFEAT
                else:
                    last_hq = alive_hqs[0]
                    if g.spectator_mode:
                        is_player_victory = None
                    else:
                        is_player_victory = last_hq == g.player_hq
                    self.state = GameState.VICTORY if is_player_victory else GameState.DEFEAT

                self.victory_screen = VictoryScreen(
                    is_victory=is_player_victory,
                    all_stats=all_stats,
                    player_team=g.player_team,
                    screen_size=self.screen.size,
                )

            self.screen.fill(pg.Color("black"))
            _map_color = g.map_color
            zoom = g.camera.zoom
            min_wx, max_wx, min_wy, max_wy = g.camera.get_render_bounds()
            num_tx = g.map_width // TILE_SIZE
            num_ty = g.map_height // TILE_SIZE
            start_tx = max(0, int(min_wx // TILE_SIZE))
            start_ty = max(0, int(min_wy // TILE_SIZE))
            end_tx = min(num_tx, int(max_wx // TILE_SIZE) + 2)
            end_ty = min(num_ty, int(max_wy // TILE_SIZE) + 2)
            for tx in range(start_tx, end_tx):
                wx = tx * TILE_SIZE
                for ty in range(start_ty, end_ty):
                    wy = ty * TILE_SIZE
                    tile_r = _map_color.r
                    tile_g = _map_color.g
                    tile_b = _map_color.b
                    c1 = (wx, wy)
                    c2 = (wx + TILE_SIZE, wy)
                    c3 = (wx + TILE_SIZE, wy + TILE_SIZE)
                    c4 = (wx, wy + TILE_SIZE)
                    iso1 = g.camera.world_to_iso(c1, zoom)
                    iso2 = g.camera.world_to_iso(c2, zoom)
                    iso3 = g.camera.world_to_iso(c3, zoom)
                    iso4 = g.camera.world_to_iso(c4, zoom)
                    pg.draw.polygon(self.screen, (tile_r, tile_g, tile_b), [iso1, iso2, iso3, iso4])

            for feature in g.terrain_features:
                if g.fog_of_war.is_visible(feature.position):
                    feature.draw(surface=self.screen, camera=g.camera)

            draw_allies = set(g.teams) if g.spectator_mode else g.player_allies
            fog = g.fog_of_war
            if not g.spectator_mode:
                g.fog_of_war.draw(self.screen, g.camera)

            mouse_pos = pg.mouse.get_pos() if g.interface else None
            for building in building_list:
                visible = building.team in draw_allies or fog.is_visible(building.position) or building.is_seen
                if building.health > 0 and visible:
                    building.draw(surface=self.screen, camera=g.camera, mouse_pos=mouse_pos)

            if g.interface and not g.spectator_mode:
                if g.interface.placing_cls is not None:
                    mouse_pos = pg.mouse.get_pos()
                    ghost_pos = g.camera.screen_to_world(mouse_pos)
                    snapped = snap_to_grid(pos=ghost_pos, grid_size=TILE_SIZE)
                    buildings_list = list(g.global_buildings)
                    unit_type = g.interface.placing_cls.__name__
                    valid = is_valid_building_position(
                        position=snapped,
                        team=g.player_team,
                        new_building_cls=g.interface.placing_cls,
                        buildings=buildings_list,
                        map_width=g.map_width,
                        map_height=g.map_height,
                    )
                    width, height = get_unit_size(unit_type)
                    half_w, half_h = width / 2, height / 2
                    temp_rect = pg.Rect(snapped[0] - half_w, snapped[1] - half_h, width, height)
                    screen_ghost = g.camera.get_screen_rect(temp_rect)
                    color = Palette.PLACEMENT_VALID_COLOR if valid else Palette.PLACEMENT_INVALID_COLOR
                    line_width = int(2 * g.camera.zoom)
                    pg.draw.rect(self.screen, color, screen_ghost, line_width)

                for unit in [u for u in unit_list if not u.is_building]:
                    visible = unit.team in draw_allies or fog.is_visible(unit.position)
                    if unit.health > 0 and visible:
                        unit.draw(surface=self.screen, camera=g.camera, mouse_pos=mouse_pos)

            else:
                for unit in [u for u in unit_list if not u.is_building]:
                    if unit.health > 0:
                        unit.draw(surface=self.screen, camera=g.camera)

            for projectile in g.projectiles:
                projectile.draw(self.screen, g.camera)
            for particle in g.particles:
                particle.draw_iso(self.screen, g.camera)

            if g.interface and not g.spectator_mode:
                g.interface.draw(self.screen)

            if not g.spectator_mode and g.selecting and g.select_rect:
                pg.draw.rect(self.screen, (255, 255, 255), g.select_rect, 2)

            draw_allies_mini = frozenset(g.teams) if g.spectator_mode else g.player_allies
            draw_mini_map(
                self.screen,
                g.camera,
                g.fog_of_war,
                g.map_width,
                g.map_height,
                g.map_color,
                g.global_buildings,
                g.global_units,
                draw_allies_mini,
            )
            draw_fitness_panel(self.screen, g)
            pg.display.flip()
            self.clock.tick(60)

    def _handle_events(self) -> None:
        g = self.game_data
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False

            elif event.type == pg.MOUSEWHEEL:
                mouse_pos = pg.mouse.get_pos()
                game_rect = pg.Rect(0, 0, g.camera.width, g.camera.height)
                if game_rect.collidepoint(mouse_pos):
                    g.camera.update_zoom(event.y, mouse_pos)

            elif event.type == pg.MOUSEBUTTONDOWN:
                mini_x = SCREEN_WIDTH - MINI_MAP_WIDTH
                mini_y = SCREEN_HEIGHT - MINI_MAP_HEIGHT
                mini_rect = pg.Rect(mini_x, mini_y, MINI_MAP_WIDTH, MINI_MAP_HEIGHT)
                in_minimap = mini_rect.collidepoint(event.pos)
                if in_minimap and event.button == 1:
                    _handle_minimap_click(game_data=g, mouse_pos=event.pos, mini_x=mini_x, mini_y=mini_y)
                    continue

                if g.spectator_mode:
                    continue

                world_pos = g.camera.screen_to_world(event.pos)
                world_pos = (
                    max(0, min(world_pos[0], g.map_width)),
                    max(0, min(world_pos[1], g.map_height)),
                )
                if event.button == 1:
                    _handle_mouse_1_click_non_spectator_mode(game_data=g, mouse_pos=event.pos, world_pos=world_pos)

                elif event.button == 3:
                    _handle_mouse_2_click_non_spectator_mode(game_data=g, mouse_pos=event.pos, world_pos=world_pos)

            elif event.type == pg.MOUSEMOTION and g.selecting:
                if g.select_start:
                    g.select_rect = pg.Rect(
                        min(g.select_start[0], event.pos[0]),
                        min(g.select_start[1], event.pos[1]),
                        abs(event.pos[0] - g.select_start[0]),
                        abs(event.pos[1] - g.select_start[1]),
                    )
            elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and g.selecting:
                _handle_mouse_1_release_while_selecting(game_data=g, mouse_pos=event.pos)

            elif event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                if g.interface and g.interface.placing_cls is not None:
                    g.interface.placing_cls = None
                else:
                    self.state = GameState.MENU
                    return

    @override
    def _initialize_game(self, *, game_mode: str, size_name: str, map_name: str, spectator_mode: bool = False) -> None:
        map_data = MAPS[map_name]
        base_width = map_data["width"]
        base_height = map_data["height"]
        color = pg.Color(map_data["color"])

        size_scales = {"tiny": 0.80, "small": 0.80, "medium": 0.80, "large": 0.80, "huge": 0.80}
        scale = size_scales[size_name]
        map_width = int(base_width * scale)
        map_height = int(base_height * scale)

        num_tx = map_width // TILE_SIZE
        num_ty = map_height // TILE_SIZE
        ownership = [[None] * num_ty for _ in range(num_tx)]

        ai_units: pg.sprite.Group[UnitIso] = pg.sprite.Group()
        global_units = pg.sprite.Group()
        global_buildings = pg.sprite.Group()
        projectiles = pg.sprite.Group()
        particles = pg.sprite.Group()
        selected_units = pg.sprite.Group()

        unit_groups: MutableMapping[Team, pg.sprite.Group[UnitIso]] = {}
        hqs = {}
        player_side: list[Team] = []
        enemy_side: list[Team] = []

        if game_mode == "1v1":
            player_side = [Team.RED]
            enemy_side = [Team.GREEN]
        elif game_mode == "2v2":
            player_side = [Team.RED, Team.BLUE]
            enemy_side = [Team.ORANGE, Team.YELLOW]
        elif game_mode == "3v3":
            player_side = [Team.RED, Team.BLUE, Team.CYAN]
            enemy_side = [Team.MAGENTA, Team.ORANGE, Team.YELLOW]
        elif game_mode == "4v4":
            player_side = [Team.RED, Team.BLUE, Team.GREEN, Team.CYAN]
            enemy_side = [Team.MAGENTA, Team.ORANGE, Team.YELLOW, Team.GREY]
        elif game_mode == "4ffa":
            player_side = [Team.RED]
            enemy_side = [Team.BLUE, Team.GREEN, Team.CYAN]

        teams = player_side + enemy_side
        positions = get_starting_positions(
            map_width=map_width,
            map_height=map_height,
            num_players=len(teams),
            edge_dist=STARTING_POSITIONS_EDGE_OFFSET,
        )
        for i, team in enumerate(teams):
            pos = positions[i]
            hq = Headquarters(position=pos, team=team)
            hq.map_width = map_width
            hq.map_height = map_height
            hq.game_stats = {
                "units_created": 3,
                "units_lost": 0,
                "units_destroyed": 0,
                "buildings_constructed": 1,
                "buildings_lost": 0,
                "buildings_destroyed": 0,
                "credits_earned": 0,
            }
            hq.rally_point = Vector2(pos[0] + (100 if pos[0] < map_width / 2 else -100), pos[1])
            hqs[team] = hq
            units: pg.sprite.Group[UnitIso] = pg.sprite.Group()
            for _ in range(3):
                offset = find_free_spawn_position(
                    target_pos=pos,
                    global_buildings=global_buildings.sprites(),
                    global_units=global_units.sprites(),
                    map_width=map_width,
                    map_height=map_height,
                )
                unit = Infantry(position=offset, team=team, hq=hq)
                unit.map_width = map_width
                unit.map_height = map_height
                units.add(unit)

            unit_groups[team] = units

        if not spectator_mode:
            player_units = unit_groups[Team.RED]
            for team in teams:
                if team != Team.RED:
                    ai_units.add(unit_groups[team])

        else:
            player_units = pg.sprite.Group()
            for team in teams:
                ai_units.add(unit_groups[team])

        for ug in unit_groups.values():
            global_units.add(ug)

        for hq in hqs.values():
            global_buildings.add(hq)

        alliances = {}
        player_side_set = set(player_side)
        for team in teams:
            if team in player_side_set:
                alliances[team] = frozenset(player_side)
            else:
                alliances[team] = frozenset(enemy_side)

        if not spectator_mode:
            player_hq = hqs[Team.RED]
            player_team = Team.RED
            player_allies = alliances[player_team]
        else:
            player_hq = None
            player_team = None
            player_allies = frozenset()

        ais = []
        for team in teams:
            if not spectator_mode and team == Team.RED:
                continue

            i = teams.index(team)
            pos = positions[i]
            center_x = map_width / 2
            center_y = map_height / 2
            build_dir = math.atan2(center_y - pos[1], center_x - pos[0])
            random.seed(team.value * 12345)
            ai = AiIso(hq=hqs[team], preferred_build_direction=build_dir, allies=alliances[team])
            ais.append(ai)

        camera = CameraIso(map_width=MAP_WIDTH, map_height=MAP_HEIGHT, width=SCREEN_WIDTH, height=SCREEN_HEIGHT)
        if spectator_mode:
            camera.rect.center = (map_width / 2, map_height / 2)

        if not spectator_mode:
            if player_hq is None:
                raise ValueError("Player HQ is None")

            interface = ProductionInterfaceIso(hq=player_hq)
            interface_rect = pg.Rect(SCREEN_WIDTH - 200, 0, 200, SCREEN_HEIGHT - CONSOLE_HEIGHT)
        else:
            interface = None
            interface_rect = pg.Rect(0, 0, 0, 0)

        self.game_data = GameDataIso(
            player_units=player_units,
            ai_units=ai_units,
            global_units=global_units,
            global_buildings=global_buildings,
            projectiles=projectiles,
            particles=particles,
            selected_units=selected_units,
            unit_groups=unit_groups,
            hqs=hqs,
            player_hq=player_hq,
            player_team=player_team,
            player_allies=player_allies,
            alliances=alliances,
            interface=interface,
            interface_rect=interface_rect,
            fog_of_war=FogOfWarIso(
                map_width=map_width, map_height=map_height, tile_size=TILE_SIZE, spectator_mode=spectator_mode
            ),
            camera=camera,
            map_color=color,
            map_width=map_width,
            map_height=map_height,
            game_mode=game_mode,
            ais=ais,
            spectator_mode=spectator_mode,
            teams=teams,
            terrain_features=generate_terrain_features(map_name=map_name, map_width=map_width, map_height=map_height),
            previous_fitness=dict.fromkeys(teams, 0),
            current_fitness={},
            fitness_deltas={},
            tile_ownership=ownership,
            tile_timer=0,
            num_tx=num_tx,
            num_ty=num_ty,
        )
