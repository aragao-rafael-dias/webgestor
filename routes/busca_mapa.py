# ==========================================
# BUSCA UNIFICADA DO MAPA
# Escolas, localidades e rotas escolares
# ==========================================

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)
from flask_login import login_required
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


busca_mapa_bp = Blueprint(
    "busca_mapa",
    __name__,
)


# ==========================================
# CONSULTAS
# ==========================================

SQL_TABELA_EXISTE = text(
    """
    SELECT to_regclass(
        :nome_tabela
    )
    """
)


SQL_ESCOLAS = text(
    """
    WITH fonte AS (
        SELECT
            e.id,
            e.geom,

            -- A busca não depende de todas as colunas existirem.
            -- Os atributos são lidos do registro como JSONB.
            TO_JSONB(e) - 'geom' AS dados

        FROM semed.escolas AS e
    ),

    escolas_normalizadas AS (
        SELECT
            id,

            COALESCE(
                NULLIF(BTRIM(dados ->> 'nome'), ''),
                NULLIF(BTRIM(dados ->> 'NOME'), ''),
                NULLIF(BTRIM(dados ->> 'nome_escola'), ''),
                NULLIF(BTRIM(dados ->> 'NOME_ESCOLA'), ''),
                'Escola sem nome'
            ) AS nome,

            COALESCE(
                NULLIF(
                    BTRIM(
                        dados
                        ->> 'bairro_povoado_assentamento'
                    ),
                    ''
                ),
                NULLIF(BTRIM(dados ->> 'localidade'), ''),
                NULLIF(BTRIM(dados ->> 'bairro'), ''),
                NULLIF(BTRIM(dados ->> 'povoado'), ''),
                NULLIF(BTRIM(dados ->> 'assentamento'), ''),
                ''
            ) AS localidade,

            COALESCE(
                NULLIF(BTRIM(dados ->> 'logradouro'), ''),
                NULLIF(BTRIM(dados ->> 'endereco'), ''),
                NULLIF(BTRIM(dados ->> 'endereço'), ''),
                ''
            ) AS logradouro,

            COALESCE(
                NULLIF(BTRIM(dados ->> 'tipo_de_escola'), ''),
                NULLIF(BTRIM(dados ->> 'tipo_escola'), ''),
                NULLIF(BTRIM(dados ->> 'tipo'), ''),
                ''
            ) AS tipo_escola,

            COALESCE(
                NULLIF(BTRIM(dados ->> 'diretor'), ''),
                NULLIF(BTRIM(dados ->> 'DIRETOR'), ''),
                ''
            ) AS diretor,

            COALESCE(
                NULLIF(BTRIM(dados ->> 'telefone'), ''),
                NULLIF(BTRIM(dados ->> 'TELEFONE'), ''),
                ''
            ) AS telefone,

            CASE
                WHEN geom IS NULL
                  OR ST_IsEmpty(geom)
                    THEN NULL

                WHEN ST_SRID(geom) = 4326
                    THEN ST_Force2D(geom)

                WHEN ST_SRID(geom) = 31984
                    THEN ST_Transform(
                        ST_Force2D(geom),
                        4326
                    )

                WHEN ABS(
                    ST_X(
                        ST_Centroid(geom)
                    )
                ) > 180
                    THEN ST_Transform(
                        ST_SetSRID(
                            ST_Force2D(geom),
                            31984
                        ),
                        4326
                    )

                ELSE ST_SetSRID(
                    ST_Force2D(geom),
                    4326
                )
            END AS geom_wgs

        FROM fonte
    )

    SELECT
        id,
        nome,
        localidade,
        logradouro,
        tipo_escola,
        diretor,
        telefone,
        ST_Y(
            ST_Centroid(geom_wgs)
        ) AS lat,
        ST_X(
            ST_Centroid(geom_wgs)
        ) AS lon

    FROM escolas_normalizadas

    WHERE
        TRANSLATE(
            LOWER(
                CONCAT_WS(
                    ' ',
                    nome,
                    localidade,
                    logradouro,
                    tipo_escola,
                    diretor,
                    telefone
                )
            ),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
        ) LIKE :termo

    ORDER BY
        CASE
            WHEN TRANSLATE(
                LOWER(nome),
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
            ) = :termo_exato
                THEN 0

            WHEN TRANSLATE(
                LOWER(nome),
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
            ) LIKE :termo_inicio
                THEN 1

            ELSE 2
        END,
        nome

    LIMIT :limite
    """
)


