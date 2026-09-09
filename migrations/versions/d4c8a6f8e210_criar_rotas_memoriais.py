"""garantir tabela de dados dos memoriais das rotas

Revision ID: d4c8a6f8e210
Revises: c41b7d29a6ef
Create Date: 2026-09-09

A tabela rotas_memoriais já pode existir em instalações anteriores porque
ela era consumida pelo gerador de memoriais sem ter sido criada pelo
Alembic. Por isso esta migração é deliberadamente compatível com bancos
legados: cria a tabela quando ausente e acrescenta apenas colunas faltantes.
"""

from alembic import op

revision = "d4c8a6f8e210"
down_revision = "c41b7d29a6ef"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS semed.rotas_memoriais (
            id SERIAL PRIMARY KEY,
            codigo_rota VARCHAR(100) NOT NULL
        )
    """)

    comandos = [
        "ADD COLUMN IF NOT EXISTS numero_linha VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS linha TEXT",
        "ADD COLUMN IF NOT EXISTS km_ida NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS km_volta NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS turnos_ativos JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ADD COLUMN IF NOT EXISTS horarios JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ADD COLUMN IF NOT EXISTS tipo_veiculo VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS quantidade_veiculos INTEGER",
        "ADD COLUMN IF NOT EXISTS onibus_pcd BOOLEAN",
        "ADD COLUMN IF NOT EXISTS inicio TEXT",
        "ADD COLUMN IF NOT EXISTS termino TEXT",
        "ADD COLUMN IF NOT EXISTS rede_ensino VARCHAR(100)",
        "ADD COLUMN IF NOT EXISTS redes_ensino JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ADD COLUMN IF NOT EXISTS localizacao VARCHAR(500)",
        "ADD COLUMN IF NOT EXISTS areas JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ADD COLUMN IF NOT EXISTS intermunicipal BOOLEAN",
        "ADD COLUMN IF NOT EXISTS assistente_mobilidade BOOLEAN",
        "ADD COLUMN IF NOT EXISTS assistente_nome VARCHAR(250)",
        "ADD COLUMN IF NOT EXISTS veiculo_placa VARCHAR(150)",
        "ADD COLUMN IF NOT EXISTS motorista VARCHAR(250)",
        "ADD COLUMN IF NOT EXISTS contato VARCHAR(150)",
        "ADD COLUMN IF NOT EXISTS escolas_atendidas JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ADD COLUMN IF NOT EXISTS observacao TEXT",
        "ADD COLUMN IF NOT EXISTS responsavel_tecnico VARCHAR(250)",
        "ADD COLUMN IF NOT EXISTS crea VARCHAR(150)",
        "ADD COLUMN IF NOT EXISTS executora VARCHAR(250)",
        "ADD COLUMN IF NOT EXISTS criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    ]

    for comando in comandos:
        op.execute(f"ALTER TABLE semed.rotas_memoriais {comando}")

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rotas_memoriais_codigo_rota
        ON semed.rotas_memoriais (codigo_rota)
    """)


def downgrade():
    # Não removemos a tabela nem colunas porque rotas_memoriais pode ser
    # anterior a esta migração e conter dados produzidos em versões legadas.
    pass
