from __future__ import annotations

import math
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any, ClassVar

import pygame as pg
from pygame.math import Vector2

from modules.camera.camera_2d import Camera2d
from modules.data import UNIT_BUTTON_LABELS, Palette
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
    UNIT_CLASSES,
)
from modules.draw_2d import BUILDING_DRAW_RECIPES, COMPLEX_DRAW_RECIPES, SIMPLE_DRAW_RECIPES, draw_mini_map
from modules.fog_of_war import FogOfWar2d
from modules.fonts import FONT_MEDIUM
from modules.game_console import GameConsole
from modules.game_data import GameData
from modules.game_object.game_object_2d import GameObject2d
from modules.game_state import GameState
from modules.geometry import (
    calculate_formation_positions_2d,
    check_collision_2d,
    closest_point_on_rect,
    get_starting_positions,
    snap_to_grid,
)
from modules.particles import create_explosion_2d
from modules.projectile_2d import Projectile
from modules.screens import MainMenu, SkirmishSetup, VictoryScreen
from modules.spatial_hash import SpatialHash2d
from modules.team import Team, team_to_color, team_to_name
from modules.unit_stats_2d import UnitStats
from modules.world_2d import (
    cleanup_dead_entities,
    find_free_spawn_position,
    handle_attacks,
    handle_unit_building_collisions,
    handle_unit_collisions,
    is_valid_building_position,
)

if TYPE_CHECKING:
    from pygame.typing import IntPoint, Point

    from modules.unit_stats_2d import WeaponStats

# =============================================================================
# Group: Base Entity Classes
# =============================================================================
# Abstract GameObject base for all entities; Unit subclass for mobile/producing entities.


