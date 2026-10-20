"""Persist the opaque voice upload path on cases."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_case_voice_storage_path"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("cases")}
    if "voice_storage_path" not in columns:
        op.add_column(
            "cases", sa.Column("voice_storage_path", sa.String(length=1024), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("cases")}
    if "voice_storage_path" in columns:
        op.drop_column("cases", "voice_storage_path")
