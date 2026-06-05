from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import pygame as pg
from pygame.math import Vector2

from modules.data_iso import TILE_SIZE
from modules.game_object.game_object_iso import GameObjectIso
from modules.geometry import closest_point_on_rect
from modules.particles import GenericParticle, create_explosion_iso
from modules.pathfinding_iso import astar
from modules.projectile_iso import Projectile
from modules.team import Team, team_to_color
from modules.unit_stats.unit_stats_iso import UnitStatsIso
from modules.world_iso import is_valid_building_position

if TYPE_CHECKING:
    from collections.abc import Container, Iterable, MutableSet

    from pygame.typing import Point

    from modules.camera.camera_iso import CameraIso
    from modules.unit_stats.unit_stats import WeaponStats


class UnitIso(GameObjectIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team)
        self.hq = hq
        self.current_weapon_index = 0
        self.attack_target: UnitIso | None = None
        self.last_shot_time = 0
        self.move_target: Point | None = None
        self.formation_target: Point | None = None
        self.turret_angle: float = 0
        self.body_angle: float = 0

        self._stats = UnitStatsIso.from_data(self.__class__.__name__)  # read-only
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

        self.path = []
        self.path_index = 0
        self.path_recompute_cooldown = 0
        self.target_body_angle = 0.0
        self.target_turret_angle = 0.0

        self.height = self._stats.height
        self.rifle_length = self._stats.rifle_length
        self.rifle_thickness = self._stats.rifle_thickness
        self.hull_rotation_speed = self._stats.hull_rotation_speed
        self.turret_rotation_speed = self._stats.turret_rotation_speed

        if self.is_producer:
            self.rally_point = Vector2(position[0] + 80, position[1])
            self.production_queue = []
            self.production_timer: int | None = None

        self.rect = pg.Rect(self.position.x - self.size[0] / 2, self.position.y - self.size[1] / 2, *self.size)
        self._setup_drawing()

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
    def is_vehicle(self) -> bool:
        return isinstance(
            self, Tank | HeavyTank | TankDestroyer | MachineGunVehicle | RocketArtillery | AttackHelicopter
        )

    def _draw_static(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = self.fly_height if self.is_air else 0
        top_z = base_z + h
        bfl = (pos.x - w / 2, pos.y - d / 2, base_z)
        bfr = (pos.x + w / 2, pos.y - d / 2, base_z)
        bbr = (pos.x + w / 2, pos.y + d / 2, base_z)
        bbl = (pos.x - w / 2, pos.y + d / 2, base_z)
        tfl = (pos.x - w / 2, pos.y - d / 2, top_z)
        tfr = (pos.x + w / 2, pos.y - d / 2, top_z)
        tbr = (pos.x + w / 2, pos.y + d / 2, top_z)
        tbl = (pos.x - w / 2, pos.y + d / 2, top_z)
        p_bfl = camera.world_to_iso_3d(*bfl, zoom)
        p_bfr = camera.world_to_iso_3d(*bfr, zoom)
        p_bbr = camera.world_to_iso_3d(*bbr, zoom)
        p_bbl = camera.world_to_iso_3d(*bbl, zoom)
        p_tfl = camera.world_to_iso_3d(*tfl, zoom)
        p_tfr = camera.world_to_iso_3d(*tfr, zoom)
        p_tbr = camera.world_to_iso_3d(*tbr, zoom)
        p_tbl = camera.world_to_iso_3d(*tbl, zoom)
        base_points = [p_bfl, p_bfr, p_bbr, p_bbl]
        front_points = [p_bfl, p_bfr, p_tfr, p_tfl]
        pg.draw.polygon(surface, _team_color, front_points)
        side_color = tuple(max(0, c - 50) for c in _team_color)
        pg.draw.polygon(surface, side_color, [p_bfr, p_bbr, p_tbr, p_tfr])
        pg.draw.polygon(surface, side_color, [p_bbr, p_bbl, p_tbl, p_tbr])
        pg.draw.polygon(surface, side_color, [p_bbl, p_bfl, p_tfl, p_tbl])
        roof_color = pg.Color(128, 128, 128) if self.is_building else pg.Color(100, 100, 100)
        roof_points = [p_tfl, p_tfr, p_tbr, p_tbl]
        pg.draw.polygon(surface, roof_color, roof_points)
        outline_color = pg.Color(0, 0, 0)
        all_edges = [
            [p_bfl, p_bfr, p_bbr, p_bbl, p_bfl],
            [p_tfl, p_tfr, p_tbr, p_tbl, p_tfl],
            [p_bfl, p_tfl],
            [p_bfr, p_tfr],
            [p_bbr, p_tbr],
            [p_bbl, p_tbl],
        ]
        for edge in all_edges:
            if len(edge) > 2:
                for i in range(len(edge) - 1):
                    pg.draw.line(surface, outline_color, edge[i], edge[i + 1], int(2 * zoom))
            else:
                pg.draw.line(surface, outline_color, edge[0], edge[1], int(2 * zoom))

        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), base_points, int(2 * zoom))

        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)

    def _draw_humanoid(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        # pyrefly: ignore [missing-attribute]
        _team_color = team_to_color[self.hq.team]
        zoom = camera.zoom
        pos = self.position
        angle = self.body_angle
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        side_color = tuple(max(0, c - 50) for c in _team_color)
        highlight_color = tuple(min(255, c + 30) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        shadow_color = pg.Color(50, 50, 50, 100)
        shadow_offset = (2 * zoom, 2 * zoom)
        base_screen = camera.world_to_iso(pos, zoom)
        shadow_r = int(4 * zoom)
        pg.draw.ellipse(
            surface,
            shadow_color,
            (
                int(base_screen[0] + shadow_offset[0] - shadow_r),
                int(base_screen[1] + shadow_offset[1] - shadow_r // 2),
                shadow_r * 2,
                shadow_r,
            ),
        )
        torso_w = 1.1
        torso_d = 0.7
        torso_h = 2.8
        torso_base_z = 2.0
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=torso_w * 0.9,
            d=torso_d * 0.9,
            h=torso_h * 0.3,
            angle=angle,
            base_z=torso_base_z + torso_h * 0.7,
            team_color=highlight_color,
            side_color=side_color,
            roof_color=highlight_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
        )
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=torso_w,
            d=torso_d,
            h=torso_h,
            angle=angle,
            base_z=torso_base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
        )
        head_base_z = torso_base_z + torso_h
        head_offset_x = 0.0 * cos_a - 0.0 * sin_a
        head_offset_y = 0.0 * sin_a + 0.0 * cos_a
        head_pos_x = pos.x + head_offset_x
        head_pos_y = pos.y + head_offset_y
        head_r_world = 0.55
        head_center_3d = (head_pos_x, head_pos_y, head_base_z + head_r_world)
        head_screen = camera.world_to_iso_3d(*head_center_3d, zoom)
        scaled_head_r = int(head_r_world * zoom * 2)
        if scaled_head_r > 0:
            pg.draw.circle(surface, _team_color, (int(head_screen[0]), int(head_screen[1])), scaled_head_r)
            eye_offset = int(0.3 * scaled_head_r)
            eye_size = int(0.1 * scaled_head_r)
            pg.draw.circle(
                surface,
                outline_color,
                (
                    int(head_screen[0] - eye_offset * cos_a),
                    int(head_screen[1] - eye_offset * sin_a),
                ),
                eye_size,
            )
            pg.draw.circle(
                surface,
                outline_color,
                (
                    int(head_screen[0] + eye_offset * cos_a),
                    int(head_screen[1] + eye_offset * sin_a),
                ),
                eye_size,
            )
            pg.draw.circle(surface, outline_color, (int(head_screen[0]), int(head_screen[1])), scaled_head_r, 2)
        arm_upper_length = 0.8
        arm_lower_length = 0.7
        arm_start_z = torso_base_z + 1.2
        arm_thickness = int(1.5 * zoom)
        left_offset_x = -0.55 * cos_a - 0.35 * sin_a
        left_offset_y = -0.55 * sin_a + 0.35 * cos_a
        arm_l_start_x = pos.x + left_offset_x
        arm_l_start_y = pos.y + left_offset_y
        elbow_l_x = arm_l_start_x - arm_upper_length * cos_a
        elbow_l_y = arm_l_start_y - arm_upper_length * sin_a
        p_l_start = camera.world_to_iso_3d(arm_l_start_x, arm_l_start_y, arm_start_z, zoom)
        p_l_elbow = camera.world_to_iso_3d(elbow_l_x, elbow_l_y, arm_start_z - 0.1, zoom)
        pg.draw.line(surface, _team_color, p_l_start, p_l_elbow, arm_thickness)
        pg.draw.line(surface, outline_color, p_l_start, p_l_elbow, 1)
        hand_l_x = elbow_l_x - arm_lower_length * cos_a
        hand_l_y = elbow_l_y - arm_lower_length * sin_a
        p_l_hand = camera.world_to_iso_3d(hand_l_x, hand_l_y, arm_start_z - 0.2, zoom)
        pg.draw.line(surface, _team_color, p_l_elbow, p_l_hand, arm_thickness - 1)
        pg.draw.line(surface, outline_color, p_l_elbow, p_l_hand, 1)
        pg.draw.circle(surface, _team_color, (int(p_l_hand[0]), int(p_l_hand[1])), int(0.15 * zoom * 2), 0)
        pg.draw.circle(surface, outline_color, (int(p_l_hand[0]), int(p_l_hand[1])), int(0.15 * zoom * 2), 1)
        right_offset_x = 0.55 * cos_a - 0.35 * sin_a
        right_offset_y = 0.55 * sin_a + 0.35 * cos_a
        arm_r_start_x = pos.x + right_offset_x
        arm_r_start_y = pos.y + right_offset_y
        elbow_r_x = arm_r_start_x + arm_upper_length * cos_a
        elbow_r_y = arm_r_start_y + arm_upper_length * sin_a
        p_r_start = camera.world_to_iso_3d(arm_r_start_x, arm_r_start_y, arm_start_z, zoom)
        p_r_elbow = camera.world_to_iso_3d(elbow_r_x, elbow_r_y, arm_start_z - 0.1, zoom)
        pg.draw.line(surface, _team_color, p_r_start, p_r_elbow, arm_thickness)
        pg.draw.line(surface, outline_color, p_r_start, p_r_elbow, 1)
        hand_r_x = elbow_r_x + arm_lower_length * cos_a
        hand_r_y = elbow_r_y + arm_lower_length * sin_a
        p_r_hand = camera.world_to_iso_3d(hand_r_x, hand_r_y, arm_start_z - 0.2, zoom)
        pg.draw.line(surface, _team_color, p_r_elbow, p_r_hand, arm_thickness - 1)
        pg.draw.line(surface, outline_color, p_r_elbow, p_r_hand, 1)
        pg.draw.circle(surface, _team_color, (int(p_r_hand[0]), int(p_r_hand[1])), int(0.15 * zoom * 2), 0)
        pg.draw.circle(surface, outline_color, (int(p_r_hand[0]), int(p_r_hand[1])), int(0.15 * zoom * 2), 1)
        leg_thigh_length = 1.0
        leg_shin_length = 1.0
        leg_start_z = 0.0
        leg_thickness = int(2.5 * zoom)
        leg_l_offset_x = -0.25 * cos_a - 0.15 * sin_a
        leg_l_offset_y = -0.25 * sin_a + 0.15 * cos_a
        leg_l_start_x = pos.x + leg_l_offset_x
        leg_l_start_y = pos.y + leg_l_offset_y
        knee_l_x = leg_l_start_x - leg_thigh_length * sin_a
        knee_l_y = leg_l_start_y + leg_thigh_length * cos_a
        p_leg_l_start = camera.world_to_iso_3d(leg_l_start_x, leg_l_start_y, leg_start_z, zoom)
        p_leg_l_knee = camera.world_to_iso_3d(knee_l_x, knee_l_y, leg_start_z + 0.1, zoom)
        pg.draw.line(surface, _team_color, p_leg_l_start, p_leg_l_knee, leg_thickness)
        pg.draw.line(surface, outline_color, p_leg_l_start, p_leg_l_knee, 1)
        foot_l_x = knee_l_x - leg_shin_length * sin_a
        foot_l_y = knee_l_y + leg_shin_length * cos_a
        p_leg_l_foot = camera.world_to_iso_3d(foot_l_x, foot_l_y, leg_start_z, zoom)
        pg.draw.line(surface, _team_color, p_leg_l_knee, p_leg_l_foot, leg_thickness - 1)
        pg.draw.line(surface, outline_color, p_leg_l_knee, p_leg_l_foot, 1)
        foot_w = int(0.4 * zoom * 2)
        foot_h = int(0.2 * zoom * 2)
        pg.draw.ellipse(
            surface,
            _team_color,
            (
                int(p_leg_l_foot[0] - foot_w // 2),
                int(p_leg_l_foot[1] - foot_h // 2),
                foot_w,
                foot_h,
            ),
        )
        pg.draw.ellipse(
            surface,
            outline_color,
            (
                int(p_leg_l_foot[0] - foot_w // 2),
                int(p_leg_l_foot[1] - foot_h // 2),
                foot_w,
                foot_h,
            ),
            1,
        )
        leg_r_offset_x = 0.25 * cos_a - 0.15 * sin_a
        leg_r_offset_y = 0.25 * sin_a + 0.15 * cos_a
        leg_r_start_x = pos.x + leg_r_offset_x
        leg_r_start_y = pos.y + leg_r_offset_y
        knee_r_x = leg_r_start_x + leg_thigh_length * sin_a
        knee_r_y = leg_r_start_y - leg_thigh_length * cos_a
        p_leg_r_start = camera.world_to_iso_3d(leg_r_start_x, leg_r_start_y, leg_start_z, zoom)
        p_leg_r_knee = camera.world_to_iso_3d(knee_r_x, knee_r_y, leg_start_z + 0.1, zoom)
        pg.draw.line(surface, _team_color, p_leg_r_start, p_leg_r_knee, leg_thickness)
        pg.draw.line(surface, outline_color, p_leg_r_start, p_leg_r_knee, 1)
        foot_r_x = knee_r_x + leg_shin_length * sin_a
        foot_r_y = knee_r_y - leg_shin_length * cos_a
        p_leg_r_foot = camera.world_to_iso_3d(foot_r_x, foot_r_y, leg_start_z, zoom)
        pg.draw.line(surface, _team_color, p_leg_r_knee, p_leg_r_foot, leg_thickness - 1)
        pg.draw.line(surface, outline_color, p_leg_r_knee, p_leg_r_foot, 1)
        pg.draw.ellipse(
            surface,
            _team_color,
            (
                int(p_leg_r_foot[0] - foot_w // 2),
                int(p_leg_r_foot[1] - foot_h // 2),
                foot_w,
                foot_h,
            ),
        )
        pg.draw.ellipse(
            surface,
            outline_color,
            (
                int(p_leg_r_foot[0] - foot_w // 2),
                int(p_leg_r_foot[1] - foot_h // 2),
                foot_w,
                foot_h,
            ),
            1,
        )
        weapon_z = arm_start_z - 0.1
        arm_r_end_x, arm_r_end_y = hand_r_x, hand_r_y
        if isinstance(self, Infantry | Grenadier | Marksman):
            rifle_start_x = arm_r_end_x + 0.3 * cos_a
            rifle_start_y = arm_r_end_y + 0.3 * sin_a
            rifle_end_x = rifle_start_x + self.rifle_length * cos_a
            rifle_end_y = rifle_start_y + self.rifle_length * sin_a
            p_rifle_start = camera.world_to_iso_3d(rifle_start_x, rifle_start_y, weapon_z, zoom)
            p_rifle_end = camera.world_to_iso_3d(rifle_end_x, rifle_end_y, weapon_z, zoom)
            team_grey = tuple(int(c * 0.6) for c in _team_color)
            barrel_color = team_grey
            stock_color = (139, 69, 19)
            highlight_color = (200, 200, 200)
            rifle_width = int(self.rifle_thickness * zoom)
            pg.draw.line(surface, barrel_color, p_rifle_start, p_rifle_end, rifle_width)
            pg.draw.line(surface, outline_color, p_rifle_start, p_rifle_end, 1)
            stock_length = int(0.4 * zoom * 2) if isinstance(self, Marksman) else int(0.6 * zoom * 2)
            stock_end_x = p_rifle_start[0] - stock_length * sin_a / zoom
            stock_end_y = p_rifle_start[1] + stock_length * cos_a / zoom
            pg.draw.line(surface, stock_color, p_rifle_start, (stock_end_x, stock_end_y), int(2 * zoom))
            muzzle_r = int(0.8 * zoom)
            pg.draw.circle(surface, highlight_color, (int(p_rifle_end[0]), int(p_rifle_end[1])), muzzle_r)
            pg.draw.circle(surface, outline_color, (int(p_rifle_end[0]), int(p_rifle_end[1])), muzzle_r, 1)
            if isinstance(self, Marksman):
                scope_pos = (
                    (p_rifle_start[0] + p_rifle_end[0]) / 2,
                    (p_rifle_start[1] + p_rifle_end[1]) / 2,
                )
                scope_r = int(1.2 * zoom)
                pg.draw.circle(surface, (120, 120, 120), (int(scope_pos[0]), int(scope_pos[1])), scope_r)
                pg.draw.circle(surface, highlight_color, (int(scope_pos[0]), int(scope_pos[1])), scope_r - 1)

        elif isinstance(self, RocketSoldier):
            _rocket_width = int(self._stats.rocket_thickness * zoom)
            shoulder_offset_x = 0.7 * cos_a - 0.5 * sin_a
            shoulder_offset_y = 0.7 * sin_a + 0.5 * cos_a
            rocket_start_x = pos.x + shoulder_offset_x
            rocket_start_y = pos.y + shoulder_offset_y
            rocket_end_x = rocket_start_x + self._stats.rocket_length * sin_a
            rocket_end_y = rocket_start_y - self._stats.rocket_length * cos_a
            p_rocket_start = camera.world_to_iso_3d(rocket_start_x, rocket_start_y, weapon_z, zoom)
            p_rocket_end = camera.world_to_iso_3d(rocket_end_x, rocket_end_y, weapon_z, zoom)
            tube_color = tuple(int(c * 0.7) for c in _team_color)
            warhead_color = (200, 50, 50)
            pg.draw.line(surface, tube_color, p_rocket_start, p_rocket_end, _rocket_width)
            pg.draw.line(surface, outline_color, p_rocket_start, p_rocket_end, 2)
            grip_length = int(0.1 * zoom * 2)
            grip_dir_perp_x = rocket_end_x - rocket_start_x
            grip_dir_perp_y = rocket_end_y - rocket_start_y
            length = math.sqrt(grip_dir_perp_x**2 + grip_dir_perp_y**2)
            if length > 0:
                grip_dir_perp_x /= length
                grip_dir_perp_y /= length
                grip_perp_x = -grip_dir_perp_y * grip_length
                grip_perp_y = grip_dir_perp_x * grip_length
            grip_mid = (
                (p_rocket_start[0] + p_rocket_end[0]) / 2,
                (p_rocket_start[1] + p_rocket_end[1]) / 2,
            )
            # pyrefly: ignore [unbound-name]
            p_grip_end1 = (grip_mid[0] + grip_perp_x, grip_mid[1] + grip_perp_y)
            p_grip_end2 = (grip_mid[0] - grip_perp_x, grip_mid[1] - grip_perp_y)
            pg.draw.line(surface, (80, 80, 80), p_grip_end1, p_grip_end2, int(2 * zoom))
            tip_r = int(0.1 * zoom)
            pg.draw.circle(surface, warhead_color, (int(p_rocket_end[0]), int(p_rocket_end[1])), tip_r)
            fin_length = int(0.1 * zoom)
            for i in range(2):
                fin_angle = math.pi / 4 + i * math.pi
                fin_end_x = p_rocket_end[0] + fin_length * math.cos(fin_angle)
                fin_end_y = p_rocket_end[1] + fin_length * math.sin(fin_angle)
                pg.draw.line(surface, (120, 120, 120), p_rocket_end, (fin_end_x, fin_end_y), 1)
        if self.selected:
            select_r = int(10 * zoom)
            pulse_alpha = int(128 + 127 * math.sin(pg.time.get_ticks() * 0.01))
            pulse_color = (255, 255, 0, pulse_alpha)
            select_surf = pg.Surface((select_r * 2, select_r * 2), pg.SRCALPHA)
            pg.draw.circle(select_surf, pulse_color, (select_r, select_r), select_r, int(3 * zoom))
            surface.blit(select_surf, (int(base_screen[0] - select_r), int(base_screen[1] - select_r)))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)

    def _draw_rotated_box(
        self,
        *,
        surface: pg.Surface,
        camera: CameraIso,
        w: float,
        d: float,
        h: float,
        angle: float,
        base_z: float,
        team_color: pg.Color | tuple[int, ...],
        side_color: tuple[int, ...],
        roof_color: pg.Color | tuple[int, ...],
        outline_color: pg.Color,
        zoom: float,
        is_turret: bool = False,
        p_bottom: list | None = None,
    ) -> None:
        cos = math.cos(angle)
        sin = math.sin(angle)

        def rotate_rel(
            points: list[tuple[float, float, float]] | list[tuple[float, float, int]], cos: float, sin: float
        ) -> list[Point]:
            return [(x * cos - y * sin, x * sin + y * cos, z) for x, y, z in points]

        rel_bottom = [
            (-w / 2, -d / 2, 0),
            (w / 2, -d / 2, 0),
            (w / 2, d / 2, 0),
            (-w / 2, d / 2, 0),
        ]
        rel_top = [(x, y, h) for x, y, _ in rel_bottom]
        rot_bottom = rotate_rel(rel_bottom, cos, sin)
        rot_top = rotate_rel(rel_top, cos, sin)
        full_bottom = [(self.position.x + rx, self.position.y + ry, base_z + rz) for rx, ry, rz in rot_bottom]
        full_top = [(self.position.x + rx, self.position.y + ry, base_z + rz) for rx, ry, rz in rot_top]
        p_bottom_local = [camera.world_to_iso_3d(*pt, zoom) for pt in full_bottom]
        p_top = [camera.world_to_iso_3d(*pt, zoom) for pt in full_top]
        if p_bottom is not None:
            p_bottom[:] = p_bottom_local
        wall_indices = [[0, 1, 1, 0], [1, 2, 2, 1], [2, 3, 3, 2], [3, 0, 0, 3]]
        avg_ys = []
        for widx in wall_indices:
            ys = [
                full_bottom[widx[0]][1],
                full_bottom[widx[1]][1],
                full_top[widx[2]][1],
                full_top[widx[3]][1],
            ]
            avg_ys.append(sum(ys) / 4)

        front_idx = avg_ys.index(min(avg_ys))
        for i, widx in enumerate(wall_indices):
            points = [
                p_bottom_local[widx[0]],
                p_bottom_local[widx[1]],
                p_top[widx[2]],
                p_top[widx[3]],
            ]
            color = team_color if i == front_idx else side_color
            pg.draw.polygon(surface, color, points)

        pg.draw.polygon(surface, roof_color, p_top)
        all_points = p_bottom_local + p_top
        bottom_edge = [0, 1, 2, 3, 0]
        top_edge = [4, 5, 6, 7, 4]
        verticals = [[0, 4], [1, 5], [2, 6], [3, 7]]
        all_edges = [bottom_edge, top_edge] + verticals
        line_width = int(1 * zoom) if is_turret else int(2 * zoom)
        for edge in all_edges:
            if len(edge) > 2:
                for j in range(len(edge) - 1):
                    pg.draw.line(
                        surface,
                        outline_color,
                        all_points[edge[j]],
                        all_points[edge[j + 1]],
                        line_width,
                    )
            else:
                pg.draw.line(surface, outline_color, all_points[edge[0]], all_points[edge[1]], line_width)

    def _draw_vehicle(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        # pyrefly: ignore [missing-attribute]
        _team_color = team_to_color[self.hq.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = self.fly_height if self.is_air else 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        roof_color = pg.Color(100, 100, 100)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=w,
            d=d,
            h=h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=roof_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))

        turret_w = self._stats.turret_width
        turret_d = self._stats.turret_depth
        turret_h = self._stats.turret_height
        turret_base_z = base_z + h
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=turret_w,
            d=turret_d,
            h=turret_h,
            angle=self.turret_angle,
            base_z=turret_base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=roof_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=True,
        )
        if isinstance(self, Tank | HeavyTank | TankDestroyer):
            barrel_length = self._stats.barrel_length
            barrel_width = self._stats.barrel_width
            barrel_height = self._stats.barrel_height
            turret_center_x = pos.x + self._stats.turret_offset_x
            turret_center_y = pos.y + self._stats.turret_offset_y
            turret_center_z = turret_base_z + turret_h / 2
            cos_t = math.cos(self.turret_angle)
            sin_t = math.sin(self.turret_angle)
            front_offset = turret_d / 2
            barrel_start_x = turret_center_x + front_offset * cos_t
            barrel_start_y = turret_center_y + front_offset * sin_t
            barrel_start_z = turret_center_z
            barrel_end_x = barrel_start_x + barrel_length * cos_t
            barrel_end_y = barrel_start_y + barrel_length * sin_t
            barrel_end_z = barrel_start_z + barrel_height / 2
            perp_cos = -sin_t
            perp_sin = cos_t
            b1 = (
                barrel_start_x - (barrel_width / 2) * perp_cos,
                barrel_start_y - (barrel_width / 2) * perp_sin,
                barrel_start_z - barrel_height / 2,
            )
            b2 = (
                barrel_start_x + (barrel_width / 2) * perp_cos,
                barrel_start_y + (barrel_width / 2) * perp_sin,
                barrel_start_z - barrel_height / 2,
            )
            b3 = (
                barrel_end_x + (barrel_width / 2) * perp_cos,
                barrel_end_y + (barrel_width / 2) * perp_sin,
                barrel_end_z - barrel_height / 2,
            )
            b4 = (
                barrel_end_x - (barrel_width / 2) * perp_cos,
                barrel_end_y - (barrel_width / 2) * perp_sin,
                barrel_end_z - barrel_height / 2,
            )
            p_b1 = camera.world_to_iso_3d(*b1, zoom)
            p_b2 = camera.world_to_iso_3d(*b2, zoom)
            p_b3 = camera.world_to_iso_3d(*b3, zoom)
            p_b4 = camera.world_to_iso_3d(*b4, zoom)
            barrel_color = tuple(min(255, c + 20) for c in _team_color)
            pg.draw.polygon(surface, barrel_color, [p_b1, p_b2, p_b3, p_b4])
            pg.draw.line(surface, outline_color, p_b1, p_b2, int(1 * zoom))
            pg.draw.line(surface, outline_color, p_b2, p_b3, int(1 * zoom))
            pg.draw.line(surface, outline_color, p_b3, p_b4, int(1 * zoom))
            pg.draw.line(surface, outline_color, p_b4, p_b1, int(1 * zoom))

        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)

    def get_chase_position_for_building(self, target_building: UnitIso) -> Vector2 | None:  # noqa: ANN001
        # pyrefly: ignore [bad-argument-type]
        closest = closest_point_on_rect(rect=target_building.rect, pos=self.position)
        dir_to_closest = Vector2(closest) - self.position
        dist_to_closest = dir_to_closest.length()
        if dist_to_closest <= self.attack_range:
            return None
        if dist_to_closest == 0:
            return None
        dir_unit = dir_to_closest.normalize()
        target_pos = Vector2(closest) - dir_unit * self.attack_range
        perp_dir = dir_unit.rotate_rad(math.pi / 2)
        max_spread = min(15, self.attack_range * 0.15)
        spread_dist = random.uniform(-max_spread, max_spread)
        target_pos += perp_dir * spread_dist
        # pyrefly: ignore [bad-argument-type]
        new_closest = closest_point_on_rect(rect=target_building.rect, pos=target_pos)
        new_dist = Vector2(new_closest).distance_to(target_pos)
        if new_dist > self.attack_range:
            overage = new_dist - self.attack_range
            adjust_dir = (Vector2(new_closest) - target_pos).normalize()
            target_pos += adjust_dir * overage * 0.5
        target_pos.x = max(0, min(target_pos.x, self.map_width))
        target_pos.y = max(0, min(target_pos.y, self.map_height))
        return target_pos

    def _setup_drawing(self) -> None:
        if isinstance(self, Infantry | Grenadier | RocketSoldier | Marksman):
            self.draw = self._draw_humanoid
        elif not self.is_vehicle:
            self.draw = self._draw_static
        else:
            self.draw = self._draw_vehicle

    def _update_production(self, *, friendly_units: MutableSet[UnitIso], all_units: MutableSet[UnitIso]) -> None:  # noqa: ANN001
        if self.production_queue:
            current_unit_count = len(friendly_units)
            if current_unit_count < 100:
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
                        new_unit = globals()["Infantry"](position=spawn_pos, team=self.team, hq=self.hq)

                    if not self.hq:
                        raise ValueError("Unit has no `hq`")

                    new_unit.map_width = self.map_width
                    new_unit.map_height = self.map_height
                    self.hq.game_stats["units_created"] += 1
                    new_unit.position = Vector2(spawn_pos)
                    new_unit.rect.center = new_unit.position
                    new_unit.move_target = self.rally_point
                    friendly_units.add(new_unit)
                    all_units.add(new_unit)
                    if repeat:
                        self.production_queue.append({"unit_type": unit_type, "repeat": True})

                    self.production_timer = None

    def update(
        self,
        *,
        particles: pg.sprite.Group[GenericParticle],
        friendly_units: MutableSet[UnitIso] | None = None,
        all_units: MutableSet[UnitIso] | None = None,
        global_buildings: Iterable[UnitIso] | None = None,
        projectiles: pg.sprite.Group[Projectile],
        enemy_units: Container[UnitIso] | None = None,
        enemy_buildings: Container[UnitIso] | None = None,
    ) -> None:
        self.under_attack_timer = max(0, self.under_attack_timer - 1)
        self.under_attack = self.under_attack_timer > 0
        if self.last_shot_time > 0:
            self.last_shot_time -= 1

        if self.attack_target:
            if self.attack_target.health <= 0 or self.distance_to(self.attack_target.position) > self.sight_range + 50:
                self.attack_target = None
                if self.move_target == getattr(self.attack_target, "position", None):
                    self.move_target = None

        if not self.is_building:
            if self.move_target:
                # pyrefly: ignore [missing-attribute]
                half_w = self.rect.width / 2
                # pyrefly: ignore [missing-attribute]
                half_h = self.rect.height / 2
                mt_x = max(half_w, min(self.move_target[0], self.map_width - half_w))
                mt_y = max(half_h, min(self.move_target[1], self.map_height - half_h))
                self.move_target = (mt_x, mt_y)
                if (
                    self.path_recompute_cooldown <= 0
                    or not self.path
                    or self.path_index >= len(self.path)
                    or (
                        Vector2(self.move_target) - Vector2(self.path[-1] if self.path else self.position)
                    ).length_squared()
                    > 2500
                ):
                    blocked = set()
                    num_tiles_x = self.map_width // TILE_SIZE
                    num_tiles_y = self.map_height // TILE_SIZE
                    # pyrefly: ignore [not-iterable]
                    for b in global_buildings:
                        if b.health <= 0 or not b.is_air:
                            continue
                        # pyrefly: ignore [missing-attribute]
                        min_tx = max(0, int(b.rect.left // TILE_SIZE))
                        # pyrefly: ignore [missing-attribute]
                        max_tx = min(num_tiles_x, int(b.rect.right // TILE_SIZE) + 1)
                        # pyrefly: ignore [missing-attribute]
                        min_ty = max(0, int(b.rect.top // TILE_SIZE))
                        # pyrefly: ignore [missing-attribute]
                        max_ty = min(num_tiles_y, int(b.rect.bottom // TILE_SIZE) + 1)
                        for tx in range(min_tx, max_tx):
                            for ty in range(min_ty, max_ty):
                                blocked.add((tx, ty))

                    self.path = astar(
                        start=self.position,
                        goal=Vector2(self.move_target),
                        # pyrefly: ignore [bad-argument-type]
                        blocked=blocked,
                        tile_size=TILE_SIZE,
                        map_width=self.map_width,
                        map_height=self.map_height,
                    )
                    self.path_index = 0
                    self.path_recompute_cooldown = 12 + random.randint(0, 8)

                self.path_recompute_cooldown -= 1
                if self.path and self.path_index < len(self.path):
                    next_wp = self.path[self.path_index]
                    dir_to_wp = next_wp - self.position
                    dist_to_wp = dir_to_wp.length()
                    waypoint_threshold = 10.0
                    if dist_to_wp > waypoint_threshold:
                        move_dir = dir_to_wp.normalize()
                        self.position += move_dir * self.speed
                        self.target_body_angle = math.atan2(move_dir.y, move_dir.x)
                    else:
                        self.path_index += 1
                        if self.path_index >= len(self.path):
                            self.path = []
                            self.move_target = None

                else:
                    self.path = []
                    self.move_target = None

            if self.attack_target and self.attack_target.health > 0:
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

                self.target_turret_angle = math.atan2(dir_to_enemy.y, dir_to_enemy.x)
                if not self.attack_target.is_building and random.random() < 0.1:
                    self.position += dir_to_enemy.rotate_rad(random.uniform(-0.5, 0.5)) * self.speed * 0.2

                if dist > self.attack_range:
                    if self.attack_target.is_building:
                        chase_pos = self.get_chase_position_for_building(self.attack_target)
                        if chase_pos is not None:
                            self.move_target = chase_pos
                            self.path = []
                        else:
                            self.move_target = None
                            self.path = []
                    else:
                        self.move_target = self.attack_target.position
                        self.path = []

        if not self.attack_target:
            self.target_turret_angle = self.body_angle

        # pyrefly: ignore [missing-attribute]
        self.position.x = max(self.rect.width / 2, min(self.position.x, self.map_width - self.rect.width / 2))
        # pyrefly: ignore [missing-attribute]
        self.position.y = max(self.rect.height / 2, min(self.position.y, self.map_height - self.rect.height / 2))
        if self.is_producer and friendly_units is not None and all_units is not None:
            self._update_production(friendly_units=friendly_units, all_units=all_units)

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

        angle_diff = (self.target_body_angle - self.body_angle + math.pi) % (2 * math.pi) - math.pi
        rot_step = min(self.hull_rotation_speed, abs(angle_diff))
        if angle_diff > 0:
            self.body_angle += rot_step
        elif angle_diff < 0:
            self.body_angle -= rot_step

        angle_diff = (self.target_turret_angle - self.turret_angle + math.pi) % (2 * math.pi) - math.pi
        rot_step = min(self.turret_rotation_speed, abs(angle_diff))
        if angle_diff > 0:
            self.turret_angle += rot_step
        elif angle_diff < 0:
            self.turret_angle -= rot_step

        if not isinstance(self.rect, pg.Rect):
            raise TypeError("Unit has unexpected `rect` type")

        self.rect.center = self.position
        self.plasma_burn_particles = [p for p in self.plasma_burn_particles if p.alive() is not False]
        if self.attack_target and self.attack_target.health > 0 and self.weapons and self.last_shot_time <= 0:
            if self.attack_target.is_building:
                # pyrefly: ignore [bad-argument-type]
                closest = closest_point_on_rect(rect=self.attack_target.rect, pos=self.position)
                dist = Vector2(closest).distance_to(self.position)
                aim_target = self.attack_target
            else:
                dist = self.distance_to(self.attack_target.position)
                aim_target = self.attack_target

            if dist <= self.attack_range:
                self.shoot(target=aim_target, projectiles=projectiles, particles=particles)

    def shoot(
        self, *, target: UnitIso, projectiles: pg.sprite.Group[Projectile], particles: pg.sprite.Group[GenericParticle]
    ) -> None:
        if not self.weapons or self.last_shot_time > 0:
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
                target.speed * math.cos(target.body_angle),
                target.speed * math.sin(target.body_angle),
            )
            predicted_pos = target.position + target_vel * time_to_target
            aim_pos = predicted_pos

        if dist > self.attack_range:
            return

        vec = aim_pos - self.position
        if vec.length() == 0:
            return

        direction = vec.normalize()
        proj = Projectile(self.position, direction, self.current_weapon.damage, self.team, self.current_weapon)
        projectiles.add(proj)  # FIXME: crash here: AttributeError: 'NoneType' object has no attribute 'add'
        self.last_shot_time = self.current_weapon.cooldown
        create_explosion_iso(position=self.position, particles=particles, team=self.team, count=3)


class Infantry(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Grenadier(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Marksman(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class RocketSoldier(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Tank(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class HeavyTank(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class TankDestroyer(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class MachineGunVehicle(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class RocketArtillery(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class AttackHelicopter(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)


class Headquarters(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
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

    def place_building(self, position: Point, unit_cls: type, all_buildings: MutableSet[UnitIso]) -> None:
        all_buildings_list = list(all_buildings)
        if is_valid_building_position(
            position=position, team=self.team, new_building_cls=unit_cls, buildings=all_buildings_list
        ):
            building = unit_cls(position=position, team=self.team, hq=self)
            building.map_width = self.map_width
            building.map_height = self.map_height
            if isinstance(building, WarFactory | Barracks | Hangar):
                building.parent_hq = self

            all_buildings.add(building)
            self.game_stats["buildings_constructed"] += 1
            self.credits -= building.cost
            self.pending_building = None


class PowerPlant(UnitIso):
    def __init__(self, *, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)

    def draw(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        cos = math.cos(self.body_angle)
        sin = math.sin(self.body_angle)
        main_w = w * 1.2
        main_d = d * 1.2
        main_h = h * 0.5
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=main_w,
            d=main_d,
            h=main_h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        for offset in [-w * 0.3, w * 0.3]:
            stack_x = pos.x + offset * cos
            stack_y = pos.y + offset * sin
            stack_base = (stack_x, stack_y, base_z + main_h)
            stack_top = (stack_x, stack_y, stack_base[2] + h * 0.6)
            p_stack_base = camera.world_to_iso_3d(*stack_base, zoom)
            p_stack_top = camera.world_to_iso_3d(*stack_top, zoom)
            pg.draw.line(surface, pg.Color(80, 80, 80), p_stack_base, p_stack_top, int(4 * zoom))
            pg.draw.circle(
                surface,
                pg.Color(60, 60, 60),
                (int(p_stack_top[0]), int(p_stack_top[1])),
                int(3 * zoom),
            )
        tower_w = w * 0.8
        tower_d = d * 0.8
        tower_h = h * 0.7
        tower_base_z = base_z
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=tower_w,
            d=tower_d,
            h=tower_h,
            angle=self.body_angle,
            base_z=tower_base_z,
            team_color=pg.Color(150, 150, 150),
            side_color=side_color,
            roof_color=pg.Color(150, 150, 150),
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
        )
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)


class Refinery(UnitIso):
    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.radius = 60

    def draw(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        cos = math.cos(self.body_angle)
        sin = math.sin(self.body_angle)
        main_w = w * 1.0
        main_d = d * 1.0
        main_h = h * 0.4
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=main_w,
            d=main_d,
            h=main_h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        for i, offset in enumerate([-w * 0.4, 0, w * 0.4]):
            tank_x = pos.x + offset * cos
            tank_y = pos.y + offset * sin
            tank_base = (tank_x, tank_y, base_z)
            tank_top = (tank_x, tank_y, base_z + h * 0.6)
            p_tank_base = camera.world_to_iso_3d(*tank_base, zoom)
            p_tank_top = camera.world_to_iso_3d(*tank_top, zoom)
            radius = int(w * 0.12 * zoom)
            pg.draw.circle(surface, pg.Color(100, 100, 100), (int(p_tank_base[0]), int(p_tank_base[1])), radius)
            pg.draw.circle(surface, pg.Color(80, 80, 80), (int(p_tank_top[0]), int(p_tank_top[1])), radius)
            pg.draw.line(surface, outline_color, p_tank_base, p_tank_top, int(2 * zoom))
        tower_x = pos.x
        tower_y = pos.y + d * 0.5 * sin
        tower_base = (tower_x, tower_y, base_z)
        tower_top = (tower_x, tower_y, base_z + h * 0.8)
        p_tower_base = camera.world_to_iso_3d(*tower_base, zoom)
        p_tower_top = camera.world_to_iso_3d(*tower_top, zoom)
        pg.draw.line(surface, pg.Color(120, 120, 120), p_tower_base, p_tower_top, int(5 * zoom))
        pipe_z = base_z + h * 0.3
        for i in range(3):
            start_x = pos.x - w * 0.4 * cos + i * w * 0.4 * cos
            start_y = pos.y - w * 0.4 * sin + i * w * 0.4 * sin
            end_x = tower_x
            end_y = tower_y
            p_start = camera.world_to_iso_3d(start_x, start_y, pipe_z, zoom)
            p_end = camera.world_to_iso_3d(end_x, end_y, pipe_z, zoom)
            pg.draw.line(surface, pg.Color(150, 150, 150), p_start, p_end, int(2 * zoom))
        flare_x = pos.x + w * 0.6 * cos
        flare_y = pos.y + w * 0.6 * sin
        flare_base = (flare_x, flare_y, base_z)
        flare_top = (flare_x, flare_y, base_z + h * 1.0)
        p_flare_base = camera.world_to_iso_3d(*flare_base, zoom)
        p_flare_top = camera.world_to_iso_3d(*flare_top, zoom)
        pg.draw.line(surface, pg.Color(100, 100, 100), p_flare_base, p_flare_top, int(3 * zoom))
        flame_points = [
            p_flare_top,
            (p_flare_top[0] - 5 * zoom, p_flare_top[1] - 3 * zoom),
            (p_flare_top[0] + 5 * zoom, p_flare_top[1] - 3 * zoom),
        ]
        pg.draw.polygon(surface, pg.Color(255, 100, 0), flame_points)
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)


class Turret(UnitIso):
    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)

    def draw(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        cos = math.cos(self.body_angle)
        sin = math.sin(self.body_angle)
        base_w = w * 1.0
        base_d = d * 1.0
        base_h = h * 0.4
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=base_w,
            d=base_d,
            h=base_h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        mount_w = w * 0.6
        mount_d = d * 0.6
        mount_h = h * 0.2
        mount_base_z = base_z + base_h
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=mount_w,
            d=mount_d,
            h=mount_h,
            angle=self.turret_angle,
            base_z=mount_base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=pg.Color(120, 120, 120),
            outline_color=outline_color,
            zoom=zoom,
            is_turret=True,
        )
        barrel_length = w * 1.5
        barrel_base_z = mount_base_z + mount_h / 2
        cos_t = math.cos(self.turret_angle)
        sin_t = math.sin(self.turret_angle)
        barrel_start_x = pos.x + (d * 0.2) * cos_t
        barrel_start_y = pos.y + (d * 0.2) * sin_t
        barrel_end_x = barrel_start_x + barrel_length * cos_t
        barrel_end_y = barrel_start_y + barrel_length * sin_t
        p_barrel_start = camera.world_to_iso_3d(barrel_start_x, barrel_start_y, barrel_base_z, zoom)
        p_barrel_end = camera.world_to_iso_3d(barrel_end_x, barrel_end_y, barrel_base_z, zoom)
        barrel_color = tuple(min(255, c + 40) for c in _team_color)
        pg.draw.line(surface, barrel_color, p_barrel_start, p_barrel_end, int(4 * zoom))
        pg.draw.circle(
            surface,
            pg.Color(100, 100, 100),
            (int(p_barrel_end[0]), int(p_barrel_end[1])),
            int(2 * zoom),
        )
        for off in [-w * 0.2, w * 0.2]:
            port_x = pos.x + off * cos
            port_y = pos.y + off * sin
            p_port = camera.world_to_iso_3d(port_x, port_y, base_z + base_h * 0.5, zoom)
            pg.draw.rect(
                surface,
                pg.Color(100, 150, 200),
                (
                    int(p_port[0] - 2 * zoom),
                    int(p_port[1] - 1 * zoom),
                    int(4 * zoom),
                    int(2 * zoom),
                ),
            )
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)


class Barracks(UnitIso):
    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.parent_hq = None

    def draw(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        cos = math.cos(self.body_angle)
        sin = math.sin(self.body_angle)
        main_w = w * 1.4
        main_d = d * 0.8
        main_h = h * 0.6
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=main_w,
            d=main_d,
            h=main_h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        roof_h = h * 0.2
        roof_base_z = base_z + main_h
        ridge_x = pos.x
        ridge_y = pos.y
        ridge_z = roof_base_z + roof_h
        p_ridge = camera.world_to_iso_3d(ridge_x, ridge_y, ridge_z, zoom)
        left_base_x = pos.x - main_w * 0.5 * cos
        left_base_y = pos.y - main_w * 0.5 * sin
        p_left_base = camera.world_to_iso_3d(left_base_x, left_base_y, roof_base_z, zoom)
        pg.draw.polygon(
            surface,
            pg.Color(100, 100, 100),
            [
                p_left_base,
                p_ridge,
                camera.world_to_iso_3d(pos.x, pos.y - d * 0.4 * sin, roof_base_z, zoom),
            ],
        )
        right_base_x = pos.x + main_w * 0.5 * cos
        right_base_y = pos.y + main_w * 0.5 * sin
        p_right_base = camera.world_to_iso_3d(right_base_x, right_base_y, roof_base_z, zoom)
        pg.draw.polygon(
            surface,
            pg.Color(100, 100, 100),
            [
                p_right_base,
                p_ridge,
                camera.world_to_iso_3d(pos.x, pos.y + d * 0.4 * sin, roof_base_z, zoom),
            ],
        )
        door_w = w * 0.4
        door_h = h * 0.4
        door_center_x = pos.x - d * 0.5 * cos
        door_center_y = pos.y - d * 0.5 * sin
        door_bl = (door_center_x - door_w / 2, door_center_y, base_z)
        door_br = (door_center_x + door_w / 2, door_center_y, base_z)
        door_tl = (door_center_x - door_w / 2, door_center_y, base_z + door_h)
        door_tr = (door_center_x + door_w / 2, door_center_y, base_z + door_h)
        p_door_bl = camera.world_to_iso_3d(*door_bl, zoom)
        p_door_br = camera.world_to_iso_3d(*door_br, zoom)
        p_door_tl = camera.world_to_iso_3d(*door_tl, zoom)
        p_door_tr = camera.world_to_iso_3d(*door_tr, zoom)
        pg.draw.polygon(surface, pg.Color(50, 50, 50), [p_door_bl, p_door_br, p_door_tr, p_door_tl])
        for level in [base_z + h * 0.3, base_z + h * 0.6]:
            for off in [-w * 0.3, w * 0.3]:
                win_x = pos.x + off * cos
                win_y = pos.y + off * sin
                p_win = camera.world_to_iso_3d(win_x, win_y, level, zoom)
                pg.draw.rect(
                    surface,
                    pg.Color(150, 200, 255),
                    (
                        int(p_win[0] - 3 * zoom),
                        int(p_win[1] - 2 * zoom),
                        int(6 * zoom),
                        int(4 * zoom),
                    ),
                )
        flag_x = pos.x + w * 0.6 * cos
        flag_y = pos.y + w * 0.6 * sin
        flag_base_z = roof_base_z + roof_h
        flag_top_z = flag_base_z + h * 0.3
        p_flag_base = camera.world_to_iso_3d(flag_x, flag_y, flag_base_z, zoom)
        p_flag_top = camera.world_to_iso_3d(flag_x, flag_y, flag_top_z, zoom)
        pg.draw.line(surface, pg.Color(100, 100, 100), p_flag_base, p_flag_top, int(2 * zoom))
        flag_end_x = flag_x + w * 0.2 * cos
        flag_end_y = flag_y + w * 0.2 * sin
        p_flag_end = camera.world_to_iso_3d(flag_end_x, flag_end_y, flag_top_z, zoom)
        pg.draw.line(surface, _team_color, p_flag_top, p_flag_end, int(4 * zoom))
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)


class WarFactory(UnitIso):
    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.parent_hq = None

    def draw(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        cos = math.cos(self.body_angle)
        sin = math.sin(self.body_angle)
        main_w = w * 1.3
        main_d = d * 1.2
        main_h = h * 0.5
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=main_w,
            d=main_d,
            h=main_h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        for off in [-1, 1]:
            attach_x = pos.x + off * (main_w * 0.3) * cos
            attach_y = pos.y + off * (main_w * 0.3) * sin
            attach_base = (attach_x, attach_y, base_z + main_h * 0.2)
            self._draw_rotated_box(
                surface=surface,
                camera=camera,
                w=w * 0.4,
                d=d * 0.6,
                h=h * 0.3,
                angle=self.body_angle,
                base_z=attach_base[2],
                team_color=pg.Color(90, 90, 90),
                side_color=side_color,
                roof_color=pg.Color(90, 90, 90),
                outline_color=outline_color,
                zoom=zoom,
                is_turret=False,
            )
        for off in [-w * 0.2, w * 0.2]:
            stack_x = pos.x + off * cos
            stack_y = pos.y + off * sin
            stack_base = (stack_x, stack_y, base_z + main_h)
            stack_top = (stack_x, stack_y, stack_base[2] + h * 0.7)
            p_stack_base = camera.world_to_iso_3d(*stack_base, zoom)
            p_stack_top = camera.world_to_iso_3d(*stack_top, zoom)
            radius = int(3 * zoom)
            pg.draw.circle(surface, pg.Color(70, 70, 70), (int(p_stack_base[0]), int(p_stack_base[1])), radius)
            pg.draw.circle(surface, pg.Color(60, 60, 60), (int(p_stack_top[0]), int(p_stack_top[1])), radius)
            pg.draw.line(surface, outline_color, p_stack_base, p_stack_top, int(2 * zoom))
        crane_z = base_z + main_h + h * 0.1
        crane_start_x = pos.x - main_w * 0.5 * cos
        crane_start_y = pos.y - main_w * 0.5 * sin
        crane_end_x = pos.x + main_w * 0.5 * cos
        crane_end_y = pos.y + main_w * 0.5 * sin
        p_crane_start = camera.world_to_iso_3d(crane_start_x, crane_start_y, crane_z, zoom)
        p_crane_end = camera.world_to_iso_3d(crane_end_x, crane_end_y, crane_z, zoom)
        pg.draw.line(surface, pg.Color(100, 100, 100), p_crane_start, p_crane_end, int(5 * zoom))
        door_w = w * 0.6
        door_h = h * 0.4
        door_center_x = pos.x - d * 0.6 * cos
        door_center_y = pos.y - d * 0.6 * sin
        door_bl = (door_center_x - door_w / 2, door_center_y, base_z)
        door_br = (door_center_x + door_w / 2, door_center_y, base_z)
        door_tl = (door_center_x - door_w / 2, door_center_y, base_z + door_h)
        door_tr = (door_center_x + door_w / 2, door_center_y, base_z + door_h)
        p_door_bl = camera.world_to_iso_3d(*door_bl, zoom)
        p_door_br = camera.world_to_iso_3d(*door_br, zoom)
        p_door_tl = camera.world_to_iso_3d(*door_tl, zoom)
        p_door_tr = camera.world_to_iso_3d(*door_tr, zoom)
        pg.draw.polygon(surface, pg.Color(40, 40, 40), [p_door_bl, p_door_br, p_door_tr, p_door_tl])
        for level in [base_z + h * 0.2, base_z + h * 0.4]:
            for off in [-w * 0.4, 0, w * 0.4]:
                win_x = pos.x + off * cos
                win_y = pos.y + off * sin
                p_win = camera.world_to_iso_3d(win_x, win_y, level, zoom)
                pg.draw.rect(
                    surface,
                    pg.Color(150, 200, 255),
                    (
                        int(p_win[0] - 4 * zoom),
                        int(p_win[1] - 2 * zoom),
                        int(8 * zoom),
                        int(4 * zoom),
                    ),
                )
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)


class Hangar(UnitIso):
    def __init__(self, position: Point, team: Team, hq: Headquarters | None = None) -> None:
        super().__init__(position=position, team=team, hq=hq)
        self.parent_hq = None

    def draw(self, *, surface: pg.Surface, camera: CameraIso, mouse_pos: Point | None = None) -> None:
        if self.health <= 0:
            return

        _team_color = team_to_color[self.team]
        zoom = camera.zoom
        w, d = self.size
        h = self.height
        pos = self.position
        base_z = 0
        side_color = tuple(max(0, c - 50) for c in _team_color)
        outline_color = pg.Color(0, 0, 0)
        p_bottom = []
        cos = math.cos(self.body_angle)
        sin = math.sin(self.body_angle)
        hangar_w = w * 1.6
        hangar_d = d * 1.4
        hangar_h = h * 0.3
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=hangar_w,
            d=hangar_d,
            h=hangar_h,
            angle=self.body_angle,
            base_z=base_z,
            team_color=_team_color,
            side_color=side_color,
            roof_color=_team_color,
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
            p_bottom=p_bottom,
        )
        roof_h = h * 0.4
        roof_base_z = base_z + hangar_h
        for side in [-1, 1]:
            roof_side_x = pos.x + side * (hangar_w * 0.5) * cos
            roof_side_y = pos.y + side * (hangar_w * 0.5) * sin
            p_roof_side = camera.world_to_iso_3d(roof_side_x, roof_side_y, roof_base_z + roof_h, zoom)
            p_base_side = camera.world_to_iso_3d(roof_side_x, roof_side_y, roof_base_z, zoom)
            pg.draw.line(surface, pg.Color(120, 120, 120), p_base_side, p_roof_side, int(4 * zoom))
        p_ridge_left = camera.world_to_iso_3d(
            pos.x - hangar_d * 0.2 * sin,
            pos.y + hangar_d * 0.2 * cos,
            roof_base_z + roof_h * 1.2,
            zoom,
        )
        p_ridge_right = camera.world_to_iso_3d(
            pos.x + hangar_d * 0.2 * sin,
            pos.y - hangar_d * 0.2 * cos,
            roof_base_z + roof_h * 1.2,
            zoom,
        )
        pg.draw.line(surface, pg.Color(100, 100, 100), p_ridge_left, p_ridge_right, int(5 * zoom))
        door_w = hangar_w * 0.4
        door_h = h * 0.5
        door_center_x = pos.x - hangar_d * 0.5 * cos
        door_center_y = pos.y - hangar_d * 0.5 * sin
        for off in [-door_w * 0.25, door_w * 0.25]:
            d_center_x = door_center_x + off
            d_bl = (d_center_x - door_w / 2, door_center_y, base_z)
            d_br = (d_center_x + door_w / 2, door_center_y, base_z)
            d_tl = (d_center_x - door_w / 2, door_center_y, base_z + door_h)
            d_tr = (d_center_x + door_w / 2, door_center_y, base_z + door_h)
            p_d_bl = camera.world_to_iso_3d(*d_bl, zoom)
            p_d_br = camera.world_to_iso_3d(*d_br, zoom)
            p_d_tl = camera.world_to_iso_3d(*d_tl, zoom)
            p_d_tr = camera.world_to_iso_3d(*d_tr, zoom)
            pg.draw.polygon(surface, pg.Color(60, 60, 60), [p_d_bl, p_d_br, p_d_tr, p_d_tl])
        pillar_offsets = [
            (-w * 0.3, -d * 0.3),
            (w * 0.3, -d * 0.3),
            (w * 0.3, d * 0.3),
            (-w * 0.3, d * 0.3),
        ]
        for off_x, off_y in pillar_offsets:
            pillar_x = pos.x + off_x * cos - off_y * sin
            pillar_y = pos.y + off_x * sin + off_y * cos
            p_pillar_base = camera.world_to_iso_3d(pillar_x, pillar_y, base_z, zoom)
            p_pillar_top = camera.world_to_iso_3d(pillar_x, pillar_y, base_z + hangar_h, zoom)
            pg.draw.line(surface, pg.Color(80, 80, 80), p_pillar_base, p_pillar_top, int(3 * zoom))
        tower_x = pos.x + w * 0.7 * cos
        tower_y = pos.y + w * 0.7 * sin
        tower_base = (tower_x, tower_y, base_z)
        self._draw_rotated_box(
            surface=surface,
            camera=camera,
            w=w * 0.3,
            d=d * 0.3,
            h=h * 0.6,
            angle=self.body_angle,
            base_z=tower_base[2],
            team_color=pg.Color(100, 80, 60),
            side_color=side_color,
            roof_color=pg.Color(100, 80, 60),
            outline_color=outline_color,
            zoom=zoom,
            is_turret=False,
        )
        apron_center = camera.world_to_iso_3d(pos.x, pos.y, base_z + hangar_h * 0.5, zoom)
        pg.draw.circle(
            surface,
            pg.Color(255, 255, 255, 80),
            (int(apron_center[0]), int(apron_center[1])),
            int(w * 0.8 * zoom),
            3,
        )
        if self.selected:
            pg.draw.polygon(surface, (255, 255, 0), p_bottom, int(2 * zoom))
        self.draw_health_bar(surface, camera, mouse_pos)
        for particle in self.plasma_burn_particles:
            particle.draw_iso(surface, camera)
