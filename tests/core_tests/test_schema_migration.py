from unittest.mock import patch

import pytest

from cloudbot.__main__ import upgrade_db_schema
from tests.core_tests.test_bot import config_mock
from tests.util.mock_db import MockDB


@pytest.mark.asyncio
async def test_empty_init(mock_db: MockDB) -> None:
    with (
        patch(
            "cloudbot.bot.Config",
            new=config_mock(
                {
                    "connections": [
                        {
                            "type": "irc",
                            "name": "foobar",
                            "nick": "TestBot",
                            "channels": [],
                            "connection": {"server": "irc.example.com"},
                        }
                    ],
                }
            ),
        ),
        patch("cloudbot.bot.create_engine") as mocked,
    ):
        mocked.return_value = mock_db.engine
        upgrade_db_schema()
