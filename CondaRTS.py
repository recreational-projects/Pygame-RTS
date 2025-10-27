from __future__ import annotations

import random

import pygame as pg

from src import geometry
from src.ai import AI
from src.camera import Camera
from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
    PRODUCTION_INTERFACE_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
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
    if selecting and select_rect:
        pg.draw.rect(surface_, (255, 255, 255), select_rect, 2)


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

    selecting = False
    select_start = None
    select_rect = None
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
                world_pos = camera.to_world(event.pos)
                target_x, target_y = event.pos
                if event.button == 1:
                    if gdi_hq.pending_building:
                        snapped_pos = geometry.snap_to_grid(world_pos)
                        if game.is_valid_building_position(
                            position=snapped_pos,
                            new_building_class=gdi_hq.pending_building,
                            team=gdi_hq.team,
                        ):
                            gdi_hq.place_building(
                                position=world_pos,
                                unit_cls=gdi_hq.pending_building,
                                game=game,
                            )
                        continue

                    if interface.handle_click(screen_pos=event.pos, game=game):
                        continue

                    for b in game.buildings:
                        b.is_selected = False

                    clicked_building = next(
                        (
                            b
                            for b in game.team_buildings(player_team)
                            if camera.rect_to_screen(b.rect).collidepoint(
                                target_x, target_y
                            )
                        ),
                        None,
                    )
                    if clicked_building:
                        game.selected_building = clicked_building
                        game.selected_building.is_selected = True
                    else:
                        game.selected_building = None
                        selecting = True
                        select_start = event.pos
                        select_rect = pg.Rect(target_x, target_y, 0, 0)

                elif event.button == 3:
                    if gdi_hq.pending_building:
                        gdi_hq.pending_building = gdi_hq.pending_building_pos = None
                        if gdi_hq.production_queue and gdi_hq.has_enough_power:
                            gdi_hq.production_timer = game.get_production_time(
                                cls=gdi_hq.production_queue[0],
                                team=player_team,
                            )
                        continue
                    clicked_field = next(
                        (
                            f
                            for f in game.iron_fields
                            if camera.rect_to_screen(f.rect).collidepoint(
                                target_x, target_y
                            )
                        ),
                        None,
                    )
                    clicked_enemy_unit = next(
                        (
                            u
                            for u in game.team_units(ai_team)
                            if camera.rect_to_screen(u.rect).collidepoint(
                                target_x, target_y
                            )
                        ),
                        None,
                    )
                    clicked_enemy_building = next(
                        (
                            b
                            for b in game.team_buildings(ai_team)
                            if camera.rect_to_screen(b.rect).collidepoint(
                                target_x, target_y
                            )
                        ),
                        None,
                    )
                    if game.selected_units:
                        group_center = geometry.mean_vector(
                            [u.position for u in game.selected_units]
                        )
                        formation_positions = geometry.calculate_formation_positions(
                            center=world_pos,
                            target=world_pos,
                            num_units=len(game.selected_units),
                        )
                        for unit, pos in zip(game.selected_units, formation_positions):
                            unit.target = pos
                            unit.formation_target = pos
                            unit.target_object = None
                            if clicked_enemy_unit:
                                unit.target_object = clicked_enemy_unit
                                unit.target = clicked_enemy_unit.position
                            elif clicked_enemy_building:
                                unit.target_object = clicked_enemy_building
                                unit.target = clicked_enemy_building.position
                            elif clicked_field:
                                unit.target = clicked_field.position
                                unit.formation_target = None

            elif event.type == pg.MOUSEMOTION and selecting:
                current_pos = event.pos
                if not select_start:
                    raise TypeError("No selection rect start point")
                    # Temporary handling, review later

                select_rect = pg.Rect(
                    min(select_start[0], current_pos[0]),
                    min(select_start[1], current_pos[1]),
                    abs(current_pos[0] - select_start[0]),
                    abs(current_pos[1] - select_start[1]),
                )
            elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and selecting:
                if not select_start:
                    raise TypeError("No selection rect start point")
                    # Temporary handling, review later

                selecting = False
                for unit in game.team_units(player_team):
                    unit.is_selected = False

                game.selected_units.clear()
                world_start = camera.to_world(select_start)
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
