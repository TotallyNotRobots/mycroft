from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from plugins import cats

if TYPE_CHECKING:
    from responses import RequestsMock


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
