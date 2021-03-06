import asyncio
from unittest.mock import MagicMock, call, patch

from cloudbot.client import Client


class Bot(MagicMock):
    loop = asyncio.get_event_loop()


class MockClient(Client):  # pylint: disable=abstract-method
    _connected = False

    def __init__(self, bot, *args, **kwargs):
        super().__init__(bot, "TestClient", *args, **kwargs)
        self.active = True

    @property
    def connected(self):
        return self._connected

    async def connect(self, timeout=None):
        self._connected = True


class FailingMockClient(MockClient):  # pylint: disable=abstract-method
    def __init__(self, *args, fail_count=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_count = fail_count

    async def connect(self, timeout=None):
        if self.fail_count is not None and self.fail_count > 0:
            self.fail_count -= 1
            raise ValueError("This is a test")


def test_reload():
    client = MockClient(Bot(), "foo", "foobot", channels=["#foo"])
    client.permissions = MagicMock()
    client.reload()
    assert client.permissions.mock_calls == [call.reload()]


def test_client_no_config():
    client = MockClient(Bot(), "foo", "foobot", channels=["#foo"])
    assert client.config.get("a") is None


def test_client():
    client = MockClient(
        Bot(), "foo", "foobot", channels=["#foo"], config={"name": "foo"}
    )

    assert client.config_channels == ["#foo"]
    assert client.config["name"] == "foo"
    assert client.type == "TestClient"

    assert client.active is True
    client.active = False
    assert client.active is False
    client.active = True

    client.loop.run_until_complete(client.try_connect())


def test_client_connect_exc():
    with patch("random.randrange", return_value=1):
        client = FailingMockClient(
            Bot(),
            "foo",
            "foobot",
            channels=["#foo"],
            config={"name": "foo"},
            fail_count=1,
        )
        client.loop.run_until_complete(client.try_connect())


def test_auto_reconnect():
    client = MockClient(
        Bot(), "foo", "foobot", channels=["#foo"], config={"name": "foo"}
    )

    client.active = False
    assert client.active is False
    assert client.connected is False
    client.loop.run_until_complete(client.auto_reconnect())
    assert client.connected is False

    client.active = True
    assert client.active is True
    assert client.connected is False
    client.loop.run_until_complete(client.auto_reconnect())
    assert client.connected is True
