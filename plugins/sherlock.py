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
from contextlib import suppress

import requests
from requests import RequestException
from sqlalchemy import Table, Column, String, DateTime, Boolean, select

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import database, colors
from cloudbot.util.async_util import create_future
from cloudbot.util.formatting import chunk_str, pluralize, get_text_list

MAX_NICK = 40
MAX_IP = 39
MAX_HOST = 64

address_table = Table(
    'addrs',
    database.metadata,
    Column('nick', String(MAX_NICK)),
    Column('addr', String(MAX_IP)),
    Column('id', String(MAX_NICK + 1 + MAX_IP), unique=True),
    Column('created', DateTime),
    Column('seen', DateTime),
    Column('reg', Boolean)
)

hosts_table = Table(
    'hosts',
    database.metadata,
    Column('nick', String(MAX_NICK)),
    Column('host', String(MAX_HOST)),
    Column('id', String(MAX_NICK + 1 + MAX_HOST), unique=True),
    Column('created', DateTime),
    Column('seen', DateTime),
    Column('reg', Boolean)
)

masks_table = Table(
    'masks',
    database.metadata,
    Column('nick', String(MAX_NICK)),
    Column('mask', String(MAX_HOST)),
    Column('id', String(MAX_NICK + 1 + MAX_HOST), unique=True),
    Column('created', DateTime),
    Column('seen', DateTime),
    Column('reg', Boolean)
)


def format_list(name, data):
    begin = colors.parse("$(dgreen){}$(clear): ".format(name))
    body = ', '.join(set(data))

    return chunk_str(begin + body)


def update_user_data(db, table, column_name, now, nick, value):
    id_value = nick + "+" + value
    res = db.execute(table.update().values(seen=now).where(table.c.id == id_value))
    if res.rowcount == 0:
        args = {
            'nick': nick,
            column_name: value,
            'id': id_value,
            'created': now,
            'seen': now,
            'reg': False
        }

        db.execute(table.insert().values(**args))

    db.commit()


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


response_map = {
    '352': ("user_mask", _handle_who_response),
    '302': ("user_host", _handle_userhost_response),
    '340': ("user_ip", _handle_userhost_response),  # USERIP responds with the same format as USERHOST
}


@asyncio.coroutine
def await_response(fut):
    return (yield from asyncio.wait_for(fut, 30))


@asyncio.coroutine
def await_command_response(conn, name, cmd, nick):
    futs = conn.memory["sherlock"]["futures"][name]
    try:
        fut = futs[nick]
    except LookupError:
        futs[nick] = fut = create_future(conn.loop)
        conn.cmd(cmd, nick)

    try:
        res = yield from await_response(fut)
    finally:
        with suppress(KeyError):
            del futs[nick]

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


@hook.on_start
def clear_regex_cache(bot):
    for conn in bot.connections.values():
        get_regex_cache(conn).clear()


@hook.on_start
def init_futures(bot):
    for conn in bot.connections.values():
        conn.memory["sherlock"] = {
            "futures": {
                "user_host": {},
                "user_ip": {},
                "user_mask": {}
            }
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
        fut = futs.pop(nick.lower())
    except LookupError:
        return

    fut.set_result(value.strip())


@asyncio.coroutine
def handle_snotice(db, event):
    conn = event.conn
    content = event.content
    for name, handler in HANDLERS.items():
        regex = get_regex(conn, name)
        match = regex.match(content)
        if match:
            print(name)
            yield from handler(db, event, match)
            break


@asyncio.coroutine
def set_user_data(event, db, table, column_name, now, nick, value_func):
    value = yield from value_func(event.conn, nick)
    yield from event.async_call(update_user_data, db, table, column_name, now, nick, value)


@asyncio.coroutine
def on_nickchange(db, event, match):
    old_nick = match.group('oldnick').lower()
    new_nick = match.group('newnick').lower()
    now = datetime.datetime.now()

    @asyncio.coroutine
    def _handle_set(table, name, func):
        value = yield from func(event.conn, new_nick)
        yield from asyncio.gather(
            event.async_call(update_user_data, db, table, name, now, old_nick, value),
            event.async_call(update_user_data, db, table, name, now, new_nick, value)
        )

    coros = [
        _handle_set(hosts_table, 'host', get_user_host),
        _handle_set(address_table, 'addr', get_user_ip),
        _handle_set(masks_table, 'mask', get_user_mask),
    ]

    yield from asyncio.gather(*coros)


@asyncio.coroutine
def on_connect(db, event, match):
    nick = match.group('nick').lower()
    ident = match.group('ident')
    host = match.group('host')
    addr = match.group('addr')

    now = datetime.datetime.now()

    coros = [
        event.async_call(update_user_data, db, hosts_table, 'host', now, nick, host),
        event.async_call(update_user_data, db, address_table, 'addr', now, nick, addr),
        set_user_data(event, db, masks_table, 'mask', now, nick, get_user_mask),
    ]

    yield from asyncio.gather(*coros)


HANDLERS = {
    'nick': on_nickchange,
    'connect': on_connect,
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


@hook.command("check")
def check_command(conn, chan, text, db, message):
    """<nick> - Looks up [nick] in the users database"""
    allowed, admin = check_channel(conn, chan)

    if not allowed:
        return

    nick = text.split(None, 1)[0].strip()

    lower_nick = nick.lower()

    start = datetime.datetime.now()

    host_rows = db.execute(select([hosts_table.c.host], hosts_table.c.nick == lower_nick))

    hosts = [row["host"] for row in host_rows]

    nick_rows = db.execute(select([hosts_table.c.nick, hosts_table.c.reg], hosts_table.c.host.in_(hosts)))

    nicks = [row["nick"] for row in nick_rows]

    addr_rows = db.execute(select([address_table.c.addr], address_table.c.nick == lower_nick))

    addresses = [row["addr"] for row in addr_rows]

    nick_addr_rows = db.execute(select([address_table.c.nick], address_table.c.addr.in_(addresses)))

    nicks.extend(row["nick"] for row in nick_addr_rows)

    mask_rows = db.execute(select([masks_table.c.mask], masks_table.c.nick == lower_nick))

    masks = [row["mask"] for row in mask_rows]

    nick_mask_rows = db.execute(select([masks_table.c.nick], masks_table.c.mask.in_(addresses)))

    nicks.extend(row["nick"] for row in nick_mask_rows)

    query_time = datetime.datetime.now() - start

    nicks = set(nicks)
    masks = set(masks)
    hosts = set(hosts)
    addresses = set(addresses)

    for line in format_results_or_paste(nick, query_time.total_seconds(), nicks, masks, hosts, addresses, admin):
        message(line)


@hook.command("check2", "checkhost")
def check_host_command(db, conn, chan, text, message):
    """<host> - Looks up [host] in the users database"""
    allowed, admin = check_channel(conn, chan)

    if not allowed:
        return

    host = text.split(None, 1)[0].strip()

    start = datetime.datetime.now()

    nick_rows = db.execute(select([hosts_table.c.nick], hosts_table.c.host == host))

    nicks = [row["nick"] for row in nick_rows]

    end = datetime.datetime.now()

    query_time = end - start

    for line in format_results_or_paste(host, query_time.total_seconds(), set(nicks), [], [], [], admin):
        message(line)


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
