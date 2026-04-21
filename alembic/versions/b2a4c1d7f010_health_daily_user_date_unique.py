"""health_daily unique (user_id, date)

Revision ID: b2a4c1d7f010
Revises: dddb487ae950
Create Date: 2026-04-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2a4c1d7f010"
down_revision: Union[str, Sequence[str], None] = "dddb487ae950"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique (user_id, date) on health_daily and drop redundant single-column index.

    The single-column index on ``date`` was too narrow for the actual query
    shape, which is always ``WHERE user_id=? AND date=?``. The composite also
    makes per-user-per-day uniqueness enforceable at the DB level, which the
    service layer already assumes in ``get_or_create_daily``.
    """
    # Collapse any pre-existing duplicates first so the constraint can attach.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id, date ORDER BY id
                   ) AS rn
            FROM health_daily
        )
        DELETE FROM health_daily
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
        """
    )

    # The index may or may not exist — dev DBs bootstrapped after the model
    # change won't have it. IF EXISTS keeps the migration idempotent across
    # both fresh and legacy databases.
    op.execute("DROP INDEX IF EXISTS ix_health_daily_date")
    # Guard ADD CONSTRAINT against dev DBs where create_all() already attached
    # the constraint from the updated model. Postgres has no "ADD CONSTRAINT
    # IF NOT EXISTS", so wrap in a DO block.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_health_daily_user_date'
            ) THEN
                ALTER TABLE health_daily
                    ADD CONSTRAINT uq_health_daily_user_date UNIQUE (user_id, date);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE health_daily DROP CONSTRAINT IF EXISTS uq_health_daily_user_date"
    )
    op.create_index(
        "ix_health_daily_date", "health_daily", ["date"], unique=False
    )
