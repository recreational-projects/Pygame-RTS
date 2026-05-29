from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import pygame as pg
from pygame.math import Vector2

from modules.draw_2d import BUILDING_DRAW_RECIPES, COMPLEX_DRAW_RECIPES, SIMPLE_DRAW_RECIPES
from modules.game_object.game_object_2d import GameObject2d
from modules.geometry import closest_point_on_rect
from modules.particles import create_explosion_2d
from modules.projectile_2d import Projectile
from modules.team import Team, team_to_color
from modules.unit_stats.unit_stats_2d import UnitStats2d
from modules.world_2d import is_valid_building_position

if TYPE_CHECKING:
    from collections.abc import MutableSet

    from pygame.sprite import Group
    from pygame.typing import Point

    from modules.camera.camera_2d import Camera2d
    from modules.unit_stats.unit_stats import WeaponStats


class Unit2d(GameObject2d):
    """
    Subclass for mobile/producing entities (units and buildings).

    Extends GameObject with movement, combat, production, income.
    """

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        """
        Unit base: loads stats from UNIT_CLASSES, sets up drawing, handles production/income if applicable.

        :param position: Initial position.
        :param team: Team enum.
        :param hq: Optional Headquarters reference.
        """
        super().__init__(position=position, team=team)
        self.hq: Headquarters | None = hq
        self.current_weapon_index = 0
        self.attack_target: Unit2d | None = None
        self.last_shot_time = 0
        self.move_target: Point | None = None
        self.formation_target: Point | None = None

        self._stats = UnitStats2d.from_data(self.__class__.__name__)  # read-only
        self.health = self._stats.hp
        self.max_health = self._stats.hp
        self.size = self._stats.size
        self.cost = self._stats.cost
        self.attack_range = self._stats.attack_range
        self.sight_range = self._stats.sight_range
        self.speed = self._stats.speed
        self.producible_items = self._stats.producible
        self.weapons = self._stats.weapons
        self.income = self._stats.income
        self.income_interval = self._stats.income_interval

        if self.is_resource:
            self.collection_timer = 0

        self.body_angle: float = 0
        self.player_ordered = False

        if self.is_producer:
            self.rally_point = Vector2(position[0] + 80, position[1])
            self.production_queue = []
            self.production_timer: int | None = None
            self.gate_open = False
            self.gate_timer = 0

        if not self.image:  # TODO: type guard - not sure why needed
            raise TypeError("Unit has no `image`")

        self.rect = self.image.get_rect(center=position)
        # Modular drawing setup
        self._setup_drawing()

    def _setup_drawing(self) -> None:
        """Sets up image or complex draw method based on type."""

        unit_type_str = self.__class__.__name__
        if unit_type_str in SIMPLE_DRAW_RECIPES:
            self.image = SIMPLE_DRAW_RECIPES[unit_type_str](self.size, team_to_color[self.team])

        if not self.image:  # TODO: type guard - not sure why needed
            raise TypeError("Unit has no `image`")

        if unit_type_str in ["Infantry", "Grenadier"]:
            self.needs_rotation = True

        elif unit_type_str in COMPLEX_DRAW_RECIPES:
            create_surfaces, draw_func = COMPLEX_DRAW_RECIPES[unit_type_str]
            self.body_surf, self.turret_surf, self.barrel_surf = create_surfaces(self.team)
            self.draw = draw_func.__get__(self, self.__class__)

        elif self.is_building and unit_type_str in BUILDING_DRAW_RECIPES:
            self.image = BUILDING_DRAW_RECIPES[unit_type_str](self.size, self.team)

        else:
            # Fallback
            self.image.fill(team_to_color[self.team])

        if not self.image:  # TODO: type guard
            raise TypeError("Unit has no `image`")

        self.rect = self.image.get_rect(center=self.position)

    @property
    def is_building(self) -> bool:
        return self._stats.is_building

    @property
    def is_air(self) -> bool:
        return self._stats.is_air

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
    def current_weapon(self) -> WeaponStats:
        return self.weapons[self.current_weapon_index]

    @property
    def is_producer(self) -> bool:
        return bool(self.producible_items)

    @property
    def is_resource(self) -> bool:
        return self.income is not None

    @property
    def turret_offset(self) -> Vector2:
        return Vector2(self._stats.turret_offset)

    @property
    def barrel_offset(self) -> Vector2:
        return Vector2(self._stats.barrel_offset)

    def update(
        self, *, friendly_units: MutableSet[Unit2d] | None = None, all_units: MutableSet[Unit2d] | None = None
    ) -> None:
        """
        Core update: handles attack targeting, movement, shooting, production, income, particle cleanup.

        :param friendly_units: Friendly unit group.
        :param all_units: Global unit group.
        """
        self.under_attack_timer = max(0, self.under_attack_timer - 1)
        self.under_attack = self.under_attack_timer > 0

        if self.last_shot_time > 0:
            self.last_shot_time -= 1

        # Clear invalid attack target
        if self.attack_target and (
            self.attack_target.health <= 0 or self.distance_to(self.attack_target.position) > self.sight_range
        ):
            if self.move_target == self.attack_target.position:
                self.move_target = None

            self.attack_target = None

        if not self.is_building and self.attack_target and self.attack_target.health > 0:
            if self.attack_target.is_building:
                # pyrefly: ignore [bad-argument-type]
                closest = closest_point_on_rect(rect=self.attack_target.rect, pos=self.position)
                dir_to_closest = Vector2(closest) - self.position
                dist = dir_to_closest.length()
            else:
                dist = self.distance_to(self.attack_target.position)
            if self.attack_target.is_building:
                # pyrefly: ignore [bad-argument-type]
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
                    # Restore move_target after combat if needed, but for now,
                    # stay stopped until enemy dead or out of sight

            # Chase the target
            elif self.attack_target.is_building:
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

        if self.is_producer and friendly_units is not None and all_units is not None:
            self._update_production(friendly_units, all_units)

        if self.is_resource:
            self.collection_timer += 1
            if self.collection_timer >= self.income_interval:
                income = self.income
                if not self.hq:
                    raise ValueError("Unit has no `hq`")

                # pyrefly: ignore [unsupported-operation]
                self.hq.credits += income
                # pyrefly: ignore [unsupported-operation]
                self.hq.game_stats["credits_earned"] += income
                self.collection_timer = 0

        if not isinstance(self.rect, pg.Rect):
            raise TypeError("Unit has unexpected `rect` type")

        self.rect.center = self.position
        self.plasma_burn_particles = [p for p in self.plasma_burn_particles if p.alive()]

    def get_chase_position_for_building(self, target_building: Unit2d) -> Vector2 | None:
        """
        Computes the position to move to so that the distance to the closest edge of the building
        is exactly attack_range.

        :param target_building: Target building.
        :return: Chase position or None if already in range.
        """
        # pyrefly: ignore [bad-argument-type]
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

    def _update_production(self, friendly_units: MutableSet[Unit2d], all_units: MutableSet[Unit2d]) -> None:
        """
        Advances production queue, spawns units at gate, opens gate animation.

        :param friendly_units: Group to add new units to.
        :param all_units: Global group to add new units to.
        """
        if self.gate_open:
            self.gate_timer -= 1
            if self.gate_timer <= 0:
                self.gate_open = False

        if self.production_queue:
            if self.production_timer is None:
                self.production_timer = self.production_time

            # pyrefly: ignore [unsupported-operation]
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

    def draw(self, surface: pg.Surface, camera: Camera2d, mouse_pos: Point | None = None) -> None:
        """
        Overridden draw for units: handles air height, rotation, rally point, gate animation.

        :param surface: Surface to draw on.
        :param camera: Camera2d for transformation.
        :param mouse_pos: Mouse position for hover.
        """
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

        # pyrefly: ignore [missing-attribute]
        scaled_size = (int(self.image.get_width() * zoom), int(self.image.get_height() * zoom))
        if scaled_size[0] > 0 and scaled_size[1] > 0:
            # pyrefly: ignore [bad-argument-type]
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

    def shoot(self, target: Unit2d, projectiles: pg.sprite.Group[Projectile]) -> None:
        """
        Fires a projectile using current weapon at target, with lead prediction.

        Triggers small explosion.

        :param target: Target entity.
        :param projectiles: Group to add projectile to.
        """
        if self.last_shot_time > 0:
            return

        if target.is_building:
            # pyrefly: ignore [bad-argument-type]
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
        create_explosion_2d(self.position, pg.sprite.Group(), self.team, 3)


# Subclasses now lean, relying on base Unit for drawing setup
class Infantry(Unit2d):
    """Infantry unit class."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Tank(Unit2d):
    """Tank unit class."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Grenadier(Unit2d):
    """Grenadier unit class."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class MachineGunVehicle(Unit2d):
    """Machine Gun Vehicle unit class."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class RocketArtillery(Unit2d):
    """Rocket Artillery unit class."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class AttackHelicopter(Unit2d):
    """Attack Helicopter unit class."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Headquarters(Unit2d):
    """Headquarters building: main base with credits, power management, building placement."""

    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        # HQ-specific: starts with credits, manages power, building placement queue.
        self.credits = self._stats.starting_credits
        self.power_output = 100
        self.power_usage = 50
        self.has_enough_power = True
        self.production_queue: list[dict[str, Any]] = []
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

    def place_building(self, position: Point, unit_cls: type, all_buildings: Group[Unit2d]) -> None:
        """
        Instantiates and places a building if valid, deducts cost.

        :param position: Placement position.
        :param unit_cls: Building class.
        :param all_buildings: Global building group.
        """
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


class Barracks(Unit2d):
    """Barracks building: produces infantry units."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.parent_hq = None


class WarFactory(Unit2d):
    """War Factory building: produces ground vehicles."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.parent_hq = None


class Hangar(Unit2d):
    """Hangar building: produces air units."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.parent_hq = None


class PowerPlant(Unit2d):
    """Power Plant building: provides power."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class OilDerrick(Unit2d):
    """Oil Derrick building: generates income from oil."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Refinery(Unit2d):
    """Refinery building: processes oil for income."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.radius = 60


class ShaleFracker(Unit2d):
    """Shale Fracker building: extracts shale for income."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class BlackMarket(Unit2d):
    """Black Market building: illicit income source."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Turret(Unit2d):
    """Defensive turret building: auto-fires on enemies."""

    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