class Unit(GameObject2d):
    """
    Subclass for mobile/producing entities (units and buildings).

    Extends GameObject with movement, combat, production, income.
    """

    def __init__(self, *, position: Point, team: Team, unit_type_str: str, hq=None) -> None:
        """
        Unit base: loads stats from UNIT_CLASSES, sets up drawing, handles production/income if applicable.

        :param position: Initial position.
        :param team: Team enum.
        :param unit_type_str: String key from UNIT_CLASSES.
        :param hq: Optional Headquarters reference.
        """
        # Unit base: loads stats from UNIT_CLASSES, sets up drawing, handles production/income if applicable.
        super().__init__(position=position, team=team)
        self.hq = hq
        self._stats = UnitStats.from_dict(UNIT_CLASSES[unit_type_str])
        self.health: int = self._stats.hp
        self.max_health: int = self._stats.hp

        self.current_weapon_index = 0
        self.attack_target = None
        self.last_shot_time = 0
        self.move_target = None
        self.formation_target = None
        self.player_ordered = False
        self.random_offset_angle = random.uniform(-0.5, 0.5)
        self.turret_angle: float = 0
        self.body_angle: float = 0
        self.team_color = team_to_color[team]
        if self.income:
            self.collection_timer = 0

        if self.producible:
            self.rally_point = Vector2(position[0] + 80, position[1])
            self.production_queue = []
            self.production_timer = None
            self.gate_open = False
            self.gate_timer = 0

        if not self.image:  # TODO: type guard - not sure why needed
            raise TypeError("Unit has no `image`")

        self.rect = self.image.get_rect(center=position)
        # Modular drawing setup
        self._setup_drawing()

    @property
    def cost(self) -> int:
        return self._stats.cost

    @property
    def speed(self) -> float:
        return self._stats.speed

    @property
    def attack_range(self) -> int:
        return self._stats.attack_range

    @property
    def sight_range(self) -> int:
        return self._stats.sight_range

    @property
    def size(self) -> tuple[int, int]:
        return self._stats.size

    @property
    def is_building(self) -> bool:
        return self._stats.is_building

    @property
    def is_air(self) -> bool:
        return self._stats.air

    @property
    def income(self) -> int | None:
        return self._stats.income

    @property
    def income_interval(self) -> int:
        return self._stats.income_interval

    @property
    def fly_height(self) -> int:
        if not self.is_air:
            raise ValueError("`fly_height` is only available for air units.")

        if self._stats.fly_height is None:
            raise ValueError("`fly_height` is `None`.")

        return self._stats.fly_height

    @property
    def production_time(self) -> int | None:
        return self._stats.production_time

    @property
    def weapons(self) -> list[WeaponStats]:
        return self._stats.weapons

    @property
    def current_weapon(self) -> WeaponStats:
        return self.weapons[self.current_weapon_index]

    @property
    def producible(self) -> list[str]:
        return self._stats.producible

    @property
    def is_resource_building(self) -> bool:
        return isinstance(self, OilDerrick | Refinery | ShaleFracker | BlackMarket)

    @property
    def is_military_producer_building(self) -> bool:
        return isinstance(self, Barracks | WarFactory | Hangar)

    def get_chase_position_for_building(self, target_building) -> Vector2 | None:
        """
        Computes the position to move to so that the distance to the closest edge of the building is exactly attack_range.

        :param target_building: Target building.
        :return: Chase position or None if already in range.
        """
        # Computes the position to move to so that the distance to the closest edge of the building is exactly attack_range.
        closest = closest_point_on_rect(rect=target_building.rect, pos=self.position)
        dir_to_closest = Vector2(closest) - self.position
        dist_to_closest = dir_to_closest.length()
        if dist_to_closest <= self.attack_range:
            return None  # Already in range

        if dist_to_closest == 0:
            return None

        dir_unit = dir_to_closest.normalize()
        target_pos = Vector2(closest) - dir_unit * self.attack_range
        # Add perpendicular spread to avoid clustering
        perp_dir = dir_unit.rotate_rad(math.pi / 2)
        spread_dist = random.uniform(-30, 30)
        target_pos += perp_dir * spread_dist
        return target_pos

    def _setup_drawing(self) -> None:
        """
        Sets up image or complex draw method based on type.
        """

        unit_type_str = self.__class__.__name__
        if unit_type_str in SIMPLE_DRAW_RECIPES:
            self.image = SIMPLE_DRAW_RECIPES[unit_type_str](self.size, self.team)

        if not self.image:  # TODO: type guard - not sure why needed
            raise TypeError("Unit has no `image`")

        if unit_type_str in ["Infantry", "Grenadier"]:
            self.needs_rotation = True

        elif unit_type_str in COMPLEX_DRAW_RECIPES:
            create_surfaces, draw_func = COMPLEX_DRAW_RECIPES[unit_type_str]
            self.body_surf, self.turret_surf, self.barrel_surf = create_surfaces(self.team)
            if unit_type_str == "AttackHelicopter":
                self.turret_offset = Vector2(12, 0)
                self.barrel_offset = Vector2(6, 0)
            else:
                self.turret_offset = Vector2(0, -3) if unit_type_str != "Turret" else Vector2(0, -15)
                self.barrel_offset = (
                    Vector2(8, 0)
                    if unit_type_str == "Tank"
                    else Vector2(10, 0)
                    if unit_type_str == "MachineGunVehicle"
                    else Vector2(15, 0)
                    if unit_type_str == "RocketArtillery"
                    else Vector2(10, 0)
                )
            self.draw = draw_func.__get__(self, self.__class__)

        elif self.is_building and unit_type_str in BUILDING_DRAW_RECIPES:
            self.image = BUILDING_DRAW_RECIPES[unit_type_str](self.size, self.team)

        else:
            # Fallback
            self.image.fill(self.team_color)

        if not self.image:  # TODO: type guard
            raise TypeError("Unit has no `image`")

        self.rect = self.image.get_rect(center=self.position)

    def _draw_gate(self, surface: pg.Surface, camera: Camera2d) -> None:
        """
        Draws animated opening gates for production buildings.

        :param surface: Surface to draw on.
        :param camera: Camera2d for transformation.
        """
        if not self.rect:  # TODO: type guard - not sure why needed
            raise TypeError("Unit has no `image`")

        door_width = self._stats.gate_width
        half_door_offset = self._stats.half_door_offset
        door_color = self._stats.door_color
        door_height = self.rect.height - 20
        half_door = door_width // 2
        left_door = pg.Rect(self.rect.right - door_width, self.rect.top + 10, half_door, door_height)
        right_door = pg.Rect(self.rect.right - half_door, self.rect.top + 10, half_door, door_height)
        open_left = left_door.move(-half_door_offset, 0)
        open_right = right_door.move(half_door_offset, 0)
        pg.draw.rect(surface, door_color, camera.get_screen_rect(open_left))
        pg.draw.rect(surface, door_color, camera.get_screen_rect(open_right))

    def _update_production(self, friendly_units, all_units) -> None:
        """
        Advances production queue, spawns units at gate, opens gate animation.

        :param friendly_units: Group to add new units to.
        :param all_units: Global group to add new units to.
        """
        # Advances production queue, spawns units at gate, opens gate animation.
        if self.gate_open:
            self.gate_timer -= 1
            if self.gate_timer <= 0:
                self.gate_open = False

        if self.production_queue:
            if self.production_timer is None:
                self.production_timer = self.production_time

            self.production_timer -= 1
            if self.production_timer <= 0:
                item = self.production_queue.pop(0)
                unit_type = item["unit_type"]
                repeat = item.get("repeat", False)

                if not isinstance(self.rect, pg.Rect):
                    raise TypeError("Unit has unexpected `rect` type")

                spawn_pos = (self.rect.right, self.rect.centery)
                try:
                    new_unit = globals()[unit_type](position=spawn_pos, team=self.team, hq=self.hq)
                except KeyError:
                    new_unit = globals()["Infantry"](position=spawn_pos, team=self.team, hq=self.hq)  # fallback

                if not self.hq:
                    raise ValueError("Unit has no `hq`")

                self.hq.game_stats["units_created"] += 1
                new_unit.position = Vector2(spawn_pos)
                new_unit.rect.center = new_unit.position
                new_unit.move_target = self.rally_point
                friendly_units.add(new_unit)
                all_units.add(new_unit)
                self.gate_open = True
                self.gate_timer = 60
                if repeat:
                    self.production_queue.append({"unit_type": unit_type, "repeat": True})

                self.production_timer = None

    def update(
        self,
        particles=None,
        friendly_units=None,
        all_units=None,
        global_buildings=None,
        projectiles=None,
        enemy_units=None,
        enemy_buildings=None,
    ) -> None:
        """
        Core update: handles attack targeting, movement, shooting, production, income, particle cleanup.

        :param particles: Particle group.
        :param friendly_units: Friendly unit group.
        :param all_units: Global unit group.
        :param global_buildings: Global building group.
        :param projectiles: Projectile group.
        :param enemy_units: Enemy units list.
        :param enemy_buildings: Enemy buildings list.
        """
        # Core update: handles attack targeting, movement, shooting, production, income, particle cleanup.
        self.under_attack_timer = max(0, self.under_attack_timer - 1)
        self.under_attack = self.under_attack_timer > 0

        if self.last_shot_time > 0:
            self.last_shot_time -= 1

        # Clear invalid attack target
        if self.attack_target:
            if not hasattr(self.attack_target, "health") or self.attack_target.health <= 0:
                if self.move_target == self.attack_target.position:
                    self.move_target = None
                self.attack_target = None
            elif self.distance_to(self.attack_target.position) > self.sight_range:
                if self.move_target == self.attack_target.position:
                    self.move_target = None
                self.attack_target = None

        if not self.is_building:
            if self.attack_target and self.attack_target.health > 0:
                if self.attack_target.is_building:
                    closest = closest_point_on_rect(rect=self.attack_target.rect, pos=self.position)
                    dir_to_closest = Vector2(closest) - self.position
                    dist = dir_to_closest.length()
                else:
                    dist = self.distance_to(self.attack_target.position)
                if self.attack_target.is_building:
                    closest_enemy = closest_point_on_rect(rect=self.attack_target.rect, pos=self.position)
                    dir_to_enemy = Vector2(closest_enemy) - self.position
                else:
                    dir_to_enemy = Vector2(self.attack_target.position) - self.position
                if dir_to_enemy.length() > 0:
                    dir_to_enemy = dir_to_enemy.normalize()
                self.turret_angle = math.atan2(dir_to_enemy.y, dir_to_enemy.x)
                if dist <= self.attack_range:
                    # Stop moving and fight
                    self.move_target = None
                    # Face the enemy
                    self.body_angle = self.turret_angle
                    # Small random movement to avoid clustering
                    if not self.attack_target.is_building and random.random() < 0.1:
                        self.position += dir_to_enemy.rotate_rad(random.uniform(-0.5, 0.5)) * self.speed * 0.2
                        # Restore move_target after combat if needed, but for now, stay stopped until enemy dead or out of sight

                else:
                    # Chase the target
                    if self.attack_target.is_building:
                        chase_pos = self.get_chase_position_for_building(self.attack_target)
                        if chase_pos is not None:
                            self.move_target = chase_pos
                        else:
                            self.move_target = None
                    else:
                        self.move_target = self.attack_target.position

        if not self.attack_target:
            self.turret_angle = self.body_angle

        # Movement
        if self.move_target:
            dir_to_target = Vector2(self.move_target) - self.position
            dist_to_move = dir_to_target.length()
            if dist_to_move > 5:
                move_dir = dir_to_target.normalize()
                self.position += move_dir * self.speed
                self.body_angle = math.atan2(move_dir.y, move_dir.x)
            else:
                self.move_target = None

        if self.producible and friendly_units is not None and all_units is not None:
            self._update_production(friendly_units, all_units)

        if hasattr(self, "collection_timer"):
            self.collection_timer += 1
            if self.collection_timer >= self.income_interval:
                income = self.income
                if not self.hq:
                    raise ValueError("Unit has no `hq`")

                self.hq.credits += income
                self.hq.game_stats["credits_earned"] += income
                self.collection_timer = 0

        if not isinstance(self.rect, pg.Rect):
            raise TypeError("Unit has unexpected `rect` type")

        self.rect.center = self.position

        self.plasma_burn_particles = [p for p in self.plasma_burn_particles if p.alive()]

    def draw(self, surface: pg.Surface, camera: Camera2d, mouse_pos: Point | None = None) -> None:
        """
        Overridden draw for units: handles air height, rotation, rally point, gate animation.

        :param surface: Surface to draw on.
        :param camera: Camera2d for transformation.
        :param mouse_pos: Mouse position for hover.
        """
        # Overridden draw for units: handles air height, rotation, rally point, gate animation.
        if self.health <= 0:
            return

        screen_pos = camera.world_to_screen(self.position)
        if self.is_air:
            screen_pos = (screen_pos[0], screen_pos[1] - self.fly_height * camera.zoom)

        zoom = camera.zoom
        if not isinstance(self.rect, pg.Rect):
            raise TypeError("Unit has unexpected `rect` type")

        screen_rect = camera.get_screen_rect(self.rect)
        if not screen_rect.colliderect((0, 0, camera.width, camera.height)):
            return

        scaled_size = (int(self.image.get_width() * zoom), int(self.image.get_height() * zoom))
        if scaled_size[0] > 0 and scaled_size[1] > 0:
            scaled_image = pg.transform.smoothscale(self.image, scaled_size)
            if hasattr(self, "needs_rotation") and self.needs_rotation:
                rotated_image = pg.transform.rotate(scaled_image, -math.degrees(self.body_angle))
                rot_rect = rotated_image.get_rect(center=screen_pos)
                surface.blit(rotated_image, rot_rect.topleft)
            else:
                offset_x = scaled_size[0] / 2
                offset_y = scaled_size[1] / 2
                blit_pos = (screen_pos[0] - offset_x, screen_pos[1] - offset_y)
                surface.blit(scaled_image, blit_pos)
        if self.selected:
            if self.is_building:
                screen_rect = camera.get_screen_rect(self.rect)
                pg.draw.rect(surface, (255, 255, 0), screen_rect, int(3 * zoom))
            else:
                radius = max(self.rect.width, self.rect.height) / 2 * zoom + 3
                pg.draw.circle(
                    surface,
                    (255, 255, 0),
                    (int(screen_pos[0]), int(screen_pos[1])),
                    int(radius),
                    int(2 * zoom),
                )
        if hasattr(self, "rally_point") and self.selected:
            rally_screen = camera.world_to_screen(self.rally_point)
            pg.draw.circle(surface, (0, 255, 0), (int(rally_screen[0]), int(rally_screen[1])), 5)
        if hasattr(self, "gate_open") and self.gate_open:
            self._draw_gate(surface, camera)
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_2d(surface, camera)

    def shoot(self, target, projectiles: pg.sprite.Group) -> None:
        """
        Fires a projectile using current weapon at target, with lead prediction.

        Triggers small explosion.

        :param target: Target entity.
        :param projectiles: Group to add projectile to.
        """
        if self.last_shot_time > 0:
            return

        if target.is_building:
            closest = closest_point_on_rect(rect=target.rect, pos=self.position)
            dist = Vector2(closest).distance_to(self.position)
            aim_pos = closest
        else:
            dist = self.distance_to(target.position)
            time_to_target = dist / self.current_weapon.projectile_speed
            target_vel = Vector2(
                target.speed * math.cos(getattr(target, "body_angle", 0)) if hasattr(target, "speed") else 0,
                target.speed * math.sin(getattr(target, "body_angle", 0)) if hasattr(target, "speed") else 0,
            )
            predicted_pos = target.position + target_vel * time_to_target
            aim_pos = predicted_pos

        if dist > self.attack_range:
            return

        vec = aim_pos - self.position
        if vec.length() == 0:
            return

        direction = vec.normalize()
        proj = Projectile(pos=self.position, direction=direction, team=self.team, weapon=self.current_weapon)
        projectiles.add(proj)
        self.last_shot_time = self.current_weapon.cooldown
        self.turret_angle = math.atan2(direction.y, direction.x)
        create_explosion_2d(position=self.position, particles=pg.sprite.Group(), team=self.team, count=3)


