import asyncio
from collections import defaultdict
from datetime import datetime

from sqlalchemy import Table, Column, String, Boolean, DateTime, PrimaryKeyConstraint
from sqlalchemy.sql import select

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import timeformat, database, web
from cloudbot.util.formatting import gen_markdown_table

table = Table(
    'tells',
    database.metadata,
    Column('connection', String(25)),
    Column('sender', String(25)),
    Column('target', String(25)),
    Column('message', String(500)),
    Column('is_read', Boolean),
    Column('time_sent', DateTime),
    Column('time_read', DateTime)
)

ignore_table = Table(
    'tell_ignores',
    database.metadata,
    Column('conn', String),
    Column('target', String),
    Column('setter', String),
    Column('set_at', DateTime),
    PrimaryKeyConstraint('conn', 'target'),
)

ignore_cache = defaultdict(set)


@hook.on_start
def load_cache(db):
    """
    :type db: sqlalchemy.orm.Session
    """
    global tell_cache
    tell_cache = []
    for row in db.execute(table.select().where(table.c.is_read == 0)):
        conn = row["connection"]
        target = row["target"]
        tell_cache.append((conn, target))


@hook.on_start
def load_ignores(db):
    """
    :type db: sqlalchemy.orm.Session
    """
    ignore_cache.clear()
    for row in db.execute(ignore_table.select()):
        ignore_cache[row['conn']].add(row['target'].lower())


def is_ignored(conn, target):
    """
    :type conn: cloudbot.client.Client
    :type target: str
    :rtype: bool
    """
    return target.lower() in ignore_cache[conn.name.lower()]


def add_ignore(db, conn, setter, target, now=None):
    """
    :type db: sqlalchemy.orm.Session
    :type conn: cloudbot.client.Client
    :type setter: str
    :type target: str
    :type now: datetime
    """
    if now is None:
        now = datetime.now()

    db.execute(ignore_table.insert().values(conn=conn.name.lower(), setter=setter, set_at=now, target=target.lower()))
    db.commit()
    load_ignores(db)


def del_ignore(db, conn, target):
    """
    :type db: sqlalchemy.orm.Session
    :type conn: cloudbot.client.Client
    :type target: str
    """
    db.execute(
        ignore_table.delete().where(ignore_table.c.conn == conn.name.lower())
            .where(ignore_table.c.target == target.lower())
    )
    db.commit()
    load_ignores(db)


def list_ignores(db, conn):
    """
    :type db: sqlalchemy.orm.Session
    :type conn: cloudbot.client.Client
    """
    for row in db.execute(ignore_table.select().where(ignore_table.c.conn == conn.name.lower())):
        yield (row['conn'], row['target'], row['setter'], row['set_at'].ctime())


def get_unread(db, server, target):
    """
    :type db: sqlalchemy.orm.Session
    :type server: str
    :type target: str
    """
    query = select([table.c.sender, table.c.message, table.c.time_sent]) \
        .where(table.c.connection == server.lower()) \
        .where(table.c.target == target.lower()) \
        .where(table.c.is_read == 0) \
        .order_by(table.c.time_sent)
    return db.execute(query).fetchall()


def count_unread(db, server, target):
    query = select([table]) \
        .where(table.c.connection == server.lower()) \
        .where(table.c.target == target.lower()) \
        .where(table.c.is_read == 0) \
        .alias("count") \
        .count()
    return db.execute(query).fetchone()[0]


def read_all_tells(db, server, target):
    query = table.update() \
        .where(table.c.connection == server.lower()) \
        .where(table.c.target == target.lower()) \
        .where(table.c.is_read == 0) \
        .values(is_read=1)
    db.execute(query)
    db.commit()
    load_cache(db)


def read_tell(db, server, target, message):
    query = table.update() \
        .where(table.c.connection == server.lower()) \
        .where(table.c.target == target.lower()) \
        .where(table.c.message == message) \
        .values(is_read=1)
    db.execute(query)
    db.commit()
    load_cache(db)


def add_tell(db, server, sender, target, message):
    query = table.insert().values(
        connection=server.lower(),
        sender=sender.lower(),
        target=target.lower(),
        message=message,
        is_read=False,
        time_sent=datetime.today()
    )
    db.execute(query)
    db.commit()
    load_cache(db)


