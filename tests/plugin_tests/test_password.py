import pytest

from plugins import password


@pytest.mark.asyncio
async def test_load(mock_bot_factory, tmp_path) -> None:
    mock_bot = mock_bot_factory(base_dir=tmp_path)
    file = mock_bot.data_path / "password_words.txt"
    file.parent.mkdir()
    file.write_text("foo\nbar", encoding="utf-8")

    password.load_words(mock_bot)
    assert len(password.common_words) == 2
