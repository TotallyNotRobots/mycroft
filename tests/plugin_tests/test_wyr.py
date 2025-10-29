from plugins import wyr


def test_wyr() -> None:
    assert wyr.wyr() == "rrrather.com has been retired"
