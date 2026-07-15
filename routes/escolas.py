from flask import Blueprint, jsonify
from sqlalchemy import text
import json

from models import db, Requisicao

escolas_bp = Blueprint(
    "escolas",
    __name__
)


@escolas_bp.route("/api/escolas")
def api_escolas():

    sql = text("""
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(jsonb_agg(features.feature), '[]'::jsonb)
    )
    FROM (
        SELECT jsonb_build_object(
            'type', 'Feature',
            'id', id,
            'geometry',
            ST_AsGeoJSON(
                ST_Transform(
                    ST_SetSRID(geom,31984),
                    4326
                )
            )::jsonb,
            'properties',
            to_jsonb(inputs)-'geom'
        ) AS feature

        FROM (
            SELECT *
            FROM semed.escolas
        ) inputs

    ) features;
    """)

    resultado = db.session.execute(sql).scalar()

    if isinstance(resultado, str):
        return jsonify(json.loads(resultado))

    return jsonify(
        resultado or
        {
            "type": "FeatureCollection",
            "features": []
        }
    )


@escolas_bp.route(
    "/api/escolas/<int:escola_id>/requisicoes",
    methods=["GET"]
)
def get_requisicoes(escola_id):

    requisicoes = (
        Requisicao.query
        .filter_by(escola_id=escola_id)
        .order_by(
            Requisicao.data_criacao.desc()
        )
        .all()
    )

    dados = [
        {
            "id": req.id,
            "descricao": req.descricao,
            "status": req.status,
            "resposta_semed": req.resposta_semed
        }

        for req in requisicoes
    ]

    return jsonify(dados)