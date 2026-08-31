from __future__ import annotations

import json
import math
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from models import db
from servicos.acessos_modulos import MODULO_SEMDU, acesso_modulo_required
from servicos.funcoes_semdu import (
    FUNCAO_ENG_AMBIENTAL,
    funcao_semdu_required,
    listar_funcoes_usuario,
    usuario_possui_funcao,
)


arborizacao_bp = Blueprint("arborizacao", __name__)

STATUS_VALIDOS = {
    "RASCUNHO",
    "EM_ANALISE",
    "APROVADO",
    "PROGRAMADO",
    "PLANTADO",
    "EM_MONITORAMENTO",
}

SQL_ESPECIES = text(
    """
    SELECT
        e.id,
        e.codigo,
        e.familia,
        e.nome_cientifico,
        e.nome_popular,
        e.biomas,
        e.origem,
        e.porte,
        e.altura_min_m,
        e.altura_max_m,
        e.diametro_copa_min_m,
        e.diametro_copa_max_m,
        e.raio_copa_min_m,
        e.raio_copa_max_m,
        e.tipo_raiz,
        e.raio_raiz_min_m,
        e.raio_raiz_max_m,
        e.grupo_ecologico,
        e.cor_flor,
        e.frutifera,
        e.invasora,
        e.nativa_regional,
        e.permitida_planejamento,
        e.espacamento_porte_m,
        e.espacamento_recomendado_m,
        e.uso_recomendado_texto,
        e.observacoes,
        e.fonte_tecnica,
        e.pagina_fonte,
        e.foto_principal_url,
        COALESCE(
            (
                SELECT jsonb_agg(
                    u.codigo_uso
                    ORDER BY u.codigo_uso
                )
                FROM semdu.arborizacao_especies_usos AS u
                WHERE u.especie_id = e.id
            ),
            '[]'::jsonb
        ) AS usos
    FROM semdu.arborizacao_especies AS e
    WHERE e.ativa IS TRUE
    ORDER BY
        e.nativa_regional DESC,
        e.nome_popular,
        e.nome_cientifico
    """
)

SQL_ESPECIE_ID = text(
    """
    SELECT
        e.*,
        COALESCE(
            (
                SELECT jsonb_agg(
                    u.codigo_uso
                    ORDER BY u.codigo_uso
                )
                FROM semdu.arborizacao_especies_usos AS u
                WHERE u.especie_id = e.id
            ),
            '[]'::jsonb
        ) AS usos
    FROM semdu.arborizacao_especies AS e
    WHERE e.id = :especie_id
      AND e.ativa IS TRUE
    """
)

SQL_PLANEJAMENTOS = text(
    """
    WITH limite AS (
        SELECT ST_Transform(
            ST_MakeEnvelope(
                :oeste,
                :sul,
                :leste,
                :norte,
                4326
            ),
            31984
        ) AS geom
    )
    SELECT jsonb_build_object(
        'type', 'Feature',
        'geometry',
            ST_AsGeoJSON(
                ST_Transform(p.geom, 4326)
            )::jsonb,
        'properties',
            jsonb_build_object(
                'id', p.id,
                'especie_id', p.especie_id,
                'nome_popular', e.nome_popular,
                'nome_cientifico', e.nome_cientifico,
                'porte', e.porte,
                'origem', e.origem,
                'status', p.status,
                'raio_copa_min_m', p.raio_copa_min_m,
                'raio_copa_max_m', p.raio_copa_max_m,
                'raio_raiz_min_m', p.raio_raiz_min_m,
                'raio_raiz_max_m', p.raio_raiz_max_m,
                'espacamento_recomendado_m',
                    p.espacamento_recomendado_m,
                'justificativa_tecnica',
                    p.justificativa_tecnica,
                'observacoes', p.observacoes,
                'validacao', p.validacao,
                'criado_em', p.criado_em,
                'atualizado_em', p.atualizado_em,
                'criado_por_nome', uc.nome,
                'atualizado_por_nome', ua.nome
            )
    ) AS feature
    FROM semdu.arborizacao_planejamento AS p
    INNER JOIN semdu.arborizacao_especies AS e
        ON e.id = p.especie_id
    LEFT JOIN semed.usuarios AS uc
        ON uc.id = p.criado_por_usuario_id
    LEFT JOIN semed.usuarios AS ua
        ON ua.id = p.atualizado_por_usuario_id
    CROSS JOIN limite
    WHERE p.ativo IS TRUE
      AND p.status <> 'CANCELADO'
      AND ST_Intersects(p.geom, limite.geom)
    ORDER BY p.id
    LIMIT :limite
    """
)

