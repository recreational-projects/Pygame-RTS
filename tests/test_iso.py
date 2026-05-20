import pygame as pg

from CondaRTSIsometricVersion import GameManager
from modules.data_iso import SCREEN_HEIGHT, SCREEN_WIDTH


def test_create_manager() -> None:
    """Test that a GameManager can be instantiated."""
    # arrange
    pg.init()
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pg.time.Clock()
    # act
    manager = GameManager(screen, clock)
    # assert
    assert manager
