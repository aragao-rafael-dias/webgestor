from __future__ import annotations

import re

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db
from servicos.acessos_modulos import (
    MODULO_SEMDU,
    acesso_modulo_required,
    obter_acesso_modulo,
)


semdu_bp = Blueprint(
    "semdu",
    __name__,
)

IDENTIFICADOR = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_$]*$"
)

LIMITE_PADRAO = 5000
LIMITE_MAXIMO = 10000


SQL_CAMADAS = text(
    """
    SELECT
        gc.f_table_name AS tabela,
        gc.f_geometry_column AS coluna_geometria,
        UPPER(
            COALESCE(
                gc.type,
                'GEOMETRY'
            )
        ) AS tipo_geometria,
        COALESCE(
            gc.srid,
            0
        ) AS srid,
        COALESCE(
            cls.reltuples::bigint,
            0
        ) AS estimativa_registros
    FROM public.geometry_columns AS gc
    LEFT JOIN pg_namespace AS ns
        ON ns.nspname = gc.f_table_schema
    LEFT JOIN pg_class AS cls
        ON cls.relnamespace = ns.oid
       AND cls.relname = gc.f_table_name
    WHERE gc.f_table_schema = 'semdu'
    ORDER BY
        gc.f_table_name,
        gc.f_geometry_column
    """
)


def _identificador_sql(
    valor: str,
) -> str:
    valor = str(
        valor or ""
    ).strip()

    if not IDENTIFICADOR.fullmatch(valor):
        abort(
            400,
            description=(
                "Identificador de camada inválido."
            ),
        )

    return (
        '"'
        + valor.replace('"', '""')
        + '"'
    )


def _id_camada(
    tabela: str,
    coluna: str,
) -> str:
    return f"{tabela}::{coluna}"


def _titulo_tabela(
    tabela: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        tabela.replace("_", " "),
    ).strip().title()


def _catalogo() -> list[dict]:
    registros = (
        db.session.execute(
            SQL_CAMADAS
        )
        .mappings()
        .all()
    )

    return [
        {
            "id": _id_camada(
                str(item["tabela"]),
                str(item["coluna_geometria"]),
            ),
            "tabela": str(
                item["tabela"]
            ),
            "titulo": _titulo_tabela(
                str(item["tabela"])
            ),
            "coluna_geometria": str(
                item["coluna_geometria"]
            ),
            "tipo_geometria": str(
                item["tipo_geometria"]
                or "GEOMETRY"
            ).upper(),
            "srid": int(
                item["srid"]
                or 0
            ),
            "estimativa_registros": max(
                int(
                    item["estimativa_registros"]
                    or 0
                ),
                0,
            ),
        }
        for item in registros
    ]


def _camada(
    tabela: str,
    coluna: str,
) -> dict:
    tabela = str(
        tabela or ""
    ).strip()

    coluna = str(
        coluna or ""
    ).strip()

    for camada in _catalogo():
        if (
            camada["tabela"] == tabela
            and camada["coluna_geometria"]
            == coluna
        ):
            return camada

    abort(
        404,
        description=(
            "Camada não encontrada no "
            "schema semdu."
        ),
    )


def _bbox():
    valor = str(
        request.args.get("bbox")
        or ""
    ).strip()

    if not valor:
        return None

    partes = [
        parte.strip()
        for parte in valor.split(",")
    ]

    if len(partes) != 4:
        abort(
            400,
            description=(
                "bbox deve usar o formato "
                "oeste,sul,leste,norte."
            ),
        )

    try:
        oeste, sul, leste, norte = map(
            float,
            partes,
        )
    except ValueError:
        abort(
            400,
            description="bbox inválido.",
        )

    if (
        oeste >= leste
        or sul >= norte
        or not (
            -180 <= oeste <= 180
            and -180 <= leste <= 180
            and -90 <= sul <= 90
            and -90 <= norte <= 90
        )
    ):
        abort(
            400,
            description="bbox inválido.",
        )

    return (
        oeste,
        sul,
        leste,
        norte,
    )


