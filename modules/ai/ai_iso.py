"""Implements AI for isometric game."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pygame.math import Vector2

from modules.data_iso import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE
from modules.geometry import calculate_formation_positions_iso, snap_to_grid
from modules.unit_stats.unit_stats_iso import get_unit_cost, get_unit_size
from modules.units.units_iso import (
    Barracks,
    Grenadier,
    Hangar,
    Headquarters,
    Infantry,
    PowerPlant,
    Refinery,
    Turret,
    WarFactory,
)
from modules.world_iso import is_valid_building_position

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

    import pygame as pg
    from pygame.typing import Point

    from modules.team import Team
    from modules.units import UnitIso

BuildingType = type(Barracks | Hangar | PowerPlant | Refinery | Turret | WarFactory)


def _get_nearest_enemy_target(
    *, enemy_buildings: Iterable[UnitIso], enemy_units: Iterable[UnitIso], from_pos: Point
) -> UnitIso | None:
    if enemy_buildings:
        building_target = _get_nearest_enemy_building(enemy_buildings=enemy_buildings, from_pos=from_pos)
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

        return unit_target

    if building_target:
        return building_target

    if unit_target:
        return unit_target

    return None


def _get_nearest_enemy_building(*, enemy_buildings: Iterable[UnitIso], from_pos: Point) -> UnitIso | None:
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

    def weighted_dist(b: BuildingType) -> float:
        weight = building_weights.get(type(b), 1.0)
        dist = b.distance_to(from_pos)
        return dist / weight

    return min((b for b in enemy_buildings if b.health > 0), key=weighted_dist, default=None)


@dataclass(kw_only=True)
class AiIso:
    hq: Headquarters
    """Headquarters for the AI."""
    preferred_build_direction: float
    """Preferred build direction angle."""
    allies: frozenset[Team]

    # internal:
    timer_offset = random.randint(0, 180)  # Stagger starts by up to 3 seconds (at 60 FPS)
    interval_multiplier = random.uniform(0.7, 1.3)  # Vary speeds: 70-130% of base intervals
    personality: Literal["AGGRESSIVE", "DEFENSIVE", "BALANCED", "RUSHER"] = random.choice(
        ["AGGRESSIVE", "DEFENSIVE", "BALANCED", "RUSHER"]
    )  # Random trait
    action_timer: int = field(init=False, default=0)
    defense_timer: int = field(init=False, default=0)
    scout_timer: int = field(init=False, default=0)
    attack_timer: int = field(init=False, default=0)
    patrol_timer: int = field(init=False, default=0)
    regroup_timer: int = field(init=False, default=0)

    barracks_index: int = field(init=False, default=0)
    warfactory_index: int = field(init=False, default=0)
    hangar_index: int = field(init=False, default=0)

    build_jitter = random.uniform(0.1, 0.5)  # Extra randomness in build angles (lower = more biased)
    economy_bias: int = field(init=False, default=1)
    threat_level: float = field(init=False, default=0)
    military_strength: int = field(init=False, default=0)
    enemy_strength: int = field(init=False, default=0)
    economy_level: int = field(init=False, default=0)
    known_enemy_pos: Point | None = field(init=False, default=None)
    nearby_enemies: list[UnitIso] = field(init=False, default_factory=list)

    resource_target: int = field(init=False, default=5)
    military_target: int = field(init=False, default=3)
    power_target: int = field(init=False, default=2)
    defense_target: int = field(init=False, default=2)
    expansion_factor: float = field(init=False, default=1.0)
    unit_counts: dict[str, int] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
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
        if self.personality == "RUSHER":
            base_priorities["Infantry"] *= 1.5
            base_priorities["AttackHelicopter"] *= 0.5
        elif self.personality == "DEFENSIVE":
            base_priorities["Grenadier"] *= 1.5
            base_priorities["Tank"] *= 0.5

        self.base_priorities = base_priorities
        self.production_priorities = base_priorities
        self.unit_counts = dict.fromkeys(base_priorities, 0)

    @property
    def aggression_bias(self) -> float:
        return 1.2 if self.personality in ["AGGRESSIVE", "RUSHER"] else 0.8 if self.personality == "DEFENSIVE" else 1.0

    @property
    def formation_spacing_mult(self) -> float:
        return 1.5 if self.personality == "RUSHER" else 0.8 if self.personality == "DEFENSIVE" else 1.0

    def update(
        self,
        *,
        friendly_units: Sequence[UnitIso],
        friendly_buildings: Collection[UnitIso],
        enemy_units: Collection[UnitIso],
        enemy_buildings: Collection[UnitIso],
        all_buildings: pg.sprite.Group[UnitIso],
        map_width: int = MAP_WIDTH,
        map_height: int = MAP_HEIGHT,
    ) -> None:
        self._assess_situation(
            friendly_units=friendly_units,
            friendly_buildings=friendly_buildings,
            enemy_units=enemy_units,
            enemy_buildings=enemy_buildings,
        )
        self.action_timer += 1
        effective_timer = (self.action_timer + self.timer_offset) * self.interval_multiplier

        _live_friendly_buildings = [b for b in friendly_buildings if b.health > 0]
        if int(effective_timer) % int(60 * self.interval_multiplier) == 0:
            barracks_list = [b for b in _live_friendly_buildings if isinstance(b, Barracks)]
            war_factory_list = [b for b in _live_friendly_buildings if isinstance(b, WarFactory)]
            hangar_list = [b for b in _live_friendly_buildings if isinstance(b, Hangar)]
            self._queue_unit_production(
                barracks_seq=barracks_list,
                war_factory_seq=war_factory_list,
                hangar_seq=hangar_list,
                friendly_unit_seq=friendly_units,
            )

        if int(effective_timer) % 120 == 0:
            enemy_hq = min(
                (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
                key=lambda b: self.hq.distance_to(b.position),
                default=None,
            )
            enemy_pos = enemy_hq.position if enemy_hq else self.known_enemy_pos
            self._update_rally_points(
                friendly_buildings=friendly_buildings, enemy_pos=enemy_pos, map_width=map_width, map_height=map_height
            )

        economy_check_interval = int(60 * self.interval_multiplier)
        if int(effective_timer) % economy_check_interval == 0 and self.hq.credits >= 300:
            priorities: list[str] = []
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
                elif built_barracks < self.military_target * 0.4:
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
                    pos = self._find_build_position(
                        building_cls=cls,
                        all_buildings=all_buildings,
                        map_width=map_width,
                        map_height=map_height,
                        prefer_near_hq=prefer_near,
                    )
                    if pos:
                        self.hq.place_building(pos, cls, all_buildings)

        self._build_defenses(all_buildings=all_buildings, map_width=map_width, map_height=map_height)
        enemy_hq = min(
            (b for b in enemy_buildings if isinstance(b, Headquarters) and b.health > 0),
            key=lambda b: self.hq.distance_to(b.position),
            default=None,
        )
        self._strategize_attacks(
            friendly_units=friendly_units,
            enemy_hq=enemy_hq,
            # pyrefly: ignore [bad-argument-type]
            enemy_buildings=enemy_buildings,
            enemy_units=enemy_units,
            map_width=map_width,
            map_height=map_height,
        )

    def _assess_situation(
        self,
        *,
        friendly_units: Iterable[UnitIso],
        friendly_buildings: Iterable[UnitIso],
        enemy_units: Iterable[UnitIso],
        enemy_buildings: Iterable[UnitIso],
    ) -> None:
        _live_friendly_units = [u for u in friendly_units if u.health > 0]
        _live_friendly_buildings = [b for b in friendly_buildings if b.health > 0]
        _live_enemy_units = [u for u in enemy_units if u.health > 0]
        self.military_strength = len(_live_friendly_units)
        self.enemy_strength = len(_live_enemy_units)

        self.nearby_enemies = [u for u in _live_enemy_units if u.distance_to(self.hq.position) < 600]
        self.threat_level = len(self.nearby_enemies) / max(1, self.enemy_strength) if self.enemy_strength > 0 else 0

        _resource_buildings = [b for b in friendly_buildings if isinstance(b, Refinery)]
        # TODO: counts dead buildings - is this intentional?
        self.economy_level = len(_resource_buildings) // 2
        self.resource_count = len([b for b in _live_friendly_buildings if isinstance(b, Refinery)])
        self.turret_count = len([b for b in _live_friendly_buildings if isinstance(b, Turret)])
        self.military_prod_count = len(
            [b for b in _live_friendly_buildings if isinstance(b, Barracks | WarFactory | Hangar)]
        )
        self.power_count = len([b for b in _live_friendly_buildings if isinstance(b, PowerPlant)])
        self.total_buildings = self.military_prod_count + self.resource_count + self.power_count + self.turret_count

        _power_plants = len([b for b in friendly_buildings if isinstance(b, PowerPlant)])
        # TODO: counts dead buildings - is this intentional?
        self.power_shortage = _power_plants < self.economy_level + 1
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
            unit: sum(1 for u in friendly_units if type(u) == unit and u.health > 0) for unit in self.base_priorities
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

    def _queue_unit_production(
        self,
        *,
        barracks_seq: Sequence[Barracks],
        war_factory_seq: Sequence[WarFactory],
        hangar_seq: Sequence[Hangar],
        friendly_unit_seq: Sequence[UnitIso],
    ) -> None:
        _live_friendly_units = [u for u in friendly_unit_seq if u.health > 0]
        num_units = len(_live_friendly_units)
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
            if barracks_seq:
                barracks = barracks_seq[self.barracks_index % len(barracks_seq)]
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

            if war_factory_seq and self.economy_level > 1:
                war_factory = war_factory_seq[self.warfactory_index % len(war_factory_seq)]
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

            if hangar_seq and self.economy_level >= 2:
                hangar = hangar_seq[self.hangar_index % len(hangar_seq)]
                self.hangar_index += 1
                if len(hangar.production_queue) < max_queue_heavy and random.random() < 0.2:
                    unit_type_str = "AttackHelicopter"
                    hangar.production_queue.append({"unit_type": unit_type_str, "repeat": False})
                    self.hq.credits -= get_unit_cost(unit_type_str)

    def _update_rally_points(
        self, *, friendly_buildings: Collection[UnitIso], enemy_pos: Point | None, map_width: int, map_height: int
    ) -> None:
        if enemy_pos is None:
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

    def _build_defenses(self, *, all_buildings: pg.sprite.Group[UnitIso], map_width: int, map_height: int) -> None:
        if (
            self.threat_level > 0.2
            and self.turret_count < self.defense_target
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

    def _find_build_position(
        self,
        *,
        building_cls: BuildingType,
        all_buildings: Iterable[UnitIso],
        map_width: int,
        map_height: int,
        prefer_near_hq: bool = True,
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
        elif building_cls.__name__ == "Refinery":
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

    def _strategize_attacks(
        self,
        *,
        friendly_units: Sequence[UnitIso],
        enemy_hq: Headquarters | None = None,
        enemy_buildings: Sequence[UnitIso],
        enemy_units: Iterable[UnitIso],
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
            self._regroup_idle_units(
                friendly_units=friendly_units,
                focal_point=focal_point,
                num_to_group=num_to_group,
                formation_type=formation_type,
            )
            self.regroup_timer = random.randint(0, regroup_interval // 2)

        self.scout_timer += 1
        scout_interval = int(20 * self.interval_multiplier)
        if self.scout_timer > scout_interval and len(friendly_units) > 1:
            if enemy_hq:
                scout_target = enemy_hq.position
            elif enemy_buildings:
                _from_pos = friendly_units[0].position if friendly_units else (0, 0)
                if _from_pos:
                    _nearest_enemy_building = _get_nearest_enemy_building(
                        enemy_buildings=enemy_buildings, from_pos=_from_pos
                    )
                    if _nearest_enemy_building:
                        scout_target = _nearest_enemy_building.position

            # pyrefly: ignore [unbound-name]
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
                self._send_attack_group(
                    friendly_units=idle_units,
                    enemy_buildings=enemy_buildings,
                    enemy_units=enemy_units,
                    num_to_send=num_to_send,
                    map_width=map_width,
                    map_height=map_height,
                )

            self.attack_timer = random.randint(0, attack_interval // 2)

        push_threshold = 0.5 * self.aggression_bias
        if self.military_strength > self.enemy_strength * push_threshold:
            idle_units = [u for u in friendly_units if u.health > 0 and u.move_target is None]
            if len(idle_units) > 3:
                attack_fraction = (0.9 if self.threat_level > 0.5 else 0.7) * self.aggression_bias
                num_to_send = int(len(idle_units) * attack_fraction)
                self._send_attack_group(
                    friendly_units=idle_units,
                    enemy_buildings=enemy_buildings,
                    enemy_units=enemy_units,
                    num_to_send=num_to_send,
                    map_width=map_width,
                    map_height=map_height,
                )

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

    def _regroup_idle_units(
        self, *, friendly_units: Sequence[UnitIso], focal_point: Point, num_to_group: int, formation_type: str = "line"
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

    def _send_attack_group(
        self,
        *,
        friendly_units: Sequence[UnitIso],
        enemy_buildings: Sequence[UnitIso],
        enemy_units: Iterable[UnitIso],
        num_to_send: int,
        map_width: int,
        map_height: int,
    ) -> None:
        if num_to_send <= 0:
            return

        primary_target = _get_nearest_enemy_target(
            enemy_buildings=enemy_buildings,
            enemy_units=enemy_units,
            from_pos=friendly_units[0].position if friendly_units else (0, 0),
        )
        if not primary_target:
            return

        # pyrefly: ignore [missing-attribute]
        target_center = primary_target.position if not hasattr(primary_target, "rect") else primary_target.rect.center
        total_pos = Vector2(0, 0)
        for u in friendly_units[:num_to_send]:
            total_pos += Vector2(u.position)

        avg_pos = total_pos / num_to_send
        formation_type = "v" if self.personality in ["AGGRESSIVE", "RUSHER"] else "line"
        spacing = 40 * self.formation_spacing_mult
        positions = calculate_formation_positions_iso(
            center=avg_pos, target=target_center, num_units=num_to_send, formation_type=formation_type, spacing=spacing
        )
        positions = [(max(0, min(p[0], map_width)), max(0, min(p[1], map_height))) for p in positions]
        attackers = friendly_units[:num_to_send]
        for unit, pos in zip(attackers, positions):
            unit.attack_target = primary_target
            unit.move_target = pos
