import pygame as pg

from CondaRTSIsometricVersion import GameManager
from modules.data_iso import SCREEN_HEIGHT, SCREEN_WIDTH, UNIT_CLASSES
from modules.unit_stats.unit_stats_iso import UnitStatsIso


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


def test_structure_unit_stats() -> None:
    """Test that all unit stats can be loaded and structured from data."""
    # arrange
    # act
    unit_stats = [UnitStatsIso.from_data(unit_cls_str) for unit_cls_str in UNIT_CLASSES]
    # assert
    assert len(unit_stats) == len(UNIT_CLASSES)
