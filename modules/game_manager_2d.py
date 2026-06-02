from __future__ import annotations

import math
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

from modules.ai_2d import AI
from modules.camera.camera_2d import Camera2d
from modules.data import Palette
from modules.data_2d import (
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
from modules.draw_2d import draw_mini_map
from modules.fog_of_war import FogOfWar2d
from modules.game_data_2d import GameData
from modules.game_state import GameState
from modules.geometry import calculate_formation_positions_2d, get_starting_positions, snap_to_grid
from modules.production_interface_2d import ProductionInterface
from modules.screens import MainMenu, SkirmishSetup, VictoryScreen
from modules.spatial_hash import SpatialHash2d
from modules.team import Team, team_to_name
from modules.unit_stats.unit_stats_2d import get_unit_cost, get_unit_size
from modules.units_2d import Headquarters, Infantry
from modules.world import handle_unit_building_collisions, handle_unit_collisions
from modules.world_2d import (
    cleanup_dead_entities,
    find_free_spawn_position,
    handle_attacks,
    handle_projectiles,
    is_valid_building_position,
)

if TYPE_CHECKING:
    from pygame.typing import IntPoint, Point

    from modules.units_2d import Unit2d


@dataclass(kw_only=True)
class GameManager:
    """
    GameManager orchestrates state machine, initializes game data, runs loops.

    Handles menu, setup, playing, victory/defeat states.
    """

    screen: pg.Surface = field(init=False)
    clock: pg.time.Clock = field(init=False)
    state: GameState = field(init=False)
    main_menu: MainMenu = field(init=False)
    skirmish_setup: SkirmishSetup = field(init=False)
    victory_screen: VictoryScreen | None = field(init=False)
    game_data: GameData = field(init=False)
    running: bool = False

    def __post_init__(self) -> None:
        pg.init()
        self.screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pg.time.Clock()
        self.state = GameState.MENU

        screen_size_ = self.screen.size
        self.main_menu = MainMenu(screen_size_)
        self.skirmish_setup = SkirmishSetup(screen_size_)
        self.victory_screen = None
        self.running = True

    def run(self) -> None:
        """
        State machine loop: menu -> setup -> playing -> victory/defeat -> menu.
        """
        # State machine loop: menu -> setup -> playing -> victory/defeat -> menu.
        while self.running:
            if self.state == GameState.MENU:
                self.main_menu.update(pg.mouse.get_pos())
                self.main_menu.draw(self.screen)

                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False
                    result = self.main_menu.handle_event(event)
                    if result == "skirmish_setup":
                        self.state = GameState.SKIRMISH_SETUP
                    elif result == "quit":
                        self.running = False

                pg.display.flip()
                self.clock.tick(60)

            elif self.state == GameState.SKIRMISH_SETUP:
                self.skirmish_setup.update(pg.mouse.get_pos())
                self.skirmish_setup.draw(self.screen)

                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False
                    result = self.skirmish_setup.handle_event(event)
                    if result == "menu":
                        self.state = GameState.MENU
                        self.skirmish_setup = SkirmishSetup(
                            screen_size=self.screen.size,
                        )
                    elif result and result[0] == "start_game":
                        _, game_mode, size_choice, map_choice, spectate = result
                        self._initialize_game(
                            game_mode=game_mode, size_name=size_choice, map_name=map_choice, spectator_mode=spectate
                        )
                        self.state = GameState.PLAYING

                pg.display.flip()
                self.clock.tick(60)

            elif self.state == GameState.PLAYING:
                self._run_game()

            elif self.state in (GameState.VICTORY, GameState.DEFEAT):
                if self.victory_screen is None:
                    raise ValueError("No victory screen")

                self.victory_screen.update(pg.mouse.get_pos())
                self.victory_screen.draw(self.screen)

                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False
                    result = self.victory_screen.handle_event(event)
                    if result == "menu":
                        self.state = GameState.MENU
                        self.skirmish_setup = SkirmishSetup(
                            screen_size=self.screen.size,
                        )

                pg.display.flip()
                self.clock.tick(60)

        pg.quit()

    def _run_game(self) -> None:
        """
        Main game loop: event handling, updates, rendering, win/loss checks.
        """
        # Main game loop: event handling, updates, rendering, win/loss checks.
        g = self.game_data

        while self.running and self.state == GameState.PLAYING:
            keys = pg.key.get_pressed()
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    self.running = False

                elif event.type == pg.MOUSEWHEEL:
                    mouse_pos = pg.mouse.get_pos()
                    game_rect = pg.Rect(0, 0, g.camera.width, g.camera.height)
                    if game_rect.collidepoint(mouse_pos):
                        world_mouse = g.camera.screen_to_world(mouse_pos)
                        g.camera.update_zoom(event.y, world_mouse)

                elif event.type == pg.MOUSEBUTTONDOWN:
                    mouse_pos = event.pos

                    mini_x = SCREEN_WIDTH - MINI_MAP_WIDTH
                    mini_y = SCREEN_HEIGHT - MINI_MAP_HEIGHT
                    mini_rect = pg.Rect(mini_x, mini_y, MINI_MAP_WIDTH, MINI_MAP_HEIGHT)
                    in_minimap = mini_rect.collidepoint(mouse_pos)
                    if in_minimap and event.button == 1:
                        self._handle_minimap_click(game_data=g, mouse_pos=mouse_pos, minimap_origin=(mini_x, mini_y))
                        continue

                    if g.spectator_mode:
                        continue

                    world_pos = g.camera.screen_to_world(mouse_pos)
                    if event.button == 1:
                        self._handle_mouse_1_click_non_spectator_mode(
                            game_data=g, mouse_pos=mouse_pos, world_pos=world_pos
                        )

                    elif event.button == 3:
                        self._handle_mouse_2_click_non_spectator_mode(
                            game_data=g, mouse_pos=mouse_pos, world_pos=world_pos
                        )

                elif event.type == pg.MOUSEMOTION and g.selecting:
                    current_pos = event.pos
                    if g.select_start:
                        g.select_rect = pg.Rect(
                            min(g.select_start[0], current_pos[0]),
                            min(g.select_start[1], current_pos[1]),
                            abs(current_pos[0] - g.select_start[0]),
                            abs(current_pos[1] - g.select_start[1]),
                        )

                elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and g.selecting:
                    if g.interface is None:
                        raise ValueError("`interface` cannot be `None`")  # TODO: typeguard

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
                        world_end = g.camera.screen_to_world(event.pos)
                        world_rect = pg.Rect(
                            min(world_start[0], world_end[0]),
                            min(world_start[1], world_end[1]),
                            abs(world_end[0] - world_start[0]),
                            abs(world_end[1] - world_start[1]),
                        )
                        for unit in g.player_units:
                            if world_rect.colliderect(unit.rect):
                                unit.selected = True
                                g.selected_units.add(unit)

                elif event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                    if g.interface and g.interface.placing_cls is not None:
                        g.interface.placing_cls = None
                    else:
                        self.state = GameState.MENU
                        return

            g.camera.update(
                g.selected_units.sprites() if not g.spectator_mode else [],
                pg.mouse.get_pos(),
                g.interface_rect,
                keys,
            )

            unit_list = list(g.global_units)
            building_list = [b for b in g.global_buildings if b.health > 0]

            def update_unit(unit: Unit2d) -> None:
                unit.update()

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(update_unit, unit) for unit in [u for u in unit_list if not u.is_building]]
                for future in futures:
                    future.result()

            for building in building_list:
                building_team = building.team
                friendly_units_for_build = g.unit_groups.get(building_team, pg.sprite.Group())
                building.update(friendly_units=friendly_units_for_build, all_units=g.global_units)

            g.projectiles.update()
            g.particles.update()

            unit_hash = SpatialHash2d(200)
            for u in unit_list:
                unit_hash.add(u)

            building_hash = SpatialHash2d(200)
            for b in building_list:
                building_hash.add(b)

            handle_unit_collisions(all_units=unit_list, unit_hash=unit_hash)
            handle_unit_building_collisions(all_units=unit_list, building_hash=building_hash)
            for unit in unit_list:
                unit.rect.center = unit.position

            # Unified attacks for all teams
            unique_teams = set(g.teams)
            for team in unique_teams:
                handle_attacks(
                    team=team,
                    all_units=unit_list,
                    all_buildings=building_list,
                    projectiles=g.projectiles,
                    particles=g.particles,
                    unit_hash=unit_hash,
                    building_hash=building_hash,
                    alliances=g.alliances,
                )

            handle_projectiles(
                projectiles=g.projectiles, all_units=unit_list, all_buildings=building_list, particles=g.particles, g=g
            )

            # Cleanup dead entities
            cleanup_dead_entities(g)

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
                    is_player_victory = None if g.spectator_mode else last_hq == g.player_hq
                    self.state = GameState.VICTORY if is_player_victory else GameState.DEFEAT

                self.victory_screen = VictoryScreen(
                    is_victory=is_player_victory,
                    all_stats=all_stats,
                    player_team=g.player_team,
                    screen_size=self.screen.size,
                )

            self.screen.fill(pg.Color("black"))

            zoom = g.camera.zoom
            tile_sw = TILE_SIZE * zoom
            tile_sh = TILE_SIZE * zoom
            start_tx = max(0, int(g.camera.rect.x // TILE_SIZE))
            start_ty = max(0, int(g.camera.rect.y // TILE_SIZE))
            end_tx = min(g.map_width // TILE_SIZE, start_tx + int(g.camera.rect.width // TILE_SIZE + 2))
            end_ty = min(
                g.map_height // TILE_SIZE,
                start_ty + int(g.camera.rect.height // TILE_SIZE + 2),
            )
            for tx in range(start_tx, end_tx):
                wx = tx * TILE_SIZE
                sx = (wx - g.camera.rect.x) * zoom
                if sx < -tile_sw or sx > g.camera.width:
                    continue
                for ty in range(start_ty, end_ty):
                    wy = ty * TILE_SIZE
                    sy = (wy - g.camera.rect.y) * zoom
                    if sy < -tile_sh or sy > g.camera.height:
                        continue
                    var_r = ((tx * 17 + ty * 31) % 41) - 20
                    var_g = ((tx * 23 + ty * 37) % 41) - 20
                    var_b = ((tx * 29 + ty * 41) % 41) - 20
                    tile_r = max(0, min(255, g.map_color.r + var_r))
                    tile_g = max(0, min(255, g.map_color.g + var_g))
                    tile_b = max(0, min(255, g.map_color.b + var_b))
                    pg.draw.rect(self.screen, (tile_r, tile_g, tile_b), (sx, sy, tile_sw, tile_sh))
                    crater_seed = (tx * 123 + ty * 456) % 100
                    if crater_seed < 5:
                        cx = sx + tile_sw / 2
                        cy = sy + tile_sh / 2
                        cr = tile_sw / 4
                        dark_r = max(0, tile_r - 40)
                        dark_g = max(0, tile_g - 40)
                        dark_b = max(0, tile_b - 40)
                        pg.draw.circle(self.screen, (dark_r, dark_g, dark_b), (int(cx), int(cy)), int(cr))

            draw_allies = set(g.teams) if g.spectator_mode else g.player_allies
            fog = g.fog_of_war
            if not g.spectator_mode:
                g.fog_of_war.draw(self.screen, g.camera)
            mouse_pos = pg.mouse.get_pos() if g.interface else None
            for building in building_list:
                visible = building.team in draw_allies or fog.is_visible(building.position) or building.is_seen
                if building.health > 0 and visible:
                    building.draw(self.screen, g.camera, mouse_pos)

            if g.interface and not g.spectator_mode:
                if g.player_team is None:
                    raise ValueError("`game_data.player_team` cannot be `None`")  # TODO: typeguard

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
                particle.draw_2d(self.screen, g.camera)

            if g.interface and not g.spectator_mode:
                g.interface.draw(self.screen)

            if not g.spectator_mode and g.selecting and g.select_rect:
                pg.draw.rect(self.screen, (255, 255, 255), g.select_rect, 2)

            draw_allies_mini = frozenset(g.teams) if g.spectator_mode else g.player_allies
            draw_mini_map(
                screen=self.screen,
                camera=g.camera,
                fog_of_war=g.fog_of_war,
                map_width=g.map_width,
                map_height=g.map_height,
                map_color=g.map_color,
                buildings=g.global_buildings,
                all_units=g.global_units,
                player_allies=draw_allies_mini,
            )

            pg.display.flip()
            self.clock.tick(60)

    @staticmethod
    def _handle_minimap_click(game_data: GameData, mouse_pos: IntPoint, minimap_origin: IntPoint) -> None:
        g = game_data
        local_x = mouse_pos[0] - minimap_origin[0]
        local_y = mouse_pos[1] - minimap_origin[1]
        scale_x = g.map_width / MINI_MAP_WIDTH
        scale_y = g.map_height / MINI_MAP_HEIGHT
        world_x = local_x * scale_x
        world_y = local_y * scale_y
        g.camera.rect.centerx = world_x
        g.camera.rect.centery = world_y
        g.camera.clamp()
        if not g.spectator_mode:
            for unit in g.player_units:
                unit.selected = False

            g.selected_units.empty()
            if g.selected_building:
                g.selected_building.selected = False

            g.selected_building = None
            g.selecting = False
            if g.interface:
                g.interface.update_producer(g.player_hq)

    @staticmethod
    def _handle_mouse_1_click_non_spectator_mode(game_data: GameData, mouse_pos: IntPoint, world_pos: Point) -> None:

        if game_data is None:
            raise ValueError("`game_data` cannot be `None`")  # TODO: typeguard

        g = game_data
        if g.interface is None:
            raise ValueError("`interface` cannot be `None`")  # TODO: typeguard

        if g.player_hq is None:
            raise ValueError("`game_data.player_hq` cannot be `None`")  # TODO: typeguard

        if g.player_team is None:
            raise ValueError("`game_data.player_team` cannot be `None`")  # TODO: typeguard

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

        if g.interface is None:
            raise ValueError("`interface` cannot be `None`")  # TODO: typeguard

        if g.interface.placing_cls is not None and not g.interface_rect.collidepoint(mouse_pos):
            snapped = snap_to_grid(pos=world_pos, grid_size=TILE_SIZE)
            buildings_list = list(g.global_buildings)
            _unit_type = g.interface.placing_cls.__name__
            cost = get_unit_cost(_unit_type)
            if g.player_hq.credits >= cost and is_valid_building_position(
                position=snapped,
                team=g.player_team,
                new_building_cls=g.interface.placing_cls,
                buildings=buildings_list,
                map_width=g.map_width,
                map_height=g.map_height,
            ):
                building = g.interface.placing_cls(snapped, g.player_team, hq=g.player_hq)
                g.global_buildings.add(building)
                g.player_hq.credits -= cost
                g.interface.placing_cls = None
            else:
                g.interface.placing_cls = None

            return

        target_x, target_y = mouse_pos
        clicked_building = next(
            (
                b
                for b in g.global_buildings
                if b.team == g.player_team and g.camera.get_screen_rect(b.rect).collidepoint(target_x, target_y)
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
            g.select_rect = pg.Rect(target_x, target_y, 0, 0)

    @staticmethod
    def _handle_mouse_2_click_non_spectator_mode(game_data: GameData, mouse_pos: IntPoint, world_pos: Point) -> None:
        if game_data is None:
            raise ValueError("`game_data` cannot be `None`")

        g = game_data
        if g.interface is None:
            raise ValueError("`interface` cannot be `None`")  # TODO: typeguard

        if g.interface.placing_cls is not None:
            g.interface.placing_cls = None

        elif g.selected_building and hasattr(g.selected_building, "rally_point"):
            g.selected_building.rally_point = Vector2(world_pos)

        elif g.selected_units:
            # Check for clicked enemy
            clicked_enemy = None
            unit_list = list(g.global_units)
            building_list = [b for b in g.global_buildings if b.health > 0]
            for u in unit_list:
                screen_rect = g.camera.get_screen_rect(u.rect)
                if screen_rect.collidepoint(mouse_pos) and u.team not in g.player_allies and u.health > 0:
                    clicked_enemy = u
                    break

            if not clicked_enemy:
                for b in building_list:
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
                    else:
                        unit.move_target = clicked_enemy.position

            else:
                # Normal move
                formation_positions = calculate_formation_positions_2d(
                    center=world_pos, num_units=len(g.selected_units)
                )
                for unit, pos in zip(g.selected_units, formation_positions):
                    unit.move_target = pos
                    unit.attack_target = None  # Clear attack target for move order
                    unit.formation_target = pos

    def _initialize_game(self, *, game_mode: str, size_name: str, map_name: str, spectator_mode: bool = False) -> None:
        """
        Sets up game world: scales map, creates teams/HQs/units, alliances, AI, camera, UI.

        :param game_mode: Game mode string (e.g., "1v1").
        :param size_name: Map size string (e.g., "medium").
        :param map_name: Map name string.
        :param spectator_mode: If True, spectator mode.
        """
        # Sets up game world: scales map, creates teams/HQs/units, alliances, AI, camera, UI.
        map_data = MAPS[map_name]
        base_width = map_data["width"]
        base_height = map_data["height"]
        color = pg.Color(map_data["color"])

        size_scales = {
            "tiny": 0.80,
            "small": 0.80,
            "medium": 0.80,
            "large": 0.80,
            "huge": 0.80,
        }
        scale = size_scales[size_name]
        map_width = int(base_width * scale)
        map_height = int(base_height * scale)

        ai_units = pg.sprite.Group()
        global_units = pg.sprite.Group()
        global_buildings = pg.sprite.Group()
        projectiles = pg.sprite.Group()
        particles = pg.sprite.Group()
        selected_units = pg.sprite.Group()

        unit_groups = {}
        hqs = {}
        player_side: list[Team] = []
        enemy_side: list[Team] = []
        num_players = 0

        if game_mode == "1v1":
            player_side = [Team.RED]
            enemy_side = [Team.GREEN]
            num_players = 2
        elif game_mode == "2v2":
            player_side = [Team.RED, Team.BLUE]
            enemy_side = [Team.ORANGE, Team.YELLOW]
            num_players = 4
        elif game_mode == "3v3":
            player_side = [Team.RED, Team.BLUE, Team.CYAN]
            enemy_side = [Team.MAGENTA, Team.ORANGE, Team.YELLOW]
            num_players = 6
        elif game_mode == "4v4":
            player_side = [Team.RED, Team.BLUE, Team.GREEN, Team.CYAN]
            enemy_side = [Team.MAGENTA, Team.ORANGE, Team.YELLOW, Team.GREY]
            num_players = 8
        elif game_mode == "4ffa":
            player_side = [Team.RED]
            enemy_side = [Team.BLUE, Team.GREEN, Team.CYAN]
            num_players = 4

        teams_list = player_side + enemy_side
        positions = get_starting_positions(
            map_width=map_width,
            map_height=map_height,
            num_players=num_players,
            edge_dist=STARTING_POSITIONS_EDGE_OFFSET,
        )

        for i, team in enumerate(teams_list):
            pos = positions[i]
            hq = Headquarters(position=pos, team=team)
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
            units = pg.sprite.Group()
            for _ in range(3):
                offset = find_free_spawn_position(
                    target_pos=pos, global_buildings=global_buildings.sprites(), global_units=global_units.sprites()
                )
                units.add(Infantry(position=offset, team=team, hq=hq))

            unit_groups[team] = units

        if not spectator_mode:
            player_units = unit_groups[Team.RED]
            for team in teams_list:
                if team != Team.RED:
                    ai_units.add(unit_groups[team])
        else:
            player_units = pg.sprite.Group()
            for team in teams_list:
                ai_units.add(unit_groups[team])

        for ug in unit_groups.values():
            global_units.add(ug)
        for hq in hqs.values():
            global_buildings.add(hq)

        alliances = {}
        player_side_set = set(player_side)
        for team in teams_list:
            if team in player_side_set:
                alliances[team] = frozenset(player_side)
            else:
                alliances[team] = frozenset(enemy_side)

        player_hq = None
        player_team = None
        player_allies = frozenset()
        camera = Camera2d(map_width=MAP_WIDTH, map_height=MAP_HEIGHT, width=SCREEN_WIDTH, height=SCREEN_HEIGHT)
        interface = None
        if not spectator_mode:
            player_hq = hqs[Team.RED]
            player_team = Team.RED
            player_allies = alliances[player_team]
            interface = ProductionInterface(hq=player_hq)
            interface_rect = pg.Rect(SCREEN_WIDTH - 200, 0, 200, SCREEN_HEIGHT - CONSOLE_HEIGHT)
        else:
            interface_rect = pg.Rect(0, 0, 0, 0)
            camera.rect.center = (map_width / 2, map_height / 2)

        ais = []
        for team in teams_list:
            if not spectator_mode and team == Team.RED:
                continue

            i = teams_list.index(team)
            pos = positions[i]
            center_x = map_width / 2
            center_y = map_height / 2
            build_dir = math.atan2(center_y - pos[1], center_x - pos[0])
            random.seed(team.value * 12345)  # Seed per team for consistent "personality" across runs
            ai = AI(hq=hqs[team], preferred_build_direction=build_dir, allies=alliances[team])
            ais.append(ai)

        self.game_data = GameData(
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
            fog_of_war=FogOfWar2d(
                map_width=map_width, map_height=map_height, tile_size=TILE_SIZE, spectator=spectator_mode
            ),
            camera=camera,
            map_color=color,
            map_width=map_width,
            map_height=map_height,
            game_mode=game_mode,
            ais=ais,
            interface_rect=interface_rect,
            spectator_mode=spectator_mode,
            teams=teams_list,
        )
