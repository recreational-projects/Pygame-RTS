from __future__ import annotations

import random

import pygame as pg

from src import geometry
from src.ai import AI
from src.camera import Camera
from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
    MOUSE_BUTTON,
    PRODUCTION_INTERFACE_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SELECTION_INDICATOR_COLOR,
    TILE_SIZE,
    VIEW_DEBUG_MODE_IS_ENABLED,
)
from src.fog_of_war import FogOfWar
from src.game import Game
from src.game_objects.buildings.headquarters import Headquarters
from src.game_objects.buildings.turret import Turret
from src.game_objects.units.harvester import Harvester
from src.game_objects.units.infantry import Infantry
from src.geometry import Coordinate
from src.iron_field import IronField
from src.player_interface import PlayerInterface
from src.team import Faction, Team


def draw(*, surface_: pg.Surface, game_: Game) -> None:
    """Draw entire game to `surface_`.

    Accesses global state.
    """
    surface_.fill(pg.Color("black"))
    surface_.blit(source=base_map, dest=camera.map_offset)
    for iron_field in game_.iron_fields:
        if iron_field.resources > 0 and (
            fog_of_war.is_explored(iron_field.position) or VIEW_DEBUG_MODE_IS_ENABLED
        ):
            iron_field.draw(surface=surface_, camera=camera)

    for building in game_.buildings:
        if (
            building.team == player_team
            or building.is_explored
            or VIEW_DEBUG_MODE_IS_ENABLED
        ):
            building.draw(surface=surface_, camera=camera)

    if not VIEW_DEBUG_MODE_IS_ENABLED:
        fog_of_war.draw(surface=surface_, camera=camera)

    for unit in game_.units:
        if (
            unit.team == player_team
            or fog_of_war.is_visible(unit.position)
            or VIEW_DEBUG_MODE_IS_ENABLED
        ):
            unit.draw(surface=surface_, camera=camera)

    for projectile in projectiles:
        if (
            projectile.team == player_team
            or fog_of_war.is_visible(projectile.position)
            or VIEW_DEBUG_MODE_IS_ENABLED
        ):
            projectile.draw(surface=surface_, camera=camera)

    for particle in particles:
        if fog_of_war.is_visible(particle.position) or VIEW_DEBUG_MODE_IS_ENABLED:
            particle.draw(surface=surface_, camera=camera)

    interface.draw(surface=surface_, game=game, camera=camera)
    if game.rect_selecting and game.selection_rect:
        pg.draw.rect(surface_, SELECTION_INDICATOR_COLOR, game.selection_rect, 2)


