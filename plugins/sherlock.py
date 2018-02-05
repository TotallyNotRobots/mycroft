"""
Nick/user tracking

Author:
    - linuxdaemon <linuxdaemon@snoonet.org>
"""

import datetime
import random
import string
from argparse import ArgumentParser
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from operator import itemgetter

import requests
from requests import RequestException
from sqlalchemy import func

from cloudbot import hook
from cloudbot.util import colors, timeparse, web
from cloudbot.util.formatting import chunk_str, get_text_list, pluralize_auto
from plugins.user_tracking import hosts_table, address_table, masks_table, rfc_casefold


def format_list(name, data):
    begin = colors.parse("$(dgreen){}$(clear): ".format(name))
    body = ', '.join(data)

    return chunk_str(begin + body)


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
            get_text_list([pluralize_auto(count, thing) for count, thing in counts], 'and'), duration)


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


def format_results_or_paste(terms, duration, nicks, masks, hosts, addresses, is_admin, paste=None):
    if isinstance(terms, str):
        terms = [terms]

    terms_list = get_text_list(["'{}'".format(term) for term in terms], 'and')
    yield "Results for {}:".format(terms_list)
    lines = list(format_results(nicks, masks, hosts, addresses, is_admin))
    if (len(lines) > 5 and paste is not False) or paste is True:
        yield do_paste(paste_results(nicks, masks, hosts, addresses, is_admin))
    else:
        yield from lines

    yield format_count(nicks, masks, hosts, addresses, is_admin, duration)


# QUERY FUNCTIONS

def filter_seen(table, _query, last_seen):
    if last_seen is not None:
        return _query.where(table.c.seen > last_seen)

    return _query


def get_for_nicks(db, table, column, nicks, last_seen=None):
    nicks = [row[0][0] for row in nicks]
    _query = filter_seen(table, table.select().where(table.c.nick.in_(nicks)), last_seen)

    results = db.execute(_query)

    return [[row[column], row['seen']] for row in results]


def get_hosts_for_nicks(db, nicks, last_seen=None):
    return get_for_nicks(db, hosts_table, 'host', nicks, last_seen)


def get_addrs_for_nicks(db, nicks, last_seen=None):
    return get_for_nicks(db, address_table, 'addr', nicks, last_seen)


def get_masks_for_nicks(db, nicks, last_seen=None):
    return get_for_nicks(db, masks_table, 'mask', nicks, last_seen)


def get_nicks(db, table, column, values, last_seen=None):
    values = [v[0].lower() for v in values]
    _query = filter_seen(table, table.select().where(func.lower(table.c[column]).in_(values)), last_seen)

    results = db.execute(_query)

    return [((row['nick'], row['nick_case']), row['seen']) for row in results]


def get_nicks_for_mask(db, mask, last_seen=None):
    return get_nicks(db, masks_table, 'mask', mask, last_seen)


def get_nicks_for_host(db, host, last_seen=None):
    return get_nicks(db, hosts_table, 'host', host, last_seen)


def get_nicks_for_addr(db, addr, last_seen=None):
    return get_nicks(db, address_table, 'addr', addr, last_seen)


def query(db, nicks=None, masks=None, hosts=None, addrs=None, last_seen=None, depth=0):
    _nicks = []
    _masks = []
    _hosts = []
    _addrs = []

    def _to_list(var):
        if not var:
            return []
        elif isinstance(var, str):
            return [(var, datetime.datetime.now())]
        return var

    nicks = _to_list(nicks)
    masks = _to_list(masks)
    hosts = _to_list(hosts)
    addrs = _to_list(addrs)

    if depth < 0:
        return nicks, masks, hosts, addrs

    if nicks:
        _masks.extend(get_masks_for_nicks(db, nicks, last_seen))
        _hosts.extend(get_hosts_for_nicks(db, nicks, last_seen))
        _addrs.extend(get_addrs_for_nicks(db, nicks, last_seen))

    if masks:
        _nicks.extend(get_nicks_for_mask(db, masks, last_seen))

    if hosts:
        _nicks.extend(get_nicks_for_host(db, hosts, last_seen))

    if addrs:
        _nicks.extend(get_nicks_for_addr(db, addrs, last_seen))

    return query(db, _nicks + nicks, _masks + masks, _hosts + hosts, _addrs + addrs, last_seen, depth - 1)


