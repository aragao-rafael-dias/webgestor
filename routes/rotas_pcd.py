# ==========================================
# ROTAS PCD
# Retorna os códigos das rotas marcadas como PCD
# em semed.rotas_memoriais.
# ==========================================

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import login_required
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


rotas_pcd_bp = Blueprint(
    "rotas_pcd",
    __name__,
)


SQL_ROTAS_PCD = text(
    """
    SELECT DISTINCT
        BTRIM(codigo_rota) AS codigo_rota

    FROM semed.rotas_memoriais

    WHERE onibus_pcd IS TRUE
      AND codigo_rota IS NOT NULL
      AND BTRIM(codigo_rota) <> ''

    ORDER BY
        BTRIM(codigo_rota)
    """
)


@rotas_pcd_bp.get(
    "/api/rotas-pcd"
)
@login_required
def listar_rotas_pcd():
    try:
        registros = (
            db.session.execute(
                SQL_ROTAS_PCD
            )
            .mappings()
            .all()
        )

        rotas = [
            registro["codigo_rota"]
            for registro in registros
            if registro.get("codigo_rota")
        ]

        return jsonify(
            {
                "rotas_pcd": rotas,
                "total": len(rotas),
            }
        )

    except SQLAlchemyError:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao consultar as rotas PCD."
        )

        return jsonify(
            {
                "rotas_pcd": [],
                "total": 0,
                "erro": (
                    "Não foi possível consultar "
                    "as rotas PCD."
                ),
            }
        ), 500