# =============================================================================
# Group: Unit Drawing & Creation + Specific Unit Classes
# =============================================================================
# Specific unit classes inherit from Unit; drawing is handled via _setup_drawing.


# Subclasses now lean, relying on base Unit for drawing setup
class Infantry(Unit):
    """
    Infantry unit class.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Infantry", hq=hq)


class Tank(Unit):
    """
    Tank unit class.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Tank", hq=hq)


class Grenadier(Unit):
    """
    Grenadier unit class.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Grenadier", hq=hq)


class MachineGunVehicle(Unit):
    """
    Machine Gun Vehicle unit class.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="MachineGunVehicle", hq=hq)


class RocketArtillery(Unit):
    """
    Rocket Artillery unit class.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="RocketArtillery", hq=hq)


class AttackHelicopter(Unit):
    """
    Attack Helicopter unit class.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="AttackHelicopter", hq=hq)


# =============================================================================
# Group: Building Drawing & Creation + Specific Building Classes + Turret
# =============================================================================
# Building classes inherit from Unit; add specific logic like income or production.


class Headquarters(Unit):
    """
    Headquarters building: main base with credits, power management, building placement.
    """

    def __init__(self, *, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Headquarters", hq=hq)
        # HQ-specific: starts with credits, manages power, building placement queue.
        self.credits = self._stats.starting_credits
        self.power_output = 100
        self.power_usage = 50
        self.has_enough_power = True
        self.production_queue: list[dict[str, Any]] = []
        self.production_timer = None
        self.pending_building = None
        self.pending_building_pos = None
        self.rally_point = Vector2(position[0] + (100 if team == Team.GREEN else position[0] - 100), position[1])
        self.radius = 50
        self.game_stats = {
            "units_created": 0,
            "units_lost": 0,
            "units_destroyed": 0,
            "buildings_constructed": 0,
            "buildings_lost": 0,
            "buildings_destroyed": 0,
            "credits_earned": 0,
        }

    def place_building(self, position: Point, unit_cls: type, all_buildings) -> None:
        """
        Instantiates and places a building if valid, deducts cost.

        :param position: Placement position.
        :param unit_cls: Building class.
        :param all_buildings: Global building group.
        """
        # Instantiates and places a building if valid, deducts cost.
        all_buildings_list = list(all_buildings)
        if is_valid_building_position(
            position=position, team=self.team, new_building_cls=unit_cls, buildings=all_buildings_list
        ):
            unit_type = unit_cls.__name__
            building = unit_cls(position, self.team, hq=self)
            if unit_type in ["WarFactory", "Barracks", "Hangar"]:
                building.parent_hq = self
            all_buildings.add(building)
            self.game_stats["buildings_constructed"] += 1
            self.credits -= building.cost
            self.pending_building = None


class Barracks(Unit):
    """
    Barracks building: produces infantry units.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Barracks", hq=hq)
        self.parent_hq = None


class WarFactory(Unit):
    """
    War Factory building: produces ground vehicles.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="WarFactory", hq=hq)
        self.parent_hq = None


class Hangar(Unit):
    """
    Hangar building: produces air units.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Hangar", hq=hq)
        self.parent_hq = None


class PowerPlant(Unit):
    """
    Power Plant building: provides power.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="PowerPlant", hq=hq)


class OilDerrick(Unit):
    """
    Oil Derrick building: generates income from oil.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="OilDerrick", hq=hq)


class Refinery(Unit):
    """
    Refinery building: processes oil for income.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Refinery", hq=hq)
        self.radius = 60


class ShaleFracker(Unit):
    """
    Shale Fracker building: extracts shale for income.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="ShaleFracker", hq=hq)


class BlackMarket(Unit):
    """
    Black Market building: illicit income source.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="BlackMarket", hq=hq)


class Turret(Unit):
    """
    Defensive turret building: auto-fires on enemies.
    """

    def __init__(self, position: Point, team: Team, hq=None) -> None:
        super().__init__(position=position, team=team, unit_type_str="Turret", hq=hq)


# =============================================================================
# Group: AI Controller
# =============================================================================
# AI class manages autonomous decision-making: production, building, scouting, attacking.


