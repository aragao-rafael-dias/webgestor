# ==========================================
# MEMORIAL DESCRITIVO DE ROTA ESCOLAR
# REPORTLAB + MAPA OSM NA SEGUNDA PÁGINA
# ==========================================

from __future__ import annotations

import io
import json
import math
import os
import re
import time
import tempfile
import zipfile
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import requests
from flask import Blueprint, abort, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from PIL import Image as PILImage
from PIL import ImageDraw, ImageEnhance, ImageFont, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image as RLImage,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from models import db


memorial_bp = Blueprint("memorial", __name__)


# ==========================================
# CONSULTAS
# ==========================================

SQL_TRECHOS_DA_ROTA = text(
    """
    WITH ancora AS (
        SELECT nome_rota
        FROM semed.rotas_geral
        WHERE id = :rota_id
    )
    SELECT
        rg.id,
        rg.nome_rota,
        rg.regiao,
        rg.trecho,
        rg.total_pontos,
        rg.pontos_notaveis::text AS pontos_notaveis_texto,
        ST_SRID(rg.geom) AS srid,
        CASE
            WHEN rg.geom IS NULL OR ST_IsEmpty(rg.geom)
                THEN NULL
            WHEN ST_SRID(rg.geom) <= 0
                THEN NULL
            ELSE ST_Length(
                ST_Transform(
                    ST_Force2D(rg.geom),
                    31984
                )
            )
        END AS extensao_metros,
        CASE
            WHEN rg.geom IS NULL OR ST_IsEmpty(rg.geom)
                THEN NULL
            WHEN ST_SRID(rg.geom) <= 0
                THEN NULL
            ELSE ST_AsGeoJSON(
                ST_Transform(
                    ST_Force2D(rg.geom),
                    4326
                )
            )
        END AS geom_geojson
    FROM semed.rotas_geral AS rg
    INNER JOIN ancora AS a
        ON a.nome_rota = rg.nome_rota
    ORDER BY
        CASE UPPER(TRIM(rg.trecho))
            WHEN 'IDA' THEN 1
            WHEN 'VOLTA' THEN 2
            ELSE 3
        END,
        rg.id
    """
)

SQL_TABELA_EXISTE = text("SELECT to_regclass(:nome_tabela)")

SQL_DADOS_MEMORIAL = text(
    """
    SELECT *
    FROM semed.rotas_memoriais
    WHERE LOWER(BTRIM(codigo_rota)) = LOWER(BTRIM(:codigo_rota))
    LIMIT 1
    """
)

SQL_PONTOS_NORMALIZADOS = text(
    """
    SELECT
        rg.id AS rota_id,
        UPPER(TRIM(rg.trecho)) AS trecho,
        p.ordem,
        p.referencia,
        p.coordenadas,
        p.lat,
        p.lon,
        p.lado_via,
        p.logradouro,
        p.direcao_seguir
    FROM semed.rotas_pontos_notaveis AS p
    INNER JOIN semed.rotas_geral AS rg
        ON rg.id = p.rota_id
    WHERE LOWER(BTRIM(rg.nome_rota)) = LOWER(BTRIM(:codigo_rota))
    ORDER BY
        CASE UPPER(TRIM(rg.trecho))
            WHEN 'IDA' THEN 1
            WHEN 'VOLTA' THEN 2
            ELSE 3
        END,
        p.ordem,
        p.id
    """
)


SQL_ESCOLAS_COORDENADAS = text(
    """
    WITH fonte AS (
        SELECT
            e.id,
            e.geom,
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

                WHEN ST_SRID(geom) <= 0
                  AND ABS(
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

                WHEN ST_SRID(geom) <= 0
                    THEN ST_SetSRID(
                        ST_Force2D(geom),
                        4326
                    )

                ELSE ST_Transform(
                    ST_Force2D(geom),
                    4326
                )
            END AS geom_wgs

        FROM fonte
    )

    SELECT
        id,
        nome,
        ST_Y(
            ST_Centroid(geom_wgs)
        ) AS lat,
        ST_X(
            ST_Centroid(geom_wgs)
        ) AS lon

    FROM escolas_normalizadas

    WHERE geom_wgs IS NOT NULL
      AND NOT ST_IsEmpty(geom_wgs)

    ORDER BY nome
    """
)


SQL_ROTAS_PARA_LOTE = text(
    """
    SELECT DISTINCT ON (LOWER(BTRIM(nome_rota)))
        id,
        nome_rota,
        regiao
    FROM semed.rotas_geral
    WHERE nome_rota IS NOT NULL
      AND BTRIM(nome_rota) <> ''
    ORDER BY
        LOWER(BTRIM(nome_rota)),
        CASE UPPER(TRIM(trecho))
            WHEN 'IDA' THEN 1
            WHEN 'VOLTA' THEN 2
            ELSE 3
        END,
        id
    """
)


TURNOS_PADRAO = ("MANHÃ", "TARDE", "NOITE", "INTEGRAL")
TIPOS_VEICULO = ("ÔNIBUS", "MICRO-ÔNIBUS 4X4", "MICRO-ÔNIBUS", "VAN")
REDES_ENSINO = ("MUNICIPAL", "ESTADUAL", "FEDERAL")
AREAS_LOCALIZACAO = ("URBANA", "RURAL")

AZUL = colors.HexColor("#173D68")
CINZA_BORDA = colors.HexColor("#666666")
PRETO = colors.HexColor("#111111")

CORES_REGIOES = {
    "1": "#4CAF50",
    "2": "#3182BD",
    "3": "#DE2D26",
    "4": "#FFEB3B",
    "5": "#9B4D96",
    "6": "#ED8936",
    "7": "#5E2D79",
    "universidade": "#009688",
}

COR_ROTA_PADRAO = "#173D68"

# Configurações cartográficas em orientação paisagem.
# A imagem completa possui uma área cartográfica à esquerda e uma
# faixa fixa de legenda à direita.
MAPA_LARGURA_PX = 1840
MAPA_ALTURA_PX = 1000
MAPA_PAINEL_DIREITO_PX = 440
MAPA_AREA_LARGURA_PX = MAPA_LARGURA_PX - MAPA_PAINEL_DIREITO_PX
MAPA_AREA_TOPO_PX = 155
MAPA_MARGEM_PX = 24

# Configurações dos mapas detalhados.
#
# Estrutura do arquivo:
#   1ª página: mapa somente com as unidades atendidas;
#   2ª página: mapa geral com pontos notáveis;
#   3ª até nª: recortes detalhados;
#   páginas finais: memorial descritivo.
MAPA_INTERVALO_ROTULO_GERAL = 5
MAPA_MAX_PONTOS_POR_DETALHE = 18
MAPA_MAX_GRUPOS_DETALHE = 8
MAPA_MIN_PONTOS_PARA_DETALHES = 1

# Formatos de saída disponíveis para o usuário.
CONTEUDO_MEMORIAL_MAPA = "memorial_mapa"
CONTEUDO_SOMENTE_MAPA = "mapa"
CONTEUDO_SOMENTE_MEMORIAL = "memorial"
CONTEUDO_ARQUIVOS_SEPARADOS = "separados"

CONTEUDOS_VALIDOS = {
    CONTEUDO_MEMORIAL_MAPA,
    CONTEUDO_SOMENTE_MAPA,
    CONTEUDO_SOMENTE_MEMORIAL,
    CONTEUDO_ARQUIVOS_SEPARADOS,
}

ESCOPO_ROTA = "rota"
ESCOPO_REGIAO = "regiao"
ESCOPO_MUNICIPIO = "municipio"
ESCOPOS_VALIDOS = {
    ESCOPO_ROTA,
    ESCOPO_REGIAO,
    ESCOPO_MUNICIPIO,
}

ORGANIZACAO_UNICO = "unico"
ORGANIZACAO_SEPARADOS = "separados"
ORGANIZACOES_VALIDAS = {
    ORGANIZACAO_UNICO,
    ORGANIZACAO_SEPARADOS,
}


# ==========================================
# NORMALIZAÇÃO
# ==========================================


def texto_limpo(valor: Any, padrao: str = "") -> str:
    if valor is None:
        return padrao
    texto = str(valor).strip()
    return texto or padrao


def decimal_seguro(valor: Any, padrao: Decimal | None = None) -> Decimal | None:
    if valor in (None, ""):
        return padrao
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return padrao


def inteiro_seguro(valor: Any, padrao: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def booleano_seguro(valor: Any, padrao: bool = False) -> bool:
    if isinstance(valor, bool):
        return valor
    if valor is None:
        return padrao
    return str(valor).strip().lower() in {
        "1", "true", "t", "yes", "sim", "s", "on",
    }


def json_seguro(valor: Any, padrao: Any) -> Any:
    if valor is None:
        return padrao
    if isinstance(valor, (list, dict)):
        return valor
    if isinstance(valor, str):
        texto_json = valor.strip()
        if not texto_json:
            return padrao
        try:
            return json.loads(texto_json)
        except json.JSONDecodeError:
            return padrao
    return padrao


def lista_textos(valor: Any) -> list[str]:
    dados = json_seguro(valor, [])
    if not isinstance(dados, list):
        return []

    resultado: list[str] = []
    for item in dados:
        if isinstance(item, dict):
            valor_item = texto_limpo(
                item.get("nome") or item.get("valor") or item.get("descricao")
            )
        else:
            valor_item = texto_limpo(item)
        if valor_item:
            resultado.append(valor_item)
    return resultado


def unidades_assistidas_detalhadas(
    valor: Any,
) -> list[dict[str, Any]]:
    """
    Normaliza as unidades de ensino atendidas.

    A ordem da lista original é preservada porque essa ordem será usada
    na numeração do mapa. Objetos podem trazer coordenadas próprias:

        {"nome": "Escola X", "assistida": true,
         "lat": -10.9, "lon": -37.6}
    """

    dados = json_seguro(valor, [])
    if not isinstance(dados, list):
        return []

    resultado: list[dict[str, Any]] = []
    chaves_vistas: set[str] = set()

    for item in dados:
        latitude = None
        longitude = None

        if isinstance(item, dict):
            marcador = (
                item.get("assistida")
                if "assistida" in item
                else item.get("atendida")
                if "atendida" in item
                else item.get("transporte")
                if "transporte" in item
                else True
            )

            if not booleano_seguro(marcador, True):
                continue

            nome = texto_limpo(
                item.get("nome")
                or item.get("unidade")
                or item.get("escola")
                or item.get("valor")
                or item.get("descricao")
            )

            latitude_decimal = decimal_seguro(
                item.get("lat")
                if item.get("lat") is not None
                else item.get("latitude")
            )
            longitude_decimal = decimal_seguro(
                item.get("lon")
                if item.get("lon") is not None
                else item.get("lng")
                if item.get("lng") is not None
                else item.get("longitude")
            )

            if latitude_decimal is not None:
                latitude = float(latitude_decimal)
            if longitude_decimal is not None:
                longitude = float(longitude_decimal)
        else:
            nome = texto_limpo(item)

        if not nome:
            continue

        chave = unicodedata.normalize(
            "NFKC",
            nome,
        ).casefold()

        if chave in chaves_vistas:
            continue

        chaves_vistas.add(chave)
        resultado.append({
            "nome": nome,
            "lat": latitude,
            "lon": longitude,
        })

    return resultado


def lista_unidades_assistidas(valor: Any) -> list[str]:
    """Compatibilidade: devolve somente os nomes das unidades assistidas."""

    return [
        item["nome"]
        for item in unidades_assistidas_detalhadas(valor)
    ]


def formatar_km(valor: Any, casas: int = 2) -> str:
    numero = decimal_seguro(valor, Decimal("0")) or Decimal("0")
    return f"{numero:.{casas}f}".replace(".", ",")


def normalizar_trecho(valor: Any) -> str:
    trecho = texto_limpo(valor).upper()
    return trecho if trecho in {"IDA", "VOLTA"} else (trecho or "OUTRO")


def limpar_direcao(valor: Any) -> str:
    direcao = texto_limpo(valor)
    if not direcao:
        return ""
    direcao = re.sub(r"^[\s➡️➜→]+", "", direcao)
    direcao = re.sub(r"[\s➡️➜→]+$", "", direcao)
    return direcao.strip()


def normalizar_logradouro(valor: Any) -> str:
    logradouro = texto_limpo(valor)
    if logradouro.upper() in {"N/A", "NA", "NÃO INFORMADO", "NAO INFORMADO"}:
        return ""
    return logradouro


def normalizar_ponto(ponto: dict[str, Any], indice: int) -> dict[str, Any]:
    ordem = inteiro_seguro(ponto.get("ordem"), indice)
    lat = decimal_seguro(ponto.get("lat"))
    lon = decimal_seguro(ponto.get("lon"))
    coordenadas = texto_limpo(ponto.get("coordenadas"))

    if not coordenadas and lat is not None and lon is not None:
        coordenadas = f"{lat:.6f}, {lon:.6f}"

    mapa_url = ""
    if lat is not None and lon is not None:
        mapa_url = f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=18/{lat:.6f}/{lon:.6f}"

    direcao = limpar_direcao(ponto.get("direcao_seguir"))

    return {
        "ordem": ordem,
        "referencia": texto_limpo(ponto.get("referencia"), "Ponto sem referência"),
        "coordenadas": coordenadas,
        "lat": lat,
        "lon": lon,
        "mapa_url": mapa_url,
        "lado_via": texto_limpo(ponto.get("lado_via")),
        "logradouro": normalizar_logradouro(ponto.get("logradouro")),
        "direcao": direcao,
        "fim_trajeto": direcao.upper() == "FIM DO TRAJETO",
    }


def pontos_do_texto_json(valor: Any) -> list[dict[str, Any]]:
    dados = json_seguro(valor, [])
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        return []

    pontos = [
        normalizar_ponto(item, indice)
        for indice, item in enumerate(dados, start=1)
        if isinstance(item, dict)
    ]
    pontos.sort(key=lambda item: (item["ordem"], item["referencia"]))
    return pontos


def extrair_linhas_geojson(valor: Any) -> list[list[tuple[float, float]]]:
    geometria = json_seguro(valor, {})
    if not isinstance(geometria, dict):
        return []

    tipo = texto_limpo(geometria.get("type"))
    coordenadas = geometria.get("coordinates")

    def linha_valida(itens: Iterable[Any]) -> list[tuple[float, float]]:
        resultado: list[tuple[float, float]] = []
        for coordenada in itens:
            if not isinstance(coordenada, (list, tuple)) or len(coordenada) < 2:
                continue
            try:
                lon = float(coordenada[0])
                lat = float(coordenada[1])
            except (TypeError, ValueError):
                continue
            if -180 <= lon <= 180 and -85 <= lat <= 85:
                resultado.append((lon, lat))
        return resultado

    if tipo == "LineString" and isinstance(coordenadas, list):
        linha = linha_valida(coordenadas)
        return [linha] if len(linha) >= 2 else []

    if tipo == "MultiLineString" and isinstance(coordenadas, list):
        linhas: list[list[tuple[float, float]]] = []
        for item in coordenadas:
            if isinstance(item, list):
                linha = linha_valida(item)
                if len(linha) >= 2:
                    linhas.append(linha)
        return linhas

    if tipo == "GeometryCollection":
        linhas: list[list[tuple[float, float]]] = []
        for item in geometria.get("geometries") or []:
            linhas.extend(extrair_linhas_geojson(item))
        return linhas

    return []


# ==========================================
# BANCO DE DADOS
# ==========================================


def tabela_existe(nome_tabela: str) -> bool:
    return bool(
        db.session.execute(
            SQL_TABELA_EXISTE,
            {"nome_tabela": nome_tabela},
        ).scalar_one_or_none()
    )


def buscar_trechos(rota_id: int):
    return (
        db.session.execute(SQL_TRECHOS_DA_ROTA, {"rota_id": rota_id})
        .mappings()
        .all()
    )


def buscar_dados_memorial(codigo_rota: str) -> dict[str, Any]:
    if not tabela_existe("semed.rotas_memoriais"):
        return {}
    resultado = (
        db.session.execute(SQL_DADOS_MEMORIAL, {"codigo_rota": codigo_rota})
        .mappings()
        .first()
    )
    return dict(resultado) if resultado else {}


def buscar_pontos_normalizados(codigo_rota: str) -> dict[str, list[dict[str, Any]]]:
    if not tabela_existe("semed.rotas_pontos_notaveis"):
        return {}

    registros = (
        db.session.execute(
            SQL_PONTOS_NORMALIZADOS,
            {"codigo_rota": codigo_rota},
        )
        .mappings()
        .all()
    )

    pontos_por_trecho: dict[str, list[dict[str, Any]]] = {}
    for indice, registro in enumerate(registros, start=1):
        trecho = normalizar_trecho(registro.get("trecho"))
        pontos_por_trecho.setdefault(trecho, []).append(
            normalizar_ponto(dict(registro), indice)
        )

    for pontos in pontos_por_trecho.values():
        pontos.sort(key=lambda item: (item["ordem"], item["referencia"]))
    return pontos_por_trecho



def buscar_escolas_coordenadas() -> list[dict[str, Any]]:
    """Carrega uma única vez as escolas georreferenciadas do município."""

    if not tabela_existe("semed.escolas"):
        return []

    try:
        registros = db.session.execute(
            SQL_ESCOLAS_COORDENADAS
        ).mappings().all()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Não foi possível carregar as coordenadas das escolas."
        )
        return []

    resultado: list[dict[str, Any]] = []

    for registro in registros:
        lat = decimal_seguro(registro.get("lat"))
        lon = decimal_seguro(registro.get("lon"))

        if lat is None or lon is None:
            continue

        resultado.append({
            "id": registro.get("id"),
            "nome": texto_limpo(registro.get("nome")),
            "lat": float(lat),
            "lon": float(lon),
        })

    return resultado


