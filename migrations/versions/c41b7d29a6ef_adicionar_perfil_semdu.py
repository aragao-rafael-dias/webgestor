"""adicionar perfil marcador SEMDU para contas exclusivas do modulo

Revision ID: c41b7d29a6ef
Revises: 8bf542f33aae
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = "c41b7d29a6ef"
down_revision = "8bf542f33aae"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_usuarios_perfil",
        "usuarios",
        schema="semed",
        type_="check",
    )
    op.create_check_constraint(
        "ck_usuarios_perfil",
        "usuarios",
        "perfil IN ('ADMIN', 'DIRETOR', 'SETOR', 'AUDITOR', 'SEMDU')",
        schema="semed",
    )


def downgrade():
    conexao = op.get_bind()
    quantidade = conexao.execute(
        sa.text(
            "SELECT COUNT(*) FROM semed.usuarios WHERE perfil = 'SEMDU'"
        )
    ).scalar_one()

    if quantidade:
        raise RuntimeError(
            "Existem contas exclusivas da SEMDU. Remova ou migre essas contas "
            "antes de reverter esta migração."
        )

    op.drop_constraint(
        "ck_usuarios_perfil",
        "usuarios",
        schema="semed",
        type_="check",
    )
    op.create_check_constraint(
        "ck_usuarios_perfil",
        "usuarios",
        "perfil IN ('ADMIN', 'DIRETOR', 'SETOR', 'AUDITOR')",
        schema="semed",
    )
