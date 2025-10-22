import time
from unittest.mock import MagicMock

import responses
from responses.matchers import query_param_matcher

from cloudbot.event import CommandEvent
from plugins import time_plugin
from tests.util import wrap_hook_response


def test_time_command_no_key(mock_requests, freeze_time, mock_api_keys):
    mock_api_keys.config.get_api_key.return_value = None
    conn = MagicMock()
    event = CommandEvent(
        text="New York",
        triggered_command="time",
        cmd_prefix=".",
        hook=MagicMock(),
        channel="#foo",
        nick="bar",
        conn=conn,
        bot=conn.bot,
    )

    assert wrap_hook_response(time_plugin.time_command, event) == [
        (
            "return",
            "This command requires a Google Developers Console API key.",
        ),
    ]
    assert conn.mock_calls == []


def test_time_command_api_disabled(mock_requests, freeze_time, mock_api_keys):
    conn = MagicMock()
    event = CommandEvent(
        text="New York",
        triggered_command="time",
        cmd_prefix=".",
        hook=MagicMock(),
        channel="#foo",
        nick="bar",
        conn=conn,
        bot=conn.bot,
    )

    mock_requests.add(
        responses.GET,
        "https://maps.googleapis.com/maps/api/geocode/json",
        json={
            "status": "REQUEST_DENIED",
        },
        match=[
            query_param_matcher(
                {
                    "address": "New York",
                    "key": "APIKEY",
                }
            )
        ],
    )

    assert wrap_hook_response(time_plugin.time_command, event) == [
        (
            "return",
            "The geocoding API is off in the Google Developers Console.",
        ),
    ]
    assert conn.mock_calls == []


def test_time_command_api_quota_limit(
    mock_requests, freeze_time, mock_api_keys
):
    conn = MagicMock()
    event = CommandEvent(
        text="New York",
        triggered_command="time",
        cmd_prefix=".",
        hook=MagicMock(),
        channel="#foo",
        nick="bar",
        conn=conn,
        bot=conn.bot,
    )

    mock_requests.add(
        responses.GET,
        "https://maps.googleapis.com/maps/api/geocode/json",
        json={
            "status": "OVER_QUERY_LIMIT",
        },
        match=[
            query_param_matcher(
                {
                    "address": "New York",
                    "key": "APIKEY",
                }
            )
        ],
    )

    assert wrap_hook_response(time_plugin.time_command, event) == [
        ("return", "The geocoding API quota has run out."),
    ]
    assert conn.mock_calls == []


def test_time_command(mock_requests, freeze_time, mock_api_keys):
    conn = MagicMock()
    event = CommandEvent(
        text="New York",
        triggered_command="time",
        cmd_prefix=".",
        hook=MagicMock(),
        channel="#foo",
        nick="bar",
        conn=conn,
        bot=conn.bot,
    )

    mock_requests.add(
        responses.GET,
        "https://maps.googleapis.com/maps/api/geocode/json",
        json={
            "status": "OK",
            "results": [
                {
                    "formatted_address": "New York, USA",
                    "geometry": {
                        "location": {
                            "lat": 123.1,
                            "lng": -45.6,
                        },
                    },
                }
            ],
        },
        match=[
            query_param_matcher(
                {
                    "address": "New York",
                    "key": "APIKEY",
                }
            )
        ],
    )
    mock_requests.add(
        responses.GET,
        "https://maps.googleapis.com/maps/api/timezone/json",
        json={
            "status": "OK",
            "rawOffset": -5,
            "dstOffset": -1,
            "timeZoneName": "EDT",
        },
        match=[
            query_param_matcher(
                {
                    "location": "123.1,-45.6",
                    "timestamp": time.time(),
                    "key": "APIKEY",
                }
            )
        ],
    )

    assert wrap_hook_response(time_plugin.time_command, event) == [
        (
            "return",
            "\x0206:14 PM, Thursday, August 22, 2019\x02 - New York, USA (EDT)",
        ),
    ]
    assert conn.mock_calls == []


def test_beats(freeze_time):
    conn = MagicMock()
    event = CommandEvent(
        text="",
        triggered_command="beats",
        cmd_prefix=".",
        hook=MagicMock(),
        channel="#foo",
        nick="bar",
        conn=conn,
        bot=conn.bot,
    )

    assert wrap_hook_response(time_plugin.beats, event) == [
        ("return", "Swatch Internet Time: @801.81"),
    ]
    assert conn.mock_calls == []
