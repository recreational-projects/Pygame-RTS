from __future__ import annotations

import math
import random
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Literal

from loguru import logger

from src import geometry
from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
)
from src.game_objects.buildings.barracks import Barracks
from src.game_objects.buildings.headquarters import Headquarters
from src.game_objects.buildings.power_plant import PowerPlant
from src.game_objects.buildings.turret import Turret
from src.game_objects.buildings.war_factory import WarFactory
from src.game_objects.units.harvester import Harvester
from src.game_objects.units.infantry import Infantry
from src.game_objects.units.tank import Tank
from src.geometry import Coordinate

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.game import Game
    from src.game_objects.buildings.building import Building
    from src.game_objects.game_object import GameObject
    from src.iron_field import IronField
    from src.team import Team


@dataclass(kw_only=True)
class AI:
    DESIRED_UNIT_RATIO = {"harvester": 4, "infantry": 6, "tank": 3, "turret": 3}
    SCALE_FACTOR = 1.8
    ACTION_INTERVAL = 50
    MAX_WAVE_SIZE = 25
    SCOUT_INTERVAL = 200
    THREAT_RANGE = 500
    """THREATENED state allowed if any enemy unit is within this distance."""

    team: Team
    opposing_team: Team
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

    def _determine_state(
        self,
        *,
        friendly_units: Iterable[GameObject],
        enemy_units: Iterable[GameObject],
        enemy_buildings_count: int,
    ) -> None:
        _player_base_size = len(list(enemy_units)) + enemy_buildings_count
        self.iron_income_rate = (
            sum(h.iron for h in friendly_units if isinstance(h, Harvester))
            / max(1, len([h for h in friendly_units if isinstance(h, Harvester)]))
            * 60
            / 40
        )
        previous_state = self.state
        self.state = (
            "BROKE"
            if self.team.iron < 300 or self.iron_income_rate < 50
            else "ATTACKED"
            if self.hq.health < self.hq.max_health * 0.6 or self.defense_cooldown > 0
            else "THREATENED"
            if any(
                u.distance_to(self.hq.position) < AI.THREAT_RANGE for u in enemy_units
            )
            else "AGGRESSIVE"
            if self.wave_number >= 2 or _player_base_size > 8
            else "BUILD_UP"
        )
        if self.state != previous_state:
            logger.debug(f"AI state {previous_state} -> {self.state}")

    def _update_scouting(
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
                    scout.target_object = None

            self.last_scout_update = AI.SCOUT_INTERVAL

        else:
            self.last_scout_update -= 1

    @staticmethod
    def _determine_priority_target(
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

    def _find_valid_building_position(
        self,
        *,
        building_cls: type[Building],
        game: Game,
        friendly_buildings: Iterable[Building],
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
                    snapped_pos = geometry.snap_to_grid(pos)
                    if game.is_valid_building_position(
                        position=snapped_pos,
                        new_building_class=building_cls,
                        team=self.hq.team,
                    ):
                        if (
                            closest_field
                            and snapped_pos.distance_to(closest_field.position) < 600
                        ):
                            return snapped_pos

                        if not closest_field:
                            return snapped_pos

        return geometry.snap_to_grid(self.hq.position)

    def _buy_object(self, cls: type[GameObject]) -> None:
        self.hq.production_queue.append(cls)
        previous_iron = self.team.iron
        self.team.iron -= cls.COST
        logger.debug(
            f"AI bought {cls.__name__}; iron {previous_iron} -> {self.team.iron}"
        )

    def _buy_objects(
        self,
        *,
        friendly_units: Iterable[GameObject],
        friendly_buildings: Iterable[Building],
        enemy_unit_counts: dict[str, int],
        iron_fields: Iterable[IronField],
        game: Game,
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
        if not has_barracks and self.team.iron >= Barracks.COST:
            self._buy_object(Barracks)
            return

        if not has_warfactory and self.team.iron >= WarFactory.COST:
            self._buy_object(WarFactory)
            return

        if (
            self.hq.has_enough_power
            and self.team.iron >= PowerPlant.COST
            and current_units["power_plant"] < desired_units["power_plant"]
        ):
            self._buy_object(PowerPlant)
            return

        if (
            (
                current_units["harvester"]
                < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
                or self.iron_income_rate < 50
            )
            and self.team.iron >= Harvester.COST
            and has_warfactory
        ):
            self._buy_object(Harvester)
            return

        if self.team.iron <= 0:
            logger.debug(f"AI can't buy. Iron: ({self.team.iron})")
            return

        production_options: list[type[GameObject]] = []
        if self.state in ["BUILD UP", "AGGRESSIVE"]:
            if (
                total_military < 6
                and has_barracks
                and self.team.iron >= Infantry.COST
                and current_units["infantry"] < desired_units["infantry"]
            ):
                production_options.append(Infantry)
            if (
                total_military < 6
                and has_warfactory
                and self.team.iron >= Tank.COST
                and current_units["tank"] < desired_units["tank"]
            ):
                production_options.append(Tank)
            if (
                self.team.iron >= Turret.COST
                and current_units["turret"] < desired_units["turret"]
            ):
                production_options.append(Turret)
            if (
                has_barracks
                and self.team.iron >= Infantry.COST
                and current_units["infantry"] < desired_units["infantry"]
            ):
                production_options.append(Infantry)
            if (
                has_warfactory
                and self.team.iron >= Tank.COST
                and current_units["tank"] < desired_units["tank"]
            ):
                production_options.append(Tank)
            if (
                current_units["harvester"] < desired_units["harvester"]
                and self.team.iron >= Harvester.COST
                and has_warfactory
            ):
                production_options.append(Harvester)
            if (
                current_units["power_plant"] < desired_units["power_plant"]
                and self.team.iron >= PowerPlant.COST
            ):
                production_options.append(PowerPlant)
            if (
                current_units["barracks"] < 2
                and self.team.iron >= Barracks.COST
                and total_military >= 6
            ):
                production_options.append(Barracks)
            if (
                current_units["war_factory"] < 2
                and self.team.iron >= WarFactory.COST
                and total_military >= 6
            ):
                production_options.append(WarFactory)
            if self.team.iron >= Headquarters.COST and current_units["harvester"] >= 2:
                production_options.append(Headquarters)

            if production_options:
                self._buy_object(random.choice(production_options))

        elif self.state in ["ATTACKED", "THREATENED"]:
            if (
                self.team.iron >= Turret.COST
                and current_units["turret"] < desired_units["turret"]
            ):
                production_options.append(Turret)
            if (
                has_warfactory
                and self.team.iron >= Tank.COST
                and current_units["tank"] < desired_units["tank"]
            ):
                production_options.append(Tank)
            if (
                has_barracks
                and self.team.iron >= Infantry.COST
                and current_units["infantry"] < desired_units["infantry"]
            ):
                production_options.append(Infantry)
            if (
                current_units["harvester"]
                < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
                and self.team.iron >= Harvester.COST
                and has_warfactory
            ):
                production_options.append(Harvester)

            if (
                current_units["power_plant"] < desired_units["power_plant"]
                and self.team.iron >= PowerPlant.COST
            ):
                production_options.append(PowerPlant)

            if production_options:
                self._buy_object(random.choice(production_options))

        elif (
            self.state == "BROKE"
            and has_warfactory
            and self.team.iron >= Harvester.COST
            and current_units["harvester"]
            < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
        ):
            self._buy_object(Harvester)

        if self.hq.production_queue and not self.hq.production_timer:
            self.hq.production_timer = game.get_production_time(
                cls=self.hq.production_queue[0],
                team=self.team,
            )
        if self.hq.pending_building_class and not self.hq.pending_building_pos:
            self.hq.pending_building_pos = self._find_valid_building_position(
                building_cls=self.hq.pending_building_class,
                game=game,
                friendly_buildings=friendly_buildings,
                iron_fields=iron_fields,
            )
            self.hq.place_building(
                position=self.hq.pending_building_pos,
                unit_cls=self.hq.pending_building_class,
                game=game,
            )

    def _coordinate_attack(
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
                target = self._determine_priority_target(
                    unit=attack_units[0],
                    enemy_units=enemy_units,
                    enemy_buildings=enemy_buildings,
                )
                if target:
                    for unit in attack_units:
                        unit.target_object = target
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
                    unit.target_object = gdi_hq

        elif tactic == "all_in":
            attack_units = combat_units[:wave_size]
            if attack_units:
                target = self._determine_priority_target(
                    unit=attack_units[0],
                    enemy_units=enemy_units,
                    enemy_buildings=enemy_buildings,
                )
                if target:
                    for unit in attack_units:
                        unit.target_object = target
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
                unit.target_object = None

    def update(self, *, game: Game, iron_fields: Iterable[IronField]) -> None:
        _friendly_units = game.team_units(self.team)
        _friendly_buildings = game.team_buildings(self.team)
        _enemy_units = game.team_units(self.opposing_team)
        _enemy_buildings = game.team_buildings(self.opposing_team)
        enemy_unit_counts = self._enemy_unit_counts(
            enemy_units=_enemy_units, enemy_buildings=_enemy_buildings
        )
        self.timer += 1
        self.wave_timer += 1
        self.surprise_attack_cooldown = max(0, self.surprise_attack_cooldown - 1)
        self._determine_state(
            friendly_units=_friendly_units,
            enemy_units=_enemy_units,
            enemy_buildings_count=len(_enemy_buildings),
        )
        self._update_scouting(
            friendly_units=_friendly_units,
            enemy_buildings=_enemy_buildings,
            iron_fields=iron_fields,
        )
        if self.timer >= self.ACTION_INTERVAL:
            self.timer = 0
            self._buy_objects(
                friendly_units=_friendly_units,
                friendly_buildings=_friendly_buildings,
                enemy_unit_counts=enemy_unit_counts,
                iron_fields=iron_fields,
                game=game,
            )
        if (
            self.surprise_attack_cooldown <= 0
            and enemy_unit_counts["tank"]
            + enemy_unit_counts["infantry"]
            + enemy_unit_counts["turret"]
            < 5
            and random.random() < 0.1
        ):
            self._coordinate_attack(
                friendly_units=_friendly_units,
                enemy_units=_enemy_units,
                enemy_buildings=_enemy_buildings,
                surprise=True,
            )
            self.surprise_attack_cooldown = 300

        elif self.wave_timer >= self.wave_interval:
            self._coordinate_attack(
                friendly_units=_friendly_units,
                enemy_units=_enemy_units,
                enemy_buildings=_enemy_buildings,
            )
