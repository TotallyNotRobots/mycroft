"""
Nick/user tracking

Author:
    - linuxdaemon <linuxdaemon@snoonet.org>
"""

import asyncio
import datetime
import string
from collections import defaultdict
from contextlib import suppress

import re
import sqlalchemy.exc
from sqlalchemy import Table, Text, Column, DateTime, PrimaryKeyConstraint, Boolean, and_

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import database
from cloudbot.util.async_util import wrap_future, create_future
from cloudbot.util.backoff import Delayer

address_table = Table(
    'addrs',
    database.metadata,
    Column('nick', Text),
    Column('addr', Text),
    Column('created', DateTime),
    Column('seen', DateTime),
    Column('reg', Boolean, default=False),
    Column('nick_case', Text),
    PrimaryKeyConstraint('nick', 'addr')
)

hosts_table = Table(
    'hosts',
    database.metadata,
    Column('nick', Text),
    Column('host', Text),
    Column('created', DateTime),
    Column('seen', DateTime),
    Column('reg', Boolean, default=False),
    Column('nick_case', Text),
    PrimaryKeyConstraint('nick', 'host')
)

masks_table = Table(
    'masks',
    database.metadata,
    Column('nick', Text),
    Column('mask', Text),
    Column('created', DateTime),
    Column('seen', DateTime),
    Column('reg', Boolean, default=False),
    Column('nick_case', Text),
    PrimaryKeyConstraint('nick', 'mask')
)

RFC_CASEMAP = str.maketrans(dict(zip(
    string.ascii_uppercase + "[]\\",
    string.ascii_lowercase + "{}|"
)))


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
            db.execute(table.update().values(seen=now, nick_case=nick).where(clause))
        finally:
            db.commit()

    nick_cf = rfc_casefold(nick)
    clause = and_(table.c.nick == nick_cf, getattr(table.c, column_name) == value)

    args = {
        'nick': nick_cf,
        column_name: value,
        'created': now,
        'seen': now,
        'reg': False,
        'nick_case': nick
    }

    delayer = Delayer(2)
    while True:
        with delayer:
            try:
                _insert_or_update()
            except sqlalchemy.exc.TimeoutError:
                pass
            else:
                break


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
    response = irc_paramlist[1].lstrip(':')
    nick, _, ident_host = response.partition('=')
    ident_host = ident_host[1:]  # strip the +/-
    nick = nick.rstrip('*')  # strip the * which indicates oper status
    ident, _, host = ident_host.partition('@')
    return nick, host


def _handle_whowas(irc_paramlist):
    return irc_paramlist[1], irc_paramlist[3]


def _handle_whowas_host(irc_paramlist):
    nick = irc_paramlist[1]
    hostmask = irc_paramlist[-1].strip().rsplit(None, 1)[1]
    host = hostmask.split('@', 1)[1]
    return nick, host


response_map = {
    '352': ("user_mask", _handle_who_response),
    '302': ("user_host", _handle_userhost_response),
    '340': ("user_ip", _handle_userhost_response),  # USERIP responds with the same format as USERHOST
    '314': ("user_whowas_mask", _handle_whowas),
    '379': ("user_whowas_host", _handle_whowas_host),
}


@asyncio.coroutine
def await_response(fut):
    return (yield from asyncio.wait_for(fut, 60))


@asyncio.coroutine
def await_command_response(conn, name, cmd, nick):
    futs = conn.memory["sherlock"]["futures"][name]
    nick_cf = rfc_casefold(nick)
    try:
        fut = futs[nick_cf]
    except LookupError:
        futs[nick_cf] = fut = create_future(conn.loop)
        conn.cmd(cmd, nick)

    try:
        res = yield from await_response(fut)
    finally:
        with suppress(KeyError):
            del futs[nick_cf]

    return res


@asyncio.coroutine
def get_user_host(conn, nick):
    return (yield from await_command_response(conn, "user_host", "USERHOST", nick))


@asyncio.coroutine
def get_user_ip(conn, nick):
    return (yield from await_command_response(conn, "user_ip", "USERIP", nick))


@asyncio.coroutine
def get_user_mask(conn, nick):
    return (yield from await_command_response(conn, "user_mask", "WHO", nick))


@asyncio.coroutine
def get_user_whowas(conn, nick):
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
        return (yield from await_response(asyncio.gather(mask_fut, host_fut)))
    except asyncio.TimeoutError:
        return None, None


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


