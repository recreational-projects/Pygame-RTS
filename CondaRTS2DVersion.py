"""Runs the 2d version of the game."""

from modules.game_manager import GameManager2d


def main() -> None:
    """Run the game."""
    manager = GameManager2d()
    manager.run()


if __name__ == "__main__":
    main()
