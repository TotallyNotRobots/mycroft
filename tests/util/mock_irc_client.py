from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from cloudbot.clients.irc import IrcClient

if TYPE_CHECKING:
    from unittest.mock import _CallList

    from cloudbot.bot import AbstractBot


class MockIrcClient(IrcClient):
    def __init__(
        self, *, bot: AbstractBot, nick=None, name=None, config=None
    ) -> None:
        config = config or {}
        config.setdefault("connection", {}).setdefault("server", "foo.invalid")
        super().__init__(
            bot=bot,
            _type="irc",
            name=name or "testconn",
            nick=nick or "TestBot",
            config=config,
        )
        self._mock = MagicMock(spec=IrcClient)
        self.ready = True
        self.active = True

    @property
    def connected(self) -> bool:
        return True

    def reload(self):
        return self._mock.reload()

    async def try_connect(self):
        return self._mock.try_connect()

    def is_nick_valid(self, nick) -> bool:
        return True

    def connect(self, timeout=None):
        return self._mock.connect()

    def send(self, line, log=True):
        return self._mock.send(line)

    def mock_calls(self) -> _CallList:
        return self._mock.mock_calls
