from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from modules.data_2d import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE
from modules.geometry import snap_to_grid
from modules.unit_stats_2d import get_unit_cost, get_unit_size
from modules.units_2d import (
    Barracks,
    BlackMarket,
    Grenadier,
    Hangar,
    Headquarters,
    Infantry,
    OilDerrick,
    PowerPlant,
    Refinery,
    ShaleFracker,
    Turret,
    WarFactory,
)
from modules.world_2d import is_valid_building_position

if TYPE_CHECKING:
    from modules.team import Team
    from modules.units_2d import Unit2d


class AI:
    """
    AI class manages autonomous decision-making: production, building, scouting, attacking.

    Supports personalities for varied behavior.
    """

    def __init__(self, *, hq, console, build_dir: float = math.pi, allies: frozenset[Team] = frozenset()) -> None:  # noqa: ANN001
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

    def update(
        self,
        friendly_units,  # noqa: ANN001
        friendly_buildings,  # noqa: ANN001
        enemy_units,  # noqa: ANN001
        enemy_buildings,  # noqa: ANN001
        all_buildings,  # noqa: ANN001
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
        self._assess_situation(
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
            self._queue_unit_production(barracks_list, war_factory_list, hangar_list, friendly_units)

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
                    and self.hq.credits >= get_unit_cost("Turret")
                ):
                    pos = self._find_build_position(
                        building_cls=Turret, all_buildings=all_buildings, map_width=map_width, map_height=map_height
                    )
                    if pos:
                        self.hq.place_building(pos, Turret, all_buildings)
                        return

                if self.resource_count == 0 and self.hq.credits >= get_unit_cost("OilDerrick"):
                    cls = OilDerrick
                elif self.resource_count < 2 and self.hq.credits >= get_unit_cost("Refinery"):
                    built_ref = any(isinstance(b, Refinery) for b in friendly_buildings if b.health > 0)
                    cls = Refinery if not built_ref else random.choice([ShaleFracker, BlackMarket])
                elif self.power_shortage and self.economy_level > 0 and self.hq.credits >= get_unit_cost("PowerPlant"):
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
                        all_possible = [
                            PowerPlant,
                            Turret,
                            OilDerrick,
                            Refinery,
                            ShaleFracker,
                            BlackMarket,
                        ]
                        cls = random.choice(all_possible)

            if self.hq.credits >= get_unit_cost(cls.__name__):
                pos = self._find_build_position(
                    building_cls=cls,
                    all_buildings=all_buildings,
                    map_width=map_width,
                    map_height=map_height,
                    prefer_near_hq=True,
                )
                if pos:
                    self.hq.place_building(pos, cls, all_buildings)

        self.defense_timer += 1
        defense_interval = int(240 * self.interval_multiplier)
        threat_threshold = 0.3 * self.aggression_bias  # Aggressive AIs build turrets sooner
        if (
            self.defense_timer > defense_interval
            and self.threat_level > threat_threshold
            and self.turret_count < min(5, self.total_buildings // 3)
            and self.hq.credits >= get_unit_cost("Turret")
        ):
            pos = self._find_build_position(
                building_cls=Turret,
                all_buildings=all_buildings,
                map_width=map_width,
                map_height=map_height,
                prefer_near_hq=True,
            )
            if pos:
                self.hq.place_building(pos, Turret, all_buildings)
            self.defense_timer = random.randint(0, defense_interval // 2)  # Reset with jitter

        enemy_hq = min(
            (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
            key=lambda b: self.hq.distance_to(b.position),
            default=None,
        )
        self._strategize_attacks(friendly_units, enemy_hq, enemy_buildings, enemy_units)

    def _assess_situation(self, *, friendly_units, friendly_buildings, enemy_units) -> None:  # noqa: ANN001
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

        self.resource_buildings = [b for b in friendly_buildings if b.is_resource]
        self.economy_level = min(3, len(self.resource_buildings) // 2)

        self.resource_count = len([b for b in friendly_buildings if b.is_resource and b.health > 0])
        self.turret_count = len([b for b in friendly_buildings if isinstance(b, Turret) and b.health > 0])

        self.military_prod_count = len([b for b in friendly_buildings if b.is_producer and b.health > 0])
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

    def _queue_unit_production(self, barracks_list, war_factory_list, hangar_list, friendly_units) -> None:  # noqa: ANN001
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
                        unit_type_str = random.choices(
                            list(self.production_priorities.keys()),
                            weights=[0.7, 0.2, 0.1, 0, 0, 0],
                        )[0]
                    else:
                        unit_type_str = random.choices(
                            list(self.production_priorities.keys()),
                            weights=list(self.production_priorities.values()),
                        )[0]

                    cost = get_unit_cost(unit_type_str)
                    if self.hq.credits >= cost:
                        barracks.production_queue.append({"unit_type": unit_type_str, "repeat": False})
                        self.hq.credits -= cost
                        if random.random() < 0.4 and unit_type_str == "Infantry" and num_units < 5:
                            barracks.production_queue[-1]["repeat"] = True

            if war_factory_list:
                war_factory = war_factory_list[self.warfactory_index % len(war_factory_list)]
                self.warfactory_index += 1
                if len(war_factory.production_queue) < 3 and self.economy_level > 1:
                    heavy_unit = random.choice(["Tank", "MachineGunVehicle", "RocketArtillery"])
                    cost = get_unit_cost(heavy_unit)
                    if self.hq.credits >= cost and num_units < target_units * 0.8:
                        war_factory.production_queue.append({"unit_type": heavy_unit, "repeat": False})
                        self.hq.credits -= cost

            if hangar_list:
                hangar = hangar_list[self.hangar_index % len(hangar_list)]
                self.hangar_index += 1
                if len(hangar.production_queue) < 2 <= self.economy_level and random.random() < 0.2:
                    hangar.production_queue.append({"unit_type": "AttackHelicopter", "repeat": False})
                    self.hq.credits -= get_unit_cost("AttackHelicopter")

    def _find_build_position(
        self,
        *,
        building_cls: type[
            Barracks | BlackMarket | Hangar | OilDerrick | PowerPlant | Refinery | ShaleFracker | Turret | WarFactory
        ],
        all_buildings,  # noqa: ANN001
        map_width: int,
        map_height: int,
        prefer_near_hq=True,  # noqa: ANN001
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

        _size = get_unit_size(building_cls.__name__)
        half_w, half_h = (_size[0] / 2, _size[1] / 2)
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

    def _strategize_attacks(self, friendly_units, enemy_hq, enemy_buildings=None, enemy_units=None) -> None:  # noqa: ANN001
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

                    elif enemy_hq:
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

                    elif enemy_hq:
                        unit.attack_target = enemy_hq
                        if enemy_hq.is_building:
                            chase_pos = unit.get_chase_position_for_building(enemy_hq)
                            unit.move_target = chase_pos if chase_pos is not None else None
                        else:
                            unit.move_target = enemy_hq.position

                    else:
                        unit.move_target = None

    def _get_nearest_enemy_target(self, enemy_buildings, enemy_units, from_pos) -> Unit2d | None:  # noqa: ANN001
        """
        Prioritizes buildings over units for targeting.

        :param enemy_buildings: List of enemy buildings.
        :param enemy_units: List of enemy units.
        :param from_pos: Position to measure from.
        :return: Nearest target or None.
        """
        # Prioritizes buildings over units for targeting.
        building_target = None
        if enemy_buildings:
            building_target = self._get_nearest_enemy_building(enemy_buildings, from_pos)

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

            return unit_target

        if building_target:
            return building_target

        if unit_target:
            return unit_target

        return None

    @staticmethod
    def _get_nearest_enemy_building(enemy_buildings, from_pos) -> Unit2d | None:  # noqa: ANN001
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

        def weighted_dist(b) -> float:  # noqa: ANN001
            weight = building_weights.get(type(b), 1.0)
            dist = b.distance_to(from_pos)
            return dist / weight

        return min((b for b in enemy_buildings if b.health > 0), key=weighted_dist, default=None)
