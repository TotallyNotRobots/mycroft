"""
Nick/user tracking

Author:
    - linuxdaemon <linuxdaemon@snoonet.org>
"""
import asyncio
import datetime
import random
import re
import string
from collections import defaultdict
from contextlib import suppress

import requests
import sqlalchemy
from requests import RequestException
from sqlalchemy import Table, Column, DateTime, Boolean, select, Text, PrimaryKeyConstraint, and_, func
from sqlalchemy.exc import IntegrityError

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import database, colors, timeparse, web
from cloudbot.util.async_util import create_future, wrap_future
from cloudbot.util.backoff import Delayer
from cloudbot.util.formatting import chunk_str, pluralize, get_text_list

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

counts = defaultdict(int)


def rfc_casefold(text):
    return text.translate(RFC_CASEMAP)


def format_list(name, data):
    begin = colors.parse("$(dgreen){}$(clear): ".format(name))
    body = ', '.join(set(data))

    return chunk_str(begin + body)


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
        except IntegrityError:
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


def get_all_channels(conn):
    conf = conn.config["plugins"]["sherlock"]["channels"]
    return conf["normal"], conf["admin"]


def get_channels(conn):
    normal, admin = get_all_channels(conn)
    return normal + admin


def get_admin_channels(conn):
    return get_all_channels(conn)[1]


def check_channel(conn, chan):
    normal_chans, admin_chans = get_all_channels(conn)
    if chan.lower() not in (normal_chans + admin_chans):
        return False, False

    return True, chan.lower() in admin_chans


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
            counts[name] += 1
            try:
                yield from handler(db, event, match)
            finally:
                counts[name] -= 1

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


# Commands


def format_results(nicks, masks, hosts, addresses, is_admin):
    if nicks:
        yield from format_list('nicks', nicks)

    if masks:
        yield from format_list('masks', masks)

    if is_admin:
        if hosts:
            yield from format_list('hosts', hosts)

        if addresses:
            yield from format_list('addrs', addresses)


def paste_results(nicks, masks, hosts, addresses, is_admin):
    if nicks:
        yield 'Nicks:'
        yield from ("  - '{}'".format(nick) for nick in nicks)
        yield ""

    if masks:
        yield 'Masks:'
        yield from ("  - '{}'".format(mask) for mask in masks)
        yield ""

    if is_admin:
        if hosts:
            yield 'Hosts:'
            yield from ("  - '{}'".format(host) for host in hosts)
            yield ""

        if addresses:
            yield 'Addresses:'
            yield from ("  - '{}'".format(addr) for addr in addresses)
            yield ""


def format_count(nicks, masks, hosts, addresses, is_admin, duration):
    counts = [
        (len(nicks), 'nick'),
        (len(masks), 'mask'),
    ]
    if is_admin:
        counts.extend([
            (len(hosts), 'host'),
            (len(addresses), 'address'),
        ])

    if all(count == 0 for count, thing in counts):
        return "None."
    else:
        return "Done. Found {} in {:.3f} seconds".format(
            get_text_list([pluralize(count, thing) for count, thing in counts], 'and'), duration)


def do_paste(it):
    out = '\n'.join(it)
    passwd = "".join(random.choice(string.ascii_letters + string.digits + "!@#$%^&*(),./") for _ in range(16))
    args = {
        "text": out,
        "expire": '1h',
        "lang": "text",
        "password": passwd
    }
    try:
        r = requests.post("https://paste.snoonet.org/paste/new", data=args)
        r.raise_for_status()
    except RequestException as e:
        return "Paste failed. ({})".format(e)

    return "Paste: {} Password: {} (paste expires in 1 hour)".format(r.url, passwd)


def format_results_or_paste(nick, duration, nicks, masks, hosts, addresses, is_admin):
    yield "Results for '{}':".format(nick)
    lines = list(format_results(nicks, masks, hosts, addresses, is_admin))
    if len(lines) > 5:
        yield do_paste(paste_results(nicks, masks, hosts, addresses, is_admin))
    else:
        yield from lines

    yield format_count(nicks, masks, hosts, addresses, is_admin, duration)


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


@hook.command("check")
def check_command(conn, chan, text, db, message):
    """<nick> [last_seen] - Looks up [nick] in the users database, optionally filtering to entries newer than [last_seen] specified in the format [-|+]5w4d3h2m1s, defaulting to forever"""
    allowed, admin = check_channel(conn, chan)

    if not allowed:
        return

    split = text.split(None, 1)
    nick = split.pop(0).strip()
    now = datetime.datetime.now()
    if split:
        interval_str = split[0].strip()
        if interval_str == '*':
            last_time = datetime.datetime.fromtimestamp(0)
        else:
            time_span = datetime.timedelta(seconds=timeparse.time_parse(interval_str))
            last_time = now + time_span
    else:
        last_time = datetime.datetime.fromtimestamp(0)

    lower_nick = rfc_casefold(nick)

    start = datetime.datetime.now()

    host_rows = db.execute(
        select([hosts_table.c.host], and_(hosts_table.c.nick == lower_nick, hosts_table.c.seen >= last_time))
    )

    hosts = [row["host"] for row in host_rows]

    nick_rows = db.execute(
        select([hosts_table.c.nick, hosts_table.c.nick_case],
               and_(hosts_table.c.host.in_(hosts), hosts_table.c.seen >= last_time))
    )

    nicks = {row["nick"]: row["nick_case"] for row in nick_rows}

    addr_rows = db.execute(
        select([address_table.c.addr], and_(address_table.c.nick == lower_nick, address_table.c.seen >= last_time))
    )

    addresses = [row["addr"] for row in addr_rows]

    nick_addr_rows = db.execute(
        select([address_table.c.nick, address_table.c.nick_case],
               and_(address_table.c.addr.in_(addresses), address_table.c.seen >= last_time))
    )

    nicks.update((row["nick"], row["nick_case"]) for row in nick_addr_rows)

    mask_rows = db.execute(
        select([masks_table.c.mask], and_(masks_table.c.nick == lower_nick, masks_table.c.seen >= last_time))
    )

    masks = [row["mask"] for row in mask_rows]

    nick_mask_rows = db.execute(
        select([masks_table.c.nick, masks_table.c.nick_case],
               and_(masks_table.c.mask.in_(masks), masks_table.c.seen >= last_time))
    )

    nicks.update((row["nick"], row["nick_case"]) for row in nick_mask_rows)

    query_time = datetime.datetime.now() - start

    nicks = set(nicks.values())
    masks = set(masks)
    hosts = set(hosts)
    addresses = set(addresses)

    for line in format_results_or_paste(nick, query_time.total_seconds(), nicks, masks, hosts, addresses, admin):
        message(line)