def _limite() -> int:
    try:
        limite = int(
            request.args.get(
                "limite",
                LIMITE_PADRAO,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        limite = LIMITE_PADRAO

    return max(
        1,
        min(
            limite,
            LIMITE_MAXIMO,
        ),
    )


def _consultar_geojson(
    camada: dict,
    bbox,
    limite: int,
) -> list:
    tabela = _identificador_sql(
        camada["tabela"]
    )

    coluna = _identificador_sql(
        camada["coluna_geometria"]
    )

    srid = int(
        camada["srid"]
    )

    if srid <= 0:
        abort(
            422,
            description=(
                "A camada não possui SRID válido. "
                "Defina o SRID no PostGIS antes de "
                "publicá-la no mapa."
            ),
        )

    filtro_bbox = ""

    parametros = {
        "limite": limite,
        "coluna_geometria":
            camada["coluna_geometria"],
    }

    if bbox:
        oeste, sul, leste, norte = bbox

        filtro_bbox = f"""
        AND ST_Intersects(
            t.{coluna},
            ST_Transform(
                ST_MakeEnvelope(
                    :oeste,
                    :sul,
                    :leste,
                    :norte,
                    4326
                ),
                {srid}
            )
        )
        """

        parametros.update(
            {
                "oeste": oeste,
                "sul": sul,
                "leste": leste,
                "norte": norte,
            }
        )

    consulta = text(
        f"""
        SELECT
            jsonb_build_object(
                'type',
                'Feature',

                'geometry',
                ST_AsGeoJSON(
                    ST_Transform(
                        ST_Force2D(
                            t.{coluna}
                        ),
                        4326
                    )
                )::jsonb,

                'properties',
                to_jsonb(t)
                - :coluna_geometria
            ) AS feature
        FROM semdu.{tabela} AS t
        WHERE t.{coluna} IS NOT NULL
          AND NOT ST_IsEmpty(
              t.{coluna}
          )
          {filtro_bbox}
        LIMIT :limite
        """
    )

    return list(
        db.session.execute(
            consulta,
            parametros,
        ).scalars()
    )


@semdu_bp.get("/semdu/login")
def login_compativel():
    if current_user.is_authenticated:
        return redirect(
            url_for("home.seletor_modulos")
        )

    return redirect(
        url_for("auth.login")
    )


@semdu_bp.get("/semdu")
@semdu_bp.get("/semdu/mapa")
@login_required
@acesso_modulo_required(
    MODULO_SEMDU
)
def mapa():
    acesso = obter_acesso_modulo(
        current_user,
        MODULO_SEMDU,
    )

    session["modulo_atual"] = (
        MODULO_SEMDU
    )

    return render_template(
        "semdu/mapa.html",
        acesso=acesso,
    )


@semdu_bp.get(
    "/api/semdu/camadas"
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def listar_camadas():
    try:
        camadas = _catalogo()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao listar as camadas SEMDU."
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível consultar "
                    "o catálogo de camadas."
                ),
            }
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "schema": "semdu",
            "quantidade": len(camadas),
            "camadas": camadas,
        }
    )


@semdu_bp.get(
    (
        "/api/semdu/camadas/"
        "<string:tabela>/<string:coluna>"
    )
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def obter_camada(
    tabela: str,
    coluna: str,
):
    camada = _camada(
        tabela,
        coluna,
    )

    try:
        feicoes = _consultar_geojson(
            camada,
            _bbox(),
            _limite(),
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao carregar semdu.%s (%s).",
            tabela,
            coluna,
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível carregar "
                    "a camada solicitada."
                ),
            }
        ), 500

    return jsonify(
        {
            "type": "FeatureCollection",
            "name": camada["tabela"],
            "schema": "semdu",
            "metadata": {
                **camada,
                "quantidade_retornada":
                    len(feicoes),
                "limite": _limite(),
            },
            "features": feicoes,
        }
    )
