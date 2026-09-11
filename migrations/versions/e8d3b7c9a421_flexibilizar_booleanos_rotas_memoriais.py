"""flexibilizar booleanos opcionais de rotas_memoriais

Revision ID: e8d3b7c9a421
Revises: d4c8a6f8e210
Create Date: 2026-09-09

Algumas instalações legadas possuem colunas booleanas do memorial com
NOT NULL, enquanto a nova tela permite o estado "Não informado". Esta
migração alinha o esquema legado ao comportamento atual da aplicação.
"""

from alembic import op

revision = "e8d3b7c9a421"
down_revision = "d4c8a6f8e210"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('semed.rotas_memoriais') IS NOT NULL THEN
                ALTER TABLE semed.rotas_memoriais
                    ALTER COLUMN intermunicipal DROP NOT NULL,
                    ALTER COLUMN onibus_pcd DROP NOT NULL,
                    ALTER COLUMN assistente_mobilidade DROP NOT NULL;
            END IF;
        END
        $$;
    """)


def downgrade():
    # Não restauramos NOT NULL automaticamente porque podem existir
    # registros com valor nulo após a atualização.
    pass