SQL_CONFLITOS_ARVORES = text(
    """
    WITH ponto AS (
        SELECT ST_Transform(
            ST_SetSRID(
                ST_MakePoint(:longitude, :latitude),
                4326
            ),
            31984
        ) AS geom
    )
    SELECT
        p.id,
        e.nome_popular,
        ROUND(
            ST_Distance(p.geom, ponto.geom)::numeric,
            2
        ) AS distancia_m,
        GREATEST(
            :espacamento_novo,
            COALESCE(p.espacamento_recomendado_m, 0)
        ) AS distancia_exigida_m
    FROM semdu.arborizacao_planejamento AS p
    INNER JOIN semdu.arborizacao_especies AS e
        ON e.id = p.especie_id
    CROSS JOIN ponto
    WHERE p.ativo IS TRUE
      AND p.status <> 'CANCELADO'
      AND p.id <> COALESCE(
          CAST(:ignorar_id AS BIGINT),
          -1
      )
      AND ST_DWithin(
          p.geom,
          ponto.geom,
          CAST(
              GREATEST(
                  CAST(:espacamento_novo AS NUMERIC),
                  COALESCE(
                      p.espacamento_recomendado_m,
                      0::NUMERIC
                  )
              )
              AS DOUBLE PRECISION
          )
      )
    ORDER BY ST_Distance(p.geom, ponto.geom)
    LIMIT 20
    """
)

SQL_REGRAS_ESPACIAIS = text(
    """
    SELECT
        id,
        codigo,
        titulo,
        tabela_schema,
        tabela_nome,
        coluna_geometria,
        distancia_min_m,
        severidade,
        mensagem,
        fonte_normativa
    FROM semdu.arborizacao_regras_espaciais
    WHERE ativa IS TRUE
    ORDER BY ordem, id
    """
)


def _numero(valor: Any, *, obrigatorio: bool = False) -> float | None:
    if valor is None or valor == "":
        if obrigatorio:
            abort(400, description="Valor numérico obrigatório.")
        return None

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        abort(400, description="Valor numérico inválido.")

    if not math.isfinite(numero):
        abort(400, description="Valor numérico inválido.")

    return numero


def _inteiro(valor: Any, *, obrigatorio: bool = False) -> int | None:
    if valor is None or valor == "":
        if obrigatorio:
            abort(400, description="Identificador obrigatório.")
        return None

    try:
        return int(valor)
    except (TypeError, ValueError):
        abort(400, description="Identificador inválido.")


def _texto(valor: Any, limite: int = 4000) -> str | None:
    texto_valor = str(valor or "").strip()
    if not texto_valor:
        return None
    return texto_valor[:limite]


def _bbox() -> tuple[float, float, float, float]:
    valor = str(request.args.get("bbox") or "").strip()

    if not valor:
        return -180.0, -90.0, 180.0, 90.0

    partes = valor.split(",")
    if len(partes) != 4:
        abort(400, description="bbox deve ser oeste,sul,leste,norte.")

    try:
        oeste, sul, leste, norte = map(float, partes)
    except ValueError:
        abort(400, description="bbox inválido.")

    if oeste >= leste or sul >= norte:
        abort(400, description="bbox inválido.")

    return oeste, sul, leste, norte


def _limite() -> int:
    try:
        valor = int(request.args.get("limite", 5000))
    except (TypeError, ValueError):
        valor = 5000
    return max(1, min(valor, 10000))


def _especie(especie_id: int) -> dict:
    especie = db.session.execute(
        SQL_ESPECIE_ID,
        {"especie_id": especie_id},
    ).mappings().one_or_none()

    if especie is None:
        abort(404, description="Espécie não encontrada.")

    return dict(especie)


def _identificador(valor: str) -> str:
    valor = str(valor or "").strip()
    if not valor or "\x00" in valor:
        raise ValueError("Identificador espacial inválido.")
    return '"' + valor.replace('"', '""') + '"'


