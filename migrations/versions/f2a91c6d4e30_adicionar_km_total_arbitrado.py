"""adicionar km total arbitrado aos memoriais

Revision ID: f2a91c6d4e30
Revises: e8d3b7c9a421
Create Date: 2026-09-15

Permite informar manualmente o KM TOTAL de uma rota. Quando o campo fica
nulo, a aplicação mantém o cálculo automático baseado nos turnos ativos e
na quantidade de veículos.
"""

from alembic import op

revision = "f2a91c6d4e30"
down_revision = "e8d3b7c9a421"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('semed.rotas_memoriais') IS NOT NULL THEN
                ALTER TABLE semed.rotas_memoriais
                    ADD COLUMN IF NOT EXISTS km_total_arbitrado NUMERIC(12,3);
            END IF;
        END
        $$;
    """)


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('semed.rotas_memoriais') IS NOT NULL THEN
                ALTER TABLE semed.rotas_memoriais
                    DROP COLUMN IF EXISTS km_total_arbitrado;
            END IF;
        END
        $$;
    """)