@hook.event(EventType.notice)
@asyncio.coroutine
def on_notice(db, nick, chan, conn, event):
    try:
        server_info = conn.memory["server_info"]
    except LookupError:
        return

    if chan.casefold() != nick.casefold():
        # This isn't a PM / Private notice, ignore it
        return

    if nick.casefold() != server_info["server_name"]:
        # This message isn't from the server, ignore it
        return

    yield from handle_snotice(db, event)


@hook.irc_raw(response_map.keys())
@asyncio.coroutine
def handle_response_numerics(conn, irc_command, irc_paramlist):
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

    if not fut.done():
        fut.set_result(value.strip())


@asyncio.coroutine
def handle_snotice(db, event):
    conn = event.conn
    content = event.content
    for name, handler in HANDLERS.items():
        regex = get_regex(conn, name)
        match = regex.match(content)
        if match:
            yield from handler(db, event, match)

            break


@asyncio.coroutine
def set_user_data(event, db, table, column_name, now, nick, value_func, conn=None):
    value = yield from value_func(event.conn if conn is None else conn, nick)
    yield from event.async_call(update_user_data, db, table, column_name, now, nick, value)


@asyncio.coroutine
def delay_call(coro, timeout):
    yield from asyncio.sleep(timeout)
    return (yield from coro)


