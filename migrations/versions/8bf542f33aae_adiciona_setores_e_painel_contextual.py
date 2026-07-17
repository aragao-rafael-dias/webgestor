"""adiciona setores e painel contextual

Revision ID: 8bf542f33aae
Revises: 46a5ee97fffd
Create Date: 2026-07-16 11:29:03.200113
"""

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql


# ==========================================
# IDENTIFICAÇÃO DA MIGRAÇÃO
# ==========================================

revision = "8bf542f33aae"
down_revision = "46a5ee97fffd"
branch_labels = None
depends_on = None


# ==========================================
# UPGRADE
# ==========================================

def upgrade():
    # ======================================
    # TABELA DE SETORES
    # ======================================

    op.create_table(
        "setores",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "nome",
            sa.String(length=180),
            nullable=False,
        ),

        sa.Column(
            "sigla",
            sa.String(length=30),
            nullable=True,
        ),

        sa.Column(
            "tipo",
            sa.String(length=30),
            server_default=sa.text("'OUTRO'"),
            nullable=False,
        ),

        sa.Column(
            "setor_pai_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "descricao",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "competencias",
            postgresql.JSONB(
                astext_type=sa.Text()
            ),
            server_default=sa.text(
                "'[]'::jsonb"
            ),
            nullable=False,
        ),

        sa.Column(
            "imagem_url",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "dados_websig",
            postgresql.JSONB(
                astext_type=sa.Text()
            ),
            server_default=sa.text(
                "'{}'::jsonb"
            ),
            nullable=False,
        ),

        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),

        sa.Column(
            "ordem",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),

        sa.Column(
            "criado_em",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.Column(
            "atualizado_em",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["setor_pai_id"],
            ["semed.setores.id"],
            name=(
                "fk_setores_setor_pai_id_"
                "setores"
            ),
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_setores",
        ),

        sa.UniqueConstraint(
            "sigla",
            name="uq_setores_sigla",
        ),

        schema="semed",
    )

    op.create_index(
        "ix_setores_ativo_ordem",
        "setores",
        [
            "ativo",
            "ordem",
        ],
        unique=False,
        schema="semed",
    )

    # ======================================
    # DADOS COMPLEMENTARES DAS ESCOLAS
    # ======================================

    op.create_table(
        "escolas_painel",

        sa.Column(
            "escola_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "imagem_url",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "dados_websig",
            postgresql.JSONB(
                astext_type=sa.Text()
            ),
            server_default=sa.text(
                "'{}'::jsonb"
            ),
            nullable=False,
        ),

        sa.Column(
            "atualizado_em",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["escola_id"],
            ["semed.escolas.id"],
            name=(
                "fk_escolas_painel_"
                "escola_id_escolas"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "escola_id",
            name="pk_escolas_painel",
        ),

        schema="semed",
    )

    # ======================================
    # VÍNCULO ENTRE USUÁRIOS E SETORES
    # ======================================

    op.create_table(
        "usuarios_setores",

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
            "setor_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "principal",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),

        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),

        sa.Column(
            "inicio_vinculo",
            sa.Date(),
            server_default=sa.text(
                "CURRENT_DATE"
            ),
            nullable=False,
        ),

        sa.Column(
            "fim_vinculo",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "criado_em",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["semed.usuarios.id"],
            name=(
                "fk_usuarios_setores_"
                "usuario_id_usuarios"
            ),
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["setor_id"],
            ["semed.setores.id"],
            name=(
                "fk_usuarios_setores_"
                "setor_id_setores"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_usuarios_setores",
        ),

        sa.UniqueConstraint(
            "usuario_id",
            "setor_id",
            name="uq_usuario_setor",
        ),

        schema="semed",
    )

    op.create_index(
        "ix_usuarios_setores_usuario_ativo",
        "usuarios_setores",
        [
            "usuario_id",
            "ativo",
        ],
        unique=False,
        schema="semed",
    )

    op.create_index(
        "ix_usuarios_setores_setor_ativo",
        "usuarios_setores",
        [
            "setor_id",
            "ativo",
        ],
        unique=False,
        schema="semed",
    )

    # ======================================
    # NOVOS CAMPOS DAS REQUISIÇÕES
    # ======================================

    op.add_column(
        "requisicoes",
        sa.Column(
            "setor_id",
            sa.Integer(),
            nullable=True,
        ),
        schema="semed",
    )

    op.add_column(
        "requisicoes",
        sa.Column(
            "respondido_por_id",
            sa.Integer(),
            nullable=True,
        ),
        schema="semed",
    )

    op.add_column(
        "requisicoes",
        sa.Column(
            "data_resposta",
            sa.DateTime(),
            nullable=True,
        ),
        schema="semed",
    )

    op.create_foreign_key(
        "fk_requisicoes_setor_id_setores",

        source_table="requisicoes",
        referent_table="setores",

        local_cols=[
            "setor_id",
        ],

        remote_cols=[
            "id",
        ],

        source_schema="semed",
        referent_schema="semed",

        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        (
            "fk_requisicoes_"
            "respondido_por_id_usuarios"
        ),

        source_table="requisicoes",
        referent_table="usuarios",

        local_cols=[
            "respondido_por_id",
        ],

        remote_cols=[
            "id",
        ],

        source_schema="semed",
        referent_schema="semed",

        ondelete="SET NULL",
    )

    op.create_index(
        "ix_requisicoes_escola_status",
        "requisicoes",
        [
            "escola_id",
            "status",
        ],
        unique=False,
        schema="semed",
    )

    op.create_index(
        "ix_requisicoes_setor_status",
        "requisicoes",
        [
            "setor_id",
            "status",
        ],
        unique=False,
        schema="semed",
    )


# ==========================================
# DOWNGRADE
# ==========================================

def downgrade():
    # ======================================
    # REMOVER CAMPOS DAS REQUISIÇÕES
    # ======================================

    op.drop_index(
        "ix_requisicoes_setor_status",
        table_name="requisicoes",
        schema="semed",
    )

    op.drop_index(
        "ix_requisicoes_escola_status",
        table_name="requisicoes",
        schema="semed",
    )

    op.drop_constraint(
        (
            "fk_requisicoes_"
            "respondido_por_id_usuarios"
        ),
        "requisicoes",
        schema="semed",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_requisicoes_setor_id_setores",
        "requisicoes",
        schema="semed",
        type_="foreignkey",
    )

    op.drop_column(
        "requisicoes",
        "data_resposta",
        schema="semed",
    )

    op.drop_column(
        "requisicoes",
        "respondido_por_id",
        schema="semed",
    )

    op.drop_column(
        "requisicoes",
        "setor_id",
        schema="semed",
    )

    # ======================================
    # REMOVER VÍNCULOS USUÁRIO–SETOR
    # ======================================

    op.drop_index(
        "ix_usuarios_setores_setor_ativo",
        table_name="usuarios_setores",
        schema="semed",
    )

    op.drop_index(
        "ix_usuarios_setores_usuario_ativo",
        table_name="usuarios_setores",
        schema="semed",
    )

    op.drop_table(
        "usuarios_setores",
        schema="semed",
    )

    # ======================================
    # REMOVER DADOS DAS ESCOLAS
    # ======================================

    op.drop_table(
        "escolas_painel",
        schema="semed",
    )

    # ======================================
    # REMOVER SETORES
    # ======================================

    op.drop_index(
        "ix_setores_ativo_ordem",
        table_name="setores",
        schema="semed",
    )

    op.drop_table(
        "setores",
        schema="semed",
    )