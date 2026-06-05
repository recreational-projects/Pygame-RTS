from __future__ import annotations

import math
import random
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, ClassVar

import pygame as pg
from pygame.math import Vector2

from modules.camera.camera_iso import CameraIso
from modules.data import UNIT_BUTTON_LABELS, Palette
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
from modules.fog_of_war import FogOfWarIso
from modules.fonts import FONT_MEDIUM
from modules.game_console import GameConsole
from modules.game_state import GameState
from modules.geometry import (
    absolute_world_to_iso,
    calculate_formation_positions_iso,
    check_collision,
    get_iso_bounds,
    get_starting_positions,
    snap_to_grid,
)
from modules.particles import create_explosion_iso
from modules.screens import MainMenu, SkirmishSetup, VictoryScreen
from modules.spatial_hash import SpatialHashIso
from modules.team import Team, team_to_color, team_to_name
from modules.terrain_feature_iso import generate_terrain_features
from modules.unit_stats.unit_stats_iso import get_unit_cost, get_unit_size
from modules.units_iso import (
    Barracks,
    Grenadier,
    Hangar,
    Headquarters,
    Infantry,
    PowerPlant,
    Refinery,
    Turret,
    UnitIso,
    WarFactory,
)
from modules.world import handle_unit_building_collisions, handle_unit_collisions
from modules.world_iso import find_free_spawn_position, handle_attacks, is_valid_building_position

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.game_object.game_object_iso import GameObjectIso