def _chave_nome_unidade(valor: Any) -> str:
    texto_nome = unicodedata.normalize(
        "NFD",
        texto_limpo(valor),
    )
    texto_nome = "".join(
        caractere
        for caractere in texto_nome
        if unicodedata.category(caractere) != "Mn"
    )
    texto_nome = re.sub(
        r"[^A-Za-z0-9]+",
        " ",
        texto_nome,
    )
    return re.sub(r"\s+", " ", texto_nome).strip().casefold()


def _pontuacao_correspondencia_nome(
    nome_procurado: Any,
    nome_candidato: Any,
) -> float:
    procurado = _chave_nome_unidade(nome_procurado)
    candidato = _chave_nome_unidade(nome_candidato)

    if not procurado or not candidato:
        return 0.0

    if procurado == candidato:
        return 1.0

    if procurado in candidato or candidato in procurado:
        proporcao = min(
            len(procurado),
            len(candidato),
        ) / max(len(procurado), len(candidato))
        return 0.88 + proporcao * 0.10

    tokens_procurado = set(procurado.split())
    tokens_candidato = set(candidato.split())
    uniao = tokens_procurado | tokens_candidato
    jaccard = (
        len(tokens_procurado & tokens_candidato) / len(uniao)
        if uniao
        else 0.0
    )

    sequencia = SequenceMatcher(
        None,
        procurado,
        candidato,
    ).ratio()

    return max(sequencia, jaccard)


def _pontos_validos_contexto(
    contexto: dict[str, Any],
) -> list[dict[str, Any]]:
    pontos: list[dict[str, Any]] = []

    for trecho in (contexto["ida"], contexto["volta"]):
        for ponto in trecho.get("pontos") or []:
            if ponto.get("lat") is None or ponto.get("lon") is None:
                continue

            pontos.append({
                "nome": " ".join(
                    item
                    for item in (
                        texto_limpo(ponto.get("referencia")),
                        texto_limpo(ponto.get("logradouro")),
                    )
                    if item
                ),
                "lat": float(ponto["lat"]),
                "lon": float(ponto["lon"]),
            })

    return pontos