if __name__ == "__main__":
    pg.init()
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pg.time.Clock()
    base_font = pg.font.SysFont(None, 24)

    projectiles: pg.sprite.Group = pg.sprite.Group()
    particles: pg.sprite.Group = pg.sprite.Group()

    player_team = Team(faction=Faction.GDI, iron=1500)
    ai_team = Team(faction=Faction.NOD, iron=1500)

    game = Game()
    _map_bottom_right = Coordinate(MAP_WIDTH, MAP_HEIGHT)
    _hq_offset_from_corner = Coordinate(300, 300)
    _gdi_hq_pos = _hq_offset_from_corner
    _nod_hq_pos = _map_bottom_right - _hq_offset_from_corner
    gdi_hq = Headquarters(position=_gdi_hq_pos, team=player_team, font=base_font)
    nod_hq = Headquarters(position=_nod_hq_pos, team=ai_team, font=base_font)
    game.objects.add(gdi_hq)
    game.objects.add(nod_hq)
    interface = PlayerInterface(
        team=player_team, hq=gdi_hq, all_buildings=game.buildings, font=base_font
    )
    ai = AI(team=ai_team, opposing_team=player_team, hq=nod_hq)

    for i in range(3):
        _infantry_spawn_offset = Coordinate(50, 0) + i * Coordinate(20, 0)
        game.objects.add(
            Infantry(position=_gdi_hq_pos + _infantry_spawn_offset, team=player_team)
        )
        game.objects.add(
            Infantry(position=_nod_hq_pos + _infantry_spawn_offset, team=ai_team)
        )

    game.objects.add(
        Harvester(
            position=_gdi_hq_pos + (100, 100),
            team=player_team,
            hq=gdi_hq,
            font=base_font,
        )
    )
    game.objects.add(
        Harvester(
            position=_nod_hq_pos + (100, 100),
            team=ai_team,
            hq=nod_hq,
            font=base_font,
        )
    )
    for _ in range(40):
        game.iron_fields.add(
            IronField(
                x=random.randint(100, MAP_WIDTH - 100),
                y=random.randint(100, MAP_HEIGHT - 100),
                font=base_font,
            ),
        )

    fog_of_war = FogOfWar()
    camera = Camera(
        pg.Rect(
            (0, 0),
            (SCREEN_WIDTH - PRODUCTION_INTERFACE_WIDTH, SCREEN_HEIGHT),
        )
    )
    base_map = pg.Surface((MAP_WIDTH, MAP_HEIGHT))
    # Improved map with grass texture
    for x in range(0, MAP_WIDTH, TILE_SIZE):
        for y in range(0, MAP_HEIGHT, TILE_SIZE):
            color = (0, random.randint(100, 150), 0)
            pg.draw.rect(base_map, color, (x, y, TILE_SIZE, TILE_SIZE))
            if random.random() < 0.1:
                pg.draw.circle(
                    base_map,
                    (0, 80, 0),
                    (x + TILE_SIZE // 2, y + TILE_SIZE // 2),
                    TILE_SIZE // 4,
                )  # Dark spots

    running = True
    while running:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False

            elif event.type == pg.MOUSEBUTTONDOWN:
                _screen_click_pos = event.pos
                _world_click_pos = camera.to_world(event.pos)

                # Mouse 1 click
                if event.button == MOUSE_BUTTON[1]:
                    if gdi_hq.pending_building:
                        gdi_hq.place_pending_building(
                            position=_world_click_pos, game=game
                        )
                        continue

                    if interface.handle_mouse_1_click(
                        screen_pos=_screen_click_pos, game=game
                    ):
                        continue

                    for b in game.buildings:
                        b.is_selected = False
                    _clicked_player_building = game.get_team_building_at_pos(
                        position=_world_click_pos, team=player_team
                    )
                    if _clicked_player_building:
                        game.selected_building = _clicked_player_building
                        game.selected_building.is_selected = True
                    else:
                        game.selected_building = None
                        game.rect_selecting = True
                        game.selection_start = _screen_click_pos
                        game.selection_rect = pg.Rect(game.selection_start, (0, 0))

                # Mouse 3 click
                elif event.button == MOUSE_BUTTON[3]:
                    if gdi_hq.pending_building:
                        gdi_hq.pending_building = None
                        gdi_hq.pending_building_pos = None
                        if gdi_hq.production_queue and gdi_hq.has_enough_power:
                            gdi_hq.production_timer = game.get_production_time(
                                cls=gdi_hq.production_queue[0],
                                team=player_team,
                            )
                        continue

                    if game.selected_units:
                        group_center = geometry.mean_vector(
                            [u.position for u in game.selected_units]
                        )
                        formation_positions = geometry.calculate_formation_positions(
                            center=_world_click_pos,
                            target=_world_click_pos,
                            num_units=len(game.selected_units),
                        )
                        _clicked_iron_field = game.get_iron_field_at_pos(
                            _world_click_pos
                        )
                        _clicked_ai_unit = game.get_team_unit_at_pos(
                            position=_world_click_pos, team=ai_team
                        )
                        _clicked_ai_building = game.get_team_building_at_pos(
                            position=_screen_click_pos, team=ai_team
                        )
                        for unit, pos in zip(game.selected_units, formation_positions):
                            unit.target = pos
                            unit.formation_target = pos
                            unit.target_object = None
                            if _clicked_ai_unit:
                                unit.target_object = _clicked_ai_unit
                                unit.target = _clicked_ai_unit.position
                            elif _clicked_ai_building:
                                unit.target_object = _clicked_ai_building
                                unit.target = _clicked_ai_building.position
                            elif _clicked_iron_field:
                                unit.target = _clicked_iron_field.position
                                unit.formation_target = None

            # Mouse move
            elif event.type == pg.MOUSEMOTION and game.rect_selecting:
                _mouse_pos = event.pos
                if not game.selection_start:
                    raise TypeError("No selection rect start point")
                    # Temporary handling, review later

                game.selection_rect = pg.Rect(
                    min(game.selection_start[0], _mouse_pos[0]),
                    min(game.selection_start[1], _mouse_pos[1]),
                    abs(_mouse_pos[0] - game.selection_start[0]),
                    abs(_mouse_pos[1] - game.selection_start[1]),
                )

            # Mouse 1 release
            elif (
                event.type == pg.MOUSEBUTTONUP
                and event.button == MOUSE_BUTTON[1]
                and game.rect_selecting
            ):
                if not game.selection_start:
                    raise TypeError("No selection rect start point")
                    # Temporary handling, review later

                game.rect_selecting = False
                for unit in game.team_units(player_team):
                    unit.is_selected = False

                game.selected_units.clear()
                world_start = camera.to_world(game.selection_start)
                world_end = camera.to_world(event.pos)
                world_rect = pg.Rect(
                    min(world_start[0], world_end[0]),
                    min(world_start[1], world_end[1]),
                    abs(world_end[0] - world_start[0]),
                    abs(world_end[1] - world_start[1]),
                )
                for unit in game.team_units(player_team):
                    if world_rect.colliderect(unit.rect):
                        unit.is_selected = True
                        game.selected_units.add(unit)

        camera.update(selected_units=game.selected_units, mouse_pos=pg.mouse.get_pos())
        for unit in game.units:
            if isinstance(unit, Harvester):
                if unit.team == player_team:
                    unit.update(
                        enemy_units=game.team_units(ai_team),
                        iron_fields=game.iron_fields,
                    )
                else:
                    unit.update(
                        enemy_units=game.team_units(player_team),
                        iron_fields=game.iron_fields,
                    )
            else:
                unit.update()

        game.iron_fields.update()
        for building in game.buildings:
            if isinstance(building, Headquarters):
                building.update(particles=particles, game=game)

            elif isinstance(building, Turret):
                if building.team == player_team:
                    _opposing_team = ai_team
                else:
                    _opposing_team = player_team

                    building.update(
                        particles=particles,
                        projectiles=projectiles,
                        enemy_units=game.team_units(_opposing_team),
                    )
            else:
                building.update(particles=particles)

        projectiles.update(particles)
        particles.update()
        game.handle_collisions()
        game.handle_attacks(
            team=player_team,
            opposing_team=ai_team,
            projectiles=projectiles,
            particles=particles,
        )
        game.handle_attacks(
            team=ai_team,
            opposing_team=player_team,
            projectiles=projectiles,
            particles=particles,
        )
        game.handle_projectiles(projectiles=projectiles, particles=particles)
        ai.update(game=game, iron_fields=game.iron_fields)
        # AI units and buildings are indirectly manipulated here
        fog_of_war.update(
            units=game.team_units(player_team),
            buildings=game.team_buildings(player_team),
        )
        for building in game.team_buildings(ai_team):
            if fog_of_war.is_explored(building.position):
                building.is_explored = True

        draw(surface_=screen, game_=game)
        for unit in game.units:
            unit.under_attack = False

        pg.display.flip()
        clock.tick(60)

    pg.quit()