def query_and_format(db, _nicks=None, _masks=None, _hosts=None, _addrs=None, last_seen=None, depth=1, is_admin=False,
                     paste=None):
    def _to_list(_arg):
        if _arg is None:
            return []
        elif isinstance(_arg, str):
            return [_arg]

        return _arg

    if not is_admin:
        # Don't perform host and address lookups in non-admin channels
        _hosts = None
        _addrs = None

        if depth > 5:
            return "Recursion depth can not exceed 5 for non-admin users."

    elif depth > 20:
        return "Recursion depth can not exceed 20."

    _nicks = _to_list(_nicks)
    _masks = _to_list(_masks)
    _hosts = _to_list(_hosts)
    _addrs = _to_list(_addrs)

    start = datetime.datetime.now()

    def _wrap_list(_data):
        return [(item, datetime.datetime.fromtimestamp(0)) for item in _data]

    __nicks = _wrap_list(_nicks)
    __masks = _wrap_list(_masks)
    __hosts = _wrap_list(_hosts)
    __addrs = _wrap_list(_addrs)

    __nicks = [((rfc_casefold(_nick), _nick), _seen) for _nick, _seen in __nicks]

    nicks, masks, hosts, addrs = query(db, __nicks, __masks, __hosts, __addrs, last_seen, depth)
    end = datetime.datetime.now()
    query_time = end - start
    nicks = [(nick_case, time) for (_nick, nick_case), time in nicks]

    tables = {
        "nicks": nicks,
        "masks": masks,
        "hosts": hosts,
        "addresses": addrs,
    }

    data = {name: defaultdict(lambda: datetime.datetime.fromtimestamp(0)) for name in tables}
    for name, tbl in tables.items():
        _data = data[name]
        for val, seen in tbl:
            _data[val] = max(_data[val], seen)

    out = {
        name: list(map(itemgetter(0), sorted(values.items(), key=itemgetter(1), reverse=True)))
        for name, values in data.items()
    }

    search_terms = [term for term in set(_nicks + _masks + _hosts + _addrs) if term]
    lines = tuple(
        format_results_or_paste(search_terms, query_time.total_seconds(), **out, is_admin=is_admin, paste=paste)
    )

    return lines


@hook.command("checkadv", "newcheck", "checkadvanced", singlethread=True)
def new_check(conn, chan, triggered_command, text, db):
    """[options] - Use -h to view full help for this command"""
    allowed, admin = check_channel(conn, chan)

    if not allowed:
        return

    parser = ArgumentParser(prog=triggered_command)

    parser.add_argument('--nick', help="Gather all data linked to NICK", action="append")
    parser.add_argument('--host', help="Gather all data linked to HOST", action="append")
    parser.add_argument('--mask', help="Gather all data linked to MASK", action="append")
    parser.add_argument('--addr', help="Gather all data linked to ADDR", action="append")

    paste_options = {
        'yes': True,
        'no': False,
        'auto': None,
    }

    parser.add_argument(
        '--paste', choices=list(paste_options), default='auto',
        help="Controls whether to force pasting of the results or not"
    )

    parser.add_argument('--depth', '-d', type=int, default=1, help="Set the maximum recursion depth")

    s_out = StringIO()
    s_err = StringIO()

    with redirect_stdout(s_out), redirect_stderr(s_err):
        try:
            args = parser.parse_args(text.split())
        except SystemExit:
            out = s_out.getvalue() + s_err.getvalue()
            return web.paste(out)

    paste = paste_options[args.paste]

    return query_and_format(
        db, args.nick, args.mask, args.host, args.addr, depth=args.depth, is_admin=admin, paste=paste
    )


@hook.command("check")
def check_command(conn, chan, text, db):
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
            last_time = None
        else:
            time_span = datetime.timedelta(seconds=timeparse.time_parse(interval_str))
            last_time = now + time_span
    else:
        last_time = None

    return query_and_format(db, nick, last_seen=last_time, is_admin=admin)


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
            last_time = None
        else:
            time_span = datetime.timedelta(seconds=timeparse.time_parse(interval_str))
            last_time = now + time_span
    else:
        last_time = None

    return query_and_format(db, _masks=host_lower, _hosts=host_lower, _addrs=host_lower, last_seen=last_time,
                            is_admin=admin)


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
                *("{}".format(tuple(r)) for r in res),
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
