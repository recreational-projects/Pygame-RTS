from __future__ import annotations

import math
import random
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

from src.barracks import Barracks
from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
)
from src.geometry import (
    Coordinate,
    is_valid_building_position,
    snap_to_grid,
)
from src.harvester import Harvester
from src.headquarters import Headquarters
from src.infantry import Infantry
from src.power_plant import PowerPlant
from src.tank import Tank
from src.turret import Turret
from src.war_factory import WarFactory

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import pygame as pg

    from src.building import Building
    from src.game_object import GameObject
    from src.iron_field import IronField


@dataclass(kw_only=True)
class AI:
    DESIRED_UNIT_RATIO = {"harvester": 4, "infantry": 6, "tank": 3, "turret": 3}
    SCALE_FACTOR = 1.8
    ACTION_INTERVAL = 50
    MAX_WAVE_SIZE = 25
    SCOUT_INTERVAL = 200
    THREAT_RANGE = 500
    """THREATENED state allowed if any enemy unit is within this distance."""

    hq: Headquarters
    timer: int = dataclass_field(init=False, default=0)
    wave_timer: int = dataclass_field(init=False, default=0)
    wave_interval: int = dataclass_field(init=False)
    wave_number: int = dataclass_field(init=False, default=0)
    state: Literal["AGGRESSIVE", "ATTACKED", "BROKE", "BUILD_UP", "THREATENED"] = (
        dataclass_field(init=False, default="BUILD_UP")
    )
    defense_cooldown: int = dataclass_field(init=False, default=0)
    scout_targets: list[Coordinate] = dataclass_field(init=False, default_factory=list)
    iron_income_rate: float = dataclass_field(init=False, default=0)
    last_scout_update: int = dataclass_field(init=False, default=0)
    surprise_attack_cooldown: int = dataclass_field(init=False, default=0)

    def __post_init__(self) -> None:
        self.wave_interval = random.randint(150, 250)

    @staticmethod
    def _enemy_unit_counts(
        *, enemy_units: Iterable[GameObject], enemy_buildings: Iterable[Building]
    ) -> dict[str, int]:
        return {
            "harvester": len([u for u in enemy_units if isinstance(u, Harvester)]),
            "tank": len([u for u in enemy_units if isinstance(u, Tank)]),
            "infantry": len([u for u in enemy_units if isinstance(u, Infantry)]),
            "turret": len([b for b in enemy_buildings if isinstance(b, Turret)]),
        }

    def determine_state(
        self,
        *,
        friendly_units: Iterable[GameObject],
        enemy_units: Sequence[GameObject],
        enemy_buildings: Sequence[Building],
    ) -> None:
        player_base_size = len(enemy_units) + len(enemy_buildings)
        self.iron_income_rate = (
            sum(h.iron for h in friendly_units if isinstance(h, Harvester))
            / max(1, len([h for h in friendly_units if isinstance(h, Harvester)]))
            * 60
            / 40
        )
        self.state = (
            "BROKE"
            if self.hq.iron < 300 or self.iron_income_rate < 50
            else "ATTACKED"
            if self.hq.health < self.hq.max_health * 0.6 or self.defense_cooldown > 0
            else "THREATENED"
            if any(
                u.distance_to(self.hq.position) < AI.THREAT_RANGE for u in enemy_units
            )
            else "AGGRESSIVE"
            if self.wave_number >= 2 or player_base_size > 8
            else "BUILD_UP"
        )

    def update_scouting(
        self,
        *,
        friendly_units: Iterable[GameObject],
        enemy_buildings: Iterable[Building],
        iron_fields: Iterable[IronField],
    ) -> None:
        if self.last_scout_update <= 0:
            if not self.scout_targets:
                self.scout_targets = [f.position for f in iron_fields]
                self.scout_targets.append(Coordinate(MAP_WIDTH // 2, MAP_HEIGHT // 2))
                gdi_hq = next(
                    (b for b in enemy_buildings if isinstance(b, Headquarters)),
                    None,
                )
                if gdi_hq:
                    self.scout_targets.append(gdi_hq.position)

            for scout in [
                u for u in friendly_units if isinstance(u, Infantry) and not u.target
            ][:3]:
                if self.scout_targets:
                    scout.target = self.scout_targets.pop(0)
                    scout.target_unit = None

            self.last_scout_update = AI.SCOUT_INTERVAL

        else:
            self.last_scout_update -= 1

    @staticmethod
    def determine_priority_target(
        *,
        unit: Infantry | Tank,
        enemy_units: Iterable[GameObject],
        enemy_buildings: Iterable[Building],
    ) -> Building | GameObject | None:
        """Return a target object for `unit`, or None."""
        targets = []
        for enemy_unit in enemy_units:
            if enemy_unit.health > 0:
                dist = unit.distance_to(enemy_unit.position)
                priority = (
                    3
                    if isinstance(enemy_unit, Harvester)
                    else 2.5
                    if isinstance(enemy_unit, Headquarters)
                    else 2
                    if isinstance(enemy_unit, Turret)
                    else 1.5
                    if enemy_unit.health / enemy_unit.max_health < 0.3
                    else 1
                )
                targets.append((enemy_unit, dist, priority))

        for enemy_building in enemy_buildings:
            if enemy_building.health > 0:
                dist = unit.distance_to(enemy_building.position)
                priority = (
                    2.5
                    if isinstance(enemy_building, Headquarters)
                    else 2
                    if isinstance(enemy_building, Turret)
                    else 1
                )
                targets.append((enemy_building, dist, priority))

        targets.sort(key=lambda x: x[1] / x[2])
        return targets[0][0] if targets and targets[0][1] < 250 else None

    def find_valid_building_position(
        self,
        *,
        building_cls: type[Building],
        friendly_buildings: Iterable[Building],
        enemy_buildings: Iterable[Building],
        iron_fields: Iterable[IronField],
    ) -> Coordinate:
        closest_field = min(
            iron_fields,
            key=lambda f: self.hq.distance_to(f.position),
            default=None,
        )
        for building in friendly_buildings:
            if building.health > 0:
                for angle in range(0, 360, 20):
                    pos = building.position + (
                        math.cos(math.radians(angle)) * 120,
                        math.sin(math.radians(angle)) * 120,
                    )
                    snapped_pos = snap_to_grid(pos)
                    if is_valid_building_position(
                        position=snapped_pos,
                        team=self.hq.team,
                        new_building_cls=building_cls,
                        buildings=list(friendly_buildings) + list(enemy_buildings),
                    ):
                        if (
                            closest_field
                            and snapped_pos.distance_to(closest_field.position) < 600
                        ):
                            return snapped_pos

                        if not closest_field:
                            return snapped_pos

        return snap_to_grid(self.hq.position)

    def _produce_obj(self, cls: type[GameObject]) -> None:
        self.hq.production_queue.append(cls)
        self.hq.iron -= cls.COST
        logger.debug(
            f"AI produced {cls.__name__}, cost: {cls.COST}, new iron: {self.hq.iron}"
        )

    def produce_objs(
        self,
        *,
        friendly_units: Iterable[GameObject],
        friendly_buildings: Iterable[Building],
        enemy_unit_counts: dict[str, int],
        enemy_buildings: Iterable[Building],
        iron_fields: Iterable[IronField],
        all_buildings: pg.sprite.Group[Any],
    ) -> None:
        current_units = {
            "harvester": len([u for u in friendly_units if isinstance(u, Harvester)]),
            "infantry": len([u for u in friendly_units if isinstance(u, Infantry)]),
            "tank": len([u for u in friendly_units if isinstance(u, Tank)]),
            "turret": len([b for b in friendly_buildings if isinstance(b, Turret)]),
            "power_plant": len(
                [b for b in friendly_buildings if isinstance(b, PowerPlant)]
            ),
            "barracks": len(
                [
                    b
                    for b in friendly_buildings
                    if isinstance(b, Barracks) and b.health > 0
                ]
            )
            + len([b for b in self.hq.production_queue if b == Barracks]),
            "war_factory": len(
                [
                    b
                    for b in friendly_buildings
                    if isinstance(b, WarFactory) and b.health > 0
                ]
            )
            + len([b for b in self.hq.production_queue if b == WarFactory]),
        }
        desired_units = {
            obj_cls: int(ratio * AI.SCALE_FACTOR)
            for obj_cls, ratio in AI.DESIRED_UNIT_RATIO.items()
        }
        desired_units["power_plant"] = max(1, (current_units["harvester"] + 1) // 2)
        desired_units["barracks"] = 1
        desired_units["war_factory"] = 1
        has_barracks = current_units["barracks"] > 0
        has_warfactory = current_units["war_factory"] > 0
        total_military = (
            current_units["infantry"] + current_units["tank"] + current_units["turret"]
        )
        iron = self.hq.iron
        logger.debug(
            f"AI production check: Iron = {iron}, Has Barracks = {has_barracks}, Has WarFactory = {has_warfactory}"
        )

        if not has_barracks and iron >= Barracks.COST:
            self._produce_obj(Barracks)
            return

        if not has_warfactory and iron >= WarFactory.COST:
            self._produce_obj(WarFactory)
            return

        if (
            self.hq.has_enough_power
            and iron >= PowerPlant.COST
            and current_units["power_plant"] < desired_units["power_plant"]
        ):
            self._produce_obj(PowerPlant)
            return

        if (
            (
                current_units["harvester"]
                < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
                or self.iron_income_rate < 50
            )
            and iron >= Harvester.COST
            and has_warfactory
        ):
            self._produce_obj(Harvester)
            return

        if iron <= 0:
            logger.debug("AI production halted: Insufficient iron")
            return

        production_options: list[type[GameObject]] = []
        if self.state in ["Build Up", "Aggressive"]:
            if (
                total_military < 6
                and has_barracks
                and iron >= Infantry.COST
                and current_units["infantry"] < desired_units["infantry"]
            ):
                production_options.append(Infantry)
            if (
                total_military < 6
                and has_warfactory
                and iron >= Tank.COST
                and current_units["tank"] < desired_units["tank"]
            ):
                production_options.append(Tank)
            if (
                iron >= Turret.COST
                and current_units["turret"] < desired_units["turret"]
            ):
                production_options.append(Turret)
            if (
                has_barracks
                and iron >= Infantry.COST
                and current_units["infantry"] < desired_units["infantry"]
            ):
                production_options.append(Infantry)
            if (
                has_warfactory
                and iron >= Tank.COST
                and current_units["tank"] < desired_units["tank"]
            ):
                production_options.append(Tank)
            if (
                current_units["harvester"] < desired_units["harvester"]
                and iron >= Harvester.COST
                and has_warfactory
            ):
                production_options.append(Harvester)
            if (
                current_units["power_plant"] < desired_units["power_plant"]
                and iron >= PowerPlant.COST
            ):
                production_options.append(PowerPlant)
            if (
                current_units["barracks"] < 2
                and iron >= Barracks.COST
                and total_military >= 6
            ):
                production_options.append(Barracks)
            if (
                current_units["war_factory"] < 2
                and iron >= WarFactory.COST
                and total_military >= 6
            ):
                production_options.append(WarFactory)
            if iron >= Headquarters.COST and current_units["harvester"] >= 2:
                production_options.append(Headquarters)

            if production_options:
                self._produce_obj(random.choice(production_options))

        elif self.state in ["Attacked", "Threatened"]:
            if (
                iron >= Turret.COST
                and current_units["turret"] < desired_units["turret"]
            ):
                production_options.append(Turret)
            if (
                has_warfactory
                and iron >= Tank.COST
                and current_units["tank"] < desired_units["tank"]
            ):
                production_options.append(Tank)
            if (
                has_barracks
                and iron >= Infantry.COST
                and current_units["infantry"] < desired_units["infantry"]
            ):
                production_options.append(Infantry)
            if (
                current_units["harvester"]
                < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
                and iron >= Harvester.COST
                and has_warfactory
            ):
                production_options.append(Harvester)

            if (
                current_units["power_plant"] < desired_units["power_plant"]
                and iron >= PowerPlant.COST
            ):
                production_options.append(PowerPlant)

            if production_options:
                self._produce_obj(random.choice(production_options))

        elif (
            self.state == "BROKE"
            and has_warfactory
            and iron >= Harvester.COST
            and current_units["harvester"]
            < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
        ):
            self._produce_obj(Harvester)

        if self.hq.production_queue and not self.hq.production_timer:
            self.hq.production_timer = self.hq.get_production_time(
                unit_class=self.hq.production_queue[0],
                friendly_buildings=friendly_buildings,
            )
        if self.hq.pending_building and not self.hq.pending_building_pos:
            pos = self.find_valid_building_position(
                building_cls=self.hq.pending_building,
                friendly_buildings=friendly_buildings,
                enemy_buildings=enemy_buildings,
                iron_fields=iron_fields,
            )
            self.hq.pending_building_pos = pos
            self.hq.place_building(
                position=pos,
                unit_cls=self.hq.pending_building,
                all_buildings=all_buildings,
            )

    def coordinate_attack(
        self,
        *,
        friendly_units: Iterable[GameObject],
        enemy_units: Iterable[GameObject],
        enemy_buildings: Iterable[Building],
        surprise: bool = False,
    ) -> None:
        self.wave_timer = 0
        self.wave_number += 1
        wave_size = (
            min(12 + self.wave_number, AI.MAX_WAVE_SIZE)
            if surprise
            else min(8 + self.wave_number * 2, AI.MAX_WAVE_SIZE)
        )
        self.wave_interval = random.randint(150, 250)
        combat_units = [
            u
            for u in friendly_units
            if isinstance(u, (Tank, Infantry)) and not u.target
        ]
        if not combat_units:
            return
        tactics = (
            ["balanced", "flank", "all_in"]
            if self.state == "AGGRESSIVE" or surprise
            else ["all_in", "defensive"]
            if self.state in ["THREATENED", "ATTACKED"]
            else ["balanced", "flank", "all_in"]
        )
        tactic = random.choice(tactics)
        if tactic == "balanced":
            infantry_count = min(
                int(wave_size * 0.6),
                len([u for u in combat_units if isinstance(u, Infantry)]),
            )
            tank_count = min(
                int(wave_size * 0.4),
                len([u for u in combat_units if isinstance(u, Tank)]),
            )
            attack_units = [u for u in combat_units if isinstance(u, Infantry)][
                :infantry_count
            ] + [u for u in combat_units if isinstance(u, Tank)][:tank_count]
            if attack_units:
                target = self.determine_priority_target(
                    unit=attack_units[0],
                    enemy_units=enemy_units,
                    enemy_buildings=enemy_buildings,
                )
                if target:
                    for unit in attack_units:
                        unit.target_unit = target
                        unit.target = target.position + (
                            random.uniform(-20, 20),
                            random.uniform(-20, 20),
                        )

        elif tactic == "flank":
            attack_units = combat_units[:wave_size]
            gdi_hq = next(
                (b for b in enemy_buildings if isinstance(b, Headquarters)),
                None,
            )
            if gdi_hq:
                group_size = len(attack_units) // 2
                for i, unit in enumerate(attack_units):
                    offset_x = (
                        random.uniform(80, 120)
                        if i < group_size
                        else random.uniform(-120, -80)
                    )
                    offset_y = (
                        random.uniform(80, 120)
                        if i < group_size
                        else random.uniform(-120, -80)
                    )
                    unit.target = gdi_hq.position + (offset_x, offset_y)
                    unit.target_unit = gdi_hq

        elif tactic == "all_in":
            attack_units = combat_units[:wave_size]
            if attack_units:
                target = self.determine_priority_target(
                    unit=attack_units[0],
                    enemy_units=enemy_units,
                    enemy_buildings=enemy_buildings,
                )
                if target:
                    for unit in attack_units:
                        unit.target_unit = target
                        unit.target = target.position + (
                            random.uniform(-20, 20),
                            random.uniform(-20, 20),
                        )

        elif tactic == "defensive":
            attack_units = combat_units[:wave_size]
            for unit in attack_units:
                unit.target = self.hq.position + (
                    random.uniform(-50, 50),
                    random.uniform(-50, 50),
                )
                unit.target_unit = None

    def update(
        self,
        *,
        friendly_units: Iterable[GameObject],
        friendly_buildings: Iterable[Building],
        enemy_units: Sequence[GameObject],
        enemy_buildings: Sequence[Building],
        iron_fields: Iterable[IronField],
        all_buildings: pg.sprite.Group[Any],
    ) -> None:
        player_unit_counts = self._enemy_unit_counts(
            enemy_units=enemy_units, enemy_buildings=enemy_buildings
        )
        self.timer += 1
        self.wave_timer += 1
        self.surprise_attack_cooldown = max(0, self.surprise_attack_cooldown - 1)
        self.determine_state(
            friendly_units=friendly_units,
            enemy_units=enemy_units,
            enemy_buildings=enemy_buildings,
        )
        self.update_scouting(
            friendly_units=friendly_units,
            enemy_buildings=enemy_buildings,
            iron_fields=iron_fields,
        )
        if self.timer >= self.ACTION_INTERVAL:
            self.timer = 0
            self.produce_objs(
                friendly_units=friendly_units,
                friendly_buildings=friendly_buildings,
                enemy_unit_counts=player_unit_counts,
                enemy_buildings=enemy_buildings,
                iron_fields=iron_fields,
                all_buildings=all_buildings,
            )
        if (
            self.surprise_attack_cooldown <= 0
            and player_unit_counts["tank"]
            + player_unit_counts["infantry"]
            + player_unit_counts["turret"]
            < 5
            and random.random() < 0.1
        ):
            self.coordinate_attack(
                friendly_units=friendly_units,
                enemy_units=enemy_units,
                enemy_buildings=enemy_buildings,
                surprise=True,
            )
            self.surprise_attack_cooldown = 300

        elif self.wave_timer >= self.wave_interval:
            self.coordinate_attack(
                friendly_units=friendly_units,
                enemy_units=enemy_units,
                enemy_buildings=enemy_buildings,
            )