class AI:
    def __init__(self, hq, console, build_dir: float = math.pi, allies: frozenset[Team] = frozenset()) -> None:
        self.hq = hq
        self.console = console
        self.allies = allies
        self.action_timer = 0
        self.economy_level = 0
        self.military_strength = 0
        self.enemy_strength = 0
        self.threat_level = 0
        self.scout_timer = 0
        self.defense_timer = 0
        self.attack_timer = 0
        self.patrol_timer = 0
        self.regroup_timer = 0
        self.barracks_index = 0
        self.warfactory_index = 0
        self.hangar_index = 0
        self.known_enemy_pos = None
        self.nearby_enemies = []
        self.personality = random.choice(["aggressive", "defensive", "balanced", "rusher"])
        self.timer_offset = random.randint(0, 180)
        self.interval_multiplier = random.uniform(0.7, 1.3)
        self.build_jitter = random.uniform(0.1, 0.5)
        self.aggression_bias = (
            1.2 if self.personality in ["aggressive", "rusher"] else 0.8 if self.personality == "defensive" else 1.0
        )
        self.economy_bias = 1.0
        base_priorities = {
            "Infantry": 0.6,
            "Grenadier": 0.2,
            "RocketSoldier": 0.1,
            "Marksman": 0.1,
            "Tank": 0.15,
            "HeavyTank": 0.1,
            "TankDestroyer": 0.1,
            "MachineGunVehicle": 0.05,
            "RocketArtillery": 0.05,
            "AttackHelicopter": 0.0,
        }
        if self.personality == "rusher":
            base_priorities["Infantry"] *= 1.5
            base_priorities["AttackHelicopter"] *= 0.5
        elif self.personality == "defensive":
            base_priorities["Grenadier"] *= 1.5
            base_priorities["Tank"] *= 0.5
        self.base_priorities = base_priorities
        self.production_priorities = base_priorities
        self.preferred_build_direction = build_dir
        self.build_bias_strength = 0.3
        self.resource_target = 5
        self.military_target = 3
        self.power_target = 2
        self.defense_target = 2
        self.expansion_factor = 1.0
        self.formation_spacing_mult = (
            1.5 if self.personality == "rusher" else 0.8 if self.personality == "defensive" else 1.0
        )
        self.unit_counts = {unit: 0 for unit in base_priorities.keys()}

    def _send_attack_group(
        self, friendly_units, enemy_buildings, enemy_units, num_to_send: int, map_width: int, map_height: int
    ) -> None:
        if num_to_send <= 0:
            return
        primary_target = self._get_nearest_enemy_target(
            enemy_buildings, enemy_units, friendly_units[0].position if friendly_units else (0, 0)
        )
        if not primary_target:
            return
        target_center = primary_target.position if not hasattr(primary_target, "rect") else primary_target.rect.center
        total_pos = Vector2(0, 0)
        for u in friendly_units[:num_to_send]:
            total_pos += Vector2(u.position)
        avg_pos = total_pos / num_to_send
        formation_type = "v" if self.personality in ["aggressive", "rusher"] else "line"
        spacing = 40 * self.formation_spacing_mult
        positions = calculate_formation_positions_iso(
            center=avg_pos, target=target_center, num_units=num_to_send, formation_type=formation_type, spacing=spacing
        )
        positions = [(max(0, min(p[0], map_width)), max(0, min(p[1], map_height))) for p in positions]
        attackers = friendly_units[:num_to_send]
        for unit, pos in zip(attackers, positions):
            unit.attack_target = primary_target
            unit.move_target = pos

    def regroup_idle_units(
        self, friendly_units, focal_point: Point, num_to_group: int, formation_type: str = "line"
    ) -> None:
        idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None][:num_to_group]
        if len(idle_units) < 2:
            return
        spacing = 30 * self.formation_spacing_mult
        positions = calculate_formation_positions_iso(
            center=focal_point,
            target=focal_point,
            num_units=len(idle_units),
            formation_type=formation_type,
            spacing=spacing,
        )
        for unit, pos in zip(idle_units, positions):
            unit.move_target = pos

    def update_rally_points(self, friendly_buildings, enemy_pos, map_width: int, map_height: int) -> None:
        if not enemy_pos:
            return
        dir_vec = Vector2(enemy_pos) - self.hq.position
        if dir_vec.length() == 0:
            return
        dir_unit = dir_vec.normalize()
        advance = 200 + min(500, self.military_strength * 25)
        target = self.hq.position + dir_unit * advance
        target.x = max(0, min(target.x, map_width))
        target.y = max(0, min(target.y, map_height))
        formation_type = "line" if self.personality == "defensive" else "v"
        positions = calculate_formation_positions_iso(
            center=target, target=target, num_units=len(friendly_buildings), formation_type=formation_type
        )
        for i, b in enumerate([b for b in friendly_buildings if hasattr(b, "rally_point")]):
            if i < len(positions):
                b.rally_point = Vector2(positions[i])
            else:
                b.rally_point = Vector2(target)
            b.rally_point.x = max(0, min(b.rally_point.x, map_width))
            b.rally_point.y = max(0, min(b.rally_point.y, map_height))

    def assess_situation(self, friendly_units, friendly_buildings, enemy_units, enemy_buildings) -> None:
        self.military_strength = len([u for u in friendly_units if u.health > 0])
        self.enemy_strength = len([u for u in enemy_units if u.health > 0])
        hq_pos = self.hq.position
        nearby_enemies = [u for u in enemy_units if u.health > 0 and u.distance_to(hq_pos) < 600]
        self.threat_level = len(nearby_enemies) / max(1, self.enemy_strength) if self.enemy_strength > 0 else 0
        self.nearby_enemies = nearby_enemies
        resource_buildings = [b for b in friendly_buildings if isinstance(b, Refinery)]
        self.economy_level = len(resource_buildings) // 2
        self.resource_count = len([b for b in friendly_buildings if isinstance(b, Refinery) and b.health > 0])
        self.turret_count = len([b for b in friendly_buildings if isinstance(b, Turret) and b.health > 0])
        self.military_prod_count = len(
            [b for b in friendly_buildings if isinstance(b, Barracks | WarFactory | Hangar) and b.health > 0]
        )
        self.power_count = len([b for b in friendly_buildings if isinstance(b, PowerPlant) and b.health > 0])
        self.total_buildings = self.military_prod_count + self.resource_count + self.power_count + self.turret_count
        power_plants = len([b for b in friendly_buildings if isinstance(b, PowerPlant)])
        self.power_shortage = power_plants < self.economy_level + 1
        time_factor = max(1.0, (self.action_timer / 3600) ** 0.5)
        self.expansion_factor = time_factor * (1 + self.economy_bias)
        self.resource_target = max(
            5,
            int(self.total_buildings * 0.3 * self.expansion_factor) + int(self.action_timer / 1200),
        )
        self.military_target = max(3, int(self.resource_count * 1.5 * self.expansion_factor))
        self.power_target = max(2, int((self.resource_target + self.military_target) * 0.4 * self.expansion_factor))
        self.defense_target = max(2, int(self.total_buildings * 0.15 * self.expansion_factor))
        enemy_hq = min(
            (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
            key=lambda b: self.hq.distance_to(b.position),
            default=None,
        )
        if enemy_hq:
            self.known_enemy_pos = enemy_hq.position
        self.unit_counts = {
            unit: sum(1 for u in friendly_units if type(u) == unit and u.health > 0)
            for unit in self.base_priorities.keys()
        }
        total_units = sum(self.unit_counts.values())
        inf_prio = 0.5 if self.threat_level > 0.5 else 0.6
        gren_prio = 0.3 if self.threat_level > 0.5 else 0.2
        rocket_prio = 0.1 if self.economy_level >= 1 else 0.0
        marksman_prio = 0.1 if self.economy_level >= 1 else 0.0
        tank_prio = 0.15 if self.economy_level >= 1 else 0.05
        heavy_tank_prio = 0.1 if self.economy_level >= 2 else 0.0
        tank_destroyer_prio = 0.1 if self.economy_level >= 2 else 0.0
        mgv_prio = 0.05 if self.economy_level >= 2 else 0.0
        rocket_art_prio = 0.05 if self.economy_level >= 2 else 0.0
        heli_prio = 0.1 if self.economy_level >= 2 else 0.0
        ideal_ratios = self.base_priorities.copy()
        total_ideal = sum(ideal_ratios.values())
        for unit in ideal_ratios:
            ideal_count = max(1, total_units * (ideal_ratios[unit] / total_ideal))
            current_count = self.unit_counts[unit]
            balance_factor = min(2.0, max(0.1, ideal_count / max(1, current_count)))
            if unit == "Infantry":
                balance_factor *= 0.7 if current_count > ideal_count * 1.5 else 1.0
            if unit == "Infantry":
                inf_prio *= balance_factor
            elif unit == "Grenadier":
                gren_prio *= balance_factor
            elif unit == "RocketSoldier":
                rocket_prio *= balance_factor
            elif unit == "Marksman":
                marksman_prio *= balance_factor
            elif unit == "Tank":
                tank_prio *= balance_factor
            elif unit == "HeavyTank":
                heavy_tank_prio *= balance_factor
            elif unit == "TankDestroyer":
                tank_destroyer_prio *= balance_factor
            elif unit == "MachineGunVehicle":
                mgv_prio *= balance_factor
            elif unit == "RocketArtillery":
                rocket_art_prio *= balance_factor
            elif unit == "AttackHelicopter":
                heli_prio *= balance_factor
        total_prio = (
            inf_prio
            + gren_prio
            + rocket_prio
            + marksman_prio
            + tank_prio
            + heavy_tank_prio
            + tank_destroyer_prio
            + mgv_prio
            + rocket_art_prio
            + heli_prio
        )
        if total_prio > 0:
            inf_prio /= total_prio
            gren_prio /= total_prio
            rocket_prio /= total_prio
            marksman_prio /= total_prio
            tank_prio /= total_prio
            heavy_tank_prio /= total_prio
            tank_destroyer_prio /= total_prio
            mgv_prio /= total_prio
            rocket_art_prio /= total_prio
            heli_prio /= total_prio
        self.production_priorities = {
            "Infantry": inf_prio,
            "Grenadier": gren_prio,
            "RocketSoldier": rocket_prio,
            "Marksman": marksman_prio,
            "Tank": tank_prio,
            "HeavyTank": heavy_tank_prio,
            "TankDestroyer": tank_destroyer_prio,
            "MachineGunVehicle": mgv_prio,
            "RocketArtillery": rocket_art_prio,
            "AttackHelicopter": heli_prio,
        }

    @staticmethod
    def _get_nearest_enemy_building(enemy_buildings, from_pos):
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
        }

        def weighted_dist(b):
            weight = building_weights.get(type(b), 1.0)
            dist = b.distance_to(from_pos)
            return dist / weight

        return min((b for b in enemy_buildings if b.health > 0), key=weighted_dist, default=None)

    def _get_nearest_enemy_target(self, enemy_buildings, enemy_units, from_pos):
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
        | type[Hangar]
        | type[PowerPlant]
        | type[Refinery]
        | type[Turret]
        | type[WarFactory],
        all_buildings,
        map_width: int,
        map_height: int,
        prefer_near_hq=True,
    ) -> tuple[float, float] | None:
        default_area = 2560 * 1440
        map_area = map_width * map_height
        scale = math.sqrt(map_area / default_area)
        hq_pos = self.hq.position
        _size = get_unit_size(building_cls.__name__)
        half_w, half_h = (_size[0] / 2, _size[1] / 2)
        max_attempts = 2000
        attempts = 0
        if building_cls.__name__ in ["PowerPlant", "Barracks", "WarFactory", "Hangar"]:
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 100, (150 + 50 * scale + 100 * self.economy_level)
        elif building_cls.__name__ in ["Refinery"]:
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 120, (200 + 100 * scale + 150 * self.economy_level)
        elif building_cls.__name__ == "Turret":
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 80, (150 + 30 * scale + 50 * self.economy_level)
        else:
            bias_angle = self.preferred_build_direction
            dist_min, dist_max = 100, (180 + 50 * scale + 100 * self.economy_level)
        if not prefer_near_hq:
            dist_min, dist_max = max(200, dist_min), 400 * scale + 200 * self.economy_level
        ring_step = 25 * scale
        num_samples_per_ring = 25
        angle_jitter = math.pi * self.build_jitter * (1.5 if self.personality == "rusher" else 1.0)
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
                    margin=60,
                ):
                    return position
                attempts += 1
                if attempts > max_attempts:
                    break
            if attempts > max_attempts:
                break
        return None

    def queue_unit_production(self, barracks_list, war_factory_list, hangar_list, friendly_units) -> None:
        num_units = len([u for u in friendly_units if u.health > 0])
        target_units = min(
            200,
            max(
                12,
                int(self.military_strength * 1.1) + int(self.threat_level * 15) + int(self.economy_level * 5),
            ),
        )
        if self.economy_level < 1:
            return
        if num_units < target_units:
            batch_size = min(3, max(1, self.economy_level))
            max_queue_light = batch_size if self.economy_level < 2 else batch_size * 2
            max_queue_heavy = batch_size - 1 if self.economy_level < 2 else batch_size
            if barracks_list:
                barracks = barracks_list[self.barracks_index % len(barracks_list)]
                self.barracks_index += 1
                if len(barracks.production_queue) < max_queue_light:
                    if self.threat_level > 0.5:
                        unit_type_str = random.choices(
                            list(self.production_priorities.keys()),
                            weights=[0.7, 0.2, 0.1, 0.0, 0, 0, 0, 0, 0, 0],
                        )[0]
                    else:
                        unit_type_str = random.choices(
                            list(self.production_priorities.keys()),
                            weights=list(self.production_priorities.values()),
                        )[0]

                    cost = get_unit_cost(unit_type_str)
                    if self.hq.credits >= cost:
                        for _ in range(batch_size):
                            if self.hq.credits < cost or len(barracks.production_queue) >= max_queue_light:
                                break

                            barracks.production_queue.append({"unit_type": unit_type_str, "repeat": False})
                            self.hq.credits -= cost

                        if random.random() < 0.4 and unit_type_str == "Infantry" and num_units < 10:
                            barracks.production_queue[-1]["repeat"] = True

            if war_factory_list and self.economy_level > 1:
                war_factory = war_factory_list[self.warfactory_index % len(war_factory_list)]
                self.warfactory_index += 1
                if len(war_factory.production_queue) < max_queue_heavy:
                    unit_type_str = random.choice(
                        [
                            "Tank",
                            "HeavyTank",
                            "TankDestroyer",
                            "MachineGunVehicle",
                            "RocketArtillery",
                        ]
                    )  # heavy units
                    cost = get_unit_cost(unit_type_str)
                    if self.hq.credits >= cost and num_units < target_units * 0.7:
                        war_factory.production_queue.append({"unit_type": unit_type_str, "repeat": False})
                        self.hq.credits -= cost

            if hangar_list and self.economy_level >= 2:
                hangar = hangar_list[self.hangar_index % len(hangar_list)]
                self.hangar_index += 1
                if len(hangar.production_queue) < max_queue_heavy and random.random() < 0.2:
                    unit_type_str = "AttackHelicopter"
                    hangar.production_queue.append({"unit_type": unit_type_str, "repeat": False})
                    self.hq.credits -= get_unit_cost(unit_type_str)

    def build_defenses(self, all_buildings, map_width: int, map_height: int) -> None:
        if (
            self.threat_level > 0.2
            and self.turret_count < self.defense_target
            and self.hq.credits >= get_unit_cost("Turret")
        ):
            pos = self.find_build_position(Turret, all_buildings, map_width, map_height, prefer_near_hq=True)
            if pos:
                self.hq.place_building(pos, Turret, all_buildings)

    def strategize_attacks(
        self,
        friendly_units,
        enemy_hq,
        enemy_buildings=None,
        enemy_units=None,
        map_width: int = MAP_WIDTH,
        map_height: int = MAP_HEIGHT,
    ) -> None:
        if not enemy_hq and not enemy_buildings and not enemy_units:
            return
        self.defense_timer += 1
        defense_check_interval = 3
        defense_threshold = 0.1
        interrupt_prob = 0.7 if self.threat_level > 0.5 else 0.3
        if (
            self.defense_timer > defense_check_interval
            and self.threat_level > defense_threshold
            and self.nearby_enemies
        ):
            hq_pos = self.hq.position
            nearby_friends = [u for u in friendly_units if u.health > 0 and u.distance_to(hq_pos) < 800]
            if nearby_friends:
                for friend in nearby_friends:
                    should_interrupt = (friend.move_target is None) or (random.random() < interrupt_prob)
                    if should_interrupt:
                        nearest_threat = min(self.nearby_enemies, key=lambda e: friend.distance_to(e.position))
                        friend.attack_target = nearest_threat
                        friend.move_target = nearest_threat.position
                self.defense_timer = random.randint(0, defense_check_interval)
        self.regroup_timer += 1
        regroup_interval = int(30 * self.interval_multiplier)
        if self.regroup_timer > regroup_interval:
            focal_point = self.hq.position
            num_to_group = min(10, len(friendly_units) // 2)
            formation_type = "line" if self.threat_level > 0.5 else "v"
            self.regroup_idle_units(friendly_units, focal_point, num_to_group, formation_type)
            self.regroup_timer = random.randint(0, regroup_interval // 2)
        self.scout_timer += 1
        scout_interval = int(20 * self.interval_multiplier)
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
            scout_tx = max(0, min(scout_target[0] + random.uniform(-200, 200), map_width))
            scout_ty = max(0, min(scout_target[1] + random.uniform(-200, 200), map_height))
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None][:8]
            positions = calculate_formation_positions_iso(
                center=(scout_tx, scout_ty), target=scout_target, num_units=len(idle_units), formation_type="line"
            )
            for scout, pos in zip(idle_units, positions):
                scout.move_target = pos
            self.scout_timer = random.randint(0, scout_interval // 2)
        self.attack_timer += 1
        attack_interval = int(10 * self.interval_multiplier)
        attack_fraction = (0.5 if self.threat_level > 0.5 else 0.4) * self.aggression_bias
        if self.attack_timer > attack_interval:
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None]
            if len(idle_units) > 0:
                num_to_send = max(1, int(len(idle_units) * attack_fraction * random.uniform(0.9, 1.3)))
                self._send_attack_group(idle_units, enemy_buildings, enemy_units, num_to_send, map_width, map_height)
            self.attack_timer = random.randint(0, attack_interval // 2)
        push_threshold = 0.5 * self.aggression_bias
        if self.military_strength > self.enemy_strength * push_threshold:
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None]
            if len(idle_units) > 3:
                attack_fraction = (0.9 if self.threat_level > 0.5 else 0.7) * self.aggression_bias
                num_to_send = int(len(idle_units) * attack_fraction)
                self._send_attack_group(idle_units, enemy_buildings, enemy_units, num_to_send, map_width, map_height)
        self.patrol_timer += 1
        patrol_interval = int(60 * self.interval_multiplier)
        if self.patrol_timer > patrol_interval:
            idle_in_base = [
                u
                for u in friendly_units
                if u.health > 0 and u.move_target is None and u.distance_to(self.hq.position) < 300
            ]
            if idle_in_base:
                num_patrol = min(8, len(idle_in_base))
                patrol_target = enemy_hq.position if enemy_hq else self.known_enemy_pos
                if patrol_target:
                    patrol_tx = max(0, min(patrol_target[0] + random.uniform(-300, 300), map_width))
                    patrol_ty = max(0, min(patrol_target[1] + random.uniform(-300, 300), map_height))
                else:
                    patrol_tx = random.uniform(0, map_width)
                    patrol_ty = random.uniform(0, map_height)
                positions = calculate_formation_positions_iso(
                    center=(patrol_tx, patrol_ty),
                    target=(patrol_tx, patrol_ty),
                    num_units=num_patrol,
                    formation_type="line",
                )
                for unit, pos in zip(idle_in_base[:num_patrol], positions):
                    unit.move_target = pos
            self.patrol_timer = random.randint(0, patrol_interval // 2)

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
        self.assess_situation(friendly_units, friendly_buildings, enemy_units, enemy_buildings)
        self.action_timer += 1
        effective_timer = (self.action_timer + self.timer_offset) * self.interval_multiplier
        if int(effective_timer) % int(60 * self.interval_multiplier) == 0:
            barracks_list = [b for b in friendly_buildings if isinstance(b, Barracks) and b.health > 0]
            war_factory_list = [b for b in friendly_buildings if isinstance(b, WarFactory) and b.health > 0]
            hangar_list = [b for b in friendly_buildings if isinstance(b, Hangar) and b.health > 0]
            self.queue_unit_production(barracks_list, war_factory_list, hangar_list, friendly_units)
        if int(effective_timer) % 120 == 0:
            enemy_hq = min(
                (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
                key=lambda b: self.hq.distance_to(b.position),
                default=None,
            )
            enemy_pos = enemy_hq.position if enemy_hq else self.known_enemy_pos
            self.update_rally_points(friendly_buildings, enemy_pos, map_width, map_height)
        economy_check_interval = int(60 * self.interval_multiplier)
        if int(effective_timer) % economy_check_interval == 0 and self.hq.credits >= 300:
            priorities = []
            if self.resource_count < self.resource_target:
                priorities.append("resource")
            if self.power_count < self.power_target:
                priorities.append("power")
            if self.military_prod_count < self.military_target:
                priorities.append("military")
            if self.turret_count < self.defense_target:
                priorities.append("defense")
            if priorities:
                priority_type = random.choice(priorities)
            else:
                rand = random.random()
                if rand < 0.4:
                    priority_type = "resource"
                elif rand < 0.7:
                    priority_type = "military"
                elif rand < 0.85:
                    priority_type = "power"
                else:
                    priority_type = "defense"
            cls = None
            if priority_type == "resource":
                if len([b for b in friendly_buildings if isinstance(b, Refinery)]) < 2:
                    cls = Refinery
                else:
                    cls = Refinery
            elif priority_type == "power":
                cls = PowerPlant
            elif priority_type == "military":
                built_barracks = len([b for b in friendly_buildings if isinstance(b, Barracks)])
                built_factory = len([b for b in friendly_buildings if isinstance(b, WarFactory)])
                built_hangar = len([b for b in friendly_buildings if isinstance(b, Hangar)])
                if built_barracks < max(2, self.resource_count // 3):
                    cls = Barracks
                elif built_factory < max(1, self.resource_count // 4):
                    cls = WarFactory
                elif built_hangar < max(1, self.resource_count // 5):
                    cls = Hangar
                else:
                    if built_barracks < self.military_target * 0.4:
                        cls = Barracks
                    elif built_factory < self.military_target * 0.3:
                        cls = WarFactory
                    else:
                        cls = Hangar

            elif priority_type == "defense":
                cls = Turret

            if cls:
                cost = get_unit_cost(cls.__name__)
                if self.hq.credits >= cost:
                    prefer_near = random.random() > 0.2 or self.total_buildings < 10
                    pos = self.find_build_position(
                        cls, all_buildings, map_width, map_height, prefer_near_hq=prefer_near
                    )
                    if pos:
                        self.hq.place_building(pos, cls, all_buildings)
        self.build_defenses(all_buildings, map_width, map_height)
        enemy_hq = min(
            (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
            key=lambda b: self.hq.distance_to(b.position),
            default=None,
        )
        self.strategize_attacks(friendly_units, enemy_hq, enemy_buildings, enemy_units, map_width, map_height)


@dataclass(kw_only=True)
class ProductionInterface:
    _BUILDING_PRODUCIBLE_ITEMS: ClassVar = {
        Barracks: ["Infantry", "Grenadier", "RocketSoldier", "Marksman"],
        WarFactory: [
            "Tank",
            "HeavyTank",
            "TankDestroyer",
            "MachineGunVehicle",
            "RocketArtillery",
        ],
        Hangar: ["AttackHelicopter"],
        Headquarters: [
            "Barracks",
            "WarFactory",
            "Hangar",
            "PowerPlant",
            "Turret",
            "Refinery",
        ],
    }  # Don't move to data for now as it contains class references
    _STR_TO_BUILDING_CLASS: ClassVar = {
        "Barracks": Barracks,
        "WarFactory": WarFactory,
        "Hangar": Hangar,
        "PowerPlant": PowerPlant,
        "Turret": Turret,
        "Refinery": Refinery,
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

    def __post_init__(self) -> None:
        self.surface = pg.Surface((self.WIDTH, SCREEN_HEIGHT - CONSOLE_HEIGHT))
        self.producer = self.hq
        self._create_top_buttons()
        self.update_producer(self.hq)

    def _create_top_buttons(self) -> None:
        self.top_rects.clear()
        start_x = self.MARGIN_X
        for i, label in enumerate(["Repair", "Sell", "Map"]):
            x = start_x + i * (self.TOP_BUTTON_WIDTH + self.TOP_BUTTON_SPACING)
            rect = pg.Rect(x, self.TOP_BUTTONS_POS_Y, self.TOP_BUTTON_WIDTH, self.TOP_BUTTON_HEIGHT)
            self.top_rects[label] = rect

    def update_producer(self, building: GameObjectIso) -> None:
        """
        Updates producible items based on `building`.
        """
        if isinstance(building, (Barracks, WarFactory, Hangar)):
            self.producer = building
        else:
            self.producer = self.hq

        self.producible_items = self._BUILDING_PRODUCIBLE_ITEMS[type(building)]

        self.item_rects = {}
        y = self.PROD_ITEMS_START_Y
        for i, item in enumerate(self.producible_items):
            rect = pg.Rect(self.MARGIN_X, y + i * self.ITEM_HEIGHT, self._BUTTON_WIDTH, self.ITEM_BUTTON_HEIGHT)
            self.item_rects[item] = rect

    def draw(self, surface_: pg.Surface, own_buildings, all_buildings) -> None:
        self.surface.fill(self.FILL_COLOR)
        pg.draw.rect(self.surface, self.LINE_COLOR, self.surface.get_rect(), width=2)
        self.surface.blit(
            FONT_MEDIUM.render(f"Credits: ${self.hq.credits}", True, pg.Color("white")),
            (self.MARGIN_X, self.CREDITS_POS_Y),
        )
        power_color = pg.Color("green") if self.hq.has_enough_power else pg.Color("red")
        self.surface.blit(
            FONT_MEDIUM.render(f"Power: {self.hq.power_output}/{self.hq.power_usage}", True, power_color),
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
            cost = get_unit_cost(item)
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
            self.surface.blit(FONT_MEDIUM.render("Queue:", True, pg.Color("white")), (self.MARGIN_X, queue_y))
            queue_y += 20
            for i, item in enumerate(self.producer.production_queue):
                unit_type = item["unit_type"] if "unit_type" in item else item["cls"].__name__
                repeat_text = " [R]" if item["repeat"] else ""
                text = f"{UNIT_BUTTON_LABELS.get(unit_type, unit_type)}{repeat_text}"
                self.surface.blit(FONT_MEDIUM.render(text, True, pg.Color("white")), (self.MARGIN_X + 10, queue_y))
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

    def handle_click(self, screen_pos, own_buildings):
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

                return True

        for item, rect in self.item_rects.items():
            if rect.collidepoint(local_pos):
                cost = get_unit_cost(item)
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


def draw_mini_map(
    screen: pg.Surface,
    camera: CameraIso,
    fog_of_war: FogOfWarIso,
    map_width: int,
    map_height: int,
    map_color: tuple,
    buildings,
    all_units,
    player_allies: set[Team],
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
    base_r, base_g, base_b = map_color
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
            tile_r = base_r
            tile_g = base_g
            tile_b = base_b
            if not fog_of_war.is_visible((tile_center_x, tile_center_y)):
                avg = (tile_r + tile_g + tile_b) // 3
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


def draw_fitness_panel(screen: pg.Surface, g) -> None:
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
    for team in g["teams"]:
        hq = g["hqs"][team]
        if hq.health <= 0:
            continue
        name = team_to_name[team]
        fitness = g["current_fitness"].get(team, 0)
        delta = g["fitness_deltas"].get(team, 0)
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


def handle_projectiles(projectiles, all_units, all_buildings, particles, g) -> None:
    for projectile in list(projectiles):
        proj_allies = g["alliances"][projectile.team]
        enemy_units = [u for u in all_units if u.team not in proj_allies and u.health > 0]
        enemy_buildings = [b for b in all_buildings if b.team not in proj_allies and b.health > 0]
        hit = False
        for e in enemy_units + enemy_buildings:
            if check_collision(entity=e, projectile=projectile):
                if e.take_damage(projectile.damage):
                    create_explosion_iso(position=e.position, particles=particles, team=e.team)
                    attacker_hq = g["hqs"][projectile.team]
                    if hasattr(e, "hq") and e.hq:
                        if e.is_building:
                            e.hq.stats["buildings_lost"] += 1
                            attacker_hq.stats["buildings_destroyed"] += 1
                        else:
                            e.hq.stats["units_lost"] += 1
                            attacker_hq.stats["units_destroyed"] += 1
                    if e in all_units:
                        all_units.remove(e)
                        if isinstance(e, UnitIso):
                            for team, ug in g["unit_groups"].items():
                                if e in ug:
                                    ug.remove(e)
                    elif e in all_buildings:
                        all_buildings.remove(e)
                hit = True
                break
        if hit:
            projectile.kill()


def cleanup_dead_entities(g) -> None:
    for group_name in ["global_units"]:
        group = g[group_name]
        dead = [obj for obj in group if hasattr(obj, "health") and obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()
                d.plasma_burn_particles = []
    for group_name in ["global_buildings"]:
        group = g[group_name]
        dead = [obj for obj in group if hasattr(obj, "health") and obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()
                d.plasma_burn_particles = []
    for team, ug in g["unit_groups"].items():
        dead = [u for u in ug if hasattr(u, "health") and u.health <= 0]
        for d in dead:
            ug.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()
                d.plasma_burn_particles = []


class GameManager:
    def __init__(self, screen, clock) -> None:
        self.screen = screen
        self.clock = clock
        self.state = GameState.MENU

        screen_size_ = self.screen.size
        self.main_menu = MainMenu(screen_size_)
        self.skirmish_setup = SkirmishSetup(screen_size_)
        self.victory_screen = None

        self.game_data = None
        self.running = True

    def initialize_game(self, game_mode, size_name, map_name, spectate: bool = False) -> None:
        map_data = MAPS[map_name]
        base_width = map_data["width"]
        base_height = map_data["height"]
        color = map_data["color"]
        size_scales = {"tiny": 0.80, "small": 0.80, "medium": 0.80, "large": 0.80, "huge": 0.80}
        scale = size_scales[size_name]
        map_width = int(base_width * scale)
        map_height = int(base_height * scale)
        terrain_features = generate_terrain_features(map_name=map_name, map_width=map_width, map_height=map_height)
        num_tx = map_width // TILE_SIZE
        num_ty = map_height // TILE_SIZE
        ownership = [[None] * num_ty for _ in range(num_tx)]

        player_units = pg.sprite.Group()
        ai_units = pg.sprite.Group()
        global_units = pg.sprite.Group()
        global_buildings = pg.sprite.Group()
        projectiles = pg.sprite.Group()
        particles = pg.sprite.Group()
        selected_units = pg.sprite.Group()
        unit_groups = {}
        hqs = {}
        teams_list = []
        player_side = []
        enemy_side = []
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
            hq.map_width = map_width
            hq.map_height = map_height
            hq.stats = {
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
        if not spectate:
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
        enemy_side_set = set(enemy_side)
        for team in teams_list:
            if team in player_side_set:
                alliances[team] = frozenset(player_side)
            else:
                alliances[team] = frozenset(enemy_side)
        if not spectate:
            player_hq = hqs[Team.RED]
            player_team = Team.RED
            player_allies = alliances[player_team]
        else:
            player_hq = None
            player_team = None
            player_allies = set()
        ais = []
        for team in teams_list:
            if not spectate and team == Team.RED:
                continue
            i = teams_list.index(team)
            pos = positions[i]
            center_x = map_width / 2
            center_y = map_height / 2
            build_dir = math.atan2(center_y - pos[1], center_x - pos[0])
            random.seed(team.value * 12345)
            ai = AI(hqs[team], GameConsole(), build_dir=build_dir, allies=alliances[team])
            ais.append(ai)
        camera = CameraIso(map_width=MAP_WIDTH, map_height=MAP_HEIGHT, width=SCREEN_WIDTH, height=SCREEN_HEIGHT)
        if spectate:
            camera.rect.center = (map_width / 2, map_height / 2)
        interface = None
        interface_rect = None
        if not spectate:
            interface = ProductionInterface(hq=player_hq)
            interface_rect = pg.Rect(SCREEN_WIDTH - 200, 0, 200, SCREEN_HEIGHT - CONSOLE_HEIGHT)
        else:
            interface_rect = pg.Rect(0, 0, 0, 0)
        self.game_data = {
            "player_units": player_units,
            "ai_units": ai_units,
            "global_units": global_units,
            "global_buildings": global_buildings,
            "projectiles": projectiles,
            "particles": particles,
            "selected_units": selected_units,
            "unit_groups": unit_groups,
            "hqs": hqs,
            "player_hq": player_hq,
            "player_team": player_team,
            "player_allies": player_allies,
            "alliances": alliances,
            "interface": interface,
            "console": GameConsole(),
            "fog_of_war": FogOfWarIso(
                map_width=map_width, map_height=map_height, tile_size=TILE_SIZE, spectator=spectate
            ),
            "camera": camera,
            "map_color": color,
            "map_width": map_width,
            "map_height": map_height,
            "game_mode": game_mode,
            "selected_building": None,
            "selecting": False,
            "select_start": None,
            "select_rect": None,
            "ais": ais,
            "interface_rect": interface_rect,
            "spectator": spectate,
            "teams": teams_list,
            "terrain_features": terrain_features,
            "previous_fitness": {team: 0 for team in teams_list},
            "current_fitness": {},
            "fitness_deltas": {},
            "tile_ownership": ownership,
            "tile_timer": 0,
            "num_tx": num_tx,
            "num_ty": num_ty,
        }

    def run_game(self) -> None:
        g = self.game_data
        while self.running and self.state == GameState.PLAYING:
            keys = pg.key.get_pressed()
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    self.running = False
                elif event.type == pg.MOUSEWHEEL:
                    mouse_pos = pg.mouse.get_pos()
                    game_rect = pg.Rect(0, 0, g["camera"].width, g["camera"].height)
                    if game_rect.collidepoint(mouse_pos):
                        g["camera"].update_zoom(event.y, mouse_pos)
                elif event.type == pg.MOUSEBUTTONDOWN:
                    mouse_pos = event.pos
                    mini_x = SCREEN_WIDTH - MINI_MAP_WIDTH
                    mini_y = SCREEN_HEIGHT - MINI_MAP_HEIGHT
                    mini_rect = pg.Rect(mini_x, mini_y, MINI_MAP_WIDTH, MINI_MAP_HEIGHT)
                    in_minimap = mini_rect.collidepoint(mouse_pos)
                    if in_minimap and event.button == 1:
                        local_x = mouse_pos[0] - mini_x
                        local_y = mouse_pos[1] - mini_y
                        scale_x = g["map_width"] / MINI_MAP_WIDTH
                        scale_y = g["map_height"] / MINI_MAP_HEIGHT
                        world_x = local_x * scale_x
                        world_y = local_y * scale_y
                        g["camera"].rect.centerx = world_x
                        g["camera"].rect.centery = world_y
                        g["camera"].clamp()
                        if not g.get("spectator", False):
                            for unit in g["player_units"]:
                                unit.selected = False
                            g["selected_units"].empty()
                            if g["selected_building"]:
                                g["selected_building"].selected = False
                            g["selected_building"] = None
                            g["selecting"] = False
                            if g["interface"]:
                                g["interface"].update_producer(g["player_hq"])
                        continue
                    if g.get("spectator", False):
                        continue
                    world_pos = g["camera"].screen_to_world(mouse_pos)
                    world_pos = (
                        max(0, min(world_pos[0], g["map_width"])),
                        max(0, min(world_pos[1], g["map_height"])),
                    )
                    target_x, target_y = mouse_pos
                    if event.button == 1:
                        own_buildings = [b for b in g["global_buildings"] if b.team == g["player_team"]]
                        result = g["interface"].handle_click(mouse_pos, own_buildings)
                        if result:
                            if isinstance(result, tuple) and result[0] == "sell":
                                building_to_sell = result[1]
                                if building_to_sell in g["global_buildings"]:
                                    g["global_buildings"].remove(building_to_sell)
                                    g["player_hq"].credits += building_to_sell.cost // 2
                                    if g["selected_building"] == building_to_sell:
                                        g["selected_building"] = None
                                        g["interface"].update_producer(g["player_hq"])
                            continue
                        if g["interface"].placing_cls is not None and not g["interface_rect"].collidepoint(mouse_pos):
                            snapped = snap_to_grid(pos=world_pos, grid_size=TILE_SIZE)
                            buildings_list = list(g["global_buildings"])
                            unit_type_str = g["interface"].placing_cls.__name__
                            cost = get_unit_cost(unit_type_str)
                            if g["player_hq"].credits >= cost and is_valid_building_position(
                                position=snapped,
                                team=g["player_team"],
                                new_building_cls=g["interface"].placing_cls,
                                buildings=buildings_list,
                                map_width=g["map_width"],
                                map_height=g["map_height"],
                            ):
                                building = g["interface"].placing_cls(snapped, g["player_team"], hq=g["player_hq"])
                                building.map_width = g["map_width"]
                                building.map_height = g["map_height"]
                                g["global_buildings"].add(building)
                                g["player_hq"].credits -= cost
                                g["interface"].placing_cls = None
                            else:
                                g["interface"].placing_cls = None
                            continue
                        clicked_building = next(
                            (
                                b
                                for b in g["global_buildings"]
                                if b.team == g["player_team"]
                                and g["camera"].get_screen_rect(b.rect).collidepoint(target_x, target_y)
                            ),
                            None,
                        )
                        if clicked_building:
                            if g["selected_building"] and g["selected_building"] != clicked_building:
                                g["selected_building"].selected = False
                            clicked_building.selected = True
                            g["selected_building"] = clicked_building
                            for unit in g["player_units"]:
                                unit.selected = False
                            g["selected_units"].empty()
                            g["interface"].update_producer(clicked_building)
                        else:
                            if g["selected_building"]:
                                g["selected_building"].selected = False
                            g["selected_building"] = None
                            g["interface"].update_producer(g["player_hq"])
                            g["selecting"] = True
                            g["select_start"] = mouse_pos
                            g["select_rect"] = pg.Rect(target_x, target_y, 0, 0)
                    elif event.button == 3:
                        if g["interface"].placing_cls is not None:
                            g["interface"].placing_cls = None
                        elif g["selected_building"] and hasattr(g["selected_building"], "rally_point"):
                            g["selected_building"].rally_point = Vector2(world_pos)
                        elif g["selected_units"]:
                            clicked_enemy = None
                            unit_list = list(g["global_units"])
                            building_list = [b for b in g["global_buildings"] if b.health > 0]
                            for u in unit_list:
                                screen_rect = g["camera"].get_screen_rect(u.rect)
                                if (
                                    screen_rect.collidepoint(mouse_pos)
                                    and u.team not in g["player_allies"]
                                    and u.health > 0
                                ):
                                    clicked_enemy = u
                                    break
                            if not clicked_enemy:
                                for b in building_list:
                                    screen_rect = g["camera"].get_screen_rect(b.rect)
                                    if (
                                        screen_rect.collidepoint(mouse_pos)
                                        and b.team not in g["player_allies"]
                                        and b.health > 0
                                    ):
                                        clicked_enemy = b
                                        break
                            if clicked_enemy:
                                for unit in g["selected_units"]:
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
                                    center=world_pos, target=world_pos, num_units=len(g["selected_units"])
                                )
                                for unit, pos in zip(g["selected_units"], formation_positions):
                                    unit.move_target = pos
                                    unit.path = []
                                    unit.attack_target = None
                                    unit.formation_target = pos
                elif event.type == pg.MOUSEMOTION and g["selecting"]:
                    current_pos = event.pos
                    if g["select_start"]:
                        g["select_rect"] = pg.Rect(
                            min(g["select_start"][0], current_pos[0]),
                            min(g["select_start"][1], current_pos[1]),
                            abs(current_pos[0] - g["select_start"][0]),
                            abs(current_pos[1] - g["select_start"][1]),
                        )
                elif event.type == pg.MOUSEBUTTONUP and event.button == 1 and g["selecting"]:
                    g["selecting"] = False
                    for unit in g["player_units"]:
                        unit.selected = False
                    g["selected_units"].empty()
                    if g["selected_building"]:
                        g["selected_building"].selected = False
                    g["selected_building"] = None
                    g["interface"].update_producer(g["player_hq"])
                    if g["select_start"]:
                        world_start = g["camera"].screen_to_world(g["select_start"])
                        world_end = g["camera"].screen_to_world(event.pos)
                        world_rect = pg.Rect(
                            min(world_start[0], world_end[0]),
                            min(world_start[1], world_end[1]),
                            abs(world_end[0] - world_start[0]),
                            abs(world_end[1] - world_start[1]),
                        )
                        for unit in g["player_units"]:
                            if world_rect.colliderect(unit.rect):
                                unit.selected = True
                                g["selected_units"].add(unit)
                elif event.type == pg.KEYDOWN:
                    if event.key == pg.K_ESCAPE:
                        if g["interface"] and g["interface"].placing_cls is not None:
                            g["interface"].placing_cls = None
                        else:
                            self.state = GameState.MENU
                            return
            g["camera"].update(
                g["selected_units"].sprites() if not g.get("spectator", False) else [],
                pg.mouse.get_pos(),
                g["interface_rect"],
                keys,
            )
            unit_list = list(g["global_units"])
            building_list = [b for b in g["global_buildings"] if b.health > 0]
            for unit in [u for u in unit_list if not u.is_building]:
                unit.update(
                    global_buildings=list(g["global_buildings"]), projectiles=g["projectiles"], particles=g["particles"]
                )

            for building in building_list:
                building_team = building.team
                friendly_units_for_build = g["unit_groups"].get(building_team, pg.sprite.Group())
                allies = g["alliances"][building_team]
                enemy_units_for_build = [
                    u for u in g["global_units"].sprites() if u.team not in allies and u.health > 0
                ]
                enemy_buildings_for_build = [
                    b for b in g["global_buildings"].sprites() if b.team not in allies and b.health > 0
                ]
                building.update(
                    particles=g["particles"],
                    friendly_units=friendly_units_for_build,
                    all_units=g["global_units"],
                    global_buildings=g["global_buildings"],
                    projectiles=g["projectiles"],
                )

            g["projectiles"].update()
            g["particles"].update()
            unit_hash = SpatialHashIso(250)
            for u in unit_list:
                unit_hash.add(u)
            building_hash = SpatialHashIso(250)
            for b in building_list:
                building_hash.add(b)
            handle_unit_collisions(all_units=unit_list, unit_hash=unit_hash)
            handle_unit_building_collisions(all_units=unit_list, building_hash=building_hash)
            for unit in unit_list:
                unit.rect.center = unit.position
            unique_teams = set(g["teams"])
            for team in unique_teams:
                handle_attacks(
                    team=team,
                    all_units=unit_list,
                    all_buildings=building_list,
                    projectiles=g["projectiles"],
                    particles=g["particles"],
                    unit_hash=unit_hash,
                    building_hash=building_hash,
                    alliances=g["alliances"],
                )
            handle_projectiles(g["projectiles"], unit_list, building_list, g["particles"], g)
            cleanup_dead_entities(g)
            g["tile_timer"] += 1
            if g["tile_timer"] >= 60:
                g["tile_timer"] = 0
                alive_hqs_pos = {team: hq.position for team, hq in g["hqs"].items() if hq.health > 0}
                if alive_hqs_pos:
                    for tx in range(g["num_tx"]):
                        tile_x = tx * TILE_SIZE + TILE_SIZE / 2
                        for ty in range(g["num_ty"]):
                            tile_y = ty * TILE_SIZE + TILE_SIZE / 2
                            min_dist = float("inf")
                            nearest_team = None
                            for team, pos in alive_hqs_pos.items():
                                dist = math.hypot(tile_x - pos.x, tile_y - pos.y)
                                if dist < min_dist:
                                    min_dist = dist
                                    nearest_team = team
                            g["tile_ownership"][tx][ty] = nearest_team
                    for team, hq in g["hqs"].items():
                        if hq.health > 0:
                            count = sum(
                                1
                                for tx in range(g["num_tx"])
                                for ty in range(g["num_ty"])
                                if g["tile_ownership"][tx][ty] == team
                            )
                            income = count * 0.050
                            hq.credits += income
                            if "credits_earned" in hq.stats:
                                hq.stats["credits_earned"] += income
            for ai in g["ais"]:
                their_team = ai.hq.team
                friendly_units_list = g["unit_groups"][their_team].sprites()
                friendly_buildings_list = [b for b in building_list if b.team == their_team]
                enemy_units_list = [
                    u
                    for team, ug in g["unit_groups"].items()
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
                    g["global_buildings"],
                    g["map_width"],
                    g["map_height"],
                )
            if "previous_fitness" not in g:
                g["previous_fitness"] = {team: 0 for team in g["teams"]}
            g["current_fitness"] = {}
            g["fitness_deltas"] = {}
            for team in g["teams"]:
                hq = g["hqs"][team]
                if hq.health > 0:
                    stats = hq.stats
                    fitness = (
                        stats.get("units_destroyed", 0) * 10
                        + stats.get("buildings_destroyed", 0) * 20
                        - stats.get("units_lost", 0) * 5
                        - stats.get("buildings_lost", 0) * 10
                        + stats.get("credits_earned", 0) // 50
                    )
                    g["current_fitness"][team] = fitness
                    prev = g["previous_fitness"].get(team, 0)
                    delta = fitness - prev
                    g["fitness_deltas"][team] = delta
                    g["previous_fitness"][team] = fitness
            if not g.get("spectator", False):
                ally_units = [u for team in g["player_allies"] for u in g["unit_groups"][team].sprites()]
                ally_buildings = [b for b in g["global_buildings"].sprites() if b.team in g["player_allies"]]
                g["fog_of_war"].update_visibility(ally_units, ally_buildings, g["global_buildings"].sprites())
            else:
                g["fog_of_war"].update_visibility([], [], g["global_buildings"].sprites())
            alive_hqs = [hq for hq in g["hqs"].values() if hq.health > 0]
            all_stats = {team_to_name[team]: hq.stats for team, hq in g["hqs"].items()}
            if g["player_hq"] and g["player_hq"].health <= 0:
                self.state = GameState.DEFEAT
                self.victory_screen = VictoryScreen(
                    is_victory=False,
                    all_stats=all_stats,
                    player_team=g["player_team"],
                    screen_size=self.screen.size,
                )
            elif len(alive_hqs) <= 1:
                if len(alive_hqs) == 0:
                    is_player_victory = None if g.get("spectator", False) else False
                    self.state = GameState.VICTORY if g.get("spectator", False) else GameState.DEFEAT
                else:
                    last_hq = alive_hqs[0]
                    if g.get("spectator", False):
                        is_player_victory = None
                    else:
                        is_player_victory = last_hq == g["player_hq"]
                    self.state = GameState.VICTORY if is_player_victory else GameState.DEFEAT

                self.victory_screen = VictoryScreen(
                    is_victory=is_player_victory,
                    all_stats=all_stats,
                    player_team=g.get("player_team"),
                    screen_size=self.screen.size,
                )
            self.screen.fill(pg.Color("black"))
            map_color = g["map_color"]
            base_r, base_g, base_b = map_color
            zoom = g["camera"].zoom
            min_wx, max_wx, min_wy, max_wy = g["camera"].get_render_bounds()
            num_tx = g["map_width"] // TILE_SIZE
            num_ty = g["map_height"] // TILE_SIZE
            start_tx = max(0, int(min_wx // TILE_SIZE))
            start_ty = max(0, int(min_wy // TILE_SIZE))
            end_tx = min(num_tx, int(max_wx // TILE_SIZE) + 2)
            end_ty = min(num_ty, int(max_wy // TILE_SIZE) + 2)
            for tx in range(start_tx, end_tx):
                wx = tx * TILE_SIZE
                for ty in range(start_ty, end_ty):
                    wy = ty * TILE_SIZE
                    tile_r = base_r
                    tile_g = base_g
                    tile_b = base_b
                    c1 = (wx, wy)
                    c2 = (wx + TILE_SIZE, wy)
                    c3 = (wx + TILE_SIZE, wy + TILE_SIZE)
                    c4 = (wx, wy + TILE_SIZE)
                    iso1 = g["camera"].world_to_iso(c1, zoom)
                    iso2 = g["camera"].world_to_iso(c2, zoom)
                    iso3 = g["camera"].world_to_iso(c3, zoom)
                    iso4 = g["camera"].world_to_iso(c4, zoom)
                    pg.draw.polygon(self.screen, (tile_r, tile_g, tile_b), [iso1, iso2, iso3, iso4])
            for feature in g["terrain_features"]:
                if g["fog_of_war"].is_visible(feature.position):
                    feature.draw(surface=self.screen, camera=g["camera"])

            draw_allies = set(g["teams"]) if g.get("spectator", False) else g["player_allies"]
            fog = g["fog_of_war"]
            if not g.get("spectator", False):
                g["fog_of_war"].draw(self.screen, g["camera"])
            mouse_pos = pg.mouse.get_pos() if g.get("interface") else None
            for building in building_list:
                visible = building.team in draw_allies or fog.is_visible(building.position) or building.is_seen
                if building.health > 0 and visible:
                    building.draw(surface=self.screen, camera=g["camera"], mouse_pos=mouse_pos)

            if g["interface"] and not g.get("spectator", False):
                if g["interface"].placing_cls is not None:
                    mouse_pos = pg.mouse.get_pos()
                    ghost_pos = g["camera"].screen_to_world(mouse_pos)
                    snapped = snap_to_grid(pos=ghost_pos, grid_size=TILE_SIZE)
                    buildings_list = list(g["global_buildings"])
                    unit_type = g["interface"].placing_cls.__name__
                    valid = is_valid_building_position(
                        position=snapped,
                        team=g["player_team"],
                        new_building_cls=g["interface"].placing_cls,
                        buildings=buildings_list,
                        map_width=g["map_width"],
                        map_height=g["map_height"],
                    )
                    width, height = get_unit_size(unit_type)
                    half_w, half_h = width / 2, height / 2
                    temp_rect = pg.Rect(snapped[0] - half_w, snapped[1] - half_h, width, height)
                    screen_ghost = g["camera"].get_screen_rect(temp_rect)
                    color = Palette.PLACEMENT_VALID_COLOR if valid else Palette.PLACEMENT_INVALID_COLOR
                    line_width = int(2 * g["camera"].zoom)
                    pg.draw.rect(self.screen, color, screen_ghost, line_width)
                for unit in [u for u in unit_list if not u.is_building]:
                    visible = unit.team in draw_allies or fog.is_visible(unit.position)
                    if unit.health > 0 and visible:
                        unit.draw(surface=self.screen, camera=g["camera"], mouse_pos=mouse_pos)
            else:
                for unit in [u for u in unit_list if not u.is_building]:
                    if unit.health > 0:
                        unit.draw(surface=self.screen, camera=g["camera"])

            for projectile in g["projectiles"]:
                projectile.draw(self.screen, g["camera"])
            for particle in g["particles"]:
                particle.draw_iso(self.screen, g["camera"])

            if g["interface"] and not g.get("spectator", False):
                g["interface"].draw(
                    self.screen,
                    [b for b in g["global_buildings"] if b.team == g["player_team"]],
                    g["global_buildings"],
                )
            if not g.get("spectator", False) and g["selecting"] and g["select_rect"]:
                pg.draw.rect(self.screen, (255, 255, 255), g["select_rect"], 2)
            draw_allies_mini = set(g["teams"]) if g.get("spectator", False) else g["player_allies"]
            mini_rect = draw_mini_map(
                self.screen,
                g["camera"],
                g["fog_of_war"],
                g["map_width"],
                g["map_height"],
                g["map_color"],
                g["global_buildings"],
                g["global_units"],
                draw_allies_mini,
            )
            draw_fitness_panel(self.screen, g)
            pg.display.flip()
            self.clock.tick(60)

    def run(self) -> None:
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
                        self.skirmish_setup = SkirmishSetup(self.screen.size)

                    elif result and result[0] == "start_game":
                        _, game_mode, size_choice, map_choice, spectate = result
                        self.initialize_game(game_mode, size_choice, map_choice, spectate)
                        self.state = GameState.PLAYING
                pg.display.flip()
                self.clock.tick(60)
            elif self.state == GameState.PLAYING:
                self.run_game()
            elif self.state in (GameState.VICTORY, GameState.DEFEAT):
                self.victory_screen.update(pg.mouse.get_pos())
                self.victory_screen.draw(self.screen)
                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False
                    result = self.victory_screen.handle_event(event)
                    if result == "menu":
                        self.state = GameState.MENU
                        self.skirmish_setup = SkirmishSetup(self.screen.size)

                pg.display.flip()
                self.clock.tick(60)
        pg.quit()


def main() -> None:
    # Entry point: initializes Pygame, creates manager, runs game.
    pg.init()
    pg.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pg.display.set_caption("Paper Tigers")
    clock = pg.time.Clock()
    manager = GameManager(screen, clock)
    manager.run()


if __name__ == "__main__":
    main()
