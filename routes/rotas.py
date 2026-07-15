from flask import Blueprint, jsonify
from sqlalchemy import text
import json

from models import db

rotas_bp = Blueprint(
    "rotas",
    __name__
)


@rotas_bp.route("/api/rotas")
def api_rotas():

    sql = text("""
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(jsonb_agg(features.feature), '[]'::jsonb)
    )
    FROM (
        SELECT jsonb_build_object(
            'type',       'Feature',
            'id',         COALESCE(id, 0),
            'geometry',   geom_4326,
            'properties', to_jsonb(inputs) - 'geom'
        ) AS feature
        FROM (
            SELECT *,
                CASE
                    WHEN ST_SRID(geom) = 4326 THEN
                        ST_AsGeoJSON(geom)::jsonb

                    WHEN ST_SRID(geom) = 31984 THEN
                        ST_AsGeoJSON(
                            ST_Transform(geom, 4326)
                        )::jsonb

                    ELSE
                        CASE
                            WHEN ST_X(ST_Centroid(geom)) > 100000 THEN
                                ST_AsGeoJSON(
                                    ST_Transform(
                                        ST_SetSRID(geom, 31984),
                                        4326
                                    )
                                )::jsonb

                            ELSE
                                ST_AsGeoJSON(
                                    ST_SetSRID(geom, 4326)
                                )::jsonb
                        END
                END AS geom_4326

            FROM semed.rotas_geral

            WHERE geom IS NOT NULL

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