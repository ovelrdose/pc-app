"""Аккаунты: пользователи с ролями, refresh-токены, гостевые сессии, внешние ключи владельца.

Revision ID: 8f3c2a91b7d4
Revises: 3b7d0c1e9a42
Create Date: 2026-11-03 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8f3c2a91b7d4"
down_revision: str | None = "3b7d0c1e9a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_ROLES = ("client", "catalog_admin", "knowledge_engineer", "superadmin")


def upgrade() -> None:
    user_role = postgresql.ENUM(*USER_ROLES, name="user_role")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "role",
            user_role,
            server_default=sa.text("'client'::user_role"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "guest_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("merged_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["merged_user_id"],
            ["users.id"],
            name=op.f("fk_guest_sessions_merged_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guest_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_guest_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_guest_sessions_merged_user_id"),
        "guest_sessions",
        ["merged_user_id"],
        unique=False,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    # Владелец консультации: индексы на колонках уже есть, добавляем только ключи.
    op.create_foreign_key(
        op.f("fk_consultations_user_id_users"),
        "consultations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_consultations_guest_session_id_guest_sessions"),
        "consultations",
        "guest_sessions",
        ["guest_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_rule_revisions_author_id_users"),
        "rule_revisions",
        "users",
        ["author_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_kb_snapshots_published_by_users"),
        "kb_snapshots",
        "users",
        ["published_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_kb_snapshots_published_by_users"), "kb_snapshots", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_rule_revisions_author_id_users"), "rule_revisions", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_consultations_guest_session_id_guest_sessions"),
        "consultations",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("fk_consultations_user_id_users"), "consultations", type_="foreignkey")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_guest_sessions_merged_user_id"), table_name="guest_sessions")
    op.drop_table("guest_sessions")
    op.drop_table("users")
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
