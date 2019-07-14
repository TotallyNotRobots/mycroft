"""
Nick/user tracking

Author:
    - linuxdaemon <linuxdaemon@snoonet.org>
"""

import datetime
import hashlib
import json
import os
import re
import shlex
import zlib
from argparse import ArgumentParser
from base64 import b64encode
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from operator import itemgetter

import requests
from requests import RequestException
from sjcl import SJCL
from sqlalchemy import func, column

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


def compress(s):
    co = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    b = co.compress(s) + co.flush()

    return b64encode(''.join(map(chr, b)).encode())


def encode_cipher(cipher):
    for k in ['salt', 'iv', 'ct']:
        cipher[k] = cipher[k].decode()

    return cipher


def do_paste(it):
    try:
        url = web.pastebins['privatebin'].paste('\n'.join(it), 'yaml', expire='1hour')
    except (RequestException, web.ServiceError) as e:
        return "Paste failed. ({})".format(e)

    return "Paste: {} (paste expires in 1 hour)".format(url)


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

def filter_seen(_query, last_seen):
    if last_seen is not None:
        return _query.where(column('seen') > last_seen)

    return _query


def get_for_nicks(db, table, column_name, nicks, last_seen=None):
    nicks = [row[0][0] for row in nicks]
    _query = filter_seen(table.select().where(table.c.nick.in_(nicks)), last_seen)

    results = db.execute(_query)

    return [[row[column_name], row['seen']] for row in results]


def get_hosts_for_nicks(db, nicks, last_seen=None):
    return get_for_nicks(db, hosts_table, 'host', nicks, last_seen)


def get_addrs_for_nicks(db, nicks, last_seen=None):
    return get_for_nicks(db, address_table, 'addr', nicks, last_seen)


def get_masks_for_nicks(db, nicks, last_seen=None):
    return get_for_nicks(db, masks_table, 'mask', nicks, last_seen)


def get_nicks(db, table, column_name, values, last_seen=None):
    values = [v[0].lower() for v in values]
    _query = filter_seen(table.select().where(func.lower(table.c[column_name]).in_(values)), last_seen)

    results = db.execute(_query)

    return [((row['nick'], row['nick_case']), row['seen']) for row in results]


CLOAK_STRIP_PREFIX_RE = re.compile(r'^(?i:Snoonet-|irc-)(.*)\.IP$')
CLOAK_FORMATS = [
    "Snoonet-{cloak}.IP",
    "irc-{cloak}.IP",
]


def get_nicks_for_mask(db, mask, last_seen=None):
    new_masks = []
    for m in mask:
        msk, *other = m
        cloak = CLOAK_STRIP_PREFIX_RE.match(msk)
        if not cloak:
            new_masks.append(m)
            continue

        new_masks.extend((
            (fmt.format(cloak=cloak.group(1)), *other)
            for fmt in CLOAK_FORMATS
        ))

    return get_nicks(db, masks_table, 'mask', new_masks, last_seen)


def get_nicks_for_host(db, host, last_seen=None):
    return get_nicks(db, hosts_table, 'host', host, last_seen)


def get_nicks_for_addr(db, addr, last_seen=None):
    return get_nicks(db, address_table, 'addr', addr, last_seen)


class QueryResults:
    def __init__(self, nicks=(), masks=(), hosts=(), addrs=()):
        self.nicks = list(nicks)
        self.masks = list(masks)
        self.hosts = list(hosts)
        self.addrs = list(addrs)

    def copy(self):
        return type(self)(*(l.copy() for l in self))

    __copy__ = copy

    def __iter__(self):
        return iter([self.nicks, self.masks, self.hosts, self.addrs])

    def __add__(self, other):
        if not isinstance(other, QueryResults):
            other = QueryResults(*other)

        self_copy = self.copy()

        for a, b in zip(self_copy, other):
            a.extend(b)

        return self_copy


def _query(db, nicks, masks, hosts, addrs, last_seen):
    """
    :type db: sqlalchemy.orm.Session
    """
    results = QueryResults()

    if nicks:
        results.masks.extend(get_masks_for_nicks(db, nicks, last_seen))
        results.hosts.extend(get_hosts_for_nicks(db, nicks, last_seen))
        results.addrs.extend(get_addrs_for_nicks(db, nicks, last_seen))

    if masks:
        results.nicks.extend(get_nicks_for_mask(db, masks, last_seen))

    if hosts:
        results.nicks.extend(get_nicks_for_host(db, hosts, last_seen))

    if addrs:
        results.nicks.extend(get_nicks_for_addr(db, addrs, last_seen))

    return results


def query(db, nicks=None, masks=None, hosts=None, addrs=None, last_seen=None, depth=0, first=True):
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

    results = _query(db, nicks, masks, hosts, addrs, last_seen)

    if not first:
        results += (nicks, masks, hosts, addrs)

    return query(
        db, results.nicks, results.masks, results.hosts, results.addrs, last_seen, depth - 1, False
    )


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
        if _hosts or _addrs:
            return "Non-admin users can not use the host or address lookup."

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
def new_check(conn, chan, triggered_command, text, db, reply):
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

    parser.add_argument(
        '--last-seen', dest="lastseen", type=timeparse.time_parse, default=None,
        help="Set the time frame to gather data from "
             "(ex. --last-seen=\"1d12h\" to match data from the last day and a half)"
    )

    s_out = StringIO()
    s_err = StringIO()

    try:
        splt = shlex.split(text)
    except ValueError as e:
        reply(str(e))
        raise

    with redirect_stdout(s_out), redirect_stderr(s_err):
        try:
            args = parser.parse_args(splt)
        except SystemExit:
            out = s_out.getvalue() + s_err.getvalue()
            return web.paste(out)

    paste = paste_options[args.paste]
    if args.lastseen is None:
        last_seen = None
    else:
        last_seen = datetime.datetime.now() - datetime.timedelta(seconds=args.lastseen)

    return query_and_format(
        db, args.nick, args.mask, args.host, args.addr, depth=args.depth, is_admin=admin, paste=paste,
        last_seen=last_seen
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
def check_host_command(db, conn, chan, text):
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

    if admin:
        hosts = host_lower
        addrs = host_lower
    else:
        hosts = None
        addrs = None

    return query_and_format(db, _masks=host_lower, _hosts=hosts, _addrs=addrs, last_seen=last_time,
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