@asyncio.coroutine
def on_nickchange(db, event, match):
    conn = event.conn
    old_nick = match.group('oldnick')
    new_nick = match.group('newnick')
    now = datetime.datetime.now()

    old_nick_cf = rfc_casefold(old_nick)
    new_nick_cf = rfc_casefold(new_nick)

    futures = conn.memory["sherlock"]["futures"]

    data_futs = futures["data"]
    nick_change_futs = futures["nick_changes"]

    futs = {
        'addr': create_future(conn.loop),
        'host': create_future(conn.loop),
        'mask': create_future(conn.loop),
    }

    data_futs[new_nick_cf] = futs

    try:
        old_futs = data_futs.pop(old_nick_cf)
    except LookupError:
        nick_change_futs[old_nick_cf] = fut = create_future(conn.loop)
        try:
            old_futs = yield from asyncio.wait_for(fut, 30)
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
        if not nick_fut.done():
            nick_fut.set_result(futs)

    @asyncio.coroutine
    def _handle_set(table, name, value_func):
        try:
            value = yield from value_func(event.conn, new_nick)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            value = yield from asyncio.wait_for(futs[name], 300)

        del futs[name]

        with suppress(KeyError):
            old_futs[name].set_result(value)

        yield from asyncio.gather(
            event.async_call(update_user_data, db, table, name, now, old_nick, value),
            event.async_call(update_user_data, db, table, name, now, new_nick, value)
        )

    @asyncio.coroutine
    def _do_mask():
        yield from _handle_set(masks_table, 'mask', get_user_mask)

    @asyncio.coroutine
    def _timeout_whowas():
        try:
            yield from asyncio.gather(
                _handle_set(hosts_table, 'host', get_user_host),
                _do_mask(),
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            mask, host = yield from get_user_whowas(event.conn, new_nick)
            if mask and host:
                with suppress(KeyError):
                    old_futs['host'].set_result(host)

                with suppress(KeyError):
                    old_futs['mask'].set_result(mask)

                yield from asyncio.gather(
                    event.async_call(update_user_data, db, hosts_table, 'host', now, old_nick, host),
                    event.async_call(update_user_data, db, hosts_table, 'host', now, new_nick, host),

                    event.async_call(update_user_data, db, masks_table, 'mask', now, old_nick, mask),
                    event.async_call(update_user_data, db, masks_table, 'mask', now, new_nick, mask),
                )

    yield from asyncio.gather(
        _handle_set(address_table, 'addr', get_user_ip),
        _timeout_whowas(),
    )

    with suppress(KeyError):
        del data_futs[new_nick_cf]


@asyncio.coroutine
def on_user_connect(db, event, match):
    nick = match.group('nick')
    ident = match.group('ident')
    host = match.group('host')
    addr = match.group('addr')

    now = datetime.datetime.now()

    nick_cf = rfc_casefold(nick)
    conn = event.conn

    mask_fut = create_future(conn.loop)

    futs = {
        'mask': mask_fut,
    }

    data_futs = conn.memory["sherlock"]["futures"]["data"]

    data_futs[nick_cf] = futs

    @asyncio.coroutine
    def _handle_set(table, name, value_func):
        try:
            value = yield from value_func(event.conn, nick)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            value = yield from futs[name]

        del futs[name]

        yield from event.async_call(update_user_data, db, table, name, now, nick, value)

    @asyncio.coroutine
    def _do_mask():
        yield from _handle_set(masks_table, 'mask', get_user_mask)

    yield from asyncio.gather(
        event.async_call(update_user_data, db, hosts_table, 'host', now, nick, host),
        event.async_call(update_user_data, db, address_table, 'addr', now, nick, addr),
        _do_mask(),
    )

    with suppress(LookupError):
        del data_futs[nick_cf]


@asyncio.coroutine
def on_user_quit(db, event, match):
    nick = match.group('nick')
    ident = match.group('ident')
    host = match.group('host')
    addr = match.group('addr')

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
            old_futs = yield from asyncio.wait_for(fut, 30)
        except asyncio.TimeoutError:
            old_futs = {}
        finally:
            with suppress(LookupError):
                del nick_change_futs[nick_cf]

    with suppress(KeyError):
        old_futs['host'].set_result(host)

    with suppress(KeyError):
        old_futs['addr'].set_result(addr)

    @asyncio.coroutine
    def _do_whowas():
        mask, _ = yield from get_user_whowas(event.conn, nick)
        if mask:
            with suppress(KeyError):
                old_futs['mask'].set_result(mask)

            yield from event.async_call(update_user_data, db, masks_table, 'mask', now, nick, mask)

    yield from asyncio.gather(
        event.async_call(update_user_data, db, hosts_table, 'host', now, nick, host),
        event.async_call(update_user_data, db, address_table, 'addr', now, nick, addr),
        _do_whowas(),
    )


HANDLERS = {
    'nick': on_nickchange,
    'connect': on_user_connect,
    'quit': on_user_quit,
}


@asyncio.coroutine
def ignore_timeout(coro):
    try:
        return (yield from coro)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass


@hook.irc_raw('352')
@asyncio.coroutine
def on_who(conn, irc_paramlist):
    try:
        lines, fut = conn.memory["sherlock"]["futures"]["who_0"][0]
    except LookupError:
        return

    if not fut.done():
        lines.append(irc_paramlist[1:])


@hook.irc_raw('315')
@asyncio.coroutine
def on_who_end(conn, irc_paramlist):
    name = irc_paramlist[1]
    if name != "0":
        return

    try:
        lines, fut = conn.memory["sherlock"]["futures"]["who_0"][0]
    except LookupError:
        return

    if not fut.done():
        fut.set_result(lines)


@hook.on_start
@asyncio.coroutine
def get_initial_data(bot, loop, db, event):
    wrap_future(asyncio.gather(
        *[get_initial_connection_data(conn, loop, db, event) for conn in bot.connections.values() if conn.connected]
    ))


@hook.irc_raw('376')
@hook.command("getdata", permissions=["botcontrol"], autohelp=False)
@asyncio.coroutine
def get_initial_connection_data(conn, loop, db, event):
    if conn.nick.endswith('-dev') and not hasattr(event, 'triggered_command'):
        # Ignore initial data update on development instances
        return

    fut = create_future(loop)
    try:
        lines, fut = conn.memory["sherlock"]["futures"]["who_0"][0]
    except LookupError:
        pass
    else:
        if not fut.done():
            return

    conn.memory["sherlock"]["futures"]["who_0"][0] = ([], fut)

    yield from asyncio.sleep(10)

    now = datetime.datetime.now()
    conn.send("WHO 0")
    try:
        lines = yield from asyncio.wait_for(fut, 30 * 60)
    except asyncio.TimeoutError:
        return
    finally:
        with suppress(LookupError):
            del conn.memory["sherlock"]["futures"]["who_0"][0]

    users = []
    for line in lines:
        chan, ident, host, server, nick, status, realname = line
        num_hops, _, realname = realname.partition(' ')
        users.append((nick, host))

    futs = [
        wrap_future(event.async_call(update_user_data, db, masks_table, 'mask', now, nick, mask))
        for nick, mask in users
    ]

    for nick, mask in users:
        yield from asyncio.gather(
            ignore_timeout(set_user_data(event, db, hosts_table, 'host', now, nick, get_user_host, conn)),
            ignore_timeout(set_user_data(event, db, address_table, 'addr', now, nick, get_user_ip, conn))
        )

    yield from asyncio.gather(*futs)
