from unittest.mock import MagicMock

from responses import RequestsMock

from plugins import cats


def test_cats(mock_requests: RequestsMock) -> None:
    mock_requests.add(
        "GET",
        "https://catfact.ninja/fact?max_length=100",
        json={"fact": "foobar"},
    )
    bot = MagicMock(user_agent="user agent")
    reply = MagicMock()
    assert cats.cats(reply, bot) == "foobar"
    assert bot.mock_calls == []
    assert reply.mock_calls == []
