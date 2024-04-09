"""
Nick/user tracking

Author:
    - linuxdaemon <linuxdaemon@snoonet.org>
"""

import asyncio
import datetime
import logging
import re
import string
from collections import defaultdict
from contextlib import suppress

import sqlalchemy.exc
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    PrimaryKeyConstraint,
    Table,
    Text,
    and_,
)

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import database
from cloudbot.util.async_util import create_future, wrap_future
from cloudbot.util.backoff import Delayer

address_table = Table(
    "addrs",
    database.metadata,
    Column("nick", Text),
    Column("addr", Text),
    Column("created", DateTime),
    Column("seen", DateTime),
    Column("reg", Boolean, default=False),
    Column("nick_case", Text),
    PrimaryKeyConstraint("nick", "addr"),
)

hosts_table = Table(
    "hosts",
    database.metadata,
    Column("nick", Text),
    Column("host", Text),
    Column("created", DateTime),
    Column("seen", DateTime),
    Column("reg", Boolean, default=False),
    Column("nick_case", Text),
    PrimaryKeyConstraint("nick", "host"),
)

masks_table = Table(
    "masks",
    database.metadata,
    Column("nick", Text),
    Column("mask", Text),
    Column("created", DateTime),
    Column("seen", DateTime),
    Column("reg", Boolean, default=False),
    Column("nick_case", Text),
    PrimaryKeyConstraint("nick", "mask"),
)

RFC_CASEMAP = str.maketrans(
    dict(zip(string.ascii_uppercase + "[]\\", string.ascii_lowercase + "{}|"))
)

logger = logging.getLogger("cloudbot")


def update_user_data(db, table, column_name, now, nick, value):
    """
    :type db: sqlalchemy.orm.Session
    :type table: Table
    :type column_name: str
    :type now: datetime.datetime
    :type nick: str
    :type value: str
    """

    def _insert_or_update():
        try:
            db.execute(table.insert().values(**args))
        except sqlalchemy.exc.IntegrityError:
            db.rollback()
            db.execute(
                table.update().values(seen=now, nick_case=nick).where(clause)
            )
        finally:
            db.commit()

    nick_cf = rfc_casefold(nick)
    clause = and_(
        table.c.nick == nick_cf, getattr(table.c, column_name) == value
    )

    args = {
        "nick": nick_cf,
        column_name: value,
        "created": now,
        "seen": now,
        "reg": False,
        "nick_case": nick,
    }

    delayer = Delayer(2)
    while True:
        with delayer:
            try:
                _insert_or_update()
            except sqlalchemy.exc.TimeoutError:
                logger.warning("SQL timeout hit, trying again")
            else:
                break


def _set_result(fut, result):
    if not fut.done():
        fut.set_result(result)


def get_regex_cache(conn):
    try:
        cache = conn.memory["sherlock"]["re_cache"]
    except LookupError:
        conn.memory.setdefault("sherlock", {})["re_cache"] = cache = {}

    return cache


def get_regex(conn, name):
    cache = get_regex_cache(conn)
    try:
        regex = cache[name.lower()]
    except LookupError:
        conf = conn.config["plugins"]["sherlock"]["regex"][name.lower()]
        cache[name.lower()] = regex = re.compile(conf)

    return regex


def rfc_casefold(text):
    return text.translate(RFC_CASEMAP)


def _handle_who_response(irc_paramlist):
    return irc_paramlist[5], irc_paramlist[3]


def _handle_userhost_response(irc_paramlist):
    response = irc_paramlist[1].lstrip(":")
    nick, _, ident_host = response.partition("=")
    ident_host = ident_host[1:]  # strip the +/-
    nick = nick.rstrip("*")  # strip the * which indicates oper status
    _, _, host = ident_host.partition("@")
    return nick, host


def _handle_whowas(irc_paramlist):
    return irc_paramlist[1], irc_paramlist[3]


def _handle_whowas_host(irc_paramlist):
    nick = irc_paramlist[1]
    hostmask = irc_paramlist[-1].strip().rsplit(None, 1)[1]
    host = hostmask.split("@", 1)[1]
    return nick, host


