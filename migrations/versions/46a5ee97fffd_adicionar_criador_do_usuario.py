"""adicionar criador do usuario

Revision ID: 46a5ee97fffd
Revises: f810af0abe72
Create Date: 2026-07-15 17:30:18.073093

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '46a5ee97fffd'
down_revision = 'f810af0abe72'
branch_labels = None
depends_on = None


def upgrade():
    """
    Adiciona à tabela de usuários a referência
    ao administrador que criou cada conta.
    """

    op.add_column(
        "usuarios",
        sa.Column(
            "criado_por_id",
            sa.Integer(),
            nullable=True,
        ),
        schema="semed",
    )

    op.create_foreign_key(
        "fk_usuarios_criado_por",
        source_table="usuarios",
        referent_table="usuarios",
        local_cols=["criado_por_id"],
        remote_cols=["id"],
        source_schema="semed",
        referent_schema="semed",
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_usuarios_criado_por_id",
        "usuarios",
        ["criado_por_id"],
        unique=False,
        schema="semed",
    )


def downgrade():
    """
    Remove a referência ao administrador
    que criou cada conta.
    """

    op.drop_index(
        "ix_usuarios_criado_por_id",
        table_name="usuarios",
        schema="semed",
    )

    op.drop_constraint(
        "fk_usuarios_criado_por",
        "usuarios",
        schema="semed",
        type_="foreignkey",
    )

    op.drop_column(
        "usuarios",
        "criado_por_id",
        schema="semed",
    )