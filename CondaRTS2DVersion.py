"""Runs the 2d version of the game."""

from modules.game_manager_2d import GameManager2d


def main() -> None:
    """Run the game."""
    manager = GameManager2d()
    manager.run()


if __name__ == "__main__":
    main()
