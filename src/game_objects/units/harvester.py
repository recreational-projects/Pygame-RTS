from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pygame as pg

from src.constants import VIEW_DEBUG_MODE_IS_ENABLED
from src.game_objects.game_object import GameObject
from src.game_objects.units.infantry import Infantry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.camera import Camera
    from src.constants import Team
    from src.game_objects.buildings.headquarters import Headquarters
    from src.iron_field import IronField

IRON_TRANSFER_RANGE = 30
"""Distance within which iron can be harvested/delivered."""


class Harvester(GameObject):
    """Resource collector."""

    # Override base class(es):
    ATTACK_RANGE = 50
    COST = 800
    IS_MOBILE = True
    POWER_USAGE = 20

    def __init__(
        self,
        position: pg.typing.SequenceLike,
        team: Team,
        hq: Headquarters,
        font: pg.Font,
    ) -> None:
        super().__init__(position=position, team=team)
        self.image = pg.Surface((50, 30), pg.SRCALPHA)
        self.rect = self.image.get_rect(center=position)
        self.hq = hq
        self.font = font
        self.speed = 2.5
        self.health = 300
        self.max_health = self.health
        self.capacity = 100
        self.iron = 0
        self.state: Literal["HARVESTING", "MOVING_TO_FIELD", "RETURNING_TO_HQ"] = (
            "MOVING_TO_FIELD"
        )
        self.target_field: IronField | None = None
        self.harvest_time = 40
        self.attack_damage = 10
        self.attack_cooldown = 30

        # Draw harvester as a truck
        pg.draw.rect(self.image, (120, 120, 120), (0, 0, 50, 30))  # Body
        pg.draw.rect(self.image, (100, 100, 100), (5, 5, 40, 20))  # Cargo area
        pg.draw.circle(self.image, (50, 50, 50), (10, 30), 5)  # Wheel 1
        pg.draw.circle(self.image, (50, 50, 50), (40, 30), 5)  # Wheel 2

    def update(
        self, *, enemy_units: Iterable[GameObject], iron_fields: Iterable[IronField]
    ) -> None:
        super().update()
        if self.cooldown_timer == 0:
            closest_target, min_dist = None, float("inf")
            for u in enemy_units:
                if u.health > 0 and isinstance(u, Infantry):
                    dist = self.distance_to(u.position)
                    if dist < Harvester.ATTACK_RANGE and dist < min_dist:
                        closest_target, min_dist = u, dist

            if closest_target:
                closest_target.health -= self.attack_damage
                if closest_target.health <= 0:
                    closest_target.kill()
                self.cooldown_timer = self.attack_cooldown

        if self.state == "MOVING_TO_FIELD":
            if not self.target_field or self.target_field.resources <= 0:
                rich_fields = [f for f in iron_fields if f.resources >= 1000]
                if rich_fields:
                    self.target_field = min(
                        rich_fields,
                        key=lambda f: self.distance_to(f.position),
                    )
                else:
                    self.target_field = min(
                        iron_fields,
                        key=lambda f: self.distance_to(f.position),
                    )
            if self.target_field:
                self.target = self.target_field.position
                if self.distance_to(self.target) < IRON_TRANSFER_RANGE:
                    self.state = "HARVESTING"
                    self.target = None
                    self.harvest_time = 40

        elif self.state == "HARVESTING":
            if self.harvest_time > 0:
                self.harvest_time -= 1
            else:
                if not self.target_field:
                    raise TypeError("No target field")
                    # Temporary handling, review later

                harvested = min(self.target_field.resources, self.capacity)
                self.iron += harvested
                self.target_field.resources -= harvested
                self.state = "RETURNING_TO_HQ"
                self.target = self.hq.position

        elif self.state == "RETURNING_TO_HQ":
            if not self.target:
                raise TypeError(
                    f"Harvester RETURNING_TO_HQ has no target.\n{self}"
                )  # Temporary handling, review later

            if self.distance_to(self.target) < IRON_TRANSFER_RANGE:
                self.hq.iron += self.iron
                self.iron = 0
                self.state = "MOVING_TO_FIELD"
                self.target = None

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        _blit_pos = camera.to_screen(self.rect.topleft)
        surface.blit(source=self.image, dest=_blit_pos)
        if self.is_selected:
            self.draw_selection_indicator(surface=surface, camera=camera)

        if VIEW_DEBUG_MODE_IS_ENABLED:
            self.draw_debug_info(surface=surface, camera=camera)

        self.draw_health_bar(surface=surface, camera=camera)
        if self.iron > 0:
            _label = self.font.render(
                text=f"Iron: {self.iron}",
                antialias=True,
                color=(255, 255, 255),
            )
            _label_pos = _blit_pos + (0, -35)
            surface.blit(source=_label, dest=_label_pos)