SQL_ROTAS = text(
    """
    WITH rotas_normalizadas AS (
        SELECT
            rg.id,
            rg.nome_rota,
            rg.regiao,
            rg.trecho,

            CASE
                WHEN rg.geom IS NULL
                  OR ST_IsEmpty(rg.geom)
                    THEN NULL

                WHEN ST_SRID(rg.geom) = 4326
                    THEN ST_Force2D(rg.geom)

                WHEN ST_SRID(rg.geom) = 31984
                    THEN ST_Transform(
                        ST_Force2D(rg.geom),
                        4326
                    )

                WHEN ABS(
                    ST_X(
                        ST_Centroid(rg.geom)
                    )
                ) > 180
                    THEN ST_Transform(
                        ST_SetSRID(
                            ST_Force2D(rg.geom),
                            31984
                        ),
                        4326
                    )

                ELSE ST_SetSRID(
                    ST_Force2D(rg.geom),
                    4326
                )
            END AS geom_wgs

        FROM semed.rotas_geral AS rg

        WHERE
            TRANSLATE(
                LOWER(
                    CONCAT_WS(
                        ' ',
                        COALESCE(rg.nome_rota, ''),
                        COALESCE(rg.regiao, ''),
                        COALESCE(rg.trecho, '')
                    )
                ),
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
            ) LIKE :termo
    ),

    rotas_agrupadas AS (
        SELECT
            LOWER(
                BTRIM(nome_rota)
            ) AS chave_rota,

            COALESCE(
                MIN(id) FILTER (
                    WHERE UPPER(
                        BTRIM(trecho)
                    ) = 'IDA'
                ),
                MIN(id)
            ) AS rota_id,

            MIN(nome_rota) AS nome_rota,
            MIN(regiao) AS regiao,

            STRING_AGG(
                DISTINCT UPPER(
                    BTRIM(trecho)
                ),
                ' / '
                ORDER BY UPPER(
                    BTRIM(trecho)
                )
            ) AS trechos,

            ST_Collect(geom_wgs)
                FILTER (
                    WHERE geom_wgs
                        IS NOT NULL
                ) AS geom_coletada

        FROM rotas_normalizadas

        WHERE nome_rota IS NOT NULL
          AND BTRIM(nome_rota) <> ''

        GROUP BY
            LOWER(
                BTRIM(nome_rota)
            )
    )

    SELECT
        rota_id,
        nome_rota,
        regiao,
        trechos,

        ST_Y(
            ST_Centroid(
                geom_coletada
            )
        ) AS centro_lat,

        ST_X(
            ST_Centroid(
                geom_coletada
            )
        ) AS centro_lon,

        ST_YMin(
            Box3D(
                ST_Envelope(
                    geom_coletada
                )
            )
        ) AS min_lat,

        ST_XMin(
            Box3D(
                ST_Envelope(
                    geom_coletada
                )
            )
        ) AS min_lon,

        ST_YMax(
            Box3D(
                ST_Envelope(
                    geom_coletada
                )
            )
        ) AS max_lat,

        ST_XMax(
            Box3D(
                ST_Envelope(
                    geom_coletada
                )
            )
        ) AS max_lon

    FROM rotas_agrupadas

    ORDER BY
        CASE
            WHEN TRANSLATE(
                LOWER(
                    COALESCE(
                        nome_rota,
                        ''
                    )
                ),
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
            ) = :termo_exato
                THEN 0

            WHEN TRANSLATE(
                LOWER(
                    COALESCE(
                        nome_rota,
                        ''
                    )
                ),
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
            ) LIKE :termo_inicio
                THEN 1

            ELSE 2
        END,
        nome_rota

    LIMIT :limite
    """
)


