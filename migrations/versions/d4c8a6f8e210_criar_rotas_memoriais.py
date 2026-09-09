"""criar tabela de dados dos memoriais das rotas

Revision ID: d4c8a6f8e210
Revises: c41b7d29a6ef
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4c8a6f8e210"
down_revision = "c41b7d29a6ef"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rotas_memoriais",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo_rota", sa.String(length=100), nullable=False),
        sa.Column("numero_linha", sa.String(length=100), nullable=True),
        sa.Column("linha", sa.Text(), nullable=True),
        sa.Column("km_ida", sa.Numeric(10, 3), nullable=True),
        sa.Column("km_volta", sa.Numeric(10, 3), nullable=True),
        sa.Column("turnos_ativos", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("horarios", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tipo_veiculo", sa.String(length=100), nullable=True),
        sa.Column("quantidade_veiculos", sa.Integer(), nullable=True),
        sa.Column("onibus_pcd", sa.Boolean(), nullable=True),
        sa.Column("inicio", sa.Text(), nullable=True),
        sa.Column("termino", sa.Text(), nullable=True),
        sa.Column("rede_ensino", sa.String(length=100), nullable=True),
        sa.Column("redes_ensino", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("localizacao", sa.String(length=500), nullable=True),
        sa.Column("areas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("intermunicipal", sa.Boolean(), nullable=True),
        sa.Column("assistente_mobilidade", sa.Boolean(), nullable=True),
        sa.Column("assistente_nome", sa.String(length=250), nullable=True),
        sa.Column("veiculo_placa", sa.String(length=150), nullable=True),
        sa.Column("motorista", sa.String(length=250), nullable=True),
        sa.Column("contato", sa.String(length=150), nullable=True),
        sa.Column("escolas_atendidas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("responsavel_tecnico", sa.String(length=250), nullable=True),
        sa.Column("crea", sa.String(length=150), nullable=True),
        sa.Column("executora", sa.String(length=250), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("codigo_rota", name="uq_rotas_memoriais_codigo_rota"),
        sa.CheckConstraint("quantidade_veiculos IS NULL OR quantidade_veiculos > 0", name="ck_rotas_memoriais_quantidade_veiculos"),
        schema="semed",
    )

    op.create_index(
        "ix_rotas_memoriais_codigo_rota",
        "rotas_memoriais",
        ["codigo_rota"],
        unique=True,
        schema="semed",
    )


def downgrade():
    op.drop_index(
        "ix_rotas_memoriais_codigo_rota",
        table_name="rotas_memoriais",
        schema="semed",
    )
    op.drop_table("rotas_memoriais", schema="semed")
