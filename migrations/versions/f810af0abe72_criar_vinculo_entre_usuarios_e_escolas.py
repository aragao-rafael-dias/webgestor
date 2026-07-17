"""criar vinculo entre usuarios e escolas

Revision ID: f810af0abe72
Revises: b825c001d57b
Create Date: 2026-07-15 13:30:17.027229

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f810af0abe72'
down_revision = 'b825c001d57b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usuarios_escolas",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "usuario_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "escola_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),

        sa.Column(
            "inicio_vinculo",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),

        sa.Column(
            "fim_vinculo",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.CheckConstraint(
            (
                "fim_vinculo IS NULL "
                "OR fim_vinculo >= inicio_vinculo"
            ),
            name="ck_usuarios_escolas_periodo",
        ),

        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["semed.usuarios.id"],
            name="fk_usuarios_escolas_usuario",
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["escola_id"],
            ["semed.escolas.id"],
            name="fk_usuarios_escolas_escola",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_usuarios_escolas",
        ),

        schema="semed",
    )

    op.create_index(
        "ix_usuarios_escolas_usuario_id",
        "usuarios_escolas",
        ["usuario_id"],
        unique=False,
        schema="semed",
    )

    op.create_index(
        "ix_usuarios_escolas_escola_id",
        "usuarios_escolas",
        ["escola_id"],
        unique=False,
        schema="semed",
    )

    op.create_index(
        "ix_usuarios_escolas_ativo",
        "usuarios_escolas",
        ["ativo"],
        unique=False,
        schema="semed",
    )


def downgrade():
    op.drop_index(
        "ix_usuarios_escolas_ativo",
        table_name="usuarios_escolas",
        schema="semed",
    )

    op.drop_index(
        "ix_usuarios_escolas_escola_id",
        table_name="usuarios_escolas",
        schema="semed",
    )

    op.drop_index(
        "ix_usuarios_escolas_usuario_id",
        table_name="usuarios_escolas",
        schema="semed",
    )

    op.drop_table(
        "usuarios_escolas",
        schema="semed",
    )