SQL_LOCALIDADES = text(
    """
    SELECT DISTINCT ON (
        TRANSLATE(
            LOWER(
                COALESCE(
                    NULLIF(
                        BTRIM(
                            p.referencia
                        ),
                        ''
                    ),
                    NULLIF(
                        BTRIM(
                            p.logradouro
                        ),
                        ''
                    ),
                    'localidade'
                )
            ),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
        ),
        ROUND(
            p.lat::NUMERIC,
            5
        ),
        ROUND(
            p.lon::NUMERIC,
            5
        )
    )
        p.id AS ponto_id,
        rg.id AS rota_id,
        rg.nome_rota,
        rg.regiao,
        rg.trecho,
        p.ordem,
        p.referencia,
        p.logradouro,
        p.lat,
        p.lon

    FROM semed.rotas_pontos_notaveis AS p

    INNER JOIN semed.rotas_geral AS rg
        ON rg.id = p.rota_id

    WHERE p.lat IS NOT NULL
      AND p.lon IS NOT NULL

      AND TRANSLATE(
            LOWER(
                CONCAT_WS(
                    ' ',
                    COALESCE(
                        p.referencia,
                        ''
                    ),
                    COALESCE(
                        p.logradouro,
                        ''
                    ),
                    COALESCE(
                        rg.nome_rota,
                        ''
                    ),
                    COALESCE(
                        rg.regiao,
                        ''
                    )
                )
            ),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
        ) LIKE :termo

    ORDER BY
        TRANSLATE(
            LOWER(
                COALESCE(
                    NULLIF(
                        BTRIM(
                            p.referencia
                        ),
                        ''
                    ),
                    NULLIF(
                        BTRIM(
                            p.logradouro
                        ),
                        ''
                    ),
                    'localidade'
                )
            ),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
        ),
        ROUND(
            p.lat::NUMERIC,
            5
        ),
        ROUND(
            p.lon::NUMERIC,
            5
        ),
        rg.nome_rota,
        p.ordem

    LIMIT :limite
    """
)


# ==========================================
# NORMALIZAÇÃO
# ==========================================


def texto_limpo(
    valor: Any,
    padrao: str = "",
) -> str:
    if valor is None:
        return padrao

    texto = str(valor).strip()
    return texto or padrao


