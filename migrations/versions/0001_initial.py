"""initial schema: slots, bookings, idempotency_keys

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "slots",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slots_start", "slots", ["start_at", "id"])
    op.create_index("ix_slots_provider", "slots", ["provider"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "slot_id", sa.Text(), sa.ForeignKey("slots.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name="ck_bookings_status"),
    )
    # THE double-booking guarantee: at most one confirmed booking per slot.
    op.create_index(
        "uq_bookings_slot_confirmed",
        "bookings",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )
    op.create_index("ix_bookings_email_page", "bookings", ["email", "created_at", "id"])

    # Used from Level 4 (idempotent retries); created now so the schema is one migration.
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("body_hash", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_index("ix_bookings_email_page", table_name="bookings")
    op.drop_index("uq_bookings_slot_confirmed", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index("ix_slots_provider", table_name="slots")
    op.drop_index("ix_slots_start", table_name="slots")
    op.drop_table("slots")
