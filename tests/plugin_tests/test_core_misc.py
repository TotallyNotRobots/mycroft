from typing import cast
from unittest.mock import MagicMock, call

import pytest
from irclib.parser import ParamList

from cloudbot.client import Client
from plugins.core import core_misc
from tests.util.mock_irc_client import MockIrcClient


class MockClient(Client):
    def __init__(self, bot, *args, **kwargs) -> None:
        super().__init__(bot, "TestClient", *args, **kwargs)
        self.active = True
        self.join = MagicMock()  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_do_joins(mock_bot_factory, mock_db) -> None:
    client = MockClient(
        mock_bot_factory(db=mock_db),
        "foo",
        "foobot",
        channels=[
            "#foo",
            "#bar key",
            ["#baz", "key1"],
            {"name": "#chan"},
            {"name": "#chan1", "key": "key2"},
        ],
    )

    client.ready = True
    client.config["join_throttle"] = 0

    await core_misc.do_joins(client)

    assert cast("MagicMock", client.join).mock_calls == [
        call("#foo", None),
        call("#bar", "key"),
        call("#baz", "key1"),
        call("#chan", None),
        call("#chan1", "key2"),
    ]


@pytest.mark.asyncio
async def test_invite_join(mock_bot_factory, mock_db) -> None:
    bot = mock_bot_factory(db=mock_db)
    conn = MockIrcClient(
        bot, "fooconn", "foo", {"connection": {"server": "host.invalid"}}
    )
    core_misc.invite(ParamList("foo", "#bar"), conn)

    assert cast("MagicMock", conn.send).mock_calls == [call("JOIN #bar")]


@pytest.mark.asyncio
async def test_invite_join_disabled(mock_bot_factory, mock_db) -> None:
    bot = mock_bot_factory(db=mock_db)
    conn = MockIrcClient(
        bot,
        "fooconn",
        "foo",
        {"connection": {"server": "host.invalid"}, "invite_join": False},
    )
    core_misc.invite(ParamList("foo", "#bar"), conn)

    assert cast("MagicMock", conn.send).mock_calls == []


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    "config,calls",
    [
        ({}, []),
        ({"log_channel": "#foo"}, [call("JOIN #foo")]),
        ({"log_channel": "#foo bar"}, [call("JOIN #foo bar")]),
        ({"log_channel": "#foo bar baz"}, [call("JOIN #foo :bar baz")]),
        (
            {"nickserv": {"nickserv_password": "foobar"}},
            [call("PRIVMSG nickserv :IDENTIFY foobar")],
        ),
        (
            {
                "nickserv": {
                    "nickserv_password": "foobar",
                    "nickserv_user": "foo",
                }
            },
            [call("PRIVMSG nickserv :IDENTIFY foo foobar")],
        ),
        (
            {
                "nickserv": {
                    "enabled": False,
                    "nickserv_password": "foobar",
                    "nickserv_user": "foo",
                }
            },
            [],
        ),
        ({"mode": "+I"}, [call("MODE foobot +I")]),
    ],
)
async def test_on_connect(config, calls, mock_db) -> None:
    bot = MagicMock()
    config = config.copy()
    config.setdefault("connection", {}).setdefault("server", "host.invalid")
    conn = MockIrcClient(bot, "fooconn", "foobot", config)

    res = await core_misc.onjoin(conn, bot)

    assert res is None

    assert cast("MagicMock", conn.send).mock_calls == calls