response_map = {
    "352": ("user_mask", _handle_who_response),
    "302": ("user_host", _handle_userhost_response),
    "340": (
        "user_ip",
        _handle_userhost_response,
    ),  # USERIP responds with the same format as USERHOST
    "314": ("user_whowas_mask", _handle_whowas),
    "652": ("user_whowas_host", _handle_whowas_host),
}


async def await_response(fut):
    return await asyncio.wait_for(fut, 60)


async def await_command_response(conn, name, cmd, nick):
    futs = conn.memory["sherlock"]["futures"][name]
    nick_cf = rfc_casefold(nick)
    try:
        fut = futs[nick_cf]
    except LookupError:
        futs[nick_cf] = fut = create_future(conn.loop)
        conn.cmd(cmd, nick)

    try:
        res = await await_response(fut)
    finally:
        with suppress(KeyError):
            del futs[nick_cf]

    return res


async def get_user_host(conn, nick):
    return await await_command_response(conn, "user_host", "USERHOST", nick)


async def get_user_ip(conn, nick):
    return await await_command_response(conn, "user_ip", "USERIP", nick)


async def get_user_mask(conn, nick):
    return await await_command_response(conn, "user_mask", "WHO", nick)


async def get_user_whowas(conn, nick):
    nick_cf = rfc_casefold(nick)
    futs = conn.memory["sherlock"]["futures"]
    send_command = False
    try:
        mask_fut = futs["user_whowas_mask"][nick_cf]
    except LookupError:
        send_command = True
        futs["user_whowas_mask"][nick_cf] = mask_fut = create_future(conn.loop)

    try:
        host_fut = futs["user_whowas_host"][nick_cf]
    except LookupError:
        send_command = True
        futs["user_whowas_host"][nick_cf] = host_fut = create_future(conn.loop)

    if send_command:
        conn.cmd("WHOWAS", nick)

    try:
        return tuple(await await_response(asyncio.gather(mask_fut, host_fut)))
    except asyncio.TimeoutError:
        logger.warning("[user_tracking] Hit timeout for whowas data")
        return None, None


@hook.command('testdata', permissions=['botcontrol'])
async def get_nick_data(conn, text):
    start = datetime.datetime.now()
    ip = await get_user_ip(conn, text)
    mask = await get_user_mask(conn, text)
    host = await get_user_host(conn, text)
    diff = datetime.datetime.now() - start
    return f"Got: {ip} {host} {mask} in {diff.total_seconds()} seconds"


@hook.on_start
def clear_regex_cache(bot):
    for conn in bot.connections.values():
        get_regex_cache(conn).clear()


@hook.on_start
def init_futures(bot):
    for conn in bot.connections.values():
        conn.memory["sherlock"] = {
            "futures": defaultdict(dict),
        }


def _is_server(nick, server_info):
    if nick.casefold() == server_info["server_name"]:
        return True

    # Temp fix for servers that inconsistently send different server names
    if "." in nick:
        return True

    return False


@hook.event(EventType.notice)
async def on_notice(db, nick, chan, conn, event):
    try:
        server_info = conn.memory["server_info"]
    except LookupError:
        logger.debug("Unable to find server info")
        return

    if chan.casefold() != nick.casefold():
        # This isn't a PM / Private notice, ignore it
        logger.debug("Notice was not private")
        return

    if not _is_server(nick, server_info):
        # This message isn't from the server, ignore it
        logger.debug("Private notice not from the server: %s", nick)
        return

    await handle_snotice(db, event)


@hook.irc_raw(list(response_map.keys()))
async def handle_response_numerics(conn, irc_command, irc_paramlist):
    try:
        name, handler = response_map[irc_command]
    except LookupError:
        return

    nick, value = handler(irc_paramlist)

    futs = conn.memory["sherlock"]["futures"][name]
    try:
        fut = futs.pop(rfc_casefold(nick))
    except LookupError:
        return

    _set_result(fut, value.strip())


async def handle_snotice(db, event):
    conn = event.conn
    content = event.content
    for name, handler in HANDLERS.items():
        regex = get_regex(conn, name)
        match = regex.match(content)
        if match:
            await handler(db, event, match)
            break
    else:
        raise ValueError("Unmatched snotice: " + content)


async def set_user_data(
    event, db, table, column_name, now, nick, value_func, conn=None
):
    value = await value_func(event.conn if conn is None else conn, nick)
    await event.async_call(
        update_user_data, db, table, column_name, now, nick, value
    )


