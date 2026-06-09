"""Gamedata functions not specific to 2d/iso game."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.team import Team

if TYPE_CHECKING:
    from collections.abc import Sequence


def determine_sides(game_mode: str) -> tuple[list[Team], list[Team]]:
    player_side: list[Team] = []
    enemy_side: list[Team] = []
    if game_mode == "1v1":
        player_side = [Team.RED]
        enemy_side = [Team.GREEN]
    elif game_mode == "2v2":
        player_side = [Team.RED, Team.BLUE]
        enemy_side = [Team.ORANGE, Team.YELLOW]
    elif game_mode == "3v3":
        player_side = [Team.RED, Team.BLUE, Team.CYAN]
        enemy_side = [Team.MAGENTA, Team.ORANGE, Team.YELLOW]
    elif game_mode == "4v4":
        player_side = [Team.RED, Team.BLUE, Team.GREEN, Team.CYAN]
        enemy_side = [Team.MAGENTA, Team.ORANGE, Team.YELLOW, Team.GREY]
    elif game_mode == "4ffa":
        player_side = [Team.RED]
        enemy_side = [Team.BLUE, Team.GREEN, Team.CYAN]

    return player_side, enemy_side


def get_starting_positions(
    *, map_width: int, map_height: int, num_players: int, edge_dist: int
) -> Sequence[tuple[float, float]]:
    """Generates balanced starting positions around the map edges for multiple players.

    :param map_width: Width of the map.
    :param map_height: Height of the map.
    :param num_players: Number of players.
    :param edge_dist: Distance from the edge.
    :return: List of starting position tuples.
    """
    half_w = map_width / 2
    half_h = map_height / 2

    base_positions = [
        (half_w, edge_dist),
        (map_width - edge_dist, edge_dist),
        (map_width - edge_dist, half_h),
        (map_width - edge_dist, map_height - edge_dist),
        (half_w, map_height - edge_dist),
        (edge_dist, map_height - edge_dist),
        (edge_dist, half_h),
        (edge_dist, edge_dist),
    ]

    step = max(1, 8 // num_players)
    selected_positions = base_positions[::step][:num_players]

    while len(selected_positions) < num_players:
        selected_positions.append(base_positions[len(selected_positions) % 8])

    return selected_positions
