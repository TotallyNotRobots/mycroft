from plugins import lmgtfy


def test_lmgtfy(patch_try_shorten) -> None:
    assert lmgtfy.lmgtfy("foo bar") == "http://lmgtfy.com/?q=foo%20bar"