async def on_nickchange(db, event, match):
    conn = event.conn
    old_nick = match.group("oldnick")
    new_nick = match.group("newnick")
    now = datetime.datetime.now()

    old_nick_cf = rfc_casefold(old_nick)
    new_nick_cf = rfc_casefold(new_nick)

    futures = conn.memory["sherlock"]["futures"]

    data_futs = futures["data"]
    nick_change_futs = futures["nick_changes"]

    futs = {
        "addr": create_future(conn.loop),
        "host": create_future(conn.loop),
        "mask": create_future(conn.loop),
    }

    data_futs[new_nick_cf] = futs

    try:
        old_futs = data_futs.pop(old_nick_cf)
    except LookupError:
        nick_change_futs[old_nick_cf] = fut = create_future(conn.loop)
        try:
            old_futs = await asyncio.wait_for(fut, 30)
        except asyncio.TimeoutError:
            old_futs = {}
        finally:
            with suppress(LookupError):
                del nick_change_futs[old_nick_cf]

    try:
        nick_fut = nick_change_futs.pop(new_nick_cf)
    except LookupError:
        pass
    else:
        _set_result(nick_fut, futs)

    async def _handle_set(table, name, value_func):
        try:
            value = await value_func(event.conn, new_nick)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            value = await asyncio.wait_for(futs[name], 300)

        del futs[name]

        with suppress(LookupError):
            _set_result(old_futs[name], value)

        await asyncio.gather(
            event.async_call(
                update_user_data, db, table, name, now, old_nick, value
            ),
            event.async_call(
                update_user_data, db, table, name, now, new_nick, value
            ),
        )

    async def _do_mask():
        await _handle_set(masks_table, "mask", get_user_mask)

    async def _timeout_whowas():
        try:
            await asyncio.gather(
                _handle_set(hosts_table, "host", get_user_host),
                _do_mask(),
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            mask, host = await get_user_whowas(event.conn, new_nick)
            if mask and host:
                with suppress(KeyError):
                    _set_result(old_futs["host"], host)

                with suppress(KeyError):
                    _set_result(old_futs["mask"], mask)

                await asyncio.gather(
                    event.async_call(
                        update_user_data,
                        db,
                        hosts_table,
                        "host",
                        now,
                        old_nick,
                        host,
                    ),
                    event.async_call(
                        update_user_data,
                        db,
                        hosts_table,
                        "host",
                        now,
                        new_nick,
                        host,
                    ),
                    event.async_call(
                        update_user_data,
                        db,
                        masks_table,
                        "mask",
                        now,
                        old_nick,
                        mask,
                    ),
                    event.async_call(
                        update_user_data,
                        db,
                        masks_table,
                        "mask",
                        now,
                        new_nick,
                        mask,
                    ),
                )

    await asyncio.gather(
        _handle_set(address_table, "addr", get_user_ip),
        _timeout_whowas(),
    )

    with suppress(KeyError):
        del data_futs[new_nick_cf]


async def on_user_connect(db, event, match):
    nick = match.group("nick")
    host = match.group("host")
    addr = match.group("addr")

    now = datetime.datetime.now()

    nick_cf = rfc_casefold(nick)
    conn = event.conn

    mask_fut = create_future(conn.loop)

    futs = {
        "mask": mask_fut,
    }

    data_futs = conn.memory["sherlock"]["futures"]["data"]

    data_futs[nick_cf] = futs

    async def _handle_set(table, name, value_func):
        try:
            value = await value_func(event.conn, nick)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            value = await futs[name]

        del futs[name]

        await event.async_call(
            update_user_data, db, table, name, now, nick, value
        )

    async def _do_mask():
        await _handle_set(masks_table, "mask", get_user_mask)

    await asyncio.gather(
        event.async_call(
            update_user_data, db, hosts_table, "host", now, nick, host
        ),
        event.async_call(
            update_user_data, db, address_table, "addr", now, nick, addr
        ),
        _do_mask(),
    )

    with suppress(LookupError):
        del data_futs[nick_cf]


async def on_user_quit(db, event, match):
    nick = match.group("nick")
    host = match.group("host")
    addr = match.group("addr")

    now = datetime.datetime.now()

    nick_cf = rfc_casefold(nick)
    conn = event.conn

    futures = conn.memory["sherlock"]["futures"]

    data_futs = futures["data"]
    nick_change_futs = futures["nick_changes"]

    try:
        old_futs = data_futs.pop(nick_cf)
    except LookupError:
        nick_change_futs[nick_cf] = fut = create_future(conn.loop)
        try:
            old_futs = await asyncio.wait_for(fut, 30)
        except asyncio.TimeoutError:
            old_futs = {}
        finally:
            with suppress(LookupError):
                del nick_change_futs[nick_cf]

    with suppress(KeyError):
        _set_result(old_futs["host"], host)

    with suppress(KeyError):
        _set_result(old_futs["addr"], addr)

    async def _do_whowas():
        mask, _ = await get_user_whowas(event.conn, nick)
        if mask:
            with suppress(KeyError):
                _set_result(old_futs["mask"], mask)

            await event.async_call(
                update_user_data, db, masks_table, "mask", now, nick, mask
            )

    await asyncio.gather(
        event.async_call(
            update_user_data, db, hosts_table, "host", now, nick, host
        ),
        event.async_call(
            update_user_data, db, address_table, "addr", now, nick, addr
        ),
        _do_whowas(),
    )


HANDLERS = {
    "nick": on_nickchange,
    "connect": on_user_connect,
    "quit": on_user_quit,
}


async def ignore_timeout(coro):
    try:
        return await coro
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("Timeout reached for %s", coro)


@hook.irc_raw("352")
async def on_who(conn, irc_paramlist):
    try:
        lines, fut = conn.memory["sherlock"]["futures"]["who_0"][0]
    except LookupError:
        return

    if not fut.done():
        lines.append(irc_paramlist[1:])


@hook.irc_raw("315")
async def on_who_end(conn, irc_paramlist):
    name = irc_paramlist[1]
    if name != "0":
        return

    try:
        lines, fut = conn.memory["sherlock"]["futures"]["who_0"][0]
    except LookupError:
        return

    _set_result(fut, lines)


@hook.on_start
async def get_initial_data(bot, loop, db, event):
    wrap_future(
        asyncio.gather(
            *[
                get_initial_connection_data(conn, loop, db, event)
                for conn in bot.connections.values()
                if conn.connected
            ]
        )
    )


@hook.irc_raw("376")
@hook.command("getdata", permissions=["botcontrol"], autohelp=False)
async def get_initial_connection_data(conn, loop, db, event):
    """
    - Update all user data

    :type conn: cloudbot.client.Client
    :type loop: asyncio.AbstractEventLoop
    :type db: sqlalchemy.orm.Session
    :type event: cloudbot.event.Event
    """
    if conn.nick.endswith("-dev") and not hasattr(event, "triggered_command"):
        # Ignore initial data update on development instances
        return

    fut = create_future(loop)
    try:
        lines, fut = conn.memory["sherlock"]["futures"]["who_0"][0]
    except LookupError:
        pass
    else:
        if not fut.done():
            return "getdata command already running"

    conn.memory["sherlock"]["futures"]["who_0"][0] = ([], fut)

    await asyncio.sleep(10)

    now = datetime.datetime.now()
    conn.cmd("WHO", "0")
    try:
        lines = await asyncio.wait_for(fut, 30 * 60)
    except asyncio.TimeoutError:
        return "Timeout reached"
    finally:
        with suppress(LookupError):
            del conn.memory["sherlock"]["futures"]["who_0"][0]

    users = []
    for line in lines:
        _, _, host, _, nick, _, realname = line
        _, _, realname = realname.partition(" ")
        users.append((nick, host))

    futs = [
        wrap_future(
            event.async_call(
                update_user_data, db, masks_table, "mask", now, nick, mask
            )
        )
        for nick, mask in users
    ]

    for nick, _ in users:
        await asyncio.gather(
            ignore_timeout(
                set_user_data(
                    event,
                    db,
                    hosts_table,
                    "host",
                    now,
                    nick,
                    get_user_host,
                    conn,
                )
            ),
            ignore_timeout(
                set_user_data(
                    event,
                    db,
                    address_table,
                    "addr",
                    now,
                    nick,
                    get_user_ip,
                    conn,
                )
            ),
        )

    await asyncio.gather(*futs)

    return "Done."
