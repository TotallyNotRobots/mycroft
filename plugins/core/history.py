from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

from cloudbot import hook
from cloudbot.event import EventType

if TYPE_CHECKING:
    from cloudbot.client import Client


def track_history(event, message_time, conn: Client) -> None:
    try:
        history = conn.history[event.chan]
    except KeyError:
        conn.history[event.chan] = deque(maxlen=100)
        # what are we doing here really
        # really really
        history = conn.history[event.chan]

    data = (event.nick, message_time, event.content)
    history.append(data)


@hook.event([EventType.message, EventType.action], singlethread=True)
def chat_tracker(event, conn: Client) -> None:
    if event.type is EventType.action:
        event.content = f"\x01ACTION {event.content}\x01"

    message_time = time.time()
    track_history(event, message_time, conn)


@hook.command(autohelp=False)
async def resethistory(event, conn: Client) -> str:
    """- resets chat history for the current channel"""
    try:
        conn.history[event.chan].clear()
        return "Reset chat history for current channel."
    except KeyError:
        # wat
        return "There is no history for this channel."
