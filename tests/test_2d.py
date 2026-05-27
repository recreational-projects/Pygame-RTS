from CondaRTS2DVersion import GameManager
from modules.data_2d import UNIT_CLASSES
from modules.unit_stats_2d import UnitStats


def test_create_manager() -> None:
    """Test that a GameManager can be instantiated."""
    # arrange
    # act
    manager = GameManager()
    # assert
    assert manager


def test_structure_unit_stats() -> None:
    """Test that all unit stats can be loaded and structured from data."""
    # arrange
    # act
    unit_stats = [UnitStats.from_data(unit_cls_str) for unit_cls_str in UNIT_CLASSES]
    # assert
    assert len(unit_stats) == len(UNIT_CLASSES)