@hook.command("checkhost", "check2")
def check_host_command(db, conn, chan, text, message):
    """<host|mask|addr> [last_seen] - Looks up [host|mask|addr] in the users database, optionally filtering to entries newer than [last_seen] specified in the format [-|+]5w4d3h2m1s, defaulting to forever"""
    allowed, admin = check_channel(conn, chan)

    if not allowed:
        return

    split = text.split(None, 1)
    host = split.pop(0).strip()
    host_lower = host.lower()
    now = datetime.datetime.now()
    if split:
        interval_str = split[0].strip()
        if interval_str == '*':
            last_time = datetime.datetime.fromtimestamp(0)
        else:
            time_span = datetime.timedelta(seconds=timeparse.time_parse(interval_str))
            last_time = now + time_span
    else:
        last_time = datetime.datetime.fromtimestamp(0)

    start = datetime.datetime.now()
    nicks = set()
    masks = set()
    hosts = set()
    addrs = set()

    mask_rows = db.execute(
        select([masks_table.c.nick_case, masks_table.c.mask],
               and_(func.lower(masks_table.c.mask) == host_lower, masks_table.c.seen >= last_time))
    ).fetchall()

    masks.update(row["mask"] for row in mask_rows)

    nicks.update(row["nick_case"] for row in mask_rows)

    if admin:
        host_rows = db.execute(
            select([hosts_table.c.nick_case, hosts_table.c.host],
                   and_(func.lower(hosts_table.c.host) == host_lower, hosts_table.c.seen >= last_time))
        ).fetchall()

        hosts.update(row["host"] for row in host_rows)

        nicks.update(row["nick_case"] for row in host_rows)

        addr_rows = db.execute(
            select([address_table.c.nick_case, address_table.c.addr],
                   and_(func.lower(address_table.c.addr) == host_lower, address_table.c.seen >= last_time))
        ).fetchall()

        addrs.update(row["addr"] for row in addr_rows)

        nicks.update(row["nick_case"] for row in addr_rows)

    end = datetime.datetime.now()

    query_time = end - start

    for line in format_results_or_paste(host, query_time.total_seconds(), nicks, masks, hosts, addrs, admin):
        message(line)


@hook.command("rawquery", permissions=["botcontrol"])
def raw_query(text, db, reply, conn):
    if not conn.nick.lower().endswith('-dev'):
        # This command should be disabled in the production bot
        return "This command may only be used in testing"

    try:
        start = datetime.datetime.now()
        res = db.execute(text)
        end = datetime.datetime.now()
        duration = end - start
    except Exception as e:
        reply(str(e))
        raise
    else:
        if res.returns_rows:
            lines = [
                "Results for '{}':".format(text),
                *res,
                "Completed in {:.3f} seconds".format(duration.total_seconds())
            ]
        else:
            lines = [
                "{} rows affected in {:.3f} seconds.".format(res.rowcount, duration.total_seconds())
            ]

        if len(lines) > 5:
            return web.paste('\n'.join(lines))
        else:
            return lines


@hook.command("nickstats", permissions=["botcontrol"])
def db_stats(db):
    host_rows = db.execute(select([hosts_table.c.nick, hosts_table.c.host]))
    address_rows = db.execute(select([address_table.c.nick, address_table.c.addr]))
    mask_rows = db.execute(select([masks_table.c.nick, masks_table.c.mask]))

    nicks = set()
    hosts = set()
    masks = set()
    addresses = set()

    for row in host_rows:
        nicks.add(row["nick"])
        hosts.add(row["host"])

    for row in address_rows:
        nicks.add(row["nick"])
        addresses.add(row["addr"])

    for row in mask_rows:
        nicks.add(row["nick"])
        masks.add(row["mask"])

    stats = [
        pluralize(len(nicks), "nick"),
        pluralize(len(hosts), "host"),
        pluralize(len(addresses), "address"),
        pluralize(len(masks), "mask"),
    ]

    return get_text_list(stats, 'and')


@hook.command("futcount", permissions=["botcontrol"])
def fut_count(conn, message):
    message(counts)
    futs = conn.memory["sherlock"]["futures"]
    message(len(futs))
    for key, data in futs.items():
        message("{}: {}".format(key, len(data)))


@hook.command("dumpdata", permissions=["botcontrol"])
def dump_data(conn):
    return conn.memory["sherlock"]["futures"]
