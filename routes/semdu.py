from __future__ import annotations

import json
import re

from flask import (
    Blueprint,
    Response,
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
from werkzeug.exceptions import HTTPException

from models import db
from servicos.acessos_modulos import (
    MODULO_SEMDU,
    acesso_modulo_required,
    obter_acesso_modulo,
)
from servicos.funcoes_semdu import (
    FUNCAO_ENG_AMBIENTAL,
    usuario_possui_funcao,
)
from servicos.ortofotos_semdu import (
    catalogar_ortofotos,
    renderizar_tile,
)


semdu_bp = Blueprint(
    "semdu",
    __name__,
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
      AND gc.f_table_name NOT LIKE 'arborizacao_%'
      AND gc.f_table_name NOT LIKE 'vw_arborizacao_%'
    ORDER BY
        gc.f_table_name,
        gc.f_geometry_column
    """
)

SQL_PREFERENCIAS_CAMADAS = text(
    """
    SELECT
        camada_id,
        estilo,
        rotulo,
        atualizado_em
    FROM semdu.websig_estilos_usuarios
    WHERE usuario_id = CAST(:usuario_id AS INTEGER)
    ORDER BY camada_id
    """
)


SQL_SALVAR_PREFERENCIA_CAMADA = text(
    """
    INSERT INTO semdu.websig_estilos_usuarios (
        usuario_id,
        camada_id,
        estilo,
        rotulo,
        criado_em,
        atualizado_em
    ) VALUES (
        CAST(:usuario_id AS INTEGER),
        CAST(:camada_id AS TEXT),
        CAST(:estilo AS JSONB),
        CAST(:rotulo AS JSONB),
        NOW(),
        NOW()
    )
    ON CONFLICT (usuario_id, camada_id)
    DO UPDATE SET
        estilo = EXCLUDED.estilo,
        rotulo = EXCLUDED.rotulo,
        atualizado_em = NOW()
    RETURNING
        camada_id,
        estilo,
        rotulo,
        atualizado_em
    """
)


SQL_EXCLUIR_PREFERENCIA_CAMADA = text(
    """
    DELETE FROM semdu.websig_estilos_usuarios
    WHERE usuario_id = CAST(:usuario_id AS INTEGER)
      AND camada_id = CAST(:camada_id AS TEXT)
    RETURNING camada_id
    """
)



def _identificador_sql(
    valor: str,
) -> str:
    """
    Coloca aspas de identificador PostgreSQL.

    O nome já foi previamente conferido contra
    public.geometry_columns. Por isso, podemos
    aceitar espaços, acentos, travessões, letras
    maiúsculas e outros nomes criados pelo QGIS.
    """
    valor = str(
        valor or ""
    ).strip()

    if (
        not valor
        or "\x00" in valor
    ):
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
                            CASE
                                WHEN ST_IsValid(
                                    t.{coluna}
                                )
                                    THEN t.{coluna}
                                ELSE ST_MakeValid(
                                    t.{coluna}
                                )
                            END
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


COR_HEXADECIMAL = re.compile(
    r"^#[0-9A-Fa-f]{6}$"
)


def _numero_limitado(
    valor,
    minimo: float,
    maximo: float,
    padrao: float,
) -> float:
    try:
        numero = float(valor)
    except (
        TypeError,
        ValueError,
    ):
        return padrao

    return min(
        maximo,
        max(
            minimo,
            numero,
        ),
    )


def _cor_hexadecimal(
    valor,
    padrao: str,
) -> str:
    cor = str(
        valor or ""
    ).strip()

    if COR_HEXADECIMAL.fullmatch(cor):
        return cor.lower()

    return padrao


def _normalizar_preferencia(
    dados: dict,
) -> tuple[dict, dict]:
    estilo_entrada = (
        dados.get("estilo")
        if isinstance(
            dados.get("estilo"),
            dict,
        )
        else {}
    )

    rotulo_entrada = (
        dados.get("rotulo")
        if isinstance(
            dados.get("rotulo"),
            dict,
        )
        else {}
    )

    tracejado = re.sub(
        r"[^0-9 ,.]+",
        "",
        str(
            estilo_entrada.get(
                "dashArray"
            )
            or ""
        ),
    )[:40]

    estilo = {
        "strokeColor": _cor_hexadecimal(
            estilo_entrada.get(
                "strokeColor"
            ),
            "#232c61",
        ),
        "fillColor": _cor_hexadecimal(
            estilo_entrada.get(
                "fillColor"
            ),
            "#232c61",
        ),
        "weight": _numero_limitado(
            estilo_entrada.get("weight"),
            1,
            12,
            3,
        ),
        "opacity": _numero_limitado(
            estilo_entrada.get("opacity"),
            0,
            1,
            0.9,
        ),
        "fillOpacity": _numero_limitado(
            estilo_entrada.get(
                "fillOpacity"
            ),
            0,
            1,
            0.22,
        ),
        "radius": _numero_limitado(
            estilo_entrada.get("radius"),
            2,
            22,
            6,
        ),
        "dashArray": tracejado,
        "pointShape": (
            estilo_entrada.get(
                "pointShape"
            )
            if estilo_entrada.get(
                "pointShape"
            ) in {
                "circle",
                "square",
            }
            else "circle"
        ),
    }

    campo_rotulo = str(
        rotulo_entrada.get("field")
        or ""
    ).strip()[:120]

    rotulo = {
        "enabled": bool(
            rotulo_entrada.get("enabled")
        ),
        "field": campo_rotulo,
        "color": _cor_hexadecimal(
            rotulo_entrada.get("color"),
            "#1d2438",
        ),
        "fontSize": _numero_limitado(
            rotulo_entrada.get(
                "fontSize"
            ),
            8,
            30,
            12,
        ),
        "haloColor": _cor_hexadecimal(
            rotulo_entrada.get(
                "haloColor"
            ),
            "#ffffff",
        ),
        "haloWidth": _numero_limitado(
            rotulo_entrada.get(
                "haloWidth"
            ),
            0,
            8,
            3,
        ),
        "minZoom": _numero_limitado(
            rotulo_entrada.get(
                "minZoom"
            ),
            0,
            24,
            15,
        ),
    }

    return estilo, rotulo


def _validar_id_camada(
    camada_id: str,
) -> dict:
    camada_id = str(
        camada_id or ""
    ).strip()

    for camada in _catalogo():
        if camada["id"] == camada_id:
            return camada

    abort(
        404,
        description=(
            "A camada informada não existe "
            "no catálogo SEMDU."
        ),
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
        pode_editar_arborizacao=(
            usuario_possui_funcao(
                current_user,
                FUNCAO_ENG_AMBIENTAL,
            )
        ),
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


def _responder_camada(
    tabela: str,
    coluna: str,
):
    limite = _limite()

    try:
        camada = _camada(
            tabela,
            coluna,
        )

        feicoes = _consultar_geojson(
            camada,
            _bbox(),
            limite,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as erro:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao carregar semdu.%s (%s).",
            tabela,
            coluna,
        )

        resposta = {
            "sucesso": False,
            "erro": (
                "O PostGIS não conseguiu processar "
                "a camada solicitada."
            ),
            "camada": {
                "tabela": tabela,
                "coluna": coluna,
            },
        }

        if current_app.debug:
            resposta["detalhes"] = str(
                getattr(
                    erro,
                    "orig",
                    erro,
                )
            )

        return jsonify(
            resposta
        ), 500
    except Exception as erro:
        current_app.logger.exception(
            "Erro inesperado ao carregar "
            "semdu.%s (%s).",
            tabela,
            coluna,
        )

        resposta = {
            "sucesso": False,
            "erro": (
                "O servidor encontrou um erro "
                "ao preparar a camada."
            ),
            "camada": {
                "tabela": tabela,
                "coluna": coluna,
            },
        }

        if current_app.debug:
            resposta["detalhes"] = str(
                erro
            )

        return jsonify(
            resposta
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
                "limite": limite,
            },
            "features": feicoes,
        }
    )


@semdu_bp.get(
    "/api/semdu/camada"
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def obter_camada_consulta():
    """
    Endpoint principal.

    Query string evita problemas com nomes de
    tabelas do QGIS que possuem espaços, acentos,
    travessões ou letras maiúsculas.
    """
    tabela = request.args.get(
        "tabela",
        "",
    )

    coluna = request.args.get(
        "coluna",
        "",
    )

    return _responder_camada(
        tabela,
        coluna,
    )


@semdu_bp.get(
    (
        "/api/semdu/camadas/"
        "<path:tabela>/<string:coluna>"
    )
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def obter_camada(
    tabela: str,
    coluna: str,
):
    """
    Endpoint legado preservado para compatibilidade.
    """
    return _responder_camada(
        tabela,
        coluna,
    )


@semdu_bp.get(
    "/api/semdu/ortofotos"
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def listar_ortofotos():
    try:
        ortofotos = catalogar_ortofotos()
    except Exception as erro:
        current_app.logger.exception(
            "Erro ao consultar as ortofotos SEMDU."
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível consultar "
                    "as ortofotos do servidor."
                ),
                "detalhes": (
                    str(erro)
                    if current_app.debug
                    else None
                ),
            }
        ), 500

    for item in ortofotos:
        item["url_tiles"] = (
            "/api/semdu/ortofotos/"
            f"{item['id']}/tiles/"
            "{z}/{x}/{y}"
        )

    return jsonify(
        {
            "sucesso": True,
            "quantidade": len(ortofotos),
            "ortofotos": ortofotos,
        }
    )


@semdu_bp.get(
    (
        "/api/semdu/ortofotos/"
        "<string:id_ortofoto>/tiles/"
        "<int:z>/<int:x>/<int:y>"
    )
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def tile_ortofoto(
    id_ortofoto: str,
    z: int,
    x: int,
    y: int,
):
    try:
        conteudo, mimetype, transparente = (
            renderizar_tile(
                id_ortofoto,
                x,
                y,
                z,
            )
        )
    except KeyError:
        abort(
            404,
            description=(
                "Ortofoto não cadastrada."
            ),
        )
    except FileNotFoundError as erro:
        abort(
            404,
            description=str(erro),
        )
    except ValueError as erro:
        abort(
            400,
            description=str(erro),
        )
    except RuntimeError as erro:
        current_app.logger.exception(
            "Dependência da ortofoto indisponível."
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": str(erro),
            }
        ), 503
    except Exception:
        current_app.logger.exception(
            "Erro ao renderizar tile %s/%s/%s/%s.",
            id_ortofoto,
            z,
            x,
            y,
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível renderizar "
                    "o tile da ortofoto."
                ),
            }
        ), 500

    resposta = Response(
        conteudo,
        mimetype=mimetype,
    )
    resposta.headers["Cache-Control"] = (
        "private, max-age=86400"
    )
    resposta.headers["X-Content-Type-Options"] = (
        "nosniff"
    )

    if transparente:
        resposta.headers[
            "X-Ortofoto-Fora-Da-Cobertura"
        ] = "1"

    return resposta


@semdu_bp.get(
    "/api/semdu/preferencias-camadas"
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def listar_preferencias_camadas():
    try:
        registros = (
            db.session.execute(
                SQL_PREFERENCIAS_CAMADAS,
                {
                    "usuario_id": int(
                        current_user.id
                    ),
                },
            )
            .mappings()
            .all()
        )
    except SQLAlchemyError as erro:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao consultar preferências cartográficas."
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível consultar as "
                    "preferências cartográficas. "
                    "Execute o SQL 21_semdu_websig_avancado.sql."
                ),
                "detalhes": (
                    str(
                        getattr(
                            erro,
                            "orig",
                            erro,
                        )
                    )
                    if current_app.debug
                    else None
                ),
            }
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "preferencias": [
                {
                    "camada_id": item[
                        "camada_id"
                    ],
                    "estilo": item[
                        "estilo"
                    ] or {},
                    "rotulo": item[
                        "rotulo"
                    ] or {},
                    "atualizado_em": (
                        item["atualizado_em"].isoformat()
                        if item["atualizado_em"]
                        else None
                    ),
                }
                for item in registros
            ],
        }
    )


@semdu_bp.put(
    "/api/semdu/preferencias-camadas"
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def salvar_preferencia_camada():
    dados = request.get_json(
        silent=True
    )

    if not isinstance(dados, dict):
        abort(
            400,
            description=(
                "Envie um objeto JSON válido."
            ),
        )

    camada_id = str(
        dados.get("camada_id")
        or ""
    ).strip()

    _validar_id_camada(
        camada_id
    )

    estilo, rotulo = (
        _normalizar_preferencia(
            dados
        )
    )

    try:
        registro = (
            db.session.execute(
                SQL_SALVAR_PREFERENCIA_CAMADA,
                {
                    "usuario_id": int(
                        current_user.id
                    ),
                    "camada_id": camada_id,
                    "estilo": json.dumps(
                        estilo,
                        ensure_ascii=False,
                    ),
                    "rotulo": json.dumps(
                        rotulo,
                        ensure_ascii=False,
                    ),
                },
            )
            .mappings()
            .one()
        )
        db.session.commit()
    except SQLAlchemyError as erro:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao salvar preferência cartográfica."
        )

        resposta = {
            "sucesso": False,
            "erro": (
                "Não foi possível salvar a preferência. "
                "Confira se o SQL do WebSIG avançado foi executado."
            ),
        }

        if current_app.debug:
            resposta["detalhes"] = str(
                getattr(
                    erro,
                    "orig",
                    erro,
                )
            )

        return jsonify(resposta), 500

    return jsonify(
        {
            "sucesso": True,
            "preferencia": {
                "camada_id": registro[
                    "camada_id"
                ],
                "estilo": registro[
                    "estilo"
                ],
                "rotulo": registro[
                    "rotulo"
                ],
                "atualizado_em": registro[
                    "atualizado_em"
                ].isoformat(),
            },
        }
    )


@semdu_bp.delete(
    "/api/semdu/preferencias-camadas"
)
@acesso_modulo_required(
    MODULO_SEMDU
)
def excluir_preferencia_camada():
    camada_id = str(
        request.args.get("camada_id")
        or ""
    ).strip()

    if not camada_id:
        abort(
            400,
            description=(
                "Informe camada_id."
            ),
        )

    try:
        removida = db.session.execute(
            SQL_EXCLUIR_PREFERENCIA_CAMADA,
            {
                "usuario_id": int(
                    current_user.id
                ),
                "camada_id": camada_id,
            },
        ).scalar_one_or_none()
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao excluir preferência cartográfica."
        )

        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível restaurar a "
                    "simbologia padrão no servidor."
                ),
            }
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "removida": bool(removida),
            "camada_id": camada_id,
        }
    )


@semdu_bp.errorhandler(
    HTTPException
)
def tratar_erro_http(
    erro: HTTPException,
):
    if request.path.startswith(
        "/api/semdu/"
    ):
        return jsonify(
            {
                "sucesso": False,
                "erro": erro.description,
                "codigo": erro.code,
            }
        ), erro.code

    return erro