def resolver_escolas_mapa(
    contexto: dict[str, Any],
    escolas_cadastradas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Resolve as coordenadas das unidades assistidas, preservando a ordem.

    Prioridades:
      1. coordenada informada no JSON escolas_atendidas;
      2. correspondência com semed.escolas;
      3. correspondência com os pontos notáveis da própria rota.
    """

    unidades = contexto.get("escolas_detalhadas") or []
    pontos_rota = _pontos_validos_contexto(contexto)
    ids_escolas_usados: set[Any] = set()
    resultado: list[dict[str, Any]] = []

    for numero, unidade in enumerate(unidades, start=1):
        nome = texto_limpo(unidade.get("nome"), f"Unidade {numero}")
        lat = unidade.get("lat")
        lon = unidade.get("lon")
        fonte = "metadados"

        if lat is None or lon is None:
            melhor_escola = None
            melhor_nota = 0.0

            for escola in escolas_cadastradas:
                if escola.get("id") in ids_escolas_usados:
                    continue

                nota = _pontuacao_correspondencia_nome(
                    nome,
                    escola.get("nome"),
                )

                if nota > melhor_nota:
                    melhor_nota = nota
                    melhor_escola = escola

            if melhor_escola is not None and melhor_nota >= 0.72:
                lat = melhor_escola["lat"]
                lon = melhor_escola["lon"]
                fonte = "semed.escolas"
                ids_escolas_usados.add(melhor_escola.get("id"))

        if lat is None or lon is None:
            melhor_ponto = None
            melhor_nota = 0.0

            for ponto in pontos_rota:
                nota = _pontuacao_correspondencia_nome(
                    nome,
                    ponto.get("nome"),
                )

                if nota > melhor_nota:
                    melhor_nota = nota
                    melhor_ponto = ponto

            if melhor_ponto is not None and melhor_nota >= 0.60:
                lat = melhor_ponto["lat"]
                lon = melhor_ponto["lon"]
                fonte = "ponto_notavel"

        resultado.append({
            "numero": numero,
            "nome": nome,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "fonte": fonte if lat is not None and lon is not None else "sem_coordenada",
        })

    return resultado


# ==========================================
# CONTEXTO DO MEMORIAL
# ==========================================


def montar_trechos(registros, pontos_normalizados):
    trechos: dict[str, dict[str, Any]] = {}

    for registro in registros:
        nome_trecho = normalizar_trecho(registro.get("trecho"))
        pontos = pontos_normalizados.get(nome_trecho, [])
        if not pontos:
            pontos = pontos_do_texto_json(registro.get("pontos_notaveis_texto"))

        extensao_metros = decimal_seguro(registro.get("extensao_metros"))
        linhas = extrair_linhas_geojson(registro.get("geom_geojson"))

        if not linhas:
            linha_pontos = [
                (float(ponto["lon"]), float(ponto["lat"]))
                for ponto in pontos
                if ponto.get("lat") is not None and ponto.get("lon") is not None
            ]
            if len(linha_pontos) >= 2:
                linhas = [linha_pontos]

        trechos[nome_trecho] = {
            "id": registro.get("id"),
            "nome": nome_trecho,
            "total_pontos_informado": inteiro_seguro(registro.get("total_pontos"), 0),
            "total_pontos": len(pontos),
            "pontos": pontos,
            "linhas": linhas,
            "srid": registro.get("srid"),
            "extensao_metros": extensao_metros or Decimal("0"),
            "extensao_km": (
                extensao_metros / Decimal("1000")
                if extensao_metros is not None
                else Decimal("0")
            ),
        }

    return trechos


def valor_oficial_ou_geometria(dados, campo, trecho):
    oficial = decimal_seguro(dados.get(campo))
    if oficial is not None:
        return oficial
    return trecho.get("extensao_km", Decimal("0"))


def montar_turnos(dados, km_ida, km_volta):
    ativos = {texto_limpo(item).upper() for item in lista_textos(dados.get("turnos_ativos"))}
    horarios = json_seguro(dados.get("horarios"), {})
    if not isinstance(horarios, dict):
        horarios = {}

    turnos = []
    for nome in TURNOS_PADRAO:
        dados_horario = horarios.get(nome) or horarios.get(nome.lower()) or {}
        if not isinstance(dados_horario, dict):
            dados_horario = {}
        ativo = nome in ativos
        turnos.append({
            "nome": nome.title(),
            "chave": nome,
            "ativo": ativo,
            "km_ida": km_ida if ativo else None,
            "km_volta": km_volta if ativo else None,
            "km_total": km_ida + km_volta if ativo else None,
            "horario": texto_limpo(dados_horario.get("horario")),
            "inicio_aulas": texto_limpo(dados_horario.get("inicio_aulas")),
            "termino_aulas": texto_limpo(dados_horario.get("termino_aulas")),
        })

    total_geral = sum(
        (turno["km_total"] for turno in turnos if turno["ativo"]),
        Decimal("0"),
    )
    return turnos, total_geral


def montar_contexto(registros, dados, pontos_normalizados):
    primeiro = registros[0]
    codigo_rota = texto_limpo(primeiro.get("nome_rota"), "Rota sem código")
    regiao_bruta = texto_limpo(primeiro.get("regiao"))
    correspondencia = re.search(r"\d+", regiao_bruta)
    regiao = correspondencia.group(0).zfill(2) if correspondencia else (regiao_bruta or "Não informada")

    trechos = montar_trechos(registros, pontos_normalizados)
    vazio = {
        "nome": "", "pontos": [], "linhas": [],
        "extensao_km": Decimal("0"), "total_pontos": 0,
        "total_pontos_informado": 0,
    }
    ida = trechos.get("IDA", {**vazio, "nome": "IDA"})
    volta = trechos.get("VOLTA", {**vazio, "nome": "VOLTA"})

    perdidos = [
        trecho["nome"]
        for trecho in (ida, volta)
        if trecho.get("total_pontos_informado", 0) > 0 and not trecho.get("pontos")
    ]
    if perdidos:
        abort(
            422,
            description=(
                "Os pontos notáveis não estão disponíveis para: "
                + ", ".join(perdidos)
                + ". Importe semed.rotas_pontos_notaveis antes de gerar o memorial."
            ),
        )

    km_ida = valor_oficial_ou_geometria(dados, "km_ida", ida)
    km_volta = valor_oficial_ou_geometria(dados, "km_volta", volta)
    turnos, total_geral = montar_turnos(dados, km_ida, km_volta)

    tipo_veiculo = texto_limpo(dados.get("tipo_veiculo")).upper()

    redes_ensino_ativas = {
        texto_limpo(item).upper()
        for item in lista_textos(dados.get("redes_ensino"))
        if texto_limpo(item)
    }

    # Compatibilidade com registros antigos que ainda possuem somente
    # a coluna singular rede_ensino.
    rede_ensino_legada = texto_limpo(
        dados.get("rede_ensino")
    ).upper()
    if rede_ensino_legada:
        redes_ensino_ativas.add(rede_ensino_legada)

    areas_ativas = {
        texto_limpo(item).upper()
        for item in lista_textos(dados.get("areas"))
    }
    escolas_detalhadas = unidades_assistidas_detalhadas(
        dados.get("escolas_atendidas")
    )
    escolas = [
        item["nome"]
        for item in escolas_detalhadas
    ]

    inicio_padrao = ida["pontos"][0]["referencia"] if ida["pontos"] else "Não informado"
    termino_padrao = ida["pontos"][-1]["referencia"] if ida["pontos"] else "Não informado"

    return {
        "codigo_rota": codigo_rota,
        "regiao": regiao,
        "numero_linha": texto_limpo(dados.get("numero_linha"), codigo_rota),
        "linha": texto_limpo(dados.get("linha"), codigo_rota),
        "km_ida": km_ida,
        "km_volta": km_volta,
        "turnos": turnos,
        "total_geral": total_geral,
        "tipo_veiculo": tipo_veiculo,
        "quantidade_veiculos": inteiro_seguro(dados.get("quantidade_veiculos"), 0),
        "onibus_pcd": booleano_seguro(dados.get("onibus_pcd")),
        "inicio": texto_limpo(dados.get("inicio"), inicio_padrao),
        "termino": texto_limpo(dados.get("termino"), termino_padrao),
        "rede_ensino": rede_ensino_legada,
        "redes_ensino_ativas": redes_ensino_ativas,
        "localizacao": texto_limpo(dados.get("localizacao"), "Lagarto"),
        "areas_ativas": areas_ativas,
        "intermunicipal": booleano_seguro(dados.get("intermunicipal")),
        "assistente_mobilidade": booleano_seguro(dados.get("assistente_mobilidade")),
        "assistente_nome": texto_limpo(dados.get("assistente_nome")),
        "veiculo_placa": texto_limpo(dados.get("veiculo_placa")),
        "motorista": texto_limpo(dados.get("motorista")),
        "contato": texto_limpo(dados.get("contato")),
        "escolas": escolas,
        "escolas_detalhadas": escolas_detalhadas,
        "escolas_mapa": [],
        "observacao": texto_limpo(dados.get("observacao")),
        "responsavel_tecnico": texto_limpo(dados.get("responsavel_tecnico")),
        "crea": texto_limpo(dados.get("crea")),
        "executora": texto_limpo(dados.get("executora"), "Topocart"),
        "ida": ida,
        "volta": volta,
        "tem_metadata": bool(dados),
    }


# ==========================================
# MAPA OSM
# ==========================================


def _fonte_pil(tamanho: int, negrito: bool = False):
    candidatos = [
        "DejaVuSans-Bold.ttf" if negrito else "DejaVuSans.ttf",
        str(Path("C:/Windows/Fonts") / ("arialbd.ttf" if negrito else "arial.ttf")),
    ]
    for caminho in candidatos:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _latlon_para_pixel_mundo(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, lat))
    escala = 256 * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * escala
    seno = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + seno) / (1 - seno)) / (4 * math.pi)) * escala
    return x, y


def _coletar_coordenadas_mapa(
    contexto: dict[str, Any],
) -> list[tuple[float, float]]:
    coordenadas: list[tuple[float, float]] = []

    for trecho in (contexto["ida"], contexto["volta"]):
        for linha in trecho.get("linhas") or []:
            coordenadas.extend(linha)

    for escola in contexto.get("escolas_mapa") or []:
        if escola.get("lat") is None or escola.get("lon") is None:
            continue
        coordenadas.append((
            float(escola["lon"]),
            float(escola["lat"]),
        ))

    inicio, final = _pontos_extremos_mapa(contexto)
    for ponto in (inicio, final):
        if ponto:
            coordenadas.append((ponto["lon"], ponto["lat"]))

    return coordenadas


def _bbox_com_margem(coordenadas: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    lons = [item[0] for item in coordenadas]
    lats = [item[1] for item in coordenadas]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    largura = max(max_lon - min_lon, 0.002)
    altura = max(max_lat - min_lat, 0.002)
    margem_lon = largura * 0.10
    margem_lat = altura * 0.10
    return (
        min_lon - margem_lon,
        min_lat - margem_lat,
        max_lon + margem_lon,
        max_lat + margem_lat,
    )


def _escolher_zoom(bbox, max_tiles: int = 20) -> int:
    min_lon, min_lat, max_lon, max_lat = bbox
    for zoom in range(17, 9, -1):
        x1, y2 = _latlon_para_pixel_mundo(min_lon, min_lat, zoom)
        x2, y1 = _latlon_para_pixel_mundo(max_lon, max_lat, zoom)
        tx1, tx2 = math.floor(min(x1, x2) / 256), math.floor(max(x1, x2) / 256)
        ty1, ty2 = math.floor(min(y1, y2) / 256), math.floor(max(y1, y2) / 256)
        quantidade = (tx2 - tx1 + 1) * (ty2 - ty1 + 1)
        if quantidade <= max_tiles:
            return zoom
    return 10


def _tile_osm(zoom: int, x: int, y: int, cache_dir: Path) -> PILImage.Image:
    cache = cache_dir / str(zoom) / str(x) / f"{y}.png"
    dias_cache = inteiro_seguro(current_app.config.get("OSM_TILE_CACHE_DAYS"), 7)
    validade = max(dias_cache, 7) * 86400

    if cache.exists() and time.time() - cache.stat().st_mtime < validade:
        try:
            return PILImage.open(cache).convert("RGB")
        except OSError:
            cache.unlink(missing_ok=True)

    url_modelo = current_app.config.get(
        "OSM_TILE_URL",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    )
    url = url_modelo.format(z=zoom, x=x, y=y)
    user_agent = current_app.config.get(
        "OSM_USER_AGENT",
        os.environ.get("OSM_USER_AGENT", "WebSIG-SEMED-Lagarto/1.0"),
    )
    timeout = float(current_app.config.get("OSM_TILE_TIMEOUT", 12))

    resposta = requests.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    resposta.raise_for_status()

    cache.parent.mkdir(parents=True, exist_ok=True)
    temporario = cache.with_suffix(".tmp")
    temporario.write_bytes(resposta.content)
    temporario.replace(cache)
    return PILImage.open(cache).convert("RGB")


def _tile_indisponivel() -> PILImage.Image:
    imagem = PILImage.new("RGB", (256, 256), "#ECEFF1")
    desenho = ImageDraw.Draw(imagem)
    desenho.line((0, 0, 256, 256), fill="#CFD8DC", width=2)
    desenho.line((0, 256, 256, 0), fill="#CFD8DC", width=2)
    desenho.text((20, 118), "OSM indisponível", fill="#607D8B", font=_fonte_pil(16))
    return imagem


def _cor_da_regiao(valor: Any) -> str:
    """Retorna no PDF a mesma cor usada pela região no mapa do WebSIG."""

    texto_regiao = unicodedata.normalize(
        "NFD",
        texto_limpo(valor),
    )

    texto_regiao = re.sub(
        r"[\u0300-\u036f]",
        "",
        texto_regiao,
    ).upper()

    if (
        "UNIVERSIT" in texto_regiao
        or "UNIVERSIDADE" in texto_regiao
    ):
        return CORES_REGIOES["universidade"]

    correspondencia = re.search(
        r"\d+",
        texto_regiao,
    )

    if not correspondencia:
        return COR_ROTA_PADRAO

    chave = str(
        int(correspondencia.group(0))
    )

    return CORES_REGIOES.get(
        chave,
        COR_ROTA_PADRAO,
    )


def _largura_texto_pil(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    fonte,
) -> int:
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    return caixa[2] - caixa[0]


def _quebrar_texto_pil(
    desenho: ImageDraw.ImageDraw,
    texto: str,
    fonte,
    largura_maxima: int,
    maximo_linhas: int = 3,
) -> list[str]:
    """Quebra o nome da linha sem deixar o texto sair da moldura."""

    palavras = texto_limpo(texto).split()
    if not palavras:
        return []

    linhas: list[str] = []
    linha_atual = ""

    for palavra in palavras:
        teste = f"{linha_atual} {palavra}".strip()

        if (
            not linha_atual
            or _largura_texto_pil(desenho, teste, fonte)
            <= largura_maxima
        ):
            linha_atual = teste
            continue

        linhas.append(linha_atual)
        linha_atual = palavra

    if linha_atual:
        linhas.append(linha_atual)

    if len(linhas) <= maximo_linhas:
        return linhas

    linhas = linhas[:maximo_linhas]
    ultima = linhas[-1]

    while (
        ultima
        and _largura_texto_pil(
            desenho,
            ultima.rstrip() + "...",
            fonte,
        ) > largura_maxima
    ):
        ultima = ultima[:-1]

    linhas[-1] = ultima.rstrip() + "..."
    return linhas


def _segmentos_tracejados(
    pixels: list[tuple[int, int]],
    tamanho_traco: float = 22,
    tamanho_espaco: float = 13,
) -> list[list[tuple[int, int]]]:
    """Converte uma polilinha em pequenos segmentos para desenho tracejado."""

    if len(pixels) < 2:
        return []

    segmentos: list[list[tuple[int, int]]] = []
    desenhando = True
    restante = tamanho_traco

    for indice in range(len(pixels) - 1):
        x1, y1 = pixels[indice]
        x2, y2 = pixels[indice + 1]
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        comprimento = math.hypot(dx, dy)

        if comprimento <= 0.001:
            continue

        ux = dx / comprimento
        uy = dy / comprimento
        percorrido = 0.0

        while percorrido < comprimento:
            passo = min(restante, comprimento - percorrido)
            inicio_x = x1 + ux * percorrido
            inicio_y = y1 + uy * percorrido
            fim_x = x1 + ux * (percorrido + passo)
            fim_y = y1 + uy * (percorrido + passo)

            if desenhando:
                segmentos.append([
                    (int(round(inicio_x)), int(round(inicio_y))),
                    (int(round(fim_x)), int(round(fim_y))),
                ])

            percorrido += passo
            restante -= passo

            if restante <= 0.001:
                desenhando = not desenhando
                restante = tamanho_traco if desenhando else tamanho_espaco

    return segmentos


def _desenhar_trajeto_regiao(
    desenho: ImageDraw.ImageDraw,
    pixels: list[tuple[int, int]],
    cor_regiao: str,
    *,
    tracejado: bool = False,
) -> None:
    """
    Desenha a rota com halo branco.

    A Ida usa linha contínua e a Volta usa linha tracejada, preservando a
    mesma cor regional em ambos os sentidos.
    """

    if len(pixels) < 2:
        return

    segmentos = (
        _segmentos_tracejados(pixels)
        if tracejado
        else [pixels]
    )

    for segmento in segmentos:
        desenho.line(
            segmento,
            fill=(35, 35, 35, 185),
            width=15,
            joint="curve",
        )
        desenho.line(
            segmento,
            fill=(255, 255, 255, 250),
            width=11,
            joint="curve",
        )
        desenho.line(
            segmento,
            fill=cor_regiao,
            width=7,
            joint="curve",
        )


def _caixas_sobrepostas(
    caixa_a: tuple[int, int, int, int],
    caixa_b: tuple[int, int, int, int],
    margem: int = 8,
) -> bool:
    """Retorna True quando duas etiquetas ocupam a mesma área do mapa."""

    a_esquerda, a_topo, a_direita, a_base = caixa_a
    b_esquerda, b_topo, b_direita, b_base = caixa_b

    return not (
        a_direita + margem < b_esquerda
        or b_direita + margem < a_esquerda
        or a_base + margem < b_topo
        or b_base + margem < a_topo
    )


def _limitar_valor(
    valor: float,
    minimo: float,
    maximo: float,
) -> float:
    return max(minimo, min(valor, maximo))


def _segmento_mais_proximo(
    x: float,
    y: float,
    linhas_pixels: list[list[tuple[int, int]]],
) -> tuple[float, float, float, float, float, float]:
    """
    Localiza o segmento da rota mais próximo do ponto notável.

    Retorna:
        ancora_x, ancora_y,
        tangente_x, tangente_y,
        normal_x, normal_y.
    """

    melhor_distancia = float("inf")
    melhor_resultado = (x, y, 1.0, 0.0, 0.0, -1.0)

    for linha in linhas_pixels:
        if len(linha) < 2:
            continue

        for indice in range(len(linha) - 1):
            x1, y1 = linha[indice]
            x2, y2 = linha[indice + 1]

            delta_x = float(x2 - x1)
            delta_y = float(y2 - y1)
            comprimento_quadrado = delta_x * delta_x + delta_y * delta_y

            if comprimento_quadrado <= 0.0001:
                continue

            fator = (
                (x - x1) * delta_x
                + (y - y1) * delta_y
            ) / comprimento_quadrado

            fator = _limitar_valor(fator, 0.0, 1.0)

            ancora_x = x1 + fator * delta_x
            ancora_y = y1 + fator * delta_y

            distancia_quadrada = (
                (x - ancora_x) ** 2
                + (y - ancora_y) ** 2
            )

            if distancia_quadrada >= melhor_distancia:
                continue

            comprimento = math.sqrt(comprimento_quadrado)
            tangente_x = delta_x / comprimento
            tangente_y = delta_y / comprimento
            normal_x = -tangente_y
            normal_y = tangente_x

            melhor_distancia = distancia_quadrada
            melhor_resultado = (
                ancora_x,
                ancora_y,
                tangente_x,
                tangente_y,
                normal_x,
                normal_y,
            )

    return melhor_resultado


def _ponto_na_borda_da_caixa(
    origem_x: float,
    origem_y: float,
    destino_x: float,
    destino_y: float,
    caixa: tuple[int, int, int, int],
) -> tuple[float, float]:
    """Calcula onde a linha de chamada encontra a borda da etiqueta."""

    esquerda, topo, direita, base = caixa
    delta_x = destino_x - origem_x
    delta_y = destino_y - origem_y

    if abs(delta_x) < 0.0001 and abs(delta_y) < 0.0001:
        return destino_x, destino_y

    candidatos: list[tuple[float, float, float]] = []

    if abs(delta_x) >= 0.0001:
        for borda_x in (esquerda, direita):
            fator = (borda_x - origem_x) / delta_x
            y_intersecao = origem_y + fator * delta_y
            if fator >= 0 and topo <= y_intersecao <= base:
                candidatos.append((fator, float(borda_x), y_intersecao))

    if abs(delta_y) >= 0.0001:
        for borda_y in (topo, base):
            fator = (borda_y - origem_y) / delta_y
            x_intersecao = origem_x + fator * delta_x
            if fator >= 0 and esquerda <= x_intersecao <= direita:
                candidatos.append((fator, x_intersecao, float(borda_y)))

    if not candidatos:
        return destino_x, destino_y

    _, ponto_x, ponto_y = min(candidatos, key=lambda item: item[0])
    return ponto_x, ponto_y


def _desenhar_ponto_deslocado(
    desenho: ImageDraw.ImageDraw,
    *,
    x: float,
    y: float,
    numero: str,
    indice_global: int,
    linhas_pixels: list[list[tuple[int, int]]],
    fonte_numero,
    cor_regiao: str,
    caixas_ocupadas: list[tuple[int, int, int, int]],
    limites: tuple[int, int, int, int],
) -> None:
    """
    Marca o ponto na rota com um traço perpendicular e posiciona o número
    fora da linha, ligado por uma chamada. As posições são testadas até
    encontrar uma área livre de outras etiquetas.
    """

    limite_esquerdo, limite_superior, limite_direito, limite_inferior = limites

    (
        ancora_x,
        ancora_y,
        tangente_x,
        tangente_y,
        normal_x,
        normal_y,
    ) = _segmento_mais_proximo(
        x,
        y,
        linhas_pixels,
    )

    caixa_texto = desenho.textbbox(
        (0, 0),
        numero,
        font=fonte_numero,
    )
    largura_texto = caixa_texto[2] - caixa_texto[0]
    altura_texto = caixa_texto[3] - caixa_texto[1]

    largura_etiqueta = max(34, largura_texto + 18)
    altura_etiqueta = max(28, altura_texto + 12)

    lado_inicial = 1 if indice_global % 2 == 0 else -1
    distancias_normais = (44, 58, 74, 92, 112)
    deslocamentos_tangenciais = (0, 24, -24, 48, -48, 72, -72)

    candidatos: list[tuple[int, int, int, int]] = []

    for lado in (lado_inicial, -lado_inicial):
        for distancia in distancias_normais:
            for deslocamento in deslocamentos_tangenciais:
                centro_x = (
                    ancora_x
                    + normal_x * distancia * lado
                    + tangente_x * deslocamento
                )
                centro_y = (
                    ancora_y
                    + normal_y * distancia * lado
                    + tangente_y * deslocamento
                )

                centro_x = _limitar_valor(
                    centro_x,
                    limite_esquerdo + largura_etiqueta / 2,
                    limite_direito - largura_etiqueta / 2,
                )
                centro_y = _limitar_valor(
                    centro_y,
                    limite_superior + altura_etiqueta / 2,
                    limite_inferior - altura_etiqueta / 2,
                )

                esquerda = int(round(centro_x - largura_etiqueta / 2))
                topo = int(round(centro_y - altura_etiqueta / 2))
                direita = esquerda + largura_etiqueta
                base = topo + altura_etiqueta

                candidatos.append((esquerda, topo, direita, base))

    caixa_escolhida = candidatos[0]

    for candidato in candidatos:
        colisao = any(
            _caixas_sobrepostas(candidato, existente, margem=8)
            for existente in caixas_ocupadas
        )
        if not colisao:
            caixa_escolhida = candidato
            break

    caixas_ocupadas.append(caixa_escolhida)

    esquerda, topo, direita, base = caixa_escolhida
    centro_etiqueta_x = (esquerda + direita) / 2
    centro_etiqueta_y = (topo + base) / 2

    chegada_x, chegada_y = _ponto_na_borda_da_caixa(
        ancora_x,
        ancora_y,
        centro_etiqueta_x,
        centro_etiqueta_y,
        caixa_escolhida,
    )

    vetor_chamada_x = centro_etiqueta_x - ancora_x
    vetor_chamada_y = centro_etiqueta_y - ancora_y
    comprimento_chamada = math.hypot(vetor_chamada_x, vetor_chamada_y)

    if comprimento_chamada > 0.001:
        unidade_x = vetor_chamada_x / comprimento_chamada
        unidade_y = vetor_chamada_y / comprimento_chamada
    else:
        unidade_x, unidade_y = normal_x, normal_y

    joelho_x = ancora_x + unidade_x * 24
    joelho_y = ancora_y + unidade_y * 24

    pontos_chamada = [
        (int(round(ancora_x)), int(round(ancora_y))),
        (int(round(joelho_x)), int(round(joelho_y))),
        (int(round(chegada_x)), int(round(chegada_y))),
    ]

    # Halo branco para a chamada continuar legível sobre o OSM.
    desenho.line(
        pontos_chamada,
        fill=(255, 255, 255, 245),
        width=7,
        joint="curve",
    )
    desenho.line(
        pontos_chamada,
        fill=cor_regiao,
        width=3,
        joint="curve",
    )

    # Traço perpendicular no local exato em que o ponto toca a rota.
    metade_traco = 10
    traco = (
        int(round(ancora_x - normal_x * metade_traco)),
        int(round(ancora_y - normal_y * metade_traco)),
        int(round(ancora_x + normal_x * metade_traco)),
        int(round(ancora_y + normal_y * metade_traco)),
    )

    desenho.line(
        traco,
        fill=(255, 255, 255, 245),
        width=9,
    )
    desenho.line(
        traco,
        fill=(35, 35, 35, 230),
        width=6,
    )
    desenho.line(
        traco,
        fill=cor_regiao,
        width=3,
    )

    # Etiqueta externa com borda dupla para funcionar também no amarelo.
    desenho.rounded_rectangle(
        caixa_escolhida,
        radius=7,
        fill=(255, 255, 255, 245),
        outline=(35, 35, 35, 235),
        width=4,
    )
    desenho.rounded_rectangle(
        (
            esquerda + 3,
            topo + 3,
            direita - 3,
            base - 3,
        ),
        radius=5,
        outline=cor_regiao,
        width=3,
    )

    caixa_numero = desenho.textbbox(
        (0, 0),
        numero,
        font=fonte_numero,
    )
    texto_largura = caixa_numero[2] - caixa_numero[0]
    texto_altura = caixa_numero[3] - caixa_numero[1]

    texto_x = esquerda + (direita - esquerda - texto_largura) / 2
    texto_y = (
        topo
        + (base - topo - texto_altura) / 2
        - caixa_numero[1]
    )

    desenho.text(
        (int(round(texto_x)), int(round(texto_y))),
        numero,
        fill=(20, 20, 20, 255),
        font=fonte_numero,
    )


def _normalizar_fundo_osm(imagem: PILImage.Image) -> PILImage.Image:
    """Clareia e dessatura o OSM para a rota e os rótulos ganharem destaque."""

    imagem_rgb = imagem.convert("RGB")
    imagem_cinza = ImageOps.grayscale(imagem_rgb).convert("RGB")
    imagem_suave = PILImage.blend(
        imagem_rgb,
        imagem_cinza,
        0.72,
    )
    imagem_suave = ImageEnhance.Contrast(
        imagem_suave,
    ).enhance(0.78)
    imagem_suave = ImageEnhance.Brightness(
        imagem_suave,
    ).enhance(1.12)
    return imagem_suave


def _preparar_base_mapa(
    bbox: tuple[float, float, float, float],
    *,
    largura_final: int = MAPA_LARGURA_PX,
    altura_final: int = MAPA_ALTURA_PX,
    max_tiles: int | None = None,
) -> tuple[
    PILImage.Image,
    Any,
    int,
]:
    """Baixa os tiles, recorta a área e devolve mapa, conversor e falhas."""

    if max_tiles is None:
        max_tiles = inteiro_seguro(
            current_app.config.get("OSM_MAX_TILES"),
            20,
        )

    zoom = _escolher_zoom(
        bbox,
        max_tiles=max_tiles,
    )

    min_lon, min_lat, max_lon, max_lat = bbox
    wx1, wy2 = _latlon_para_pixel_mundo(min_lon, min_lat, zoom)
    wx2, wy1 = _latlon_para_pixel_mundo(max_lon, max_lat, zoom)
    esquerda, direita = min(wx1, wx2), max(wx1, wx2)
    topo, base = min(wy1, wy2), max(wy1, wy2)

    proporcao_destino = largura_final / altura_final
    largura_area = max(direita - esquerda, 1)
    altura_area = max(base - topo, 1)
    proporcao_atual = largura_area / altura_area

    if proporcao_atual > proporcao_destino:
        nova_altura = largura_area / proporcao_destino
        acrescimo = (nova_altura - altura_area) / 2
        topo -= acrescimo
        base += acrescimo
    else:
        nova_largura = altura_area * proporcao_destino
        acrescimo = (nova_largura - largura_area) / 2
        esquerda -= acrescimo
        direita += acrescimo

    tx1, tx2 = math.floor(esquerda / 256), math.floor(direita / 256)
    ty1, ty2 = math.floor(topo / 256), math.floor(base / 256)

    mosaico = PILImage.new(
        "RGB",
        (
            (tx2 - tx1 + 1) * 256,
            (ty2 - ty1 + 1) * 256,
        ),
        "white",
    )

    cache_dir = Path(current_app.instance_path) / "cache" / "osm_tiles"
    falhas = 0

    for tile_x in range(tx1, tx2 + 1):
        for tile_y in range(ty1, ty2 + 1):
            try:
                tile = _tile_osm(
                    zoom,
                    tile_x,
                    tile_y,
                    cache_dir,
                )
            except Exception:
                falhas += 1
                tile = _tile_indisponivel()

            mosaico.paste(
                tile,
                (
                    (tile_x - tx1) * 256,
                    (tile_y - ty1) * 256,
                ),
            )

    crop = (
        max(0, int(esquerda - tx1 * 256)),
        max(0, int(topo - ty1 * 256)),
        min(mosaico.width, int(direita - tx1 * 256)),
        min(mosaico.height, int(base - ty1 * 256)),
    )

    if crop[2] <= crop[0] or crop[3] <= crop[1]:
        base_mapa = mosaico
    else:
        base_mapa = mosaico.crop(crop)

    base_mapa = base_mapa.resize(
        (largura_final, altura_final),
        PILImage.Resampling.LANCZOS,
    )
    base_mapa = _normalizar_fundo_osm(base_mapa)

    largura_mundo = max(direita - esquerda, 1)
    altura_mundo = max(base - topo, 1)

    def converter(lon: float, lat: float) -> tuple[int, int]:
        x_mundo, y_mundo = _latlon_para_pixel_mundo(
            lon,
            lat,
            zoom,
        )
        x = int(
            (x_mundo - esquerda)
            / largura_mundo
            * largura_final
        )
        y = int(
            (y_mundo - topo)
            / altura_mundo
            * altura_final
        )
        return x, y

    return base_mapa, converter, falhas


def _coletar_pontos_mapa(contexto) -> list[dict[str, Any]]:
    """Reúne Ida e Volta com rótulos I/V e índice global estável."""

    pontos_mapa: list[dict[str, Any]] = []
    indice_global = 0

    for trecho in (contexto["ida"], contexto["volta"]):
        nome_trecho = texto_limpo(
            trecho.get("nome"),
            "OUTRO",
        ).upper()
        prefixo = (
            "I"
            if nome_trecho == "IDA"
            else "V"
            if nome_trecho == "VOLTA"
            else "P"
        )

        pontos_validos = [
            ponto
            for ponto in trecho.get("pontos") or []
            if ponto.get("lat") is not None
            and ponto.get("lon") is not None
        ]

        for indice_trecho, ponto in enumerate(pontos_validos):
            ordem = inteiro_seguro(
                ponto.get("ordem"),
                indice_trecho + 1,
            )
            pontos_mapa.append({
                "ponto": ponto,
                "trecho": nome_trecho,
                "prefixo": prefixo,
                "rotulo": f"{prefixo}{ordem}",
                "ordem": ordem,
                "indice_trecho": indice_trecho,
                "total_trecho": len(pontos_validos),
                "indice_global": indice_global,
                "lon": float(ponto["lon"]),
                "lat": float(ponto["lat"]),
            })
            indice_global += 1

    return pontos_mapa


def _ponto_referencia_importante(item: dict[str, Any]) -> bool:
    referencia = texto_limpo(
        item["ponto"].get("referencia"),
    ).upper()

    palavras_chave = (
        "ESCOLA",
        "COLÉGIO",
        "COLEGIO",
        "U.M.E.I",
        "UMEI",
        "UNIVERSIDADE",
        "CAMPUS",
        "CRECHE",
        "CENTRO DE EXCELÊNCIA",
        "CENTRO DE EXCELENCIA",
    )
    return any(
        palavra in referencia
        for palavra in palavras_chave
    )


def _ponto_deve_ter_rotulo_geral(item: dict[str, Any]) -> bool:
    """Rótula início, fim, escolas e cada quinto ponto no mapa geral."""

    if item["indice_trecho"] in {
        0,
        item["total_trecho"] - 1,
    }:
        return True

    if item["ordem"] % MAPA_INTERVALO_ROTULO_GERAL == 0:
        return True

    return _ponto_referencia_importante(item)


def _desenhar_marca_simples(
    desenho: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    cor_regiao: str,
) -> None:
    """Marca discreta para pontos que não recebem número no mapa geral."""

    desenho.ellipse(
        (x - 5, y - 5, x + 5, y + 5),
        fill=(255, 255, 255, 245),
        outline=(35, 35, 35, 220),
        width=2,
    )
    desenho.ellipse(
        (x - 2, y - 2, x + 2, y + 2),
        fill=cor_regiao,
    )


def _distancia_geografica_quadrada(
    ponto: dict[str, Any],
    centro: tuple[float, float],
    latitude_media: float,
) -> float:
    fator_lon = math.cos(math.radians(latitude_media))
    dx = (ponto["lon"] - centro[0]) * fator_lon
    dy = ponto["lat"] - centro[1]
    return dx * dx + dy * dy


def _agrupar_pontos_detalhe(
    pontos: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """
    Agrupa pontos por proximidade geográfica usando k-means determinístico.

    Grupos muito grandes são divididos pela ordem do itinerário para impedir
    páginas excessivamente congestionadas.
    """

    if len(pontos) < MAPA_MIN_PONTOS_PARA_DETALHES:
        return []

    quantidade_grupos = min(
        MAPA_MAX_GRUPOS_DETALHE,
        max(
            1,
            math.ceil(
                len(pontos)
                / MAPA_MAX_PONTOS_POR_DETALHE
            ),
        ),
    )

    latitude_media = sum(
        item["lat"] for item in pontos
    ) / len(pontos)

    # Inicialização farthest-first, estável e sem dependências externas.
    primeiro = min(
        pontos,
        key=lambda item: (
            item["lon"],
            item["lat"],
            item["indice_global"],
        ),
    )
    centros = [(primeiro["lon"], primeiro["lat"])]

    while len(centros) < quantidade_grupos:
        candidato = max(
            pontos,
            key=lambda item: min(
                _distancia_geografica_quadrada(
                    item,
                    centro,
                    latitude_media,
                )
                for centro in centros
            ),
        )
        novo_centro = (
            candidato["lon"],
            candidato["lat"],
        )
        if novo_centro in centros:
            break
        centros.append(novo_centro)

    for _ in range(20):
        grupos = [[] for _ in centros]

        for ponto in pontos:
            indice_centro = min(
                range(len(centros)),
                key=lambda indice: _distancia_geografica_quadrada(
                    ponto,
                    centros[indice],
                    latitude_media,
                ),
            )
            grupos[indice_centro].append(ponto)

        novos_centros: list[tuple[float, float]] = []
        for indice, grupo in enumerate(grupos):
            if not grupo:
                novos_centros.append(centros[indice])
                continue
            novos_centros.append((
                sum(item["lon"] for item in grupo) / len(grupo),
                sum(item["lat"] for item in grupo) / len(grupo),
            ))

        deslocamento = sum(
            (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            for a, b in zip(centros, novos_centros)
        )
        centros = novos_centros
        if deslocamento < 1e-14:
            break

    grupos_finais: list[list[dict[str, Any]]] = []

    for grupo in grupos:
        grupo.sort(key=lambda item: item["indice_global"])

        if len(grupo) <= MAPA_MAX_PONTOS_POR_DETALHE:
            if grupo:
                grupos_finais.append(grupo)
            continue

        for inicio in range(
            0,
            len(grupo),
            MAPA_MAX_PONTOS_POR_DETALHE,
        ):
            grupos_finais.append(
                grupo[
                    inicio:
                    inicio + MAPA_MAX_PONTOS_POR_DETALHE
                ]
            )

    grupos_finais.sort(
        key=lambda grupo: min(
            item["indice_global"]
            for item in grupo
        )
    )

    return grupos_finais


def _bbox_pontos_detalhe(
    grupo: list[dict[str, Any]],
) -> tuple[float, float, float, float]:
    coordenadas = [
        (item["lon"], item["lat"])
        for item in grupo
    ]
    min_lon, min_lat, max_lon, max_lat = _bbox_com_margem(
        coordenadas,
    )

    # Detalhes ganham margem adicional para linhas de chamada.
    largura = max(max_lon - min_lon, 0.0015)
    altura = max(max_lat - min_lat, 0.0015)
    return (
        min_lon - largura * 0.15,
        min_lat - altura * 0.15,
        max_lon + largura * 0.15,
        max_lat + altura * 0.15,
    )


def _desenhar_titulo_mapa(
    desenho: ImageDraw.ImageDraw,
    contexto: dict[str, Any],
    cor_regiao: str,
    *,
    subtitulo: str = "",
) -> int:
    """Desenha o título somente sobre a área cartográfica."""

    margem_titulo_x = MAPA_MARGEM_PX
    largura_texto_titulo = MAPA_AREA_LARGURA_PX - 145
    fonte_codigo = _fonte_pil(30, negrito=True)
    fonte_descricao = _fonte_pil(23, negrito=True)
    fonte_subtitulo = _fonte_pil(18, negrito=True)

    codigo_rota = texto_limpo(
        contexto.get("codigo_rota"),
        "Rota sem código",
    )
    descricao_rota = texto_limpo(
        contexto.get("linha"),
        codigo_rota,
    )

    linhas_descricao = _quebrar_texto_pil(
        desenho,
        descricao_rota,
        fonte_descricao,
        largura_texto_titulo,
        maximo_linhas=2,
    )

    altura_linha = 29
    altura_subtitulo = 27 if subtitulo else 0
    altura_titulo = 56 + max(1, len(linhas_descricao)) * altura_linha + altura_subtitulo
    topo_titulo = 18
    base_titulo = topo_titulo + altura_titulo

    desenho.rounded_rectangle(
        (
            margem_titulo_x,
            topo_titulo,
            MAPA_AREA_LARGURA_PX - margem_titulo_x,
            base_titulo,
        ),
        radius=16,
        fill=(255, 255, 255, 238),
        outline=cor_regiao,
        width=5,
    )
    desenho.rounded_rectangle(
        (
            margem_titulo_x + 10,
            topo_titulo + 12,
            margem_titulo_x + 24,
            base_titulo - 12,
        ),
        radius=7,
        fill=cor_regiao,
    )

    x_texto = margem_titulo_x + 42
    desenho.text(
        (x_texto, topo_titulo + 10),
        codigo_rota,
        fill="#173D68",
        font=fonte_codigo,
    )

    y_descricao = topo_titulo + 49
    for linha_texto in linhas_descricao:
        desenho.text(
            (x_texto, y_descricao),
            linha_texto,
            fill="#263238",
            font=fonte_descricao,
        )
        y_descricao += altura_linha

    if subtitulo:
        desenho.text(
            (x_texto, y_descricao + 1),
            subtitulo,
            fill="#455A64",
            font=fonte_subtitulo,
        )

    return base_titulo


def _desenhar_seta_norte(
    desenho: ImageDraw.ImageDraw,
    *,
    centro_x: int,
    topo: int,
) -> None:
    """Desenha uma seta norte simples e legível."""

    fonte_norte = _fonte_pil(31, negrito=True)
    desenho.text(
        (centro_x - 11, topo),
        "N",
        fill="#173D68",
        font=fonte_norte,
    )

    ponta_y = topo + 43
    base_y = topo + 137

    desenho.polygon(
        [
            (centro_x, ponta_y),
            (centro_x - 27, base_y),
            (centro_x, base_y - 20),
            (centro_x + 27, base_y),
        ],
        fill=(23, 61, 104, 245),
        outline=(20, 20, 20, 220),
    )
    desenho.line(
        (centro_x, ponta_y + 8, centro_x, base_y + 18),
        fill=(23, 61, 104, 245),
        width=7,
    )


def _desenhar_amostra_marcador(
    desenho: ImageDraw.ImageDraw,
    *,
    centro_x: int,
    centro_y: int,
    texto: str,
    cor: str,
    raio: int = 15,
) -> None:
    desenho.ellipse(
        (
            centro_x - raio - 3,
            centro_y - raio - 3,
            centro_x + raio + 3,
            centro_y + raio + 3,
        ),
        fill=(255, 255, 255, 250),
        outline=(30, 30, 30, 230),
        width=3,
    )
    desenho.ellipse(
        (
            centro_x - raio,
            centro_y - raio,
            centro_x + raio,
            centro_y + raio,
        ),
        fill=cor,
        outline=(255, 255, 255, 245),
        width=2,
    )
    fonte = _fonte_pil(17, negrito=True)
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    desenho.text(
        (
            centro_x - (caixa[2] - caixa[0]) / 2,
            centro_y - (caixa[3] - caixa[1]) / 2 - caixa[1],
        ),
        texto,
        fill="#FFFFFF",
        font=fonte,
    )


def _desenhar_legenda_mapa(
    desenho: ImageDraw.ImageDraw,
    contexto: dict[str, Any],
    cor_regiao: str,
    *,
    modo_detalhe: bool = False,
) -> int:
    """Desenha legenda, seta norte e escolas na faixa direita."""

    painel_x = MAPA_AREA_LARGURA_PX + 16
    painel_direita = MAPA_LARGURA_PX - 16
    painel_topo = 16
    painel_base = MAPA_ALTURA_PX - 16

    desenho.rounded_rectangle(
        (
            painel_x,
            painel_topo,
            painel_direita,
            painel_base,
        ),
        radius=18,
        fill=(250, 250, 250, 250),
        outline=(70, 70, 70, 210),
        width=3,
    )

    fonte_titulo = _fonte_pil(25, negrito=True)
    desenho.text(
        (painel_x + 20, painel_topo + 18),
        "LEGENDA",
        fill="#173D68",
        font=fonte_titulo,
    )

    _desenhar_seta_norte(
        desenho,
        centro_x=painel_direita - 78,
        topo=painel_topo + 8,
    )

    y = painel_topo + 88
    fonte_item = _fonte_pil(17)
    fonte_secao = _fonte_pil(18, negrito=True)

    desenho.text(
        (painel_x + 20, y),
        "Trajeto",
        fill="#263238",
        font=fonte_secao,
    )
    y += 37

    _desenhar_trajeto_regiao(
        desenho,
        [(painel_x + 24, y + 10), (painel_x + 105, y + 10)],
        cor_regiao,
        tracejado=False,
    )
    desenho.text(
        (painel_x + 124, y - 3),
        "Ida",
        fill="#111111",
        font=fonte_item,
    )
    y += 39

    _desenhar_trajeto_regiao(
        desenho,
        [(painel_x + 24, y + 10), (painel_x + 105, y + 10)],
        cor_regiao,
        tracejado=True,
    )
    desenho.text(
        (painel_x + 124, y - 3),
        "Volta",
        fill="#111111",
        font=fonte_item,
    )
    y += 51

    desenho.text(
        (painel_x + 20, y),
        "Extremos da rota",
        fill="#263238",
        font=fonte_secao,
    )
    y += 43

    _desenhar_amostra_marcador(
        desenho,
        centro_x=painel_x + 42,
        centro_y=y,
        texto="I",
        cor="#2E7D32",
    )
    desenho.text(
        (painel_x + 70, y - 12),
        "Ponto inicial",
        fill="#111111",
        font=fonte_item,
    )
    y += 43

    _desenhar_amostra_marcador(
        desenho,
        centro_x=painel_x + 42,
        centro_y=y,
        texto="F",
        cor="#C62828",
    )
    desenho.text(
        (painel_x + 70, y - 12),
        "Ponto final",
        fill="#111111",
        font=fonte_item,
    )
    y += 53

    desenho.line(
        (painel_x + 18, y, painel_direita - 18, y),
        fill=(150, 150, 150, 190),
        width=2,
    )
    y += 16

    escolas = contexto.get("escolas_mapa") or []
    desenho.text(
        (painel_x + 20, y),
        "Unidades de ensino atendidas",
        fill="#263238",
        font=fonte_secao,
    )
    y += 38

    altura_disponivel = painel_base - y - 18

    if not escolas:
        desenho.text(
            (painel_x + 20, y),
            "Nenhuma unidade informada.",
            fill="#666666",
            font=_fonte_pil(15),
        )
        return painel_x

    quantidade = len(escolas)
    colunas = 2 if quantidade > 14 else 1
    linhas_por_coluna = math.ceil(quantidade / colunas)
    largura_util = painel_direita - painel_x - 34
    largura_coluna = largura_util / colunas
    altura_item = min(
        46,
        max(
            20,
            int(altura_disponivel / max(linhas_por_coluna, 1)),
        ),
    )

    if quantidade <= 8:
        fonte_escola_tamanho = 17
    elif quantidade <= 14:
        fonte_escola_tamanho = 14
    elif quantidade <= 24:
        fonte_escola_tamanho = 12
    else:
        fonte_escola_tamanho = 10

    fonte_escola = _fonte_pil(fonte_escola_tamanho)
    raio_legenda = 13 if quantidade <= 14 else 10

    for indice, escola in enumerate(escolas):
        coluna = indice // linhas_por_coluna
        linha = indice % linhas_por_coluna
        x_coluna = painel_x + 18 + coluna * largura_coluna
        y_item = y + linha * altura_item

        numero = str(escola.get("numero", ""))
        possui_coordenada = (
            escola.get("lat") is not None
            and escola.get("lon") is not None
        )
        cor_numero = cor_regiao if possui_coordenada else "#9E9E9E"

        _desenhar_amostra_marcador(
            desenho,
            centro_x=int(x_coluna + raio_legenda + 2),
            centro_y=int(y_item + raio_legenda + 2),
            texto=numero,
            cor=cor_numero,
            raio=raio_legenda,
        )

        nome = texto_limpo(escola.get("nome"), "Unidade sem nome")
        if not possui_coordenada:
            nome += " (sem coordenada)"

        largura_nome = int(
            largura_coluna - 2 * raio_legenda - 22
        )
        max_linhas = 2 if colunas == 1 and altura_item >= 36 else 1
        linhas = _quebrar_texto_pil(
            desenho,
            nome,
            fonte_escola,
            largura_nome,
            maximo_linhas=max_linhas,
        )

        texto_y = y_item
        for linha_texto in linhas:
            desenho.text(
                (
                    int(x_coluna + 2 * raio_legenda + 12),
                    int(texto_y),
                ),
                linha_texto,
                fill="#111111",
                font=fonte_escola,
            )
            texto_y += fonte_escola_tamanho + 3

    return painel_x


def _desenhar_atribuicao(
    desenho: ImageDraw.ImageDraw,
    falhas: int,
) -> None:
    atribuicao = (
        "© OpenStreetMap contributors - "
        "https://www.openstreetmap.org/copyright"
    )
    if falhas:
        atribuicao += f" | {falhas} tile(s) indisponível(is)"

    fonte_atribuicao = _fonte_pil(14)
    caixa = desenho.textbbox(
        (0, 0),
        atribuicao,
        font=fonte_atribuicao,
    )
    largura_texto = caixa[2] - caixa[0]

    desenho.rectangle(
        (
            MAPA_AREA_LARGURA_PX - largura_texto - 34,
            MAPA_ALTURA_PX - 28,
            MAPA_AREA_LARGURA_PX - 12,
            MAPA_ALTURA_PX - 4,
        ),
        fill=(255, 255, 255, 225),
    )
    desenho.text(
        (
            MAPA_AREA_LARGURA_PX - largura_texto - 26,
            MAPA_ALTURA_PX - 26,
        ),
        atribuicao,
        fill="#222222",
        font=fonte_atribuicao,
    )


def _linhas_pixels_contexto(
    contexto: dict[str, Any],
    converter,
    desenho: ImageDraw.ImageDraw,
    cor_regiao: str,
) -> list[list[tuple[int, int]]]:
    linhas_pixels: list[list[tuple[int, int]]] = []

    for trecho in (contexto["ida"], contexto["volta"]):
        tracejado = texto_limpo(
            trecho.get("nome"),
        ).upper() == "VOLTA"

        for linha in trecho.get("linhas") or []:
            pixels = [
                converter(lon, lat)
                for lon, lat in linha
            ]
            if len(pixels) < 2:
                continue

            linhas_pixels.append(pixels)
            _desenhar_trajeto_regiao(
                desenho,
                pixels,
                cor_regiao,
                tracejado=tracejado,
            )

    return linhas_pixels


def _pontos_extremos_mapa(
    contexto: dict[str, Any],
) -> tuple[dict[str, float] | None, dict[str, float] | None]:
    """Retorna o primeiro e o último ponto do itinerário principal."""

    for trecho in (contexto["ida"], contexto["volta"]):
        pontos = [
            ponto
            for ponto in trecho.get("pontos") or []
            if ponto.get("lat") is not None
            and ponto.get("lon") is not None
        ]

        if pontos:
            return (
                {
                    "lat": float(pontos[0]["lat"]),
                    "lon": float(pontos[0]["lon"]),
                },
                {
                    "lat": float(pontos[-1]["lat"]),
                    "lon": float(pontos[-1]["lon"]),
                },
            )

    linhas = [
        linha
        for trecho in (contexto["ida"], contexto["volta"])
        for linha in (trecho.get("linhas") or [])
        if len(linha) >= 2
    ]

    if linhas:
        primeira = linhas[0][0]
        ultima = linhas[-1][-1]
        return (
            {"lon": float(primeira[0]), "lat": float(primeira[1])},
            {"lon": float(ultima[0]), "lat": float(ultima[1])},
        )

    return None, None


def _desenhar_marcador_mapa(
    desenho: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    texto: str,
    cor: str,
    raio: int = 19,
) -> None:
    desenho.ellipse(
        (
            x - raio - 4,
            y - raio - 4,
            x + raio + 4,
            y + raio + 4,
        ),
        fill=(255, 255, 255, 250),
        outline=(25, 25, 25, 230),
        width=4,
    )
    desenho.ellipse(
        (
            x - raio,
            y - raio,
            x + raio,
            y + raio,
        ),
        fill=cor,
        outline=(255, 255, 255, 245),
        width=2,
    )

    fonte = _fonte_pil(19 if len(texto) <= 2 else 16, negrito=True)
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    desenho.text(
        (
            x - (caixa[2] - caixa[0]) / 2,
            y - (caixa[3] - caixa[1]) / 2 - caixa[1],
        ),
        texto,
        fill="#FFFFFF",
        font=fonte,
    )


def _renderizar_mapa(
    contexto: dict[str, Any],
    *,
    bbox: tuple[float, float, float, float],
    pontos_exibidos: list[dict[str, Any]] | None = None,
    modo_detalhe: bool = False,
    subtitulo: str = "",
) -> io.BytesIO:
    """
    Renderiza uma página de mapa em paisagem.

    Quando ``pontos_exibidos`` é ``None``, o mapa contém somente:
      - trajeto;
      - ponto inicial;
      - ponto final;
      - unidades de ensino atendidas.

    Quando ``pontos_exibidos`` é informado, os pontos notáveis também
    são desenhados. No modo detalhado, todos recebem rótulo.
    """

    altura_area_cartografica = (
        MAPA_ALTURA_PX - MAPA_AREA_TOPO_PX
    )

    mapa_osm, converter_base, falhas = _preparar_base_mapa(
        bbox,
        largura_final=MAPA_AREA_LARGURA_PX,
        altura_final=altura_area_cartografica,
    )

    def converter(
        lon: float,
        lat: float,
    ) -> tuple[int, int]:
        x, y = converter_base(lon, lat)
        return x, y + MAPA_AREA_TOPO_PX

    base_mapa = PILImage.new(
        "RGB",
        (MAPA_LARGURA_PX, MAPA_ALTURA_PX),
        "#F4F5F6",
    )
    base_mapa.paste(
        mapa_osm,
        (0, MAPA_AREA_TOPO_PX),
    )

    desenho = ImageDraw.Draw(
        base_mapa,
        "RGBA",
    )

    desenho.line(
        (
            0,
            MAPA_AREA_TOPO_PX,
            MAPA_AREA_LARGURA_PX,
            MAPA_AREA_TOPO_PX,
        ),
        fill=(80, 80, 80, 180),
        width=2,
    )
    desenho.line(
        (
            MAPA_AREA_LARGURA_PX,
            0,
            MAPA_AREA_LARGURA_PX,
            MAPA_ALTURA_PX,
        ),
        fill=(80, 80, 80, 210),
        width=4,
    )

    cor_regiao = _cor_da_regiao(
        contexto.get("regiao")
    )

    linhas_pixels = _linhas_pixels_contexto(
        contexto,
        converter,
        desenho,
        cor_regiao,
    )

    base_titulo = _desenhar_titulo_mapa(
        desenho,
        contexto,
        cor_regiao,
        subtitulo=subtitulo,
    )

    # As escolas permanecem visíveis em todos os mapas.
    for escola in contexto.get("escolas_mapa") or []:
        if (
            escola.get("lat") is None
            or escola.get("lon") is None
        ):
            continue

        x, y = converter(
            float(escola["lon"]),
            float(escola["lat"]),
        )

        _desenhar_marcador_mapa(
            desenho,
            x=x,
            y=y,
            texto=str(
                escola.get("numero", "")
            ),
            cor=cor_regiao,
            raio=18,
        )

    # A primeira página não recebe pontos notáveis.
    if pontos_exibidos:
        limites_rotulos = (
            20,
            max(
                MAPA_AREA_TOPO_PX + 12,
                base_titulo + 14,
            ),
            MAPA_AREA_LARGURA_PX - 20,
            MAPA_ALTURA_PX - 38,
        )

        fonte_numero = _fonte_pil(
            15 if modo_detalhe else 14,
            negrito=True,
        )
        caixas_rotulos: list[
            tuple[int, int, int, int]
        ] = []

        rotular_todos_no_geral = (
            len(pontos_exibidos)
            <= MAPA_MAX_PONTOS_POR_DETALHE
        )

        for item in pontos_exibidos:
            x, y = converter(
                float(item["lon"]),
                float(item["lat"]),
            )

            deve_rotular = (
                modo_detalhe
                or rotular_todos_no_geral
                or _ponto_deve_ter_rotulo_geral(
                    item
                )
            )

            if deve_rotular:
                _desenhar_ponto_deslocado(
                    desenho,
                    x=x,
                    y=y,
                    numero=item["rotulo"],
                    indice_global=item[
                        "indice_global"
                    ],
                    linhas_pixels=linhas_pixels,
                    fonte_numero=fonte_numero,
                    cor_regiao=cor_regiao,
                    caixas_ocupadas=caixas_rotulos,
                    limites=limites_rotulos,
                )
            else:
                _desenhar_marca_simples(
                    desenho,
                    x=x,
                    y=y,
                    cor_regiao=cor_regiao,
                )

    inicio_rota, final_rota = (
        _pontos_extremos_mapa(contexto)
    )

    inicio_x = None
    inicio_y = None

    if inicio_rota:
        inicio_x, inicio_y = converter(
            inicio_rota["lon"],
            inicio_rota["lat"],
        )

        _desenhar_marcador_mapa(
            desenho,
            x=inicio_x,
            y=inicio_y,
            texto="I",
            cor="#2E7D32",
            raio=21,
        )

    if final_rota:
        final_x, final_y = converter(
            final_rota["lon"],
            final_rota["lat"],
        )

        if (
            inicio_x is not None
            and inicio_y is not None
            and math.hypot(
                final_x - inicio_x,
                final_y - inicio_y,
            ) < 12
        ):
            final_x += 34

        _desenhar_marcador_mapa(
            desenho,
            x=final_x,
            y=final_y,
            texto="F",
            cor="#C62828",
            raio=21,
        )

    _desenhar_legenda_mapa(
        desenho,
        contexto,
        cor_regiao,
        modo_detalhe=modo_detalhe,
    )

    _desenhar_atribuicao(
        desenho,
        falhas,
    )

    buffer = io.BytesIO()
    base_mapa.save(
        buffer,
        format="PNG",
        optimize=True,
    )
    buffer.seek(0)
    return buffer


def gerar_imagem_mapa(
    contexto: dict[str, Any],
) -> io.BytesIO:
    """
    Primeira página: mapa somente com as unidades atendidas.

    O mapa também mantém o trajeto, o ponto inicial e o ponto final,
    mas não exibe os demais pontos notáveis.
    """

    coordenadas = _coletar_coordenadas_mapa(
        contexto
    )

    if not coordenadas:
        raise RuntimeError(
            (
                "A rota não possui coordenadas "
                "válidas para gerar o mapa."
            )
        )

    return _renderizar_mapa(
        contexto,
        bbox=_bbox_com_margem(
            coordenadas
        ),
        pontos_exibidos=None,
        modo_detalhe=False,
        subtitulo=(
            "Unidades de ensino atendidas"
        ),
    )


def gerar_imagem_mapa_geral_detalhado(
    contexto: dict[str, Any],
) -> io.BytesIO:
    """
    Segunda página: mapa geral com os pontos notáveis.

    Em rotas extensas, apenas os principais pontos recebem rótulo;
    todos os demais continuam marcados e aparecem numerados nos
    recortes detalhados seguintes.
    """

    pontos_mapa = _coletar_pontos_mapa(
        contexto
    )
    coordenadas = _coletar_coordenadas_mapa(
        contexto
    )

    coordenadas.extend(
        (
            float(item["lon"]),
            float(item["lat"]),
        )
        for item in pontos_mapa
    )

    if not coordenadas:
        raise RuntimeError(
            (
                "A rota não possui coordenadas "
                "válidas para gerar o mapa detalhado."
            )
        )

    return _renderizar_mapa(
        contexto,
        bbox=_bbox_com_margem(
            coordenadas
        ),
        pontos_exibidos=pontos_mapa,
        modo_detalhe=False,
        subtitulo=(
            "Mapa geral com pontos notáveis"
        ),
    )


def gerar_imagens_mapas_detalhados(
    contexto: dict[str, Any],
) -> list[tuple[str, io.BytesIO]]:
    """
    Terceira até a enésima página:
    recortes aproximados com todos os pontos numerados.
    """

    pontos_mapa = _coletar_pontos_mapa(
        contexto
    )

    if not pontos_mapa:
        return []

    grupos = _agrupar_pontos_detalhe(
        pontos_mapa
    )
    resultados: list[
        tuple[str, io.BytesIO]
    ] = []

    total_grupos = len(grupos)

    for indice, grupo in enumerate(
        grupos,
        start=1,
    ):
        if not grupo:
            continue

        rotulos = [
            item["rotulo"]
            for item in grupo
        ]

        primeiro = rotulos[0]
        ultimo = rotulos[-1]

        titulo = (
            f"DETALHE {indice}/{total_grupos} — "
            f"PONTOS {primeiro} A {ultimo}"
        )

        imagem = _renderizar_mapa(
            contexto,
            bbox=_bbox_pontos_detalhe(
                grupo
            ),
            pontos_exibidos=grupo,
            modo_detalhe=True,
            subtitulo=titulo.title(),
        )

        resultados.append(
            (titulo, imagem)
        )

    return resultados


# ==========================================
# COMPONENTES DO PDF
# ==========================================


class Checkbox(Flowable):
    def __init__(self, marcado=False, tamanho=7):
        super().__init__()
        self.marcado = bool(marcado)
        self.width = tamanho
        self.height = tamanho

    def draw(self):
        self.canv.setStrokeColor(PRETO)
        self.canv.setLineWidth(0.7)
        self.canv.rect(0, 0, self.width, self.height, stroke=1, fill=0)
        if self.marcado:
            self.canv.setFillColor(PRETO)
            margem = 1.2
            self.canv.rect(
                margem, margem,
                self.width - 2 * margem,
                self.height - 2 * margem,
                stroke=0, fill=1,
            )


class MemorialDocTemplate(BaseDocTemplate):
    def __init__(self, *args, **kwargs):
        self.contexto = kwargs.pop("contexto")
        self.assets_dir = Path(kwargs.pop("assets_dir"))
        primeiro_template = kwargs.pop(
            "primeiro_template",
            "memorial",
        )
        super().__init__(*args, **kwargs)

        largura_retrato, altura_retrato = A4
        pagina_paisagem = landscape(A4)
        largura_paisagem, altura_paisagem = pagina_paisagem

        frame_memorial = Frame(
            10 * mm,
            14 * mm,
            largura_retrato - 20 * mm,
            altura_retrato - 48 * mm,
            id="conteudo_memorial",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        frame_mapa = Frame(
            10 * mm,
            14 * mm,
            largura_paisagem - 20 * mm,
            altura_paisagem - 48 * mm,
            id="conteudo_mapa",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        template_memorial = PageTemplate(
            id="memorial",
            pagesize=A4,
            frames=[frame_memorial],
            onPage=self.desenhar_cabecalho_rodape_memorial,
        )
        template_mapa = PageTemplate(
            id="mapa",
            pagesize=pagina_paisagem,
            frames=[frame_mapa],
            onPage=self.desenhar_cabecalho_rodape_mapa,
        )

        templates = (
            [template_mapa, template_memorial]
            if primeiro_template == "mapa"
            else [template_memorial, template_mapa]
        )
        self.addPageTemplates(templates)

    def _desenhar_cabecalho_rodape(
        self,
        canvas,
        doc,
        tamanho_pagina,
    ):
        canvas.saveState()
        largura, altura = tamanho_pagina
        x = 10 * mm
        y_topo = altura - 5 * mm
        h = 24 * mm
        w = largura - 20 * mm

        canvas.setStrokeColor(colors.HexColor("#777777"))
        canvas.setLineWidth(0.6)
        canvas.rect(x, y_topo - h, w, h, stroke=1, fill=0)

        w1, w3 = 46 * mm, 34 * mm
        w2 = w - w1 - w3
        canvas.line(x + w1, y_topo - h, x + w1, y_topo)
        canvas.line(x + w1 + w2, y_topo - h, x + w1 + w2, y_topo)

        canvas.setFont("Courier", 7)
        canvas.setFillColor(PRETO)
        canvas.drawString(x + 2 * mm, y_topo - 4 * mm, "Contratante:")

        def desenhar_imagem(nome, cx, cy, max_w, max_h):
            caminho = self.assets_dir / nome
            if not caminho.exists():
                return
            try:
                from reportlab.lib.utils import ImageReader
                imagem = ImageReader(str(caminho))
                iw, ih = imagem.getSize()
                escala = min(max_w / iw, max_h / ih)
                dw, dh = iw * escala, ih * escala
                canvas.drawImage(
                    imagem,
                    cx - dw / 2,
                    cy - dh / 2,
                    width=dw,
                    height=dh,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                current_app.logger.exception(
                    "Erro ao desenhar %s.",
                    caminho,
                )

        centro_y = y_topo - h / 2 - 1 * mm
        desenhar_imagem(
            "brasao_lagarto.png",
            x + w1 / 2,
            centro_y,
            21 * mm,
            16 * mm,
        )
        desenhar_imagem(
            "semed_prefeitura_lagarto.png",
            x + w1 + w2 / 2,
            centro_y,
            w2 - 8 * mm,
            16 * mm,
        )

        conteudo_topo = altura - 31 * mm
        conteudo_base = 15 * mm
        canvas.setStrokeColor(colors.HexColor("#777777"))
        canvas.setLineWidth(0.55)
        canvas.rect(
            10 * mm,
            conteudo_base,
            largura - 20 * mm,
            conteudo_topo - conteudo_base,
            stroke=1,
            fill=0,
        )

        canvas.setStrokeColor(AZUL)
        canvas.setLineWidth(1.5)
        canvas.line(20 * mm, 11 * mm, largura - 22 * mm, 11 * mm)
        canvas.setFillColor(PRETO)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(
            largura - 10 * mm,
            8.5 * mm,
            str(doc.page),
        )
        canvas.restoreState()

    def desenhar_cabecalho_rodape_memorial(self, canvas, doc):
        self._desenhar_cabecalho_rodape(
            canvas,
            doc,
            A4,
        )

    def desenhar_cabecalho_rodape_mapa(self, canvas, doc):
        self._desenhar_cabecalho_rodape(
            canvas,
            doc,
            landscape(A4),
        )


def criar_estilos():
    base = getSampleStyleSheet()
    return {
        "normal": ParagraphStyle(
            "MemorialNormal", parent=base["Normal"],
            fontName="Helvetica", fontSize=8.2, leading=10.3,
            textColor=PRETO, spaceAfter=0,
        ),
        "normal_pequeno": ParagraphStyle(
            "MemorialNormalPequeno", parent=base["Normal"],
            fontName="Helvetica", fontSize=7.2, leading=8.6,
            textColor=PRETO, spaceAfter=0,
        ),
        "rotulo": ParagraphStyle(
            "MemorialRotulo", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8.2, leading=10.2,
            textColor=PRETO, spaceAfter=0,
        ),
        "titulo": ParagraphStyle(
            "MemorialTitulo", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=13, leading=15,
            textColor=colors.white, alignment=TA_CENTER, spaceAfter=0,
        ),
        "titulo_mapa": ParagraphStyle(
            "TituloMapa", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=12, leading=14,
            textColor=AZUL, alignment=TA_CENTER, spaceAfter=0,
        ),
        "ponto_titulo": ParagraphStyle(
            "PontoTitulo", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8.6, leading=10.5,
            textColor=PRETO, spaceAfter=2,
        ),
        "ponto": ParagraphStyle(
            "Ponto", parent=base["Normal"],
            fontName="Helvetica", fontSize=8.2, leading=10.2,
            spaceAfter=2,
        ),
        "direcao": ParagraphStyle(
            "Direcao", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=8.1, leading=9.8,
            spaceAfter=0,
        ),
        "direcao_seta": ParagraphStyle(
            "DirecaoSeta", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=10, leading=10,
            textColor=colors.white, alignment=TA_CENTER,
        ),
        "rodape_tecnico": ParagraphStyle(
            "ResponsavelTecnico", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=7.5, leading=9,
            alignment=TA_CENTER,
        ),
    }


def p(texto: Any, estilo, negrito_rotulo: str | None = None):
    conteudo = texto_limpo(texto)
    if negrito_rotulo:
        conteudo = f"<b>{negrito_rotulo}</b> {conteudo}"
    return Paragraph(conteudo.replace("\n", "<br/>"), estilo)


def checkbox_com_texto(marcado, texto, estilo, largura=None):
    tabela = Table(
        [[Checkbox(marcado, 7), Paragraph(texto, estilo)]],
        colWidths=[4.5 * mm, largura] if largura else [4.5 * mm, None],
    )
    tabela.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tabela


def bloco_titulo(estilos):
    tabela = Table(
        [[Paragraph("MEMORIAL DESCRITIVO DE ROTA ESCOLAR", estilos["titulo"])]],
        colWidths=[190 * mm],
    )
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabela


def bloco_identificacao(ctx, estilos):
    conteudo = [
        p(ctx["regiao"], estilos["normal"], "Região:"),
        Spacer(1, 7 * mm),
        p(ctx["numero_linha"], estilos["normal"], "Número da Linha:"),
        Spacer(1, 7 * mm),
        p(ctx["linha"], estilos["normal"], "Linha:"),
    ]
    tabela = Table([[conteudo]], colWidths=[190 * mm], rowHeights=[36 * mm])
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tabela


def tabela_quilometragem(ctx, estilos):
    dados = [[
        Paragraph("<b>Turno:</b>", estilos["normal"]),
        Paragraph("<b>Ida:</b>", estilos["normal"]),
        Paragraph("<b>Volta:</b>", estilos["normal"]),
        Paragraph("<b>Total km</b>", estilos["normal"]),
    ]]
    for turno in ctx["turnos"]:
        dados.append([
            checkbox_com_texto(turno["ativo"], turno["nome"], estilos["normal_pequeno"]),
            formatar_km(turno["km_ida"]) if turno["km_ida"] is not None else "",
            formatar_km(turno["km_volta"]) if turno["km_volta"] is not None else "",
            formatar_km(turno["km_total"]) if turno["km_total"] is not None else "",
        ])
    tabela = Table(dados, colWidths=[27 * mm, 16 * mm, 17 * mm, 20 * mm])
    tabela.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
    ]))
    return [
        Paragraph("<b>Quilometragem da Rota:</b>", estilos["normal"]),
        Spacer(1, 2 * mm), tabela, Spacer(1, 3 * mm),
        Paragraph(
            f"<b>Total Geral (km/turno):</b> {formatar_km(ctx['total_geral'])} km.",
            estilos["normal"],
        ),
    ]


def tabela_tipo_veiculo(ctx, estilos):
    checks = [Checkbox(tipo == ctx["tipo_veiculo"], 7) for tipo in TIPOS_VEICULO]
    tabela = Table([checks], colWidths=[20 * mm] * 4)
    tabela.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [
        Paragraph("<b>Tipo de Veículo:</b>", estilos["normal"]),
        Spacer(1, 3 * mm),
        Paragraph("<b>Ônibus / Micro-Ônibus 4x4 / Micro-Ônibus / Van:</b>", estilos["normal"]),
        Spacer(1, 4 * mm), tabela,
    ]


def tabela_quantidade(ctx, estilos):
    numeros = [Paragraph(f"<b>{n}.</b>", estilos["normal"]) for n in range(1, 6)]
    checks = [Checkbox(n == ctx["quantidade_veiculos"], 7) for n in range(1, 6)]
    tabela = Table([numeros, checks], colWidths=[12 * mm] * 5)
    tabela.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return [Paragraph("<b>Quantidade Veículo:</b>", estilos["normal"]), Spacer(1, 2 * mm), tabela]


def tabela_sim_nao(rotulo, valor, estilos):
    return [
        Paragraph(f"<b>{rotulo}</b>", estilos["normal"]),
        Spacer(1, 2 * mm),
        Table(
            [[
                checkbox_com_texto(valor, "Sim", estilos["normal"]),
                checkbox_com_texto(not valor, "Não", estilos["normal"]),
            ]],
            colWidths=[30 * mm, 30 * mm],
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]),
        ),
    ]


def bloco_resumo_primeira_pagina(ctx, estilos):
    rede_opcoes = [
        checkbox_com_texto(
            rede in ctx["redes_ensino_ativas"],
            rede.title(),
            estilos["normal_pequeno"],
        )
        for rede in REDES_ENSINO
    ]
    areas_opcoes = [
        checkbox_com_texto(area in ctx["areas_ativas"], area.title(), estilos["normal"])
        for area in AREAS_LOCALIZACAO
    ]

    dados = [
        [tabela_quilometragem(ctx, estilos), tabela_tipo_veiculo(ctx, estilos)],
        [tabela_quantidade(ctx, estilos), tabela_sim_nao("Ônibus PCD:", ctx["onibus_pcd"], estilos)],
        [[
            p(ctx["inicio"] + ".", estilos["normal"], "Início:"), Spacer(1, 5 * mm),
            p(ctx["termino"] + ".", estilos["normal"], "Término:"),
        ], [
            Paragraph("<b>Rede de Ensino:</b>", estilos["normal"]), Spacer(1, 3 * mm),
            Paragraph("<b>Municipal / Estadual / Federal</b>", estilos["normal"]), Spacer(1, 4 * mm),
            Table([rede_opcoes], colWidths=[27 * mm, 25 * mm, 25 * mm], style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ])),
        ]],
        [[
            p(ctx["localizacao"], estilos["normal"], "Localização:"), Spacer(1, 5 * mm),
            Paragraph("<b>Área Urbana/Área Rural</b>", estilos["normal"]), Spacer(1, 2 * mm),
            Table([areas_opcoes], colWidths=[34 * mm, 34 * mm], style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ])), Spacer(1, 4 * mm),
            *tabela_sim_nao("Intermunicipal:", ctx["intermunicipal"], estilos),
        ], [
            *tabela_sim_nao("Assistente de Mobilidade:", ctx["assistente_mobilidade"], estilos),
            Spacer(1, 3 * mm), p(ctx["assistente_nome"], estilos["normal"], "Nome:"),
        ]],
        [
            p(ctx["veiculo_placa"], estilos["normal"], "Nº do Veículo / Placa:"),
            [p(ctx["motorista"], estilos["normal"], "Motorista:"), Spacer(1, 4 * mm), p(ctx["contato"], estilos["normal"], "Contato:")],
        ],
    ]

    tabela = Table(
        dados,
        colWidths=[88 * mm, 102 * mm],
        rowHeights=[57 * mm, 24 * mm, 37 * mm, 40 * mm, 17 * mm],
    )
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tabela


def _imagem_mapa_pdf(
    buffer_mapa: io.BytesIO,
) -> RLImage:
    return RLImage(
        buffer_mapa,
        width=277 * mm,
        height=150 * mm,
    )


def bloco_mapa_primeira_pagina(
    ctx: dict[str, Any],
    estilos: dict[str, ParagraphStyle],
) -> list[Any]:
    """
    Primeira página:
    mapa somente com escolas atendidas, início e final.
    """

    buffer_mapa = gerar_imagem_mapa(
        ctx
    )

    return [
        Paragraph(
            "MAPA GERAL DAS UNIDADES ATENDIDAS",
            estilos["titulo_mapa"],
        ),
        Spacer(1, 2 * mm),
        _imagem_mapa_pdf(
            buffer_mapa
        ),
    ]


def bloco_mapa_segunda_pagina(
    ctx: dict[str, Any],
    estilos: dict[str, ParagraphStyle],
) -> list[Any]:
    """
    Segunda página:
    mapa geral com pontos notáveis.
    """

    buffer_mapa = (
        gerar_imagem_mapa_geral_detalhado(
            ctx
        )
    )

    return [
        Paragraph(
            "MAPA GERAL COM DETALHES DA ROTA",
            estilos["titulo_mapa"],
        ),
        Spacer(1, 2 * mm),
        _imagem_mapa_pdf(
            buffer_mapa
        ),
    ]


def blocos_mapas_detalhados(
    ctx: dict[str, Any],
    estilos: dict[str, ParagraphStyle],
) -> list[Any]:
    """
    Terceira até a enésima página:
    um recorte detalhado por página.
    """

    elementos: list[Any] = []
    mapas = gerar_imagens_mapas_detalhados(
        ctx
    )

    for titulo, buffer_mapa in mapas:
        elementos.extend([
            NextPageTemplate("mapa"),
            PageBreak(),
            Paragraph(
                titulo,
                estilos["titulo_mapa"],
            ),
            Spacer(1, 2 * mm),
            _imagem_mapa_pdf(
                buffer_mapa
            ),
        ])

    return elementos


def bloco_detalhes(ctx, estilos):
    unidades = ctx.get("escolas") or []

    if unidades:
        unidades_texto = "<br/>".join(
            f"• {texto_limpo(nome)}"
            for nome in unidades
        )
    else:
        unidades_texto = (
            "Nenhuma unidade de ensino foi informada como "
            "assistida pelo transporte escolar."
        )

    escolas = Table(
        [[Paragraph(
            "<b>Unidades de Ensino Assistidas pelo Transporte Escolar:</b>"
            f"<br/>{unidades_texto}",
            estilos["normal"],
        )]],
        colWidths=[190 * mm],
    )
    escolas.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    horarios_dados = [[
        Paragraph("<b>Turno:</b>", estilos["normal"]),
        Paragraph("<b>Horário:</b>", estilos["normal"]),
        Paragraph("<b>Início da Aulas:</b>", estilos["normal"]),
        Paragraph("<b>Término da Aula:</b>", estilos["normal"]),
    ]]
    for turno in ctx["turnos"]:
        horarios_dados.append([
            checkbox_com_texto(turno["ativo"], turno["nome"], estilos["normal"]),
            turno["horario"], turno["inicio_aulas"], turno["termino_aulas"],
        ])
    horarios = Table(horarios_dados, colWidths=[45 * mm, 35 * mm, 55 * mm, 55 * mm])
    horarios.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))

    observacao = Table(
        [[Paragraph(
            f"<b>Observação:</b><br/>{texto_limpo(ctx['observacao']).replace(chr(10), '<br/>')}",
            estilos["normal"],
        )]],
        colWidths=[190 * mm], rowHeights=[25 * mm],
    )
    observacao.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, CINZA_BORDA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [escolas, horarios, observacao]


def bloco_ponto(ponto, estilos):
    linhas = [Paragraph(f"{ponto['ordem']}. {ponto['referencia']}", estilos["ponto_titulo"])]
    if ponto["coordenadas"]:
        if ponto["mapa_url"]:
            coordenadas = (
                f'<link href="{ponto["mapa_url"]}">'
                f'<u><font color="#0000EE">({ponto["coordenadas"]})</font></u></link>'
            )
        else:
            coordenadas = f"({ponto['coordenadas']})"
        linhas.append(Paragraph(f"• <b>COORDENADAS:</b> {coordenadas}", estilos["ponto"]))
    if ponto["lado_via"]:
        linhas.append(Paragraph(f"• <b>LADO:</b> {ponto['lado_via']}", estilos["ponto"]))
    if ponto["logradouro"]:
        linhas.append(Paragraph(f"• <b>LOGRADOURO:</b> {ponto['logradouro']}", estilos["ponto"]))
    if ponto["direcao"] and not ponto["fim_trajeto"]:
        direcao = Table(
            [[Paragraph("&gt;", estilos["direcao_seta"]), Paragraph(ponto["direcao"], estilos["direcao"])]],
            colWidths=[6 * mm, 176 * mm],
        )
        direcao.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#73A9BE")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 1),
            ("RIGHTPADDING", (0, 0), (0, 0), 1),
            ("TOPPADDING", (0, 0), (0, 0), 1),
            ("BOTTOMPADDING", (0, 0), (0, 0), 1),
            ("LEFTPADDING", (1, 0), (1, 0), 3),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ]))
        linhas.append(direcao)
    linhas.append(Spacer(1, 4 * mm))
    return KeepTogether(linhas)


def blocos_itinerario(ctx, estilos):
    elementos = [
        Table(
            [[Paragraph("<b>Itinerário da Linha:</b>", estilos["normal"])]],
            colWidths=[190 * mm],
            style=TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.55, CINZA_BORDA),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]),
        ),
        Spacer(1, 5 * mm),
    ]

    for trecho in (ctx["ida"], ctx["volta"]):
        if not trecho["pontos"]:
            continue
        elementos.append(Paragraph(f"• &nbsp;&nbsp; <b>{trecho['nome']}:</b>", estilos["rotulo"]))
        elementos.append(Spacer(1, 4 * mm))
        for indice, ponto in enumerate(trecho["pontos"]):
            if indice == 0:
                elementos.append(Paragraph("<b>INÍCIO:</b>", estilos["rotulo"]))
                elementos.append(Spacer(1, 3 * mm))
            if indice == len(trecho["pontos"]) - 1:
                elementos.append(Paragraph("<b>CHEGADA:</b>", estilos["rotulo"]))
                elementos.append(Spacer(1, 3 * mm))
            elementos.append(bloco_ponto(ponto, estilos))
        elementos.append(Spacer(1, 3 * mm))

    if ctx["responsavel_tecnico"] or ctx["crea"]:
        responsavel = "RESPONSÁVEL TÉCNICO"
        if ctx["responsavel_tecnico"]:
            responsavel += f": {ctx['responsavel_tecnico']}"
        if ctx["crea"]:
            responsavel += f" &nbsp;&nbsp;&nbsp; Registro Profissional: {ctx['crea']}"
        elementos.append(Spacer(1, 5 * mm))
        elementos.append(Table(
            [[Paragraph(responsavel, estilos["rodape_tecnico"])]],
            colWidths=[190 * mm],
            style=TableStyle([
                ("LINEABOVE", (0, 0), (-1, 0), 0.55, CINZA_BORDA),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]),
        ))
    return elementos


def _normalizar_conteudo(valor: Any) -> str:
    texto = texto_limpo(valor, CONTEUDO_MEMORIAL_MAPA).lower()

    aliases = {
        "completo": CONTEUDO_MEMORIAL_MAPA,
        "memorial+mapa": CONTEUDO_MEMORIAL_MAPA,
        "memorial_e_mapa": CONTEUDO_MEMORIAL_MAPA,
        "so_mapa": CONTEUDO_SOMENTE_MAPA,
        "somente_mapa": CONTEUDO_SOMENTE_MAPA,
        "so_memorial": CONTEUDO_SOMENTE_MEMORIAL,
        "somente_memorial": CONTEUDO_SOMENTE_MEMORIAL,
        "separado": CONTEUDO_ARQUIVOS_SEPARADOS,
        "arquivos_separados": CONTEUDO_ARQUIVOS_SEPARADOS,
    }

    texto = aliases.get(texto, texto)

    if texto not in CONTEUDOS_VALIDOS:
        abort(400, description="Formato de conteúdo inválido.")

    return texto


def _normalizar_escopo(valor: Any) -> str:
    texto = texto_limpo(valor, ESCOPO_MUNICIPIO).lower()
    if texto not in ESCOPOS_VALIDOS:
        abort(400, description="Escopo de geração inválido.")
    return texto


def _normalizar_organizacao(valor: Any) -> str:
    texto = texto_limpo(valor, ORGANIZACAO_UNICO).lower()
    if texto not in ORGANIZACOES_VALIDAS:
        abort(400, description="Organização dos arquivos inválida.")
    return texto


def _conteudo_inclui_memorial(conteudo: str) -> bool:
    return conteudo in {
        CONTEUDO_MEMORIAL_MAPA,
        CONTEUDO_SOMENTE_MEMORIAL,
        CONTEUDO_ARQUIVOS_SEPARADOS,
    }


def _conteudo_inclui_mapa(conteudo: str) -> bool:
    return conteudo in {
        CONTEUDO_MEMORIAL_MAPA,
        CONTEUDO_SOMENTE_MAPA,
        CONTEUDO_ARQUIVOS_SEPARADOS,
    }


def _elementos_memorial_contexto(
    contexto: dict[str, Any],
    estilos: dict[str, ParagraphStyle],
) -> list[Any]:
    """
    Monta somente as páginas textuais do memorial.
    """

    return [
        bloco_titulo(estilos),
        Spacer(1, 3 * mm),
        bloco_identificacao(
            contexto,
            estilos,
        ),
        bloco_resumo_primeira_pagina(
            contexto,
            estilos,
        ),
        PageBreak(),
        *bloco_detalhes(
            contexto,
            estilos,
        ),
        *blocos_itinerario(
            contexto,
            estilos,
        ),
    ]


def _elementos_mapas_contexto(
    contexto: dict[str, Any],
    estilos: dict[str, ParagraphStyle],
) -> list[Any]:
    """
    Monta todas as páginas cartográficas da rota.

    Ordem:
      1. mapa somente com as unidades atendidas;
      2. mapa geral com pontos notáveis;
      3. mapas detalhados por recorte.
    """

    return [
        *bloco_mapa_primeira_pagina(
            contexto,
            estilos,
        ),
        NextPageTemplate("mapa"),
        PageBreak(),
        *bloco_mapa_segunda_pagina(
            contexto,
            estilos,
        ),
        *blocos_mapas_detalhados(
            contexto,
            estilos,
        ),
    ]


def _elementos_contexto_pdf(
    contexto: dict[str, Any],
    estilos: dict[str, ParagraphStyle],
    conteudo: str,
) -> list[Any]:
    """
    Organiza uma rota individual.

    Quando o PDF contém memorial e mapas, o memorial aparece
    primeiro e todas as páginas cartográficas ficam no final.
    """

    elementos_memorial = _elementos_memorial_contexto(
        contexto,
        estilos,
    )
    elementos_mapas = _elementos_mapas_contexto(
        contexto,
        estilos,
    )

    if conteudo == CONTEUDO_MEMORIAL_MAPA:
        return [
            *elementos_memorial,
            NextPageTemplate("mapa"),
            PageBreak(),
            *elementos_mapas,
        ]

    if conteudo == CONTEUDO_SOMENTE_MAPA:
        return elementos_mapas

    if conteudo == CONTEUDO_SOMENTE_MEMORIAL:
        return elementos_memorial

    raise ValueError(
        (
            "Conteúdo não pode ser gerado "
            f"em um único PDF: {conteudo}"
        )
    )


def gerar_pdf_multiplas_rotas(
    contextos: list[dict[str, Any]],
    assets_dir: Path,
    *,
    conteudo: str,
    titulo_documento: str,
) -> io.BytesIO:
    """
    Gera um PDF de uma ou várias rotas.

    Para documentos que combinam memorial e mapa:
      1. são inseridos todos os memoriais;
      2. depois são inseridos todos os mapas.

    Assim, as páginas cartográficas ficam efetivamente nas
    últimas páginas do PDF, inclusive em arquivos de região
    ou do município inteiro.
    """

    if not contextos:
        raise ValueError(
            "Nenhuma rota foi informada para o PDF."
        )

    if conteudo == CONTEUDO_ARQUIVOS_SEPARADOS:
        raise ValueError(
            (
                "Arquivos separados devem ser "
                "gerados individualmente."
            )
        )

    buffer = io.BytesIO()
    estilos = criar_estilos()

    primeiro_template = (
        "mapa"
        if conteudo == CONTEUDO_SOMENTE_MAPA
        else "memorial"
    )

    tamanho_inicial = (
        landscape(A4)
        if primeiro_template == "mapa"
        else A4
    )

    documento = MemorialDocTemplate(
        buffer,
        pagesize=tamanho_inicial,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=34 * mm,
        bottomMargin=14 * mm,
        title=titulo_documento,
        author="WebSIG",
        contexto=contextos[0],
        assets_dir=assets_dir,
        primeiro_template=primeiro_template,
    )

    elementos: list[Any] = []

    if conteudo == CONTEUDO_MEMORIAL_MAPA:
        # ==========================================
        # PRIMEIRA PARTE: TODOS OS MEMORIAIS
        # ==========================================
        for indice, contexto in enumerate(contextos):
            if indice > 0:
                elementos.extend([
                    NextPageTemplate("memorial"),
                    PageBreak(),
                ])

            elementos.extend(
                _elementos_memorial_contexto(
                    contexto,
                    estilos,
                )
            )

        # ==========================================
        # SEGUNDA PARTE: TODOS OS MAPAS
        # ==========================================
        for contexto in contextos:
            elementos.extend([
                NextPageTemplate("mapa"),
                PageBreak(),
            ])

            elementos.extend(
                _elementos_mapas_contexto(
                    contexto,
                    estilos,
                )
            )

    elif conteudo == CONTEUDO_SOMENTE_MEMORIAL:
        for indice, contexto in enumerate(contextos):
            if indice > 0:
                elementos.extend([
                    NextPageTemplate("memorial"),
                    PageBreak(),
                ])

            elementos.extend(
                _elementos_memorial_contexto(
                    contexto,
                    estilos,
                )
            )

    elif conteudo == CONTEUDO_SOMENTE_MAPA:
        for indice, contexto in enumerate(contextos):
            if indice > 0:
                elementos.extend([
                    NextPageTemplate("mapa"),
                    PageBreak(),
                ])

            elementos.extend(
                _elementos_mapas_contexto(
                    contexto,
                    estilos,
                )
            )

    else:
        raise ValueError(
            f"Conteúdo inválido para geração: {conteudo}"
        )

    documento.build(elementos)
    buffer.seek(0)
    return buffer


def gerar_pdf_memorial(
    contexto: dict[str, Any],
    assets_dir: Path,
    *,
    conteudo: str = CONTEUDO_MEMORIAL_MAPA,
) -> io.BytesIO:
    conteudo = _normalizar_conteudo(conteudo)

    if conteudo == CONTEUDO_ARQUIVOS_SEPARADOS:
        raise ValueError(
            "Use o gerador de arquivos para criar memorial e mapa separados."
        )

    return gerar_pdf_multiplas_rotas(
        [contexto],
        assets_dir,
        conteudo=conteudo,
        titulo_documento=f"Rota {contexto['codigo_rota']}",
    )


# ==========================================
# SELEÇÃO DAS ROTAS E GERAÇÃO EM LOTE
# ==========================================

PERFIS_GERACAO_LOTE = {"ADMIN", "AUDITOR"}


def _perfil_usuario_atual() -> str:
    return texto_limpo(
        getattr(current_user, "perfil", "")
    ).upper()


def _validar_permissao_lote() -> None:
    if _perfil_usuario_atual() not in PERFIS_GERACAO_LOTE:
        abort(
            403,
            description=(
                "Somente administradores e auditores podem gerar "
                "arquivos de várias rotas de uma vez."
            ),
        )


def _chave_regiao(valor: Any) -> str:
    texto_regiao = unicodedata.normalize(
        "NFD",
        texto_limpo(valor),
    )
    texto_regiao = "".join(
        caractere
        for caractere in texto_regiao
        if unicodedata.category(caractere) != "Mn"
    ).upper()

    if "UNIVERSIT" in texto_regiao or "UNIVERSIDADE" in texto_regiao:
        return "universidade"

    numero = re.search(r"\d+", texto_regiao)
    if numero:
        return str(int(numero.group(0)))

    return re.sub(r"\s+", "_", texto_regiao.strip().lower()) or "sem_regiao"


def _rotulo_regiao(valor: Any) -> str:
    chave = _chave_regiao(valor)
    if chave == "universidade":
        return "Região Universitária"
    if chave.isdigit():
        return f"Região {int(chave)}"
    return texto_limpo(valor, "Sem região")


def _normalizar_regiao_pasta(valor: Any) -> str:
    chave = _chave_regiao(valor)
    if chave == "universidade":
        return "UNIVERSITARIA"
    if chave.isdigit():
        return chave.zfill(2)
    return secure_filename(chave.upper()) or "SEM_REGIAO"


def _listar_rotas_para_lote() -> list[dict[str, Any]]:
    return [
        dict(registro)
        for registro in db.session.execute(
            SQL_ROTAS_PARA_LOTE
        ).mappings().all()
    ]


def _chave_codigo_rota(valor: Any) -> str:
    """Normaliza o código da rota para comparações seguras."""

    return unicodedata.normalize(
        "NFKC",
        texto_limpo(valor),
    ).casefold()


def _selecionar_rotas(
    *,
    escopo: str,
    rota_id: int | None,
    regiao: str,
) -> list[dict[str, Any]]:
    rotas = _listar_rotas_para_lote()

    if not rotas:
        abort(
            404,
            description=(
                "Nenhuma rota foi encontrada "
                "no banco de dados."
            ),
        )

    if escopo == ESCOPO_ROTA:
        if rota_id is None:
            abort(
                400,
                description=(
                    "Selecione a rota que será gerada."
                ),
            )

        # O GeoJSON possui um ID para cada trecho (IDA/VOLTA).
        # Já a listagem de lote mantém somente um ID representativo
        # por nome_rota. Por isso, o ID clicado no mapa pode ser o
        # trecho VOLTA e não coincidir com o ID representativo.
        # Primeiro resolvemos qualquer ID de trecho para o nome da rota.
        trechos_da_rota = buscar_trechos(
            rota_id
        )

        if not trechos_da_rota:
            abort(
                404,
                description=(
                    "A rota selecionada não existe "
                    "em semed.rotas_geral."
                ),
            )

        primeiro_trecho = trechos_da_rota[0]
        codigo_rota = texto_limpo(
            primeiro_trecho.get("nome_rota")
        )
        chave_codigo = _chave_codigo_rota(
            codigo_rota
        )

        selecionadas = [
            rota
            for rota in rotas
            if _chave_codigo_rota(
                rota.get("nome_rota")
            ) == chave_codigo
        ]

        # Salvaguarda: mesmo que a consulta de lote não retorne o
        # registro representativo, o próprio trecho clicado continua
        # sendo suficiente para gerar o documento.
        if not selecionadas:
            selecionadas = [
                {
                    "id": rota_id,
                    "nome_rota": codigo_rota,
                    "regiao": primeiro_trecho.get(
                        "regiao"
                    ),
                }
            ]

    elif escopo == ESCOPO_REGIAO:
        chave_desejada = _chave_regiao(
            regiao
        )

        if not texto_limpo(regiao):
            abort(
                400,
                description=(
                    "Selecione a região que será gerada."
                ),
            )

        selecionadas = [
            rota
            for rota in rotas
            if _chave_regiao(
                rota.get("regiao")
            ) == chave_desejada
        ]

    else:
        selecionadas = rotas

    if not selecionadas:
        abort(
            404,
            description=(
                "Nenhuma rota corresponde "
                "aos filtros informados."
            ),
        )

    return selecionadas


def _carregar_contexto_registro(
    registro_rota: dict[str, Any],
    *,
    exigir_metadados: bool,
    escolas_cadastradas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rota_id = int(registro_rota["id"])
    codigo_consulta = texto_limpo(
        registro_rota.get("nome_rota"),
        f"Rota_{rota_id}",
    )

    registros = buscar_trechos(rota_id)
    if not registros:
        raise RuntimeError("Rota não encontrada.")

    codigo_rota = texto_limpo(
        registros[0].get("nome_rota"),
        codigo_consulta,
    )

    dados = buscar_dados_memorial(codigo_rota)
    if exigir_metadados and not dados:
        raise RuntimeError(
            "Não há registro em semed.rotas_memoriais para esta rota."
        )

    pontos_normalizados = buscar_pontos_normalizados(codigo_rota)
    contexto = montar_contexto(
        registros,
        dados,
        pontos_normalizados,
    )

    contexto["escolas_mapa"] = resolver_escolas_mapa(
        contexto,
        escolas_cadastradas or [],
    )

    return contexto


def _mensagem_excecao(erro: Exception) -> str:
    if isinstance(erro, HTTPException):
        return texto_limpo(erro.description, erro.name)
    return texto_limpo(str(erro), erro.__class__.__name__)


def _carregar_contextos_lote(
    rotas: list[dict[str, Any]],
    *,
    conteudo: str,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    contextos: list[dict[str, Any]] = []
    erros: list[tuple[str, str]] = []
    exigir_metadados = _conteudo_inclui_memorial(conteudo)
    escolas_cadastradas = (
        buscar_escolas_coordenadas()
        if _conteudo_inclui_mapa(conteudo)
        else []
    )

    for registro in rotas:
        codigo = texto_limpo(
            registro.get("nome_rota"),
            f"Rota_{registro.get('id')}",
        )

        try:
            contextos.append(
                _carregar_contexto_registro(
                    registro,
                    exigir_metadados=exigir_metadados,
                    escolas_cadastradas=escolas_cadastradas,
                )
            )

        except Exception as erro_rota:
            db.session.rollback()
            mensagem = _mensagem_excecao(erro_rota)
            erros.append((codigo, mensagem))
            current_app.logger.exception(
                "Erro ao preparar a rota %s para geração.",
                codigo,
            )

    if not contextos:
        primeiro_erro = erros[0][1] if erros else "Nenhuma rota pôde ser gerada."
        abort(
            422,
            description=(
                "Nenhum arquivo pôde ser gerado. "
                f"Primeiro erro: {primeiro_erro}"
            ),
        )

    return contextos, erros


def _nome_pdf(conteudo: str, nome_base: str) -> str:
    base_segura = secure_filename(nome_base) or "Rotas"

    prefixos = {
        CONTEUDO_MEMORIAL_MAPA: "Memorial_e_Mapa",
        CONTEUDO_SOMENTE_MAPA: "Mapa",
        CONTEUDO_SOMENTE_MEMORIAL: "Memorial",
    }

    return secure_filename(
        f"{prefixos[conteudo]}_{base_segura}.pdf"
    )


def _arquivos_pdf(
    contextos: list[dict[str, Any]],
    *,
    assets_dir: Path,
    conteudo: str,
    organizacao: str,
    nome_base: str,
) -> list[tuple[str, io.BytesIO]]:
    arquivos: list[tuple[str, io.BytesIO]] = []

    if organizacao == ORGANIZACAO_UNICO:
        if conteudo == CONTEUDO_ARQUIVOS_SEPARADOS:
            for parte in (
                CONTEUDO_SOMENTE_MEMORIAL,
                CONTEUDO_SOMENTE_MAPA,
            ):
                arquivos.append((
                    _nome_pdf(parte, nome_base),
                    gerar_pdf_multiplas_rotas(
                        contextos,
                        assets_dir,
                        conteudo=parte,
                        titulo_documento=nome_base,
                    ),
                ))
        else:
            arquivos.append((
                _nome_pdf(conteudo, nome_base),
                gerar_pdf_multiplas_rotas(
                    contextos,
                    assets_dir,
                    conteudo=conteudo,
                    titulo_documento=nome_base,
                ),
            ))

        return arquivos

    for contexto in contextos:
        codigo = texto_limpo(contexto.get("codigo_rota"), "Rota")
        pasta = f"REGIAO_{_normalizar_regiao_pasta(contexto.get('regiao'))}"

        partes = (
            (
                CONTEUDO_SOMENTE_MEMORIAL,
                CONTEUDO_SOMENTE_MAPA,
            )
            if conteudo == CONTEUDO_ARQUIVOS_SEPARADOS
            else (conteudo,)
        )

        for parte in partes:
            nome = _nome_pdf(parte, codigo)
            arquivos.append((
                f"{pasta}/{nome}",
                gerar_pdf_memorial(
                    contexto,
                    assets_dir,
                    conteudo=parte,
                ),
            ))

    return arquivos


def _montar_relatorio_zip(
    *,
    arquivos: list[str],
    erros: list[tuple[str, str]],
) -> str:
    linhas = [
        "GERAÇÃO DE MEMORIAIS E MAPAS",
        "",
        f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Arquivos: {len(arquivos)}",
        f"Rotas com erro: {len(erros)}",
        "",
    ]

    if arquivos:
        linhas.extend([
            "ARQUIVOS GERADOS",
            "----------------",
            *arquivos,
            "",
        ])

    if erros:
        linhas.extend([
            "ROTAS COM ERRO",
            "---------------",
        ])
        linhas.extend(
            f"{codigo}: {mensagem}"
            for codigo, mensagem in erros
        )
        linhas.append("")

    return "\n".join(linhas)


def _criar_zip(
    arquivos: list[tuple[str, io.BytesIO]],
    *,
    erros: list[tuple[str, str]],
) -> tempfile.SpooledTemporaryFile:
    buffer_zip = tempfile.SpooledTemporaryFile(
        max_size=64 * 1024 * 1024,
        mode="w+b",
    )

    nomes_gerados: list[str] = []

    with zipfile.ZipFile(
        buffer_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as arquivo_zip:
        for caminho, buffer_pdf in arquivos:
            buffer_pdf.seek(0)
            arquivo_zip.writestr(caminho, buffer_pdf.read())
            buffer_pdf.close()
            nomes_gerados.append(caminho)

        arquivo_zip.writestr(
            "RELATORIO_GERACAO.txt",
            _montar_relatorio_zip(
                arquivos=nomes_gerados,
                erros=erros,
            ).encode("utf-8"),
        )

    buffer_zip.seek(0)
    return buffer_zip


def _resposta_arquivos(
    arquivos: list[tuple[str, io.BytesIO]],
    *,
    nome_base: str,
    total_rotas: int,
    erros: list[tuple[str, str]],
    forcar_zip: bool,
):
    if len(arquivos) == 1 and not forcar_zip:
        nome, buffer_pdf = arquivos[0]
        resposta = send_file(
            buffer_pdf,
            download_name=nome,
            as_attachment=True,
            mimetype="application/pdf",
            conditional=False,
        )
    else:
        buffer_zip = _criar_zip(arquivos, erros=erros)
        nome_zip = secure_filename(
            f"{nome_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )
        resposta = send_file(
            buffer_zip,
            download_name=nome_zip,
            as_attachment=True,
            mimetype="application/zip",
            conditional=False,
        )

    resposta.headers["X-Memoriais-Gerados"] = str(total_rotas)
    resposta.headers["X-Memoriais-Erros"] = str(len(erros))
    return resposta


def _nome_base_escopo(
    *,
    escopo: str,
    regiao: str,
    contextos: list[dict[str, Any]],
) -> str:
    if escopo == ESCOPO_ROTA:
        return texto_limpo(contextos[0].get("codigo_rota"), "Rota")

    if escopo == ESCOPO_REGIAO:
        return secure_filename(
            _rotulo_regiao(regiao).replace(" ", "_")
        ) or "Regiao"

    return "Municipio_de_Lagarto"


def _executar_geracao(
    *,
    escopo: str,
    conteudo: str,
    organizacao: str,
    rota_id: int | None,
    regiao: str,
):
    if escopo != ESCOPO_ROTA:
        _validar_permissao_lote()

    rotas = _selecionar_rotas(
        escopo=escopo,
        rota_id=rota_id,
        regiao=regiao,
    )

    contextos, erros = _carregar_contextos_lote(
        rotas,
        conteudo=conteudo,
    )

    assets_dir = Path(current_app.static_folder) / "img" / "memorial"
    nome_base = _nome_base_escopo(
        escopo=escopo,
        regiao=regiao,
        contextos=contextos,
    )

    # Uma rota já é naturalmente um único conjunto. A opção "separados"
    # do conteúdo ainda produz Memorial.pdf + Mapa.pdf dentro de um ZIP.
    organizacao_efetiva = (
        ORGANIZACAO_UNICO
        if escopo == ESCOPO_ROTA
        else organizacao
    )

    arquivos = _arquivos_pdf(
        contextos,
        assets_dir=assets_dir,
        conteudo=conteudo,
        organizacao=organizacao_efetiva,
        nome_base=nome_base,
    )

    forcar_zip = (
        conteudo == CONTEUDO_ARQUIVOS_SEPARADOS
        or organizacao_efetiva == ORGANIZACAO_SEPARADOS
    )

    return _resposta_arquivos(
        arquivos,
        nome_base=f"Geracao_{nome_base}",
        total_rotas=len(contextos),
        erros=erros,
        forcar_zip=forcar_zip,
    )


# ==========================================
# ENDPOINTS
# ==========================================


@memorial_bp.get("/api/rotas/memoriais/opcoes")
@login_required
def opcoes_geracao_memoriais():
    rotas = _listar_rotas_para_lote()

    regioes_por_chave: dict[str, dict[str, str]] = {}
    rotas_saida: list[dict[str, Any]] = []

    for rota in rotas:
        chave = _chave_regiao(rota.get("regiao"))
        regioes_por_chave.setdefault(
            chave,
            {
                "id": chave,
                "nome": _rotulo_regiao(rota.get("regiao")),
            },
        )

        rotas_saida.append({
            "id": int(rota["id"]),
            "nome": texto_limpo(rota.get("nome_rota"), f"Rota {rota['id']}"),
            "regiao_id": chave,
            "regiao": _rotulo_regiao(rota.get("regiao")),
        })

    regioes = sorted(
        regioes_por_chave.values(),
        key=lambda item: (
            0 if item["id"].isdigit() else 1,
            int(item["id"]) if item["id"].isdigit() else item["nome"],
        ),
    )

    rotas_saida.sort(key=lambda item: item["nome"].casefold())

    return jsonify({
        "regioes": regioes,
        "rotas": rotas_saida,
        "pode_gerar_lote": _perfil_usuario_atual() in PERFIS_GERACAO_LOTE,
    })


@memorial_bp.get("/api/rotas/memoriais/gerar")
@login_required
def gerar_memoriais_flexiveis():
    escopo = _normalizar_escopo(request.args.get("escopo"))
    conteudo = _normalizar_conteudo(request.args.get("conteudo"))
    organizacao = _normalizar_organizacao(request.args.get("organizacao"))
    rota_id = inteiro_seguro(request.args.get("rota_id"), 0) or None
    regiao = texto_limpo(request.args.get("regiao"))

    try:
        return _executar_geracao(
            escopo=escopo,
            conteudo=conteudo,
            organizacao=organizacao,
            rota_id=rota_id,
            regiao=regiao,
        )

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Erro de banco na geração de memoriais.")
        abort(500, description="Erro ao consultar os dados para geração.")


@memorial_bp.get("/api/rotas/memoriais")
@login_required
def gerar_todos_memoriais():
    """Compatibilidade: gera um PDF completo por rota dentro de um ZIP."""

    try:
        return _executar_geracao(
            escopo=ESCOPO_MUNICIPIO,
            conteudo=CONTEUDO_MEMORIAL_MAPA,
            organizacao=ORGANIZACAO_SEPARADOS,
            rota_id=None,
            regiao="",
        )

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Erro de banco ao gerar todos os memoriais.")
        abort(500, description="Erro ao consultar os dados para geração.")


@memorial_bp.get("/api/rotas/<int:rota_id>/memorial")
@login_required
def gerar_memorial(rota_id: int):
    conteudo = _normalizar_conteudo(request.args.get("conteudo"))

    try:
        return _executar_geracao(
            escopo=ESCOPO_ROTA,
            conteudo=conteudo,
            organizacao=ORGANIZACAO_UNICO,
            rota_id=rota_id,
            regiao="",
        )

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro de banco ao gerar memorial da rota %s.",
            rota_id,
        )
        abort(500, description="Erro ao consultar os dados do memorial.")
    except Exception:
        current_app.logger.exception(
            "Erro ao gerar memorial da rota %s.",
            rota_id,
        )
        raise