from plugins import dig


def test_dig() -> None:
    s = "The jsondns API no longer exists. This command is retired."
    assert dig.dig() == s
