import pygame as pg

from CondaRTSIsometricVersion import GameManager
from modules.data_iso import SCREEN_HEIGHT, SCREEN_WIDTH


def test_create_manager() -> None:
    # arrange
    pg.init()
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pg.time.Clock()
    font_large = pg.font.SysFont(None, 72)
    font_medium = pg.font.SysFont(None, 28)
    # act
    manager = GameManager(screen, clock, font_large, font_medium)
    # assert
    assert manager
