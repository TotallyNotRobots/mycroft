from unittest.mock import MagicMock

from cloudbot.clients.irc import IrcClient


class MockIrcClient(IrcClient):
    def __init__(self, bot, name, nick, config) -> None:
        super().__init__(bot, "irc", name, nick, config=config)
        self.connect = MagicMock()  # type: ignore[method-assign]
        self.send = MagicMock()  # type: ignore[method-assign]
