"""Update quote table to use booleans

Revision ID: 18971030c3e0
Revises: 60f88c7765e0
Create Date: 2025-11-17 19:28:52.970673

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

from cloudbot.util.database import Session

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.sql import TableClause

# revision identifiers, used by Alembic.
revision: str = "18971030c3e0"
down_revision: str | Sequence[str] | None = "60f88c7765e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = sa.inspect(op.get_bind())
    old_table: TableClause = sa.table(
        "quote",
        sa.column("chan", sa.String(25)),
        sa.column("nick", sa.String(25)),
        sa.column("add_nick", sa.String(25)),
        sa.column("msg", sa.String(500)),
        sa.column("time", sa.REAL),
        sa.column("deleted", sa.String(5)),
    )

    if inspector.has_table(old_table.name):
        with Session(bind=op.get_bind()) as session:
            old_quotes = session.execute(sa.select(old_table)).fetchall()

        op.drop_table("new_quote", if_exists=True)
        new_table = op.create_table(
            "new_quote",
            sa.Column("chan", sa.String),
            sa.Column("nick", sa.String),
            sa.Column("add_nick", sa.String),
            sa.Column("msg", sa.String),
            sa.Column("time", sa.REAL),
            sa.Column("deleted", sa.Boolean, default=False),
            sa.PrimaryKeyConstraint("chan", "nick", "msg"),
        )
        op.bulk_insert(
            new_table.name,
            [
                {
                    "chan": row.chan,
                    "nick": row.nick,
                    "add_nick": row.add_nick,
                    "msg": row.msg,
                    "time": row.time,
                    "deleted": row.deleted in (1, "1", True),
                }
                for row in old_quotes
            ],
        )
        op.drop_table(old_table.name)


def downgrade() -> None:
    """Downgrade schema."""
    inspector = sa.inspect(op.get_bind())
    new_table: TableClause = sa.table(
        "new_quote",
        sa.column("chan", sa.String(25)),
        sa.column("nick", sa.String(25)),
        sa.column("add_nick", sa.String(25)),
        sa.column("msg", sa.String(500)),
        sa.column("time", sa.REAL),
        sa.column("deleted", sa.Boolean, default=False),
    )

    if inspector.has_table(new_table.name):
        with Session(bind=op.get_bind()) as session:
            new_quotes = session.execute(sa.select(new_table)).fetchall()

        op.drop_table("quote", if_exists=True)
        old_table = op.create_table(
            "quote",
            sa.Column("chan", sa.String(25)),
            sa.Column("nick", sa.String(25)),
            sa.Column("add_nick", sa.String(25)),
            sa.Column("msg", sa.String(500)),
            sa.Column("time", sa.REAL),
            sa.Column("deleted", sa.String(5), default=0),
            sa.PrimaryKeyConstraint("chan", "nick", "time"),
        )

        op.bulk_insert(
            old_table.name,
            [
                {
                    "chan": row.chan,
                    "nick": row.nick,
                    "add_nick": row.add_nick,
                    "msg": row.msg,
                    "time": row.time,
                    "deleted": 1 if row.deleted else 0,
                }
                for row in new_quotes
            ],
        )

        op.drop_table(new_table.name)