def tell_check(conn, nick):
    for _conn, _target in tell_cache:
        if (conn, nick.lower()) == (_conn, _target):
            return True


@hook.event([EventType.message, EventType.action], singlethread=True)
def tellinput(event, conn, db, nick, notice):
    """
    :type event: cloudbot.event.Event
    :type conn: cloudbot.client.Client
    :type db: sqlalchemy.orm.Session
    """
    if 'showtells' in event.content.lower():
        return

    if tell_check(conn.name, nick):
        tells = get_unread(db, conn.name, nick)
    else:
        return

    if tells:
        user_from, message, time_sent = tells[0]
        reltime = timeformat.time_since(time_sent)

        if reltime == 0:
            reltime_formatted = "just a moment"
        else:
            reltime_formatted = reltime

        reply = "{} sent you a message {} ago: {}".format(user_from, reltime_formatted, message)
        if len(tells) > 1:
            reply += " (+{} more, {}showtells to view)".format(len(tells) - 1, conn.config["command_prefix"][0])

        read_tell(db, conn.name, nick, message)
        notice(reply)


@hook.command(autohelp=False)
def showtells(nick, notice, db, conn):
    """- View all pending tell messages (sent in a notice)."""

    tells = get_unread(db, conn.name, nick)

    if not tells:
        notice("You have no pending messages.")
        return

    for tell in tells:
        sender, message, time_sent = tell
        past = timeformat.time_since(time_sent)
        notice("{} sent you a message {} ago: {}".format(sender, past, message))

    read_all_tells(db, conn.name, nick)


@hook.command("tell")
def tell_cmd(text, nick, db, notice, conn, notice_doc, is_nick_valid):
    """<nick> <message> - Relay <message> to <nick> when <nick> is around."""
    query = text.split(' ', 1)

    if len(query) != 2:
        notice_doc()
        return

    target = query[0]
    message = query[1].strip()
    sender = nick

    if is_ignored(conn, target):
        notice("You may not send a tell to that user.")
        return

    if target.lower() == sender.lower():
        notice("Have you looked in a mirror lately?")
        return

    if not is_nick_valid(target.lower()) or target.lower() == conn.nick.lower():
        notice("Invalid nick '{}'.".format(target))
        return

    if count_unread(db, conn.name, target.lower()) >= 10:
        notice("Sorry, {} has too many messages queued already.".format(target))
        return

    add_tell(db, conn.name, sender, target.lower(), message)
    notice("Your message has been saved, and {} will be notified once they are active.".format(target))


def check_permissions(event, *perms):
    return any(event.has_permission(perm) for perm in perms)


@hook.command("tellignore", autohelp=False)
def tell_ignore(conn, db, text, nick, event):
    """[nick] - Disallow tells being sent to [nick]"""
    is_self = False
    if not text or text.casefold() == nick.casefold():
        text = nick
        is_self = True
    elif not check_permissions(event, 'botcontrol', 'ignore'):
        event.notice("Sorry, you are not allowed to use this command.")
        return None

    target = text.split()[0]
    if is_ignored(conn, target):
        return "{!r} will already not receive any tells.".format(
            "You" if is_self else target
        )

    add_ignore(db, conn, nick, target)
    return "{!r} can no longer be sent tells.".format(
        "You" if is_self else target
    )


@hook.command("tellunignore", autohelp=False)
def tell_unignore(conn, db, text, event, nick):
    """[nick] - Removes [nick] from the tellignore list"""
    is_self = False
    if not text or text.casefold() == nick.casefold():
        text = nick
        is_self = True
    elif not check_permissions(event, 'botcontrol', 'ignore'):
        event.notice("Sorry, you are not allowed to use this command.")
        return None

    target = text.split()[0]
    if not is_ignored(conn, target):
        return "{!r} will already receive tells.".format(
            "You" if is_self else target
        )

    del_ignore(db, conn, target)
    return "{!r} can now be sent tells.".format(
        "You" if is_self else target
    )


@hook.command("listtellignores", permissions=["botcontrol", "ignore"])
def tell_list_ignores(conn, db):
    """- Returns the current list of people who are not able to recieve tells"""
    ignores = list(list_ignores(db, conn))
    md = gen_markdown_table(["Connection", "Target", "Setter", "Set At"], ignores)
    return web.paste(md, 'md', 'hastebin')
