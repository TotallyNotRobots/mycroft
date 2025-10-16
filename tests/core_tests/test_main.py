import logging
from unittest.mock import patch

import pytest

from cloudbot.__main__ import async_main


@pytest.mark.asyncio
async def test_main():
    async def run():
        return False

    with (
        patch("cloudbot.__main__.CloudBot") as mocked_bot,
        patch(
            "cloudbot.__main__.upgrade_db_schema"
        ) as mocked_upgrade_db_schema,
    ):
        mocked_bot().run = run
        await async_main()
        assert logging._srcfile is None
        assert not logging.logThreads
        assert not logging.logProcesses
        mocked_upgrade_db_schema.assert_called_once()
