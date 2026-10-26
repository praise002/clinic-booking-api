"""idempotency_keys.response: jsonb -> json

A replay must be the same response as the first, byte for byte. JSONB re-sorts object keys
when it stores them; JSON keeps the text exactly as written.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "idempotency_keys",
        "response",
        type_=postgresql.JSON(),
        existing_type=postgresql.JSONB(),
        postgresql_using="response::json",
    )


def downgrade() -> None:
    op.alter_column(
        "idempotency_keys",
        "response",
        type_=postgresql.JSONB(),
        existing_type=postgresql.JSON(),
        postgresql_using="response::jsonb",
    )