class AI:
    """
    AI class manages autonomous decision-making: production, building, scouting, attacking.

    Supports personalities for varied behavior.
    """

    def __init__(self, hq, console, build_dir: float = math.pi, allies: frozenset[Team] = frozenset()) -> None:
        """
        Initializes AI with personality traits, timers, biases for varied behavior.

        :param hq: Headquarters for the AI.
        :param console: Console for logging.
        :param build_dir: Preferred build direction angle.
        :param allies: Set of allied teams.
        """
        # Initializes AI with personality traits, timers, biases for varied behavior.
        self.hq = hq
        self.console = console
        self.allies = allies
        self.action_timer = 0
        self.build_attempts = {}
        self.economy_level = 0
        self.military_strength = 0
        self.enemy_strength = 0
        self.threat_level = 0
        self.scout_timer = 0
        self.defense_timer = 0
        self.attack_timer = 0
        self.build_queue = []
        self.barracks_index = 0
        self.warfactory_index = 0
        self.hangar_index = 0
        self.personality = random.choice(["aggressive", "defensive", "balanced", "rusher"])  # Random trait
        self.timer_offset = random.randint(0, 180)  # Stagger starts by up to 3 seconds (at 60 FPS)
        self.interval_multiplier = random.uniform(0.7, 1.3)  # Vary speeds: 70-130% of base intervals
        self.build_jitter = random.uniform(0.1, 0.5)  # Extra randomness in build angles (lower = more biased)
        self.aggression_bias = (
            1.2 if self.personality in ["aggressive", "rusher"] else 0.8 if self.personality == "defensive" else 1.0
        )
        self.economy_bias = (
            0.8 if self.personality in ["aggressive", "rusher"] else 1.2 if self.personality == "defensive" else 1.0
        )

        # Adjust priorities based on personality
        base_priorities = {
            "Infantry": 0.6,
            "Grenadier": 0.2,
            "Tank": 0.15,
            "MachineGunVehicle": 0.05,
            "RocketArtillery": 0.05,
            "AttackHelicopter": 0.0,
        }
        if self.personality == "rusher":
            base_priorities["Infantry"] *= 1.5  # Rush cheap units
            base_priorities["AttackHelicopter"] *= 0.5
        elif self.personality == "defensive":
            base_priorities["Grenadier"] *= 1.5  # More area denial
            base_priorities["Tank"] *= 0.5
        self.production_priorities = base_priorities
        self.preferred_build_direction = build_dir
        self.build_bias_strength = 0.3

    def assess_situation(self, *, friendly_units, friendly_buildings, enemy_units) -> None:
        """
        Evaluates economy, military, threats to adjust priorities dynamically.

        :param friendly_units: List of friendly units.
        :param friendly_buildings: List of friendly buildings.
        :param enemy_units: List of enemy units.
        """
        # Evaluates economy, military, threats to adjust priorities dynamically.
        self.military_strength = len([u for u in friendly_units if u.health > 0])
        self.enemy_strength = len([u for u in enemy_units if u.health > 0])

        hq_pos = self.hq.position
        nearby_enemies = [u for u in enemy_units if u.health > 0 and u.distance_to(hq_pos) < 600]
        self.threat_level = len(nearby_enemies) / max(1, self.enemy_strength) if self.enemy_strength > 0 else 0

        self.resource_buildings = [b for b in friendly_buildings if b.is_resource_building]
        self.economy_level = min(3, len(self.resource_buildings) // 2)

        self.resource_count = len([b for b in friendly_buildings if b.is_resource_building and b.health > 0])
        self.turret_count = len([b for b in friendly_buildings if isinstance(b, Turret) and b.health > 0])

        self.military_prod_count = len(
            [b for b in friendly_buildings if b.is_military_producer_building and b.health > 0]
        )
        _power_count = len([b for b in friendly_buildings if isinstance(b, PowerPlant) and b.health > 0])
        self.total_buildings = sum((self.military_prod_count, self.resource_count, _power_count, self.turret_count))

        power_plants = len([b for b in friendly_buildings if isinstance(b, PowerPlant)])
        self.power_shortage = power_plants < self.economy_level + 1

        inf_prio = 0.5 if self.threat_level > 0.5 else 0.6
        gren_prio = 0.3 if self.threat_level > 0.5 else 0.2
        tank_prio = 0.15 if self.economy_level >= 1 else 0.05
        mgv_prio = 0.05 if self.economy_level >= 2 else 0.0
        rocket_prio = 0.05 if self.economy_level >= 2 else 0.0
        heli_prio = 0.1 if self.economy_level >= 2 else 0.0
        total_prio = inf_prio + gren_prio + tank_prio + mgv_prio + rocket_prio + heli_prio
        if total_prio > 0:
            inf_prio /= total_prio
            gren_prio /= total_prio
            tank_prio /= total_prio
            mgv_prio /= total_prio
            rocket_prio /= total_prio
            heli_prio /= total_prio
        self.production_priorities = {
            "Infantry": inf_prio,
            "Grenadier": gren_prio,
            "Tank": tank_prio,
            "MachineGunVehicle": mgv_prio,
            "RocketArtillery": rocket_prio,
            "AttackHelicopter": heli_prio,
        }

    @staticmethod
    def _get_nearest_enemy_building(enemy_buildings, from_pos):
        """
        Finds nearest enemy building, weighted by strategic value (HQ > factories > resources).

        :param enemy_buildings: List of enemy buildings.
        :param from_pos: Position to measure distance from.
        :return: Nearest building or None.
        """
        # Finds nearest enemy building, weighted by strategic value (HQ > factories > resources).
        if not enemy_buildings:
            return None

        building_weights = {
            Headquarters: 1.0,
            Barracks: 0.8,
            WarFactory: 0.8,
            Hangar: 0.8,
            Refinery: 0.7,
            PowerPlant: 0.6,
            Turret: 0.5,
            OilDerrick: 0.4,
            ShaleFracker: 0.4,
            BlackMarket: 0.4,
        }

        def weighted_dist(b):
            weight = building_weights.get(type(b), 1.0)
            dist = b.distance_to(from_pos)
            return dist / weight

        return min((b for b in enemy_buildings if b.health > 0), key=weighted_dist, default=None)

    def _get_nearest_enemy_target(self, enemy_buildings, enemy_units, from_pos):
        """
        Prioritizes buildings over units for targeting.

        :param enemy_buildings: List of enemy buildings.
        :param enemy_units: List of enemy units.
        :param from_pos: Position to measure from.
        :return: Nearest target or None.
        """
        # Prioritizes buildings over units for targeting.
        if enemy_buildings:
            building_target = self._get_nearest_enemy_building(enemy_buildings, from_pos)
        else:
            building_target = None

        if enemy_units:
            unit_target = min(
                (u for u in enemy_units if u.health > 0 and isinstance(u, Infantry | Grenadier)),
                key=lambda u: u.distance_to(from_pos),
                default=None,
            )
            if not unit_target:
                unit_target = min(
                    (u for u in enemy_units if u.health > 0),
                    key=lambda u: u.distance_to(from_pos),
                    default=None,
                )
        else:
            unit_target = None

        if building_target and unit_target:
            if building_target.distance_to(from_pos) < unit_target.distance_to(from_pos):
                return building_target
            else:
                return unit_target
        elif building_target:
            return building_target
        elif unit_target:
            return unit_target
        return None

    def find_build_position(
        self,
        building_cls: type[Barracks]
        | type[BlackMarket]
        | type[Hangar]
        | type[OilDerrick]
        | type[PowerPlant]
        | type[Refinery]
        | type[ShaleFracker]
        | type[Turret]
        | type[WarFactory],
        all_buildings,
        map_width: int,
        map_height: int,
        prefer_near_hq=True,
    ) -> tuple[float, float] | None:
        """
        Searches for valid build spot in expanding rings around HQ, with directional bias.

        :param building_cls: Building class to place.
        :param all_buildings: Global buildings for validation.
        :param map_width: Map width.
        :param map_height: Map height.
        :param prefer_near_hq: If True, search near HQ.
        :return: Valid position or None.
        """
        # Searches for valid build spot in expanding rings around HQ, with directional bias.
        default_area = 2560 * 1440
        map_area = map_width * map_height
        scale = math.sqrt(map_area / default_area)
        hq_pos = self.hq.position
        half_w, half_h = (
            UNIT_CLASSES[building_cls.__name__]["size"][0] / 2,
            UNIT_CLASSES[building_cls.__name__]["size"][1] / 2,
        )
        max_attempts = 2000
        attempts = 0

        if building_cls.__name__ in ["PowerPlant", "Barracks", "WarFactory", "Hangar"]:
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 100, 150 + 50 * scale
        elif building_cls.__name__ in ["OilDerrick", "Refinery", "ShaleFracker", "BlackMarket"]:
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 120, 200 + 100 * scale
        elif building_cls.__name__ == "Turret":
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 80, 150 + 30 * scale
        else:
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 100, 180 + 50 * scale

        if not prefer_near_hq:
            dist_min, dist_max = max(200, dist_min), 400 * scale

        ring_step = 25 * scale  # Increased from 20: Wider rings to sample more spaced positions
        num_samples_per_ring = 25  # Increased from 20: More attempts per ring for better spacing
        # Increase jitter for personality
        angle_jitter = (
            math.pi * self.build_jitter * (1.5 if self.personality == "rusher" else 1.0)
        )  # Rushers spread out more
        for ring_dist in range(int(dist_min), int(dist_max + 100), int(ring_step)):
            for _ in range(num_samples_per_ring):
                angle_offset = random.uniform(-angle_jitter, angle_jitter) + random.uniform(-0.2, 0.2)
                angle = bias_angle + angle_offset
                dist = ring_dist + random.uniform(-ring_step / 2, ring_step / 2)
                center_x = hq_pos.x + dist * math.cos(angle)
                center_y = hq_pos.y + dist * math.sin(angle)
                center_x = max(half_w, min(map_width - half_w, center_x))
                center_y = max(half_h, min(map_height - half_h, center_y))
                snapped_center = snap_to_grid(pos=(center_x, center_y), grid_size=TILE_SIZE)
                position = snapped_center
                if is_valid_building_position(
                    position=position,
                    team=self.hq.team,
                    new_building_cls=building_cls,
                    buildings=list(all_buildings),
                    map_width=map_width,
                    map_height=map_height,
                ):
                    return position
                attempts += 1
                if attempts > max_attempts:
                    break
            if attempts > max_attempts:
                break
        return None

    def queue_unit_production(self, barracks_list, war_factory_list, hangar_list, friendly_units) -> None:
        """
        Queues unit production based on priorities, economy, threats; cycles factories.

        :param barracks_list: List of barracks.
        :param war_factory_list: List of war factories.
        :param hangar_list: List of hangars.
        :param friendly_units: Friendly units for counting.
        """
        # Queues unit production based on priorities, economy, threats; cycles factories.
        num_units = len([u for u in friendly_units if u.health > 0])
        target_units = max(8, int(self.military_strength * 1.5) + int(self.threat_level * 25))

        if num_units < target_units:
            if barracks_list:
                barracks = barracks_list[self.barracks_index % len(barracks_list)]
                self.barracks_index += 1
                if len(barracks.production_queue) < 5:
                    if self.threat_level > 0.5:
                        unit_type = random.choices(
                            list(self.production_priorities.keys()),
                            weights=[0.7, 0.2, 0.1, 0, 0, 0],
                        )[0]
                    else:
                        unit_type = random.choices(
                            list(self.production_priorities.keys()),
                            weights=list(self.production_priorities.values()),
                        )[0]

                    cost = UNIT_CLASSES[unit_type]["cost"]
                    if self.hq.credits >= cost:
                        barracks.production_queue.append({"unit_type": unit_type, "repeat": False})
                        self.hq.credits -= cost
                        if random.random() < 0.4 and unit_type == "Infantry" and num_units < 5:
                            barracks.production_queue[-1]["repeat"] = True

            if war_factory_list:
                war_factory = war_factory_list[self.warfactory_index % len(war_factory_list)]
                self.warfactory_index += 1
                if len(war_factory.production_queue) < 3 and self.economy_level > 1:
                    heavy_unit = random.choice(["Tank", "MachineGunVehicle", "RocketArtillery"])
                    cost = UNIT_CLASSES[heavy_unit]["cost"]
                    if self.hq.credits >= cost and num_units < target_units * 0.8:
                        war_factory.production_queue.append({"unit_type": heavy_unit, "repeat": False})
                        self.hq.credits -= cost

            if hangar_list:
                hangar = hangar_list[self.hangar_index % len(hangar_list)]
                self.hangar_index += 1
                if len(hangar.production_queue) < 2 and self.economy_level >= 2:
                    if random.random() < 0.2:
                        hangar.production_queue.append({"unit_type": "AttackHelicopter", "repeat": False})
                        self.hq.credits -= UNIT_CLASSES["AttackHelicopter"]["cost"]

    def build_defenses(self, all_buildings, map_width, map_height) -> None:
        """
        Builds turrets near HQ if threatened and affordable.

        :param all_buildings: Global buildings.
        :param map_width: Map width.
        :param map_height: Map height.
        """
        # Builds turrets near HQ if threatened and affordable.
        if self.threat_level > 0.2 and self.hq.credits >= UNIT_CLASSES["Turret"]["cost"]:
            pos = self.find_build_position(Turret, all_buildings, map_width, map_height, prefer_near_hq=True)
            if pos:
                self.hq.place_building(pos, Turret, all_buildings)

    def strategize_attacks(self, friendly_units, enemy_hq, enemy_buildings=None, enemy_units=None) -> None:
        """
        Periodic scouting and attack waves; aggressive push if superior.

        :param friendly_units: Friendly units.
        :param enemy_hq: Enemy HQ.
        :param enemy_buildings: Enemy buildings.
        :param enemy_units: Enemy units.
        """
        # Periodic scouting and attack waves; aggressive push if superior.
        if not enemy_hq and not enemy_buildings and not enemy_units:
            return

        self.scout_timer += 1
        scout_interval = int(60 * self.interval_multiplier)  # Varied: 42-78 frames
        if self.scout_timer > scout_interval and len(friendly_units) > 1:
            scout_target = (
                enemy_hq.position
                if enemy_hq
                else (
                    self._get_nearest_enemy_building(
                        enemy_buildings, friendly_units[0].position if friendly_units else (0, 0)
                    ).position
                    if enemy_buildings
                    else (0, 0)
                )
            )
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None][:3]
            for scout in idle_units:
                scout.move_target = (
                    scout_target[0] + random.uniform(-200, 200),
                    scout_target[1] + random.uniform(-200, 200),
                )
            self.scout_timer = random.randint(0, scout_interval // 2)  # Jitter reset

        self.attack_timer += 1
        attack_interval = int(30 * self.interval_multiplier)  # Varied: 21-39 frames
        attack_fraction = (0.3 if self.threat_level > 0.5 else 0.2) * self.aggression_bias  # Personality tweak
        if self.attack_timer > attack_interval:
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None]
            if len(idle_units) > 0:
                num_to_send = max(
                    1, int(len(idle_units) * attack_fraction * random.uniform(0.8, 1.2))
                )  # Extra randomness
                for unit in idle_units[:num_to_send]:
                    primary_target = self._get_nearest_enemy_target(enemy_buildings, enemy_units, unit.position)
                    if primary_target:
                        unit.attack_target = primary_target
                        if primary_target.is_building:
                            chase_pos = unit.get_chase_position_for_building(primary_target)
                            unit.move_target = chase_pos if chase_pos is not None else None
                        else:
                            unit.move_target = primary_target.position
                    else:
                        if enemy_hq:
                            unit.attack_target = enemy_hq
                            if enemy_hq.is_building:
                                chase_pos = unit.get_chase_position_for_building(enemy_hq)
                                unit.move_target = chase_pos if chase_pos is not None else None
                            else:
                                unit.move_target = enemy_hq.position
                        else:
                            unit.move_target = None
            self.attack_timer = random.randint(0, attack_interval // 2)

        # Aggressive push: Scale by personality
        push_threshold = 0.5 * self.aggression_bias
        if self.military_strength > self.enemy_strength * push_threshold:
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None]
            if len(idle_units) > 3:
                attack_fraction = (0.8 if self.threat_level > 0.5 else 0.5) * self.aggression_bias
                num_to_send = int(len(idle_units) * attack_fraction)
                for unit in idle_units[:num_to_send]:
                    primary_target = self._get_nearest_enemy_target(enemy_buildings, enemy_units, unit.position)
                    if primary_target:
                        unit.attack_target = primary_target
                        if primary_target.is_building:
                            chase_pos = unit.get_chase_position_for_building(primary_target)
                            unit.move_target = chase_pos if chase_pos is not None else None
                        else:
                            unit.move_target = primary_target.position
                    else:
                        if enemy_hq:
                            unit.attack_target = enemy_hq
                            if enemy_hq.is_building:
                                chase_pos = unit.get_chase_position_for_building(enemy_hq)
                                unit.move_target = chase_pos if chase_pos is not None else None
                            else:
                                unit.move_target = enemy_hq.position
                        else:
                            unit.move_target = None

    def update(
        self,
        friendly_units,
        friendly_buildings,
        enemy_units,
        enemy_buildings,
        all_buildings,
        map_width: int = MAP_WIDTH,
        map_height: int = MAP_HEIGHT,
    ) -> None:
        """
        Main AI loop: assesses, produces, builds, defends, attacks with timed, jittered intervals.

        :param friendly_units: Friendly units.
        :param friendly_buildings: Friendly buildings.
        :param enemy_units: Enemy units.
        :param enemy_buildings: Enemy buildings.
        :param all_buildings: Global buildings.
        :param map_width: Map width.
        :param map_height: Map height.
        """
        # Main AI loop: assesses, produces, builds, defends, attacks with timed, jittered intervals.
        self.assess_situation(
            friendly_units=friendly_units, friendly_buildings=friendly_buildings, enemy_units=enemy_units
        )
        self.action_timer += 1

        # Apply offset and multiplier for desync
        effective_timer = (self.action_timer + self.timer_offset) * self.interval_multiplier

        # Production: Base 60, now varied (e.g., 42-78 frames)
        if int(effective_timer) % int(60 * self.interval_multiplier) == 0:
            barracks_list = [b for b in friendly_buildings if isinstance(b, Barracks) and b.health > 0]
            war_factory_list = [b for b in friendly_buildings if isinstance(b, WarFactory) and b.health > 0]
            hangar_list = [b for b in friendly_buildings if isinstance(b, Hangar) and b.health > 0]
            self.queue_unit_production(barracks_list, war_factory_list, hangar_list, friendly_units)

        # Building: Base 180, now varied (e.g., 126-234 frames)
        if int(effective_timer) % int(180 * self.interval_multiplier) == 0 and self.hq.credits >= 300:
            # Tweak building choice with personality
            if self.personality == "rusher" and self.resource_count == 0:
                cls = Barracks  # Rush military over economy
            elif self.personality == "defensive" and self.turret_count < self.total_buildings // 3:
                cls = Turret
            else:
                if (
                    self.threat_level > 0.4
                    and self.turret_count < min(3, self.total_buildings // 2)
                    and self.hq.credits >= UNIT_CLASSES["Turret"]["cost"]
                ):
                    pos = self.find_build_position(Turret, all_buildings, map_width, map_height)
                    if pos:
                        self.hq.place_building(pos, Turret, all_buildings)
                        return

                if self.resource_count == 0 and self.hq.credits >= UNIT_CLASSES["OilDerrick"]["cost"]:
                    cls = OilDerrick
                elif self.resource_count < 2 and self.hq.credits >= UNIT_CLASSES["Refinery"]["cost"]:
                    built_ref = any(isinstance(b, Refinery) for b in friendly_buildings if b.health > 0)
                    if not built_ref:
                        cls = Refinery
                    else:
                        cls = random.choice([ShaleFracker, BlackMarket])
                elif (
                    self.power_shortage
                    and self.economy_level > 0
                    and self.hq.credits >= UNIT_CLASSES["PowerPlant"]["cost"]
                ):
                    cls = PowerPlant
                elif self.military_prod_count < max(1, self.resource_count // 2 + 1):
                    built_barracks = any(isinstance(b, Barracks) for b in friendly_buildings if b.health > 0)
                    built_factory = any(isinstance(b, WarFactory) for b in friendly_buildings if b.health > 0)
                    built_hangar = any(isinstance(b, Hangar) for b in friendly_buildings if b.health > 0)
                    if not built_barracks:
                        cls = Barracks
                    elif self.resource_count >= 2 and not built_factory:
                        cls = WarFactory
                    elif self.resource_count >= 3 and not built_hangar:
                        cls = Hangar
                    else:
                        cls = random.choice([Barracks, WarFactory, Hangar])
                else:
                    rand = random.random()
                    if rand < 0.4:
                        cls = random.choice([Barracks, WarFactory, Hangar])
                    elif rand < 0.7:
                        cls = random.choice([OilDerrick, Refinery, ShaleFracker, BlackMarket])
                    else:
                        all_possible = [PowerPlant, Turret] + [
                            OilDerrick,
                            Refinery,
                            ShaleFracker,
                            BlackMarket,
                        ]
                        cls = random.choice(all_possible)

            cost = UNIT_CLASSES[cls.__name__]["cost"]
            if self.hq.credits >= cost:
                pos = self.find_build_position(cls, all_buildings, map_width, map_height, prefer_near_hq=True)
                if pos:
                    self.hq.place_building(pos, cls, all_buildings)

        self.defense_timer += 1
        defense_interval = int(240 * self.interval_multiplier)
        threat_threshold = 0.3 * self.aggression_bias  # Aggressive AIs build turrets sooner
        if (
            self.defense_timer > defense_interval
            and self.threat_level > threat_threshold
            and self.turret_count < min(5, self.total_buildings // 3)
            and self.hq.credits >= UNIT_CLASSES["Turret"]["cost"]
        ):
            pos = self.find_build_position(Turret, all_buildings, map_width, map_height, prefer_near_hq=True)
            if pos:
                self.hq.place_building(pos, Turret, all_buildings)
            self.defense_timer = random.randint(0, defense_interval // 2)  # Reset with jitter

        enemy_hq = min(
            (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
            key=lambda b: self.hq.distance_to(b.position),
            default=None,
        )
        self.strategize_attacks(friendly_units, enemy_hq, enemy_buildings, enemy_units)


# =============================================================================
# Group: Production UI Constants
# =============================================================================
# Dataclass for production sidebar UI layout and colors.


@dataclass(kw_only=True)
class ProductionInterface:
    """
    Dataclass for production sidebar UI layout and colors.

    Manages the right-hand UI panel for building/production.
    """

    _BUILDING_PRODUCIBLE_ITEMS: ClassVar = {
        Barracks: ["Infantry", "Grenadier"],
        WarFactory: ["Tank", "MachineGunVehicle", "RocketArtillery"],
        Hangar: ["AttackHelicopter"],
        Headquarters: [
            "Barracks",
            "WarFactory",
            "Hangar",
            "PowerPlant",
            "Turret",
            "OilDerrick",
            "Refinery",
            "ShaleFracker",
            "BlackMarket",
        ],
    }  # Don't move to data for now as it contains class references
    _STR_TO_BUILDING_CLASS: ClassVar = {
        "Barracks": Barracks,
        "WarFactory": WarFactory,
        "Hangar": Hangar,
        "PowerPlant": PowerPlant,
        "Turret": Turret,
        "OilDerrick": OilDerrick,
        "Refinery": Refinery,
        "ShaleFracker": ShaleFracker,
        "BlackMarket": BlackMarket,
    }  # Don't move to data for now as it contains class references

    WIDTH: ClassVar = 200
    MARGIN_X: ClassVar = 20
    CREDITS_POS_Y: ClassVar = 10
    POWER_POS_Y: ClassVar = 35
    TOP_BUTTONS_POS_Y: ClassVar = 60
    TOP_BUTTON_WIDTH: ClassVar = 55
    TOP_BUTTON_HEIGHT: ClassVar = 25
    TOP_BUTTON_SPACING: ClassVar = 5
    PROD_ITEMS_START_Y: ClassVar = 100
    ITEM_HEIGHT: ClassVar = 50
    ITEM_BUTTON_HEIGHT: ClassVar = 40
    PRODUCTION_QUEUE_POS_Y: ClassVar = 300
    BUTTON_SPACING_Y: ClassVar = 10
    BUTTON_RADIUS: ClassVar = 5
    ACTION_BUTTON_HEIGHT: ClassVar = 40
    FILL_COLOR: ClassVar = pg.Color(60, 60, 60)
    LINE_COLOR: ClassVar = pg.Color(100, 100, 100)
    ACTIVE_TAB_COLOR: ClassVar = pg.Color(0, 200, 200)
    INACTIVE_TAB_COLOR: ClassVar = pg.Color(50, 50, 50)
    ACTION_ALLOWED_COLOR: ClassVar = pg.Color(0, 200, 0)
    ACTION_BLOCKED_COLOR: ClassVar = pg.Color(200, 0, 0)
    MAX_PRODUCTION_QUEUE_LENGTH: ClassVar = 5

    _BUTTON_WIDTH = WIDTH - 2 * MARGIN_X

    hq: Headquarters
    all_buildings = None
    surface: pg.Surface = dataclass_field(init=False)
    top_rects: dict = dataclass_field(init=False, default_factory=dict)
    item_rects: dict = dataclass_field(init=False, default_factory=dict)
    placing_cls: type | None = dataclass_field(init=False, default=None)
    producer: Barracks | WarFactory | Hangar | Headquarters = dataclass_field(init=False)
    """Current (selected) producing building. Defaults to HQ."""
    producible_items: list = dataclass_field(default_factory=list)
    """Currently producible items based on `producer` class."""
    production_timer: float | None = dataclass_field(init=False, default=None)

    def __post_init__(self) -> None:
        """
        Post-init: creates surface, top buttons, labels, defaults to HQ producer.
        """
        self.surface = pg.Surface((self.WIDTH, SCREEN_HEIGHT - CONSOLE_HEIGHT))
        self.producer = self.hq
        self._create_top_buttons()
        self.update_producer(self.hq)

    def _create_top_buttons(self) -> None:
        """
        Creates rects for Repair/Sell/Map buttons.
        """
        self.top_rects.clear()
        start_x = self.MARGIN_X
        for i, label in enumerate(["Repair", "Sell", "Map"]):
            x = start_x + i * (self.TOP_BUTTON_WIDTH + self.TOP_BUTTON_SPACING)
            rect = pg.Rect(x, self.TOP_BUTTONS_POS_Y, self.TOP_BUTTON_WIDTH, self.TOP_BUTTON_HEIGHT)
            self.top_rects[label] = rect

    def update_producer(self, building: Unit | None) -> None:
        """
        Updates producible items based on `building`.
        """
        if building is None:
            raise ValueError("Building must be provided.")

        if isinstance(building, (Barracks, WarFactory, Hangar)):
            self.producer = building
        else:
            self.producer = self.hq

        self.producible_items = self._BUILDING_PRODUCIBLE_ITEMS.get(self.producer.__class__, [])

        self.item_rects = {}
        y = self.PROD_ITEMS_START_Y
        for i, item in enumerate(self.producible_items):
            rect = pg.Rect(self.MARGIN_X, y + i * self.ITEM_HEIGHT, self._BUTTON_WIDTH, self.ITEM_BUTTON_HEIGHT)
            self.item_rects[item] = rect

    def draw(self, surface_: pg.Surface) -> None:
        """
        Renders sidebar: credits/power, buttons, queue with progress.

        :param surface_: Main screen surface.
        """
        self.surface.fill(self.FILL_COLOR)
        pg.draw.rect(self.surface, self.LINE_COLOR, self.surface.get_rect(), width=2)

        self.surface.blit(
            FONT_MEDIUM.render(f"Credits: ${self.hq.credits}", True, pg.Color("white")),
            (self.MARGIN_X, self.CREDITS_POS_Y),
        )

        power_color = pg.Color("green") if self.hq.has_enough_power else pg.Color("red")
        self.surface.blit(
            FONT_MEDIUM.render(
                f"Power: {self.hq.power_output}/{self.hq.power_usage}",
                True,
                power_color,
            ),
            (self.MARGIN_X, self.POWER_POS_Y),
        )

        for label, rect in self.top_rects.items():
            color = self.INACTIVE_TAB_COLOR
            pg.draw.rect(self.surface, color, rect, border_radius=self.BUTTON_RADIUS)
            pg.draw.rect(self.surface, self.LINE_COLOR, rect, 1)
            text_surf = FONT_MEDIUM.render(label, True, pg.Color("white"))
            text_rect = text_surf.get_rect(center=rect.center)
            self.surface.blit(text_surf, text_rect)

        for item, rect in self.item_rects.items():
            cost = UNIT_CLASSES[item]["cost"]
            label = UNIT_BUTTON_LABELS.get(item, item)
            can_produce = self.hq.credits >= cost
            color = self.ACTION_ALLOWED_COLOR if can_produce else self.ACTION_BLOCKED_COLOR
            pg.draw.rect(self.surface, color, rect, border_radius=self.BUTTON_RADIUS)
            label_surf = FONT_MEDIUM.render(label, True, pg.Color("white"))
            label_rect = label_surf.get_rect(x=rect.x + 5, y=rect.y + 5)
            self.surface.blit(label_surf, label_rect)
            cost_surf = FONT_MEDIUM.render(f"({cost})", True, pg.Color("white"))
            cost_rect = cost_surf.get_rect(x=rect.x + 5, y=rect.y + 25)
            self.surface.blit(cost_surf, cost_rect)

        if hasattr(self.producer, "production_queue") and self.producer.production_queue:
            queue_y = self.PRODUCTION_QUEUE_POS_Y
            self.surface.blit(
                FONT_MEDIUM.render("Queue:", True, pg.Color("white")),
                (self.MARGIN_X, queue_y),
            )
            queue_y += 20
            for i, item in enumerate(self.producer.production_queue):
                unit_type = item["unit_type"] if "unit_type" in item else item["cls"].__name__
                repeat_text = " [R]" if item["repeat"] else ""
                text = f"{UNIT_BUTTON_LABELS.get(unit_type, unit_type)}{repeat_text}"
                self.surface.blit(
                    FONT_MEDIUM.render(text, True, pg.Color("white")),
                    (self.MARGIN_X + 10, queue_y),
                )
                repeat_rect = pg.Rect(self.MARGIN_X + 150, queue_y, 20, 20)
                repeat_color = self.ACTION_ALLOWED_COLOR if item["repeat"] else self.INACTIVE_TAB_COLOR
                pg.draw.rect(self.surface, repeat_color, repeat_rect, border_radius=2)
                if item["repeat"]:
                    self.surface.blit(
                        FONT_MEDIUM.render("R", True, pg.Color("white")),
                        (repeat_rect.x + 6, repeat_rect.y + 3),
                    )
                if i == 0 and self.producer.production_timer is not None:
                    progress = (
                        1 - (self.producer.production_timer / 90.0)
                        if "Hangar" in str(type(self.producer))
                        else 1 - (self.producer.production_timer / 60.0)
                    )
                    bar_width = 100 * progress
                    pg.draw.rect(
                        self.surface,
                        self.ACTION_ALLOWED_COLOR,
                        (self.MARGIN_X + 10, queue_y + 20, bar_width, 5),
                    )
                    pg.draw.rect(self.surface, self.LINE_COLOR, (self.MARGIN_X + 10, queue_y + 20, 100, 5), 1)
                queue_y += 25

        surface_.blit(self.surface, (SCREEN_WIDTH - self.WIDTH, 0))

    def handle_click(self, screen_pos: Point, own_buildings) -> bool | tuple:
        """
        Handles clicks on buttons: repair, sell, queue items, start placement.

        :param screen_pos: Mouse position.
        :param own_buildings: Player's buildings.
        :return: True if handled, or tuple ('sell', building) for sell action.
        """
        # Handles clicks on buttons: repair, sell, queue items, start placement.
        local_pos = (screen_pos[0] - (SCREEN_WIDTH - self.WIDTH), screen_pos[1])

        for label, rect in self.top_rects.items():
            if rect.collidepoint(local_pos):
                if label == "Repair":
                    if self.producer != self.hq:
                        missing = self.producer.max_health - self.producer.health
                        if missing > 0:
                            cost = missing * 1
                            if self.hq.credits >= cost:
                                self.hq.credits -= cost
                                self.producer.health = self.producer.max_health

                elif label == "Sell":
                    if self.producer != self.hq:
                        return ("sell", self.producer)

                elif label == "Map":
                    pass

                return True

        for item, rect in self.item_rects.items():
            if rect.collidepoint(local_pos):
                cost = UNIT_CLASSES[item]["cost"]
                if self.hq.credits >= cost:
                    if isinstance(self.producer, Headquarters):
                        self.placing_cls = self._STR_TO_BUILDING_CLASS[item]
                    else:
                        if len(self.producer.production_queue) < self.MAX_PRODUCTION_QUEUE_LENGTH:
                            self.producer.production_queue.append({"unit_type": item, "repeat": False})
                            self.hq.credits -= cost
                        return True

                return False

        return False


# =============================================================================
# Group: Game Loop Handlers
# =============================================================================
# Functions for minimap rendering, collision resolution, attack handling, projectile updates, cleanup.
def handle_projectiles(projectiles, all_units, all_buildings, particles, g) -> None:
    """
    Updates projectiles, checks hits on enemies, applies damage/explosions.

    :param projectiles: Projectile group.
    :param all_units: All units.
    :param all_buildings: All buildings.
    :param particles: Particle group.
    :param g: Game data dict.
    """
    # Updates projectiles, checks hits on enemies, applies damage/explosions.
    for projectile in list(projectiles):
        proj_allies = g.alliances[projectile.team]
        enemy_units = [u for u in all_units if u.team not in proj_allies and u.health > 0]
        enemy_buildings = [b for b in all_buildings if b.team not in proj_allies and b.health > 0]

        hit = False
        for e in enemy_units + enemy_buildings:
            if check_collision_2d(e, projectile):
                if e.take_damage(projectile.damage):
                    create_explosion_2d(position=e.position, particles=particles, team=e.team)
                    attacker_hq = g.hqs[projectile.team]
                    if hasattr(e, "hq") and e.hq:
                        if e.is_building:
                            e.hq.game_stats["buildings_lost"] += 1
                            attacker_hq.game_stats["buildings_destroyed"] += 1
                        else:
                            e.hq.game_stats["units_lost"] += 1
                            attacker_hq.game_stats["units_destroyed"] += 1
                    if e in all_units:
                        all_units.remove(e)
                        if isinstance(e, Unit):
                            for team, ug in g.unit_groups.items():
                                if e in ug:
                                    ug.remove(e)
                    elif e in all_buildings:
                        all_buildings.remove(e)
                hit = True
                break
        if hit:
            projectile.kill()


# =============================================================================
# Group: Game Orchestrator
# =============================================================================
# GameManager orchestrates state machine, initializes game data, runs loops.


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

    def _initialize_game(self, game_mode: str, size_name: str, map_name: str, spectator_mode: bool = False) -> None:
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

        player_units = pg.sprite.Group()
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
            for j in range(3):
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
            ai = AI(hqs[team], GameConsole(), build_dir=build_dir, allies=alliances[team])
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
            console=GameConsole(),
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

                elif event.type == pg.KEYDOWN:
                    if event.key == pg.K_ESCAPE:
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

            def update_unit(unit: Unit) -> None:
                unit.update()

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(update_unit, unit) for unit in [u for u in unit_list if not u.is_building]]
                for future in futures:
                    future.result()

            for building in building_list:
                building_team = building.team
                friendly_units_for_build = g.unit_groups.get(building_team, pg.sprite.Group())
                allies = g.alliances[building_team]
                enemy_units_for_build = [u for u in g.global_units if u.team not in allies and u.health > 0]
                enemy_buildings_for_build = [b for b in g.global_buildings if b.team not in allies and b.health > 0]
                building.update(
                    particles=g.particles,
                    friendly_units=friendly_units_for_build,
                    all_units=g.global_units,
                    global_buildings=g.global_buildings,
                    projectiles=g.projectiles,
                    enemy_units=enemy_units_for_build,
                    enemy_buildings=enemy_buildings_for_build,
                )

            g.projectiles.update()
            g.particles.update()

            unit_hash = SpatialHash2d(200)
            for u in unit_list:
                unit_hash.add(u)

            building_hash = SpatialHash2d(200)
            for b in building_list:
                building_hash.add(b)

            handle_unit_collisions(unit_list, unit_hash)
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
                    unit_hash=unit_hash,
                    building_hash=building_hash,
                    alliances=g.alliances,
                )

            handle_projectiles(g.projectiles, unit_list, building_list, g.particles, g)

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
                    friendly_units_list,
                    friendly_buildings_list,
                    enemy_units_list,
                    enemy_buildings_list,
                    g.global_buildings,
                    g.map_width,
                    g.map_height,
                )

            if not g.spectator_mode:
                ally_units = [u for team in g.player_allies for u in g.unit_groups[team].sprites()]
                ally_buildings = [b for b in g.global_buildings if b.team in g.player_allies]
                g.fog_of_war.update_visibility(ally_units, ally_buildings, g.global_buildings)
            else:
                g.fog_of_war.update_visibility([], [], g.global_buildings)

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
                    width, height = UNIT_CLASSES[unit_type]["size"]
                    half_w, half_h = width / 2, height / 2
                    temp_rect = pg.Rect(snapped[0] - half_w, snapped[1] - half_h, width, height)
                    screen_ghost = g.camera.get_screen_rect(temp_rect)
                    color = Palette.PLACEMENT_VALID_COLOR if valid else Palette.PLACEMENT_INVALID_COLOR
                    line_width = int(2 * g.camera.zoom)
                    pg.draw.rect(self.screen, color, screen_ghost, line_width)

                for unit in [u for u in unit_list if not u.is_building]:
                    visible = unit.team in draw_allies or fog.is_visible(unit.position)
                    if unit.health > 0 and visible:
                        unit.draw(self.screen, g.camera, mouse_pos)
            else:
                for unit in [u for u in unit_list if not u.is_building]:
                    if unit.health > 0:
                        unit.draw(self.screen, g.camera)

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

        own_buildings = [b for b in g.global_buildings if b.team == g.player_team]
        result = g.interface.handle_click(mouse_pos, own_buildings)
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
            unit_type = g.interface.placing_cls.__name__
            cost = UNIT_CLASSES[unit_type]["cost"]
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
                        self._initialize_game(game_mode, size_choice, map_choice, spectate)
                        self.state = GameState.PLAYING

                pg.display.flip()
                self.clock.tick(60)

            elif self.state == GameState.PLAYING:
                self._run_game()

            elif self.state in (GameState.VICTORY, GameState.DEFEAT):
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


def main() -> None:
    manager = GameManager()
    manager.run()


if __name__ == "__main__":
    main()
