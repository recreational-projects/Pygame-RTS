from CondaRTS2DVersion import GameManager


def test_create_manager() -> None:
    # arrange
    # act
    manager = GameManager()
    # assert
    assert manager