def normalizar_busca(
    valor: Any,
) -> str:
    texto = unicodedata.normalize(
        "NFD",
        texto_limpo(valor),
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(
            caractere
        ) != "Mn"
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip().lower()


def numero_seguro(
    valor: Any,
) -> float | None:
    if valor is None:
        return None

    try:
        return float(valor)
    except (
        TypeError,
        ValueError,
    ):
        return None


def tabela_existe(
    nome_tabela: str,
) -> bool:
    return bool(
        db.session.execute(
            SQL_TABELA_EXISTE,
            {
                "nome_tabela":
                    nome_tabela,
            },
        ).scalar_one_or_none()
    )


def chave_regiao(
    valor: Any,
) -> str:
    texto = normalizar_busca(
        valor,
    ).upper()

    if (
        "UNIVERSIT" in texto
        or "UNIVERSIDADE" in texto
    ):
        return "universidade"

    correspondencia = re.search(
        r"\d+",
        texto,
    )

    if correspondencia:
        return str(
            int(
                correspondencia.group(0)
            )
        )

    return (
        texto
        .lower()
        .replace(
            " ",
            "_",
        )
    )


def parametros_busca(
    consulta: str,
    limite: int,
) -> dict[str, Any]:
    termo_normalizado = normalizar_busca(
        consulta,
    )

    return {
        "termo":
            f"%{termo_normalizado}%",

        "termo_exato":
            termo_normalizado,

        "termo_inicio":
            f"{termo_normalizado}%",

        "limite":
            limite,
    }


# ==========================================
# FORMATAÇÃO DOS RESULTADOS
# ==========================================


def resultados_escolas(
    consulta: str,
    limite: int,
) -> list[dict[str, Any]]:
    registros = (
        db.session.execute(
            SQL_ESCOLAS,
            parametros_busca(
                consulta,
                limite,
            ),
        )
        .mappings()
        .all()
    )

    resultados: list[
        dict[str, Any]
    ] = []

    for registro in registros:
        localidade = texto_limpo(
            registro.get(
                "localidade"
            )
        )

        logradouro = texto_limpo(
            registro.get(
                "logradouro"
            )
        )

        tipo_escola = texto_limpo(
            registro.get(
                "tipo_escola"
            )
        )

        diretor = texto_limpo(
            registro.get(
                "diretor"
            )
        )

        detalhes = [
            tipo_escola,
            localidade,
            logradouro,
        ]

        detalhes = [
            item
            for item in detalhes
            if item
        ]

        if diretor:
            detalhes.append(
                f"Diretor(a): {diretor}"
            )

        resultados.append(
            {
                "tipo": "escola",
                "id": registro.get(
                    "id"
                ),
                "titulo": texto_limpo(
                    registro.get(
                        "nome"
                    ),
                    "Escola sem nome",
                ),
                "subtitulo": (
                    " • ".join(
                        detalhes
                    )
                    or "Unidade escolar"
                ),
                "lat": numero_seguro(
                    registro.get(
                        "lat"
                    )
                ),
                "lon": numero_seguro(
                    registro.get(
                        "lon"
                    )
                ),
            }
        )

    return resultados


def resultados_rotas(
    consulta: str,
    limite: int,
) -> list[dict[str, Any]]:
    registros = (
        db.session.execute(
            SQL_ROTAS,
            parametros_busca(
                consulta,
                limite,
            ),
        )
        .mappings()
        .all()
    )

    resultados: list[
        dict[str, Any]
    ] = []

    for registro in registros:
        min_lat = numero_seguro(
            registro.get(
                "min_lat"
            )
        )

        min_lon = numero_seguro(
            registro.get(
                "min_lon"
            )
        )

        max_lat = numero_seguro(
            registro.get(
                "max_lat"
            )
        )

        max_lon = numero_seguro(
            registro.get(
                "max_lon"
            )
        )

        bbox = None

        if None not in (
            min_lat,
            min_lon,
            max_lat,
            max_lon,
        ):
            bbox = [
                [
                    min_lat,
                    min_lon,
                ],
                [
                    max_lat,
                    max_lon,
                ],
            ]

        regiao = texto_limpo(
            registro.get(
                "regiao"
            ),
            "Região não informada",
        )

        trechos = texto_limpo(
            registro.get(
                "trechos"
            )
        )

        resultados.append(
            {
                "tipo": "rota",
                "id": registro.get(
                    "rota_id"
                ),
                "titulo": texto_limpo(
                    registro.get(
                        "nome_rota"
                    ),
                    "Rota sem nome",
                ),
                "subtitulo": (
                    regiao
                    + (
                        f" • {trechos}"
                        if trechos
                        else ""
                    )
                ),
                "regiao": regiao,
                "regiao_chave":
                    chave_regiao(
                        regiao
                    ),
                "lat": numero_seguro(
                    registro.get(
                        "centro_lat"
                    )
                ),
                "lon": numero_seguro(
                    registro.get(
                        "centro_lon"
                    )
                ),
                "bbox": bbox,
            }
        )

    return resultados


def resultados_localidades(
    consulta: str,
    limite: int,
) -> list[dict[str, Any]]:
    if not tabela_existe(
        "semed.rotas_pontos_notaveis"
    ):
        return []

    registros = (
        db.session.execute(
            SQL_LOCALIDADES,
            parametros_busca(
                consulta,
                limite,
            ),
        )
        .mappings()
        .all()
    )

    resultados: list[
        dict[str, Any]
    ] = []

    for registro in registros:
        referencia = texto_limpo(
            registro.get(
                "referencia"
            )
        )

        logradouro = texto_limpo(
            registro.get(
                "logradouro"
            )
        )

        titulo = (
            referencia
            or logradouro
            or "Localidade"
        )

        detalhes = [
            texto_limpo(
                registro.get(
                    "nome_rota"
                )
            ),
            texto_limpo(
                registro.get(
                    "trecho"
                )
            ),
        ]

        detalhes = [
            item
            for item in detalhes
            if item
        ]

        resultados.append(
            {
                "tipo": "localidade",
                "id": registro.get(
                    "ponto_id"
                ),
                "rota_id": registro.get(
                    "rota_id"
                ),
                "titulo": titulo,
                "subtitulo": (
                    " • ".join(
                        detalhes
                    )
                    or "Ponto notável"
                ),
                "lat": numero_seguro(
                    registro.get(
                        "lat"
                    )
                ),
                "lon": numero_seguro(
                    registro.get(
                        "lon"
                    )
                ),
                "ordem": registro.get(
                    "ordem"
                ),
                "logradouro":
                    logradouro,
            }
        )

    return resultados


# ==========================================
# CONSULTA TOLERANTE A FALHAS
# ==========================================


def executar_categoria(
    nome_categoria: str,
    funcao: Callable[
        [str, int],
        list[dict[str, Any]],
    ],
    consulta: str,
    limite: int,
    avisos: list[str],
) -> list[dict[str, Any]]:
    """
    Impede que uma categoria com problema
    derrube toda a pesquisa.

    Exemplo: se a consulta de localidades
    falhar, escolas e rotas ainda aparecem.
    """

    try:
        return funcao(
            consulta,
            limite,
        )

    except SQLAlchemyError:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao consultar %s "
            "na busca unificada.",
            nome_categoria,
        )

        avisos.append(
            f"Não foi possível consultar "
            f"{nome_categoria}."
        )

        return []


