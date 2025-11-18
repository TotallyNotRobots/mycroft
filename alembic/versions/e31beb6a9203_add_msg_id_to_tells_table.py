"""Add msg_id to tells table

Revision ID: e31beb6a9203
Revises: 18971030c3e0
Create Date: 2025-11-17 21:20:53.433195

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

from cloudbot.util.database import Session

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e31beb6a9203"
down_revision: str | Sequence[str] | None = "18971030c3e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = sa.inspect(op.get_bind())
    old_table = sa.table(
        "tells",
        sa.column("connection", sa.String),
        sa.column("sender", sa.String),
        sa.column("target", sa.String),
        sa.column("message", sa.String),
        sa.column("is_read", sa.Boolean),
        sa.column("time_sent", sa.DateTime),
        sa.column("time_read", sa.DateTime),
    )
    if inspector.has_table(old_table.name):
        with Session(bind=op.get_bind()) as session:
            old_tells = (
                session.execute(sa.select(old_table)).mappings().fetchall()
            )

        op.drop_table("tell_messages", if_exists=True)
        new_table = op.create_table(
            "tell_messages",
            sa.Column(
                "msg_id", sa.Integer, primary_key=True, autoincrement=True
            ),
            sa.Column("conn", sa.String, index=True),
            sa.Column("sender", sa.String),
            sa.Column("target", sa.String, index=True),
            sa.Column("message", sa.String),
            sa.Column("is_read", sa.Boolean, default=False, index=True),
            sa.Column("time_sent", sa.DateTime),
            sa.Column("time_read", sa.DateTime),
        )

        op.bulk_insert(
            new_table,
            [
                {
                    "conn": row["connection"],
                    "sender": row["sender"],
                    "target": row["target"],
                    "message": row["message"],
                    "is_read": row["is_read"],
                    "time_sent": row["time_sent"],
                    "time_read": row["time_read"],
                }
                for row in old_tells
            ],
        )

        op.drop_table(old_table.name)


def downgrade() -> None:
    """Downgrade schema."""
    inspector = sa.inspect(op.get_bind())
    new_table = sa.table(
        "tell_messages",
        sa.column("msg_id", sa.Integer),
        sa.column("conn", sa.String),
        sa.column("sender", sa.String),
        sa.column("target", sa.String),
        sa.column("message", sa.String),
        sa.column("is_read", sa.Boolean),
        sa.column("time_sent", sa.DateTime),
        sa.column("time_read", sa.DateTime),
    )

    if inspector.has_table(new_table.name):
        with Session(bind=op.get_bind()) as session:
            new_tells = (
                session.execute(sa.select(new_table)).mappings().fetchall()
            )

        op.drop_table("tells", if_exists=True)
        old_table = op.create_table(
            "tells",
            sa.Column("connection", sa.String, index=True),
            sa.Column("sender", sa.String),
            sa.Column("target", sa.String, index=True),
            sa.Column("message", sa.String),
            sa.Column("is_read", sa.Boolean, default=False, index=True),
            sa.Column("time_sent", sa.DateTime),
            sa.Column("time_read", sa.DateTime),
        )

        op.bulk_insert(
            old_table,
            [
                {
                    "connection": row["conn"],
                    "sender": row["sender"],
                    "target": row["target"],
                    "message": row["message"],
                    "is_read": row["is_read"],
                    "time_sent": row["time_sent"],
                    "time_read": row["time_read"],
                }
                for row in new_tells
            ],
        )

        op.drop_table(new_table.name)
