from CondaRTS2DVersion import GameManager


def test_create_manager() -> None:
    """Test that a GameManager can be instantiated."""
    # arrange
    # act
    manager = GameManager()
    # assert
    assert manager
