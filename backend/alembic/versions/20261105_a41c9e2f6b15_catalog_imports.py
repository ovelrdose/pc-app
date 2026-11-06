"""Журнал импорта каталога: таблица catalog_imports (ADR 0010 п.1).

Revision ID: a41c9e2f6b15
Revises: 8f3c2a91b7d4
Create Date: 2026-11-05 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a41c9e2f6b15"
down_revision: str | None = "8f3c2a91b7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMPORT_STATUSES = ("completed", "failed")


def upgrade() -> None:
    status = postgresql.ENUM(*IMPORT_STATUSES, name="catalog_import_status")
    op.create_table(
        "catalog_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_catalog_imports_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_imports")),
    )
    op.create_index(
        op.f("ix_catalog_imports_created_by"), "catalog_imports", ["created_by"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_catalog_imports_created_by"), table_name="catalog_imports")
    op.drop_table("catalog_imports")
    postgresql.ENUM(name="catalog_import_status").drop(op.get_bind(), checkfirst=True)