# ==========================================
# ENDPOINT
# ==========================================


@busca_mapa_bp.get(
    "/api/busca-mapa"
)
@login_required
def buscar_no_mapa():
    consulta = texto_limpo(
        request.args.get(
            "q",
            "",
        )
    )

    if len(consulta) < 2:
        return jsonify(
            {
                "consulta": consulta,
                "resultados": [],
                "total": 0,
                "mensagem": (
                    "Digite pelo menos "
                    "2 caracteres."
                ),
            }
        )

    consulta = consulta[:120]
    limite_por_tipo = 12
    avisos: list[str] = []

    escolas = executar_categoria(
        "escolas",
        resultados_escolas,
        consulta,
        limite_por_tipo,
        avisos,
    )

    rotas = executar_categoria(
        "rotas",
        resultados_rotas,
        consulta,
        limite_por_tipo,
        avisos,
    )

    localidades = executar_categoria(
        "localidades",
        resultados_localidades,
        consulta,
        limite_por_tipo,
        avisos,
    )

    resultados = [
        *escolas,
        *rotas,
        *localidades,
    ]

    resposta = {
        "consulta": consulta,
        "resultados": resultados,
        "total": len(resultados),
        "totais": {
            "escolas":
                len(escolas),
            "rotas":
                len(rotas),
            "localidades":
                len(localidades),
        },
        "avisos": avisos,
    }

    if not resultados and len(avisos) == 3:
        resposta["erro"] = (
            "Não foi possível consultar "
            "a busca."
        )

        return jsonify(
            resposta
        ), 500

    return jsonify(
        resposta
    )