def _regra_existe(regra: dict) -> bool:
    consulta = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM public.geometry_columns
            WHERE f_table_schema = :schema
              AND f_table_name = :tabela
              AND f_geometry_column = :coluna
        )
        """
    )
    return bool(
        db.session.execute(
            consulta,
            {
                "schema": regra["tabela_schema"],
                "tabela": regra["tabela_nome"],
                "coluna": regra["coluna_geometria"],
            },
        ).scalar_one()
    )


def _avaliar_regra_espacial(
    regra: dict,
    latitude: float,
    longitude: float,
) -> dict:
    if not _regra_existe(regra):
        return {
            "codigo": regra["codigo"],
            "titulo": regra["titulo"],
            "resultado": "INDISPONIVEL",
            "severidade": "AVISO",
            "mensagem": (
                "A camada configurada para esta verificação "
                "não está registrada em geometry_columns."
            ),
            "fonte_normativa": regra["fonte_normativa"],
        }

    schema = _identificador(regra["tabela_schema"])
    tabela = _identificador(regra["tabela_nome"])
    coluna = _identificador(regra["coluna_geometria"])

    consulta = text(
        f"""
        WITH ponto AS (
            SELECT ST_Transform(
                ST_SetSRID(
                    ST_MakePoint(:longitude, :latitude),
                    4326
                ),
                31984
            ) AS geom
        )
        SELECT
            EXISTS (
                SELECT 1
                FROM {schema}.{tabela} AS t
                CROSS JOIN ponto
                WHERE t.{coluna} IS NOT NULL
                  AND ST_DWithin(
                      ST_Transform(
                          ST_Force2D(t.{coluna}),
                          31984
                      ),
                      ponto.geom,
                      :distancia
                  )
            ) AS conflito,
            (
                SELECT ROUND(
                    MIN(
                        ST_Distance(
                            ST_Transform(
                                ST_Force2D(t.{coluna}),
                                31984
                            ),
                            ponto.geom
                        )
                    )::numeric,
                    2
                )
                FROM {schema}.{tabela} AS t
                CROSS JOIN ponto
                WHERE t.{coluna} IS NOT NULL
            ) AS distancia_mais_proxima_m
        """
    )

    resultado = db.session.execute(
        consulta,
        {
            "latitude": latitude,
            "longitude": longitude,
            "distancia": float(regra["distancia_min_m"]),
        },
    ).mappings().one()

    conflito = bool(resultado["conflito"])

    return {
        "codigo": regra["codigo"],
        "titulo": regra["titulo"],
        "resultado": "CONFLITO" if conflito else "CONFORME",
        "severidade": regra["severidade"],
        "mensagem": regra["mensagem"],
        "distancia_min_m": float(regra["distancia_min_m"]),
        "distancia_mais_proxima_m": (
            float(resultado["distancia_mais_proxima_m"])
            if resultado["distancia_mais_proxima_m"] is not None
            else None
        ),
        "fonte_normativa": regra["fonte_normativa"],
    }


def validar_local(
    especie: dict,
    latitude: float,
    longitude: float,
    *,
    ignorar_id: int | None = None,
    raio_raiz_min_m: float | None = None,
    raio_raiz_max_m: float | None = None,
) -> dict:
    bloqueios: list[dict] = []
    avisos: list[dict] = []
    verificacoes: list[dict] = []

    if not especie.get("permitida_planejamento"):
        bloqueios.append(
            {
                "codigo": "ESPECIE_NAO_LIBERADA",
                "mensagem": (
                    "A espécie não está liberada para novo plantio "
                    "automático. É necessária decisão técnica específica."
                ),
                "fonte": especie.get("fonte_tecnica"),
            }
        )

    if especie.get("invasora"):
        bloqueios.append(
            {
                "codigo": "ESPECIE_INVASORA",
                "mensagem": (
                    "Espécies marcadas como invasoras não podem ser "
                    "incluídas pelo fluxo comum de planejamento."
                ),
                "fonte": especie.get("fonte_tecnica"),
            }
        )

    espacamento = float(
        especie.get("espacamento_recomendado_m") or 0
    )

    conflitos = db.session.execute(
        SQL_CONFLITOS_ARVORES,
        {
            "latitude": latitude,
            "longitude": longitude,
            "espacamento_novo": espacamento,
            "ignorar_id": ignorar_id,
        },
    ).mappings().all()

    for conflito in conflitos:
        bloqueios.append(
            {
                "codigo": "ESPACAMENTO_ARVORES",
                "mensagem": (
                    f"Conflito com {conflito['nome_popular']} "
                    f"a {conflito['distancia_m']} m. "
                    f"Distância exigida: "
                    f"{conflito['distancia_exigida_m']} m."
                ),
                "planejamento_id": conflito["id"],
                "distancia_m": float(conflito["distancia_m"]),
                "distancia_exigida_m": float(
                    conflito["distancia_exigida_m"]
                ),
                "fonte": (
                    "Lei Municipal nº 1.009/2021, art. 17, e "
                    "Parecer Técnico SEMDU nº 004/2026."
                ),
            }
        )

    if especie.get("raio_copa_max_m") is None:
        avisos.append(
            {
                "codigo": "COPA_SEM_RAIO_NUMERICO",
                "mensagem": (
                    "O parecer não apresenta raio máximo numérico "
                    "de copa para esta espécie."
                ),
                "fonte": especie.get("fonte_tecnica"),
            }
        )

    raiz_min = (
        raio_raiz_min_m
        if raio_raiz_min_m is not None
        else especie.get("raio_raiz_min_m")
    )
    raiz_max = (
        raio_raiz_max_m
        if raio_raiz_max_m is not None
        else especie.get("raio_raiz_max_m")
    )

    if raiz_min is None or raiz_max is None:
        avisos.append(
            {
                "codigo": "RAIZ_SEM_RAIO_NUMERICO",
                "mensagem": (
                    "O parecer descreve o sistema radicular, mas não "
                    "define raios mínimo e máximo. Preencha-os somente "
                    "quando houver avaliação técnica para o local."
                ),
                "fonte": especie.get("fonte_tecnica"),
            }
        )

    regras = db.session.execute(
        SQL_REGRAS_ESPACIAIS
    ).mappings().all()

    if not regras:
        avisos.append(
            {
                "codigo": "INFRAESTRUTURA_NAO_CONFIGURADA",
                "mensagem": (
                    "Não há camadas de infraestrutura vinculadas às "
                    "regras automáticas. Fiação, calçada, tubulação, "
                    "postes, esquinas e construções devem ser conferidos "
                    "pela responsável técnica."
                ),
                "fonte": (
                    "Parecer Técnico SEMDU nº 004/2026, "
                    "Considerações Gerais."
                ),
            }
        )

    for regra in regras:
        try:
            resultado = _avaliar_regra_espacial(
                dict(regra),
                latitude,
                longitude,
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception(
                "Erro na regra espacial %s.",
                regra["codigo"],
            )
            resultado = {
                "codigo": regra["codigo"],
                "titulo": regra["titulo"],
                "resultado": "INDISPONIVEL",
                "severidade": "AVISO",
                "mensagem": (
                    "A verificação automática falhou. "
                    "Realize conferência técnica."
                ),
                "fonte_normativa": regra["fonte_normativa"],
            }

        verificacoes.append(resultado)

        if resultado["resultado"] == "CONFLITO":
            destino = (
                bloqueios
                if resultado["severidade"] == "BLOQUEIO"
                else avisos
            )
            destino.append(
                {
                    "codigo": resultado["codigo"],
                    "mensagem": resultado["mensagem"],
                    "fonte": resultado.get("fonte_normativa"),
                    "distancia_m": resultado.get(
                        "distancia_mais_proxima_m"
                    ),
                }
            )

    return {
        "valido": not bloqueios,
        "bloqueios": bloqueios,
        "avisos": avisos,
        "verificacoes": verificacoes,
        "parametros": {
            "espacamento_recomendado_m": espacamento,
            "raio_copa_min_m": especie.get("raio_copa_min_m"),
            "raio_copa_max_m": especie.get("raio_copa_max_m"),
            "raio_raiz_min_m": raiz_min,
            "raio_raiz_max_m": raiz_max,
        },
    }


def _corpo_json() -> dict:
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        abort(400, description="Envie um objeto JSON válido.")
    return corpo


def _parametros_planejamento(corpo: dict) -> dict:
    especie_id = _inteiro(corpo.get("especie_id"), obrigatorio=True)
    latitude = _numero(corpo.get("latitude"), obrigatorio=True)
    longitude = _numero(corpo.get("longitude"), obrigatorio=True)

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        abort(400, description="Coordenadas inválidas.")

    raiz_min = _numero(corpo.get("raio_raiz_min_m"))
    raiz_max = _numero(corpo.get("raio_raiz_max_m"))

    if raiz_min is not None and raiz_min < 0:
        abort(400, description="O raio mínimo da raiz não pode ser negativo.")
    if raiz_max is not None and raiz_max < 0:
        abort(400, description="O raio máximo da raiz não pode ser negativo.")
    if raiz_min is not None and raiz_max is not None and raiz_min > raiz_max:
        abort(400, description="O raio mínimo da raiz excede o máximo.")

    status = str(corpo.get("status") or "RASCUNHO").strip().upper()
    if status not in STATUS_VALIDOS:
        abort(400, description="Status de planejamento inválido.")

    return {
        "especie_id": especie_id,
        "latitude": latitude,
        "longitude": longitude,
        "raio_raiz_min_m": raiz_min,
        "raio_raiz_max_m": raiz_max,
        "status": status,
        "justificativa_tecnica": _texto(
            corpo.get("justificativa_tecnica")
        ),
        "observacoes": _texto(corpo.get("observacoes")),
    }


@arborizacao_bp.get("/api/semdu/arborizacao/permissoes")
@acesso_modulo_required(MODULO_SEMDU)
def permissoes():
    return jsonify(
        {
            "pode_visualizar": True,
            "pode_editar": usuario_possui_funcao(
                current_user,
                FUNCAO_ENG_AMBIENTAL,
            ),
            "funcao_exigida": FUNCAO_ENG_AMBIENTAL,
            "funcoes_usuario": sorted(
                listar_funcoes_usuario(current_user)
            ),
        }
    )


@arborizacao_bp.get("/api/semdu/arborizacao/especies")
@acesso_modulo_required(MODULO_SEMDU)
def especies():
    try:
        registros = db.session.execute(
            SQL_ESPECIES
        ).mappings().all()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao listar espécies da arborização."
        )
        return jsonify(
            {
                "sucesso": False,
                "erro": "Não foi possível consultar as espécies.",
            }
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "quantidade": len(registros),
            "especies": [dict(item) for item in registros],
        }
    )


@arborizacao_bp.get("/api/semdu/arborizacao/planejamentos")
@acesso_modulo_required(MODULO_SEMDU)
def planejamentos():
    oeste, sul, leste, norte = _bbox()

    try:
        features = db.session.execute(
            SQL_PLANEJAMENTOS,
            {
                "oeste": oeste,
                "sul": sul,
                "leste": leste,
                "norte": norte,
                "limite": _limite(),
            },
        ).scalars().all()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao consultar o planejamento arbóreo."
        )
        return jsonify(
            {
                "sucesso": False,
                "erro": "Não foi possível consultar os plantios planejados.",
            }
        ), 500

    return jsonify(
        {
            "type": "FeatureCollection",
            "name": "arborizacao_planejamento",
            "features": features,
            "metadata": {
                "quantidade": len(features),
                "srid_origem": 31984,
            },
        }
    )


@arborizacao_bp.post("/api/semdu/arborizacao/validar-local")
@acesso_modulo_required(MODULO_SEMDU)
def validar_local_api():
    corpo = _corpo_json()
    parametros = _parametros_planejamento(corpo)
    especie = _especie(parametros["especie_id"])

    try:
        resultado = validar_local(
            especie,
            parametros["latitude"],
            parametros["longitude"],
            ignorar_id=_inteiro(corpo.get("ignorar_id")),
            raio_raiz_min_m=parametros["raio_raiz_min_m"],
            raio_raiz_max_m=parametros["raio_raiz_max_m"],
        )
    except SQLAlchemyError as erro:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao validar local de plantio."
        )

        resposta = {
            "sucesso": False,
            "erro": "Não foi possível validar o local.",
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

    return jsonify(
        {
            "sucesso": True,
            "especie": {
                "id": especie["id"],
                "nome_popular": especie["nome_popular"],
                "nome_cientifico": especie["nome_cientifico"],
            },
            "resultado": resultado,
        }
    )


@arborizacao_bp.post("/api/semdu/arborizacao/planejamentos")
@acesso_modulo_required(MODULO_SEMDU)
@funcao_semdu_required(FUNCAO_ENG_AMBIENTAL)
def criar_planejamento():
    corpo = _corpo_json()
    parametros = _parametros_planejamento(corpo)
    especie = _especie(parametros["especie_id"])

    try:
        validacao = validar_local(
            especie,
            parametros["latitude"],
            parametros["longitude"],
            raio_raiz_min_m=parametros["raio_raiz_min_m"],
            raio_raiz_max_m=parametros["raio_raiz_max_m"],
        )

        if not validacao["valido"]:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": "O local possui bloqueios técnicos.",
                    "validacao": validacao,
                }
            ), 422

        planejamento_id = db.session.execute(
            text(
                """
                INSERT INTO semdu.arborizacao_planejamento (
                    especie_id,
                    geom,
                    raio_copa_min_m,
                    raio_copa_max_m,
                    raio_raiz_min_m,
                    raio_raiz_max_m,
                    espacamento_recomendado_m,
                    status,
                    justificativa_tecnica,
                    observacoes,
                    validacao,
                    criado_por_usuario_id,
                    atualizado_por_usuario_id
                ) VALUES (
                    :especie_id,
                    ST_Transform(
                        ST_SetSRID(
                            ST_MakePoint(:longitude, :latitude),
                            4326
                        ),
                        31984
                    ),
                    :raio_copa_min_m,
                    :raio_copa_max_m,
                    :raio_raiz_min_m,
                    :raio_raiz_max_m,
                    :espacamento,
                    :status,
                    :justificativa,
                    :observacoes,
                    CAST(:validacao AS jsonb),
                    :usuario_id,
                    :usuario_id
                )
                RETURNING id
                """
            ),
            {
                "especie_id": especie["id"],
                "longitude": parametros["longitude"],
                "latitude": parametros["latitude"],
                "raio_copa_min_m": especie.get("raio_copa_min_m"),
                "raio_copa_max_m": especie.get("raio_copa_max_m"),
                "raio_raiz_min_m": parametros["raio_raiz_min_m"],
                "raio_raiz_max_m": parametros["raio_raiz_max_m"],
                "espacamento": especie.get("espacamento_recomendado_m"),
                "status": parametros["status"],
                "justificativa": parametros["justificativa_tecnica"],
                "observacoes": parametros["observacoes"],
                "validacao": json.dumps(validacao, ensure_ascii=False),
                "usuario_id": int(current_user.id),
            },
        ).scalar_one()

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao criar planejamento arbóreo."
        )
        return jsonify(
            {
                "sucesso": False,
                "erro": "Não foi possível salvar o planejamento.",
            }
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "mensagem": "Plantio planejado com sucesso.",
            "id": planejamento_id,
            "validacao": validacao,
        }
    ), 201


@arborizacao_bp.put("/api/semdu/arborizacao/planejamentos/<int:planejamento_id>")
@acesso_modulo_required(MODULO_SEMDU)
@funcao_semdu_required(FUNCAO_ENG_AMBIENTAL)
def atualizar_planejamento(planejamento_id: int):
    corpo = _corpo_json()
    parametros = _parametros_planejamento(corpo)
    especie = _especie(parametros["especie_id"])

    existente = db.session.execute(
        text(
            """
            SELECT id
            FROM semdu.arborizacao_planejamento
            WHERE id = :id
              AND ativo IS TRUE
            """
        ),
        {"id": planejamento_id},
    ).scalar_one_or_none()

    if existente is None:
        abort(404, description="Planejamento não encontrado.")

    try:
        validacao = validar_local(
            especie,
            parametros["latitude"],
            parametros["longitude"],
            ignorar_id=planejamento_id,
            raio_raiz_min_m=parametros["raio_raiz_min_m"],
            raio_raiz_max_m=parametros["raio_raiz_max_m"],
        )

        if not validacao["valido"]:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": "O local possui bloqueios técnicos.",
                    "validacao": validacao,
                }
            ), 422

        db.session.execute(
            text(
                """
                UPDATE semdu.arborizacao_planejamento
                SET
                    especie_id = :especie_id,
                    geom = ST_Transform(
                        ST_SetSRID(
                            ST_MakePoint(:longitude, :latitude),
                            4326
                        ),
                        31984
                    ),
                    raio_copa_min_m = :raio_copa_min_m,
                    raio_copa_max_m = :raio_copa_max_m,
                    raio_raiz_min_m = :raio_raiz_min_m,
                    raio_raiz_max_m = :raio_raiz_max_m,
                    espacamento_recomendado_m = :espacamento,
                    status = :status,
                    justificativa_tecnica = :justificativa,
                    observacoes = :observacoes,
                    validacao = CAST(:validacao AS jsonb),
                    atualizado_por_usuario_id = :usuario_id,
                    atualizado_em = NOW()
                WHERE id = :id
                """
            ),
            {
                "id": planejamento_id,
                "especie_id": especie["id"],
                "longitude": parametros["longitude"],
                "latitude": parametros["latitude"],
                "raio_copa_min_m": especie.get("raio_copa_min_m"),
                "raio_copa_max_m": especie.get("raio_copa_max_m"),
                "raio_raiz_min_m": parametros["raio_raiz_min_m"],
                "raio_raiz_max_m": parametros["raio_raiz_max_m"],
                "espacamento": especie.get("espacamento_recomendado_m"),
                "status": parametros["status"],
                "justificativa": parametros["justificativa_tecnica"],
                "observacoes": parametros["observacoes"],
                "validacao": json.dumps(validacao, ensure_ascii=False),
                "usuario_id": int(current_user.id),
            },
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao atualizar planejamento arbóreo %s.",
            planejamento_id,
        )
        return jsonify(
            {
                "sucesso": False,
                "erro": "Não foi possível atualizar o planejamento.",
            }
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "mensagem": "Planejamento atualizado.",
            "id": planejamento_id,
            "validacao": validacao,
        }
    )


@arborizacao_bp.delete("/api/semdu/arborizacao/planejamentos/<int:planejamento_id>")
@acesso_modulo_required(MODULO_SEMDU)
@funcao_semdu_required(FUNCAO_ENG_AMBIENTAL)
def cancelar_planejamento(planejamento_id: int):
    """
    Faz exclusão lógica do planejamento.

    O registro não é apagado fisicamente, pois precisa
    permanecer disponível para auditoria. Ele recebe
    status CANCELADO e deixa de aparecer no mapa.
    """
    corpo = request.get_json(silent=True) or {}
    motivo = _texto(
        corpo.get("motivo"),
        2000,
    )

    if not motivo:
        abort(
            400,
            description=(
                "Informe o motivo técnico "
                "do cancelamento."
            ),
        )

    try:
        cancelado_id = db.session.execute(
            text(
                """
                UPDATE semdu.arborizacao_planejamento
                SET
                    status = 'CANCELADO',
                    ativo = FALSE,
                    observacoes = CONCAT_WS(
                        E'\n',
                        NULLIF(
                            BTRIM(observacoes),
                            ''
                        ),
                        CAST(
                            :motivo
                            AS TEXT
                        )
                    ),
                    atualizado_por_usuario_id = CAST(
                        :usuario_id
                        AS INTEGER
                    ),
                    atualizado_em = NOW()
                WHERE id = CAST(
                    :id
                    AS BIGINT
                )
                  AND ativo IS TRUE
                  AND status <> 'CANCELADO'
                RETURNING id
                """
            ),
            {
                "id": planejamento_id,
                "motivo": (
                    "Cancelamento técnico: "
                    + motivo
                ),
                "usuario_id": int(
                    current_user.id
                ),
            },
        ).scalar_one_or_none()

        if cancelado_id is None:
            db.session.rollback()
            abort(
                404,
                description=(
                    "O planejamento não foi encontrado "
                    "ou já está cancelado."
                ),
            )

        db.session.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as erro:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao cancelar planejamento arbóreo %s.",
            planejamento_id,
        )

        resposta = {
            "sucesso": False,
            "erro": (
                "Não foi possível cancelar o planejamento."
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

        return jsonify(
            resposta
        ), 500

    return jsonify(
        {
            "sucesso": True,
            "id": cancelado_id,
            "mensagem": (
                "Planejamento cancelado e removido "
                "das camadas ativas."
            ),
        }
    )


@arborizacao_bp.errorhandler(HTTPException)
def erro_http(erro: HTTPException):
    if request.path.startswith("/api/semdu/arborizacao/"):
        return jsonify(
            {
                "sucesso": False,
                "erro": erro.description,
                "codigo": erro.code,
            }
        ), erro.code

    return erro
