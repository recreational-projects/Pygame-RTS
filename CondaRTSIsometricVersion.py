"""Runs the isometric version of the game."""

from __future__ import annotations

import pygame as pg

from modules.game_manager_iso import GameManagerIso


def main() -> None:
    """Run the game."""
    pg.init()
    pg.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
    manager = GameManagerIso()
    manager.run()


if __name__ == "__main__":
    main()
