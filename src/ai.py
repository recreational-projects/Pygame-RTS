from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Literal

from src.barracks import Barracks
from src.constants import (
    MAP_HEIGHT,
    MAP_WIDTH,
    Team,
)
from src.geometry import (
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
    from src.game_console import GameConsole
    from src.game_object import GameObject
    from src.geometry import Coordinate
    from src.iron_field import IronField


@dataclass(kw_only=True)
class Friendlies:
    """Data container for own team's objects."""

    units: Iterable[GameObject]
    harvesters: set[Harvester] = dataclass_field(init=False, default_factory=set)
    infantry: set[Infantry] = dataclass_field(init=False, default_factory=set)
    tanks: set[Tank] = dataclass_field(init=False, default_factory=set)
    buildings: Iterable[Building]
    turrets: set[Turret] = dataclass_field(init=False, default_factory=set)
    power_plants: set[PowerPlant] = dataclass_field(init=False, default_factory=set)
    barracks: set[Barracks] = dataclass_field(init=False, default_factory=set)
    war_factories: set[WarFactory] = dataclass_field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        self.harvesters = {u for u in self.units if isinstance(u, Harvester)}
        self.infantry = {u for u in self.units if isinstance(u, Infantry)}
        self.tanks = {u for u in self.units if isinstance(u, Tank)}
        self.turrets = {b for b in self.buildings if isinstance(b, Turret)}
        self.power_plants = {b for b in self.buildings if isinstance(b, PowerPlant)}
        self.barracks = {b for b in self.buildings if isinstance(b, Barracks)}
        self.war_factories = {b for b in self.buildings if isinstance(b, WarFactory)}


# @dataclass(kw_only=True)
# class Enemies:
#
#     buildings: InitVar[Iterable[Building]]
#     units: Iterable[GameObject] = dataclass_field(default_factory=set)
#     buildings_count: int = dataclass_field(init=False)
#
#     def __post_init__(self, enemy_buildings: Iterable[Building]) -> None:
#         self.buildings_count = len(list(enemy_buildings))
#         # self.tank_count = len({u for u in enemy_units if isinstance(u, Tank)})
#         # self.infantry_count = len({u for u in enemy_units if isinstance(u, Infantry)})
#         # self.turret_count = len({b for b in enemy_buildings if isinstance(b, Turret)})
#
#     # @property
#     # def total(self) -> int:
#     #     return sum((self.harvester_count, self.tank_count, self.infantry_count, self.buildings_count))


@dataclass(kw_only=True)
class AI:
    DESIRED_UNIT_RATIO = {"harvester": 4, "infantry": 6, "tank": 3, "turret": 3}
    SCALE_FACTOR = 1.8
    ACTION_INTERVAL = 50
    MAX_WAVE_SIZE = 25
    SCOUT_INTERVAL = 200

    hq: Headquarters
    console: GameConsole
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

    def _update_income_rate(
        self,
        friendly_harvesters: Iterable[Harvester],
    ) -> None:
        self.iron_income_rate = (
            sum(h.iron for h in friendly_harvesters)
            / max(1, len([friendly_harvesters]))
            * 60
            / 40
        )

    def _determine_state(
        self,
        *,
        enemy_units: Sequence[GameObject],
        enemy_buildings: Sequence[Building],
    ) -> None:
        player_base_size = len(enemy_units) + len(enemy_buildings)
        self.state = (
            "BROKE"
            if self.hq.iron < 300 or self.iron_income_rate < 50
            else "ATTACKED"
            if self.hq.health < self.hq.max_health * 0.6 or self.defense_cooldown > 0
            else "THREATENED"
            if any(
                math.sqrt(
                    (u.rect.centerx - self.hq.rect.centerx) ** 2
                    + (u.rect.centery - self.hq.rect.centery) ** 2
                )
                < 500
                for u in enemy_units
            )
            else "AGGRESSIVE"
            if self.wave_number >= 2 or player_base_size > 8
            else "BUILD_UP"
        )

    def _update_scout_targets(
        self,
        *,
        friendly_infantry: Iterable[Infantry],
        enemy_hq: Headquarters | None,
        iron_fields: Iterable[IronField],
    ) -> None:
        if not self.scout_targets:
            self.scout_targets = [f.rect.center for f in iron_fields]
            self.scout_targets.append((MAP_WIDTH // 2, MAP_HEIGHT // 2))
            if enemy_hq:
                self.scout_targets.append(enemy_hq.rect.center)

        for scout in [i for i in friendly_infantry if not i.target][:3]:
            if self.scout_targets:
                scout.target = self.scout_targets.pop(0)
                scout.target_unit = None

        self.last_scout_update = AI.SCOUT_INTERVAL

    @staticmethod
    def _determine_priority_target(
        *,
        unit: Infantry | Tank,
        enemy_units: Iterable[GameObject],
        enemy_buildings: Iterable[Building],
    ) -> Building | GameObject | None:
        targets = []
        for u in {u for u in enemy_units if u.health > 0}:
            dist = math.sqrt(
                (unit.rect.centerx - u.rect.centerx) ** 2
                + (unit.rect.centery - u.rect.centery) ** 2
            )
            priority = (
                3
                if isinstance(u, Harvester)
                else 2.5
                if isinstance(u, Headquarters)
                else 2
                if isinstance(u, Turret)
                else 1.5
                if u.health / u.max_health < 0.3
                else 1
            )
            targets.append((u, dist, priority))

        for b in {b for b in enemy_buildings if b.health > 0}:
            dist = math.sqrt(
                (unit.rect.centerx - b.rect.centerx) ** 2
                + (unit.rect.centery - b.rect.centery) ** 2
            )
            priority = (
                2.5
                if isinstance(b, Headquarters)
                else 2
                if isinstance(b, Turret)
                else 1
            )
            targets.append((b, dist, priority))

        targets.sort(key=lambda x: x[1] / x[2])
        return targets[0][0] if targets and targets[0][1] < 250 else None

    def _find_valid_building_position(
        self,
        *,
        building_cls: type[Building],
        friendly_buildings: Iterable[Building],
        enemy_buildings: Iterable[Building],
        iron_fields: Iterable[IronField],
    ) -> Coordinate:
        closest_field = min(
            iron_fields,
            key=lambda f: math.sqrt(
                (f.rect.centerx - self.hq.rect.centerx) ** 2
                + (f.rect.centery - self.hq.rect.centery) ** 2
            ),
            default=None,
        )
        buildings = {b for b in friendly_buildings if b.health > 0}
        for building, angle in itertools.product(buildings, range(0, 360, 20)):
            x = building.rect.centerx + math.cos(math.radians(angle)) * 120
            y = building.rect.centery + math.sin(math.radians(angle)) * 120
            snapped_position = snap_to_grid((x, y))
            if is_valid_building_position(
                position=snapped_position,
                team=self.hq.team,
                new_building_cls=building_cls,
                buildings=list(friendly_buildings) + list(enemy_buildings),
            ):
                if (
                    closest_field
                    and math.sqrt(
                        (x - closest_field.rect.centerx) ** 2
                        + (y - closest_field.rect.centery) ** 2
                    )
                    < 600
                ):
                    return x, y
                elif not closest_field:
                    return x, y

        return snap_to_grid(self.hq.rect.center)

    def _produce_obj(self, cls: type[GameObject]) -> None:
        self.hq.production_queue.append(cls)
        self.hq.iron -= cls.COST
        self.console.log(
            f"AI produced {cls.__name__}, cost: {cls.COST}, new iron: {self.hq.iron}"
        )

    def produce_objs(
        self,
        *,
        friendlies: Friendlies,
        enemy_unit_counts: dict[str, int],
        enemy_buildings: Iterable[Building],
        iron_fields: Iterable[IronField],
        all_buildings: pg.sprite.Group[Building],
    ) -> None:
        """
        Parameters
        ----------
        all_buildings:
            used for collision detection
        """
        desired_units = {
            obj_cls: int(ratio * AI.SCALE_FACTOR)
            for obj_cls, ratio in AI.DESIRED_UNIT_RATIO.items()
        }
        current_harvesters = len(friendlies.harvesters)
        current_infantry = len(friendlies.infantry)
        current_tanks = len(friendlies.tanks)
        current_turrets = len(friendlies.turrets)
        current_power_plants = len(friendlies.power_plants)
        current_barracks = len([b for b in friendlies.barracks if b.health > 0]) + len(
            [cls for cls in self.hq.production_queue if cls == Barracks]
        )
        current_war_factories = len(
            [b for b in friendlies.barracks if b.health > 0]
        ) + len([cls for cls in self.hq.production_queue if cls == WarFactory])

        desired_units["power_plant"] = max(1, (current_harvesters + 1) // 2)
        has_barracks = current_barracks > 0
        has_war_factory = current_war_factories > 0
        iron = self.hq.iron
        self.console.log(
            f"AI production check: Iron = {iron}, Has Barracks = {has_barracks}, Has WarFactory = {has_war_factory}"
        )

        if not has_barracks and iron >= Barracks.COST:
            self._produce_obj(Barracks)
            return

        elif not has_war_factory and iron >= WarFactory.COST:
            self._produce_obj(WarFactory)
            return

        elif (
            current_power_plants < desired_units["power_plant"]
            and self.hq.has_enough_power
            and iron >= PowerPlant.COST
        ):
            self._produce_obj(PowerPlant)
            return

        if (
            (
                current_harvesters
                < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
                or self.iron_income_rate < 50
            )
            and has_war_factory
            and iron >= Harvester.COST
        ):
            self._produce_obj(Harvester)
            return

        if iron <= 0:
            self.console.log("AI production halted: Insufficient iron")
            return

        production_options: list[type[GameObject]] = []
        if self.state in ["Build Up", "Aggressive"]:
            total_military = current_infantry + current_tanks + current_turrets
            if (
                total_military < 6
                and current_infantry < desired_units["infantry"]
                and has_barracks
                and iron >= Infantry.COST
            ):
                production_options.append(Infantry)
            if (
                total_military < 6
                and current_tanks < desired_units["tank"]
                and has_war_factory
                and iron >= Tank.COST
            ):
                production_options.append(Tank)
            if current_turrets < desired_units["turret"] and iron >= Turret.COST:
                production_options.append(Turret)
            if (
                current_infantry < desired_units["infantry"]
                and has_barracks
                and iron >= Infantry.COST
            ):
                production_options.append(Infantry)
            if (
                current_tanks < desired_units["tank"]
                and has_war_factory
                and iron >= Tank.COST
            ):
                production_options.append(Tank)
            if (
                current_harvesters < desired_units["harvester"]
                and has_war_factory
                and iron >= Harvester.COST
            ):
                production_options.append(Harvester)
            if (
                current_power_plants < desired_units["power_plant"]
                and iron >= PowerPlant.COST
            ):
                production_options.append(PowerPlant)
            if total_military >= 6 and current_barracks < 2 and iron >= Barracks.COST:
                production_options.append(Barracks)
            if (
                total_military >= 6
                and current_war_factories < 2
                and iron >= WarFactory.COST
            ):
                production_options.append(WarFactory)
            if current_harvesters >= 2 and iron >= Headquarters.COST:
                production_options.append(Headquarters)

            if production_options:
                self._produce_obj(random.choice(production_options))

        elif self.state in ["Attacked", "Threatened"]:
            if iron >= Turret.COST and current_turrets < desired_units["turret"]:
                production_options.append(Turret)
            if (
                current_tanks < desired_units["tank"]
                and has_war_factory
                and iron >= Tank.COST
            ):
                production_options.append(Tank)
            if (
                current_infantry < desired_units["infantry"]
                and has_barracks
                and iron >= Infantry.COST
            ):
                production_options.append(Infantry)
            if (
                current_harvesters
                < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
                and has_war_factory
                and iron >= Harvester.COST
            ):
                production_options.append(Harvester)

            if (
                current_power_plants < desired_units["power_plant"]
                and iron >= PowerPlant.COST
            ):
                production_options.append(PowerPlant)

            if production_options:
                self._produce_obj(random.choice(production_options))

        elif (
            self.state == "Broke"
            and current_harvesters
            < min(desired_units["harvester"], enemy_unit_counts["harvester"] + 1)
            and has_war_factory
            and iron >= Harvester.COST
        ):
            self._produce_obj(Harvester)

        if self.hq.production_queue and not self.hq.production_timer:
            self.hq.production_timer = self.hq.get_production_time(
                unit_class=self.hq.production_queue[0],
                friendly_buildings=friendlies.buildings,
            )
        if self.hq.pending_building and not self.hq.pending_building_pos:
            x, y = self._find_valid_building_position(
                building_cls=self.hq.pending_building,
                friendly_buildings=friendlies.buildings,
                enemy_buildings=enemy_buildings,
                iron_fields=iron_fields,
            )
            self.hq.pending_building_pos = x, y
            self.hq.place_building(
                x=x,
                y=y,
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
            if self.state == "Aggressive" or surprise
            else ["all_in", "defensive"]
            if self.state in ["Threatened", "Attacked"]
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
                        unit.target_unit = target
                        unit.target = (
                            target.rect.centerx + random.uniform(-20, 20),
                            target.rect.centery + random.uniform(-20, 20),
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
                    unit.target = (
                        gdi_hq.rect.centerx + offset_x,
                        gdi_hq.rect.centery + offset_y,
                    )
                    unit.target_unit = gdi_hq

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
                        unit.target_unit = target
                        unit.target = (
                            target.rect.centerx + random.uniform(-20, 20),
                            target.rect.centery + random.uniform(-20, 20),
                        )
        elif tactic == "defensive":
            attack_units = combat_units[:wave_size]
            for unit in attack_units:
                unit.target = (
                    self.hq.rect.centerx + random.uniform(-50, 50),
                    self.hq.rect.centery + random.uniform(-50, 50),
                )
                unit.target_unit = None

    def update(
        self,
        *,
        friendly_units: Iterable[GameObject],
        enemy_units: Sequence[GameObject],
        enemy_buildings: Sequence[Building],
        iron_fields: Iterable[IronField],
        all_buildings: pg.sprite.Group[Building],
    ) -> None:
        """
        Parameters
        ----------
        all_buildings:
            used for collision detection
        """
        friendlies = Friendlies(
            units=friendly_units,
            buildings={b for b in all_buildings if b.team == Team.GDI},
        )
        self._update_income_rate(friendlies.harvesters)
        player_unit_counts = self._enemy_unit_counts(
            enemy_units=enemy_units, enemy_buildings=enemy_buildings
        )
        self.timer += 1
        self.wave_timer += 1
        self.surprise_attack_cooldown = max(0, self.surprise_attack_cooldown - 1)
        self._determine_state(
            enemy_units=enemy_units,
            enemy_buildings=enemy_buildings,
        )
        if self.last_scout_update <= 0:
            self._update_scout_targets(
                friendly_infantry=friendlies.infantry,
                enemy_hq=next(
                    (b for b in enemy_buildings if isinstance(b, Headquarters)),
                    None,
                ),
                iron_fields=iron_fields,
            )
        else:
            self.last_scout_update -= 1

        if self.timer >= self.ACTION_INTERVAL:
            self.timer = 0
            self.produce_objs(
                friendlies=friendlies,
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
                friendly_units=friendlies.units,
                enemy_units=enemy_units,
                enemy_buildings=enemy_buildings,
                surprise=True,
            )
            self.surprise_attack_cooldown = 300

        elif self.wave_timer >= self.wave_interval:
            self.coordinate_attack(
                friendly_units=friendlies.units,
                enemy_units=enemy_units,
                enemy_buildings=enemy_buildings,
            )
