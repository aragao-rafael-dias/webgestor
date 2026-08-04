# ==========================================
# IMPORTAÇÃO SEGURA DE ROTAS A PARTIR DE GEOJSON
# ==========================================

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from flask import Flask, current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


# ==========================================
# CONSULTAS
# ==========================================

SQL_TABELAS_OBRIGATORIAS = text(
    """
    SELECT
        to_regclass('semed.rotas_geral') AS rotas_geral,
        to_regclass('semed.rotas_pontos_notaveis') AS pontos_notaveis
    """
)

SQL_BUSCAR_ROTAS_EXISTENTES = text(
    """
    SELECT
        rg.id,
        rg.nome_rota,
        rg.regiao,
        rg.trecho,
        rg.total_pontos,
        rg.pontos_notaveis::text AS pontos_notaveis_texto,
        ST_AsGeoJSON(rg.geom) AS geometria_geojson,
        (
            SELECT COUNT(*)
            FROM semed.rotas_pontos_notaveis AS p
            WHERE p.rota_id = rg.id
        ) AS quantidade_pontos
    FROM semed.rotas_geral AS rg
    WHERE LOWER(BTRIM(rg.nome_rota)) = LOWER(BTRIM(:nome_rota))
      AND UPPER(BTRIM(rg.trecho)) = UPPER(BTRIM(:trecho))
    ORDER BY
        quantidade_pontos DESC,
        rg.id ASC
    """
)

SQL_INSERIR_ROTA = text(
    """
    INSERT INTO semed.rotas_geral (
        nome_rota,
        regiao,
        trecho,
        total_pontos,
        pontos_notaveis,
        geom
    ) VALUES (
        :nome_rota,
        :regiao,
        :trecho,
        :total_pontos,
        NULL,
        ST_Force2D(
            ST_SetSRID(
                ST_GeomFromGeoJSON(:geometria_geojson),
                4326
            )
        )
    )
    RETURNING id
    """
)

SQL_ATUALIZAR_ROTA = text(
    """
    UPDATE semed.rotas_geral
    SET
        nome_rota = :nome_rota,
        regiao = :regiao,
        trecho = :trecho,
        total_pontos = :total_pontos,
        pontos_notaveis = NULL,
        geom = ST_Force2D(
            ST_SetSRID(
                ST_GeomFromGeoJSON(:geometria_geojson),
                4326
            )
        )
    WHERE id = :rota_id
    """
)

SQL_EXCLUIR_PONTOS_ROTA = text(
    """
    DELETE FROM semed.rotas_pontos_notaveis
    WHERE rota_id = :rota_id
    """
)

SQL_EXCLUIR_ROTA = text(
    """
    DELETE FROM semed.rotas_geral
    WHERE id = :rota_id
    """
)

SQL_INSERIR_PONTO = text(
    """
    INSERT INTO semed.rotas_pontos_notaveis (
        rota_id,
        ordem,
        referencia,
        coordenadas,
        lat,
        lon,
        lado_via,
        logradouro,
        direcao_seguir,
        atualizado_em
    ) VALUES (
        :rota_id,
        :ordem,
        :referencia,
        :coordenadas,
        :lat,
        :lon,
        :lado_via,
        :logradouro,
        :direcao_seguir,
        NOW()
    )
    """
)

SQL_CHAVES_ESTRANGEIRAS_ROTA = text(
    """
    SELECT
        ns.nspname AS esquema,
        cls.relname AS tabela,
        att.attname AS coluna
    FROM pg_constraint AS con
    INNER JOIN pg_class AS cls
        ON cls.oid = con.conrelid
    INNER JOIN pg_namespace AS ns
        ON ns.oid = cls.relnamespace
    INNER JOIN LATERAL unnest(con.conkey)
        WITH ORDINALITY AS origem(attnum, ordem)
        ON TRUE
    INNER JOIN LATERAL unnest(con.confkey)
        WITH ORDINALITY AS destino(attnum, ordem)
        ON destino.ordem = origem.ordem
    INNER JOIN pg_attribute AS att
        ON att.attrelid = con.conrelid
       AND att.attnum = origem.attnum
    INNER JOIN pg_attribute AS att_destino
        ON att_destino.attrelid = con.confrelid
       AND att_destino.attnum = destino.attnum
    WHERE con.contype = 'f'
      AND con.confrelid = 'semed.rotas_geral'::regclass
      AND array_length(con.conkey, 1) = 1
      AND att_destino.attname = 'id'
    ORDER BY
        ns.nspname,
        cls.relname,
        att.attname
    """
)

SQL_PONTOS_BACKUP = text(
    """
    SELECT
        id,
        rota_id,
        ordem,
        referencia,
        coordenadas,
        lat,
        lon,
        lado_via,
        logradouro,
        direcao_seguir,
        criado_em,
        atualizado_em
    FROM semed.rotas_pontos_notaveis
    WHERE rota_id = :rota_id
    ORDER BY ordem, id
    """
)

SQL_DUPLICIDADES_RESTANTES = text(
    """
    SELECT
        LOWER(BTRIM(nome_rota)) AS nome_normalizado,
        UPPER(BTRIM(trecho)) AS trecho_normalizado,
        COUNT(*) AS quantidade,
        ARRAY_AGG(id ORDER BY id) AS ids
    FROM semed.rotas_geral
    WHERE nome_rota IS NOT NULL
      AND BTRIM(nome_rota) <> ''
      AND trecho IS NOT NULL
      AND BTRIM(trecho) <> ''
    GROUP BY
        LOWER(BTRIM(nome_rota)),
        UPPER(BTRIM(trecho))
    HAVING COUNT(*) > 1
    ORDER BY
        LOWER(BTRIM(nome_rota)),
        UPPER(BTRIM(trecho))
    """
)

SQL_CRIAR_INDICE_UNICO = text(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS
        uq_rotas_geral_nome_trecho_normalizado
    ON semed.rotas_geral (
        LOWER(BTRIM(nome_rota)),
        UPPER(BTRIM(trecho))
    )
    WHERE nome_rota IS NOT NULL
      AND BTRIM(nome_rota) <> ''
      AND trecho IS NOT NULL
      AND BTRIM(trecho) <> ''
    """
)

SQL_VALIDAR_IMPORTACAO = text(
    """
    SELECT
        rg.id AS rota_id,
        rg.nome_rota,
        rg.regiao,
        UPPER(BTRIM(rg.trecho)) AS trecho,
        COALESCE(rg.total_pontos, 0) AS pontos_informados,
        COUNT(p.id) AS pontos_importados
    FROM semed.rotas_geral AS rg
    LEFT JOIN semed.rotas_pontos_notaveis AS p
        ON p.rota_id = rg.id
    WHERE LOWER(BTRIM(rg.nome_rota)) = LOWER(BTRIM(:nome_rota))
      AND UPPER(BTRIM(rg.trecho)) = UPPER(BTRIM(:trecho))
    GROUP BY
        rg.id,
        rg.nome_rota,
        rg.regiao,
        rg.trecho,
        rg.total_pontos
    ORDER BY rg.id
    """
)


# ==========================================
# ESTRUTURAS
# ==========================================


@dataclass(frozen=True)
class PontoGeoJSON:
    ordem: int
    referencia: str
    coordenadas: str | None
    lat: float | None
    lon: float | None
    lado_via: str | None
    logradouro: str | None
    direcao_seguir: str | None


@dataclass(frozen=True)
class TrechoGeoJSON:
    nome_rota: str
    regiao: str
    trecho: str
    total_pontos: int
    pontos: tuple[PontoGeoJSON, ...]
    geometria: dict[str, Any]

    @property
    def chave(self) -> tuple[str, str]:
        return (
            self.nome_rota.strip().casefold(),
            self.trecho.strip().upper(),
        )


@dataclass
class ResultadoImportacao:
    nome_rota: str
    regiao: str
    trecho: str
    status: str
    rota_id: int | None = None
    total_pontos: int = 0
    duplicadas_removidas: int = 0
    mensagem: str = ""


# ==========================================
# NORMALIZAÇÃO E VALIDAÇÃO
# ==========================================


def texto_limpo(valor: Any, padrao: str = "") -> str:
    if valor is None:
        return padrao

    texto = str(valor).strip()
    return texto or padrao


def inteiro_seguro(valor: Any, padrao: int | None = None) -> int | None:
    try:
        if valor in (None, ""):
            return padrao
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def float_seguro(valor: Any) -> float | None:
    try:
        if valor in (None, "", "N/A", "NA"):
            return None
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def normalizar_trecho(valor: Any) -> str:
    trecho = texto_limpo(valor).upper()

    if trecho not in {"IDA", "VOLTA"}:
        raise ValueError(
            f"Trecho inválido: {valor!r}. Use 'Ida' ou 'Volta'."
        )

    return trecho.title()


def normalizar_texto_opcional(valor: Any) -> str | None:
    texto = texto_limpo(valor)

    if texto.upper() in {
        "",
        "N/A",
        "NA",
        "NÃO INFORMADO",
        "NAO INFORMADO",
    }:
        return None

    return texto


def validar_geometria(geometria: Any, indice: int) -> dict[str, Any]:
    if not isinstance(geometria, dict):
        raise ValueError(
            f"Feição {indice}: geometria ausente ou inválida."
        )

    tipo = texto_limpo(geometria.get("type"))

    if tipo not in {"LineString", "MultiLineString"}:
        raise ValueError(
            f"Feição {indice}: geometria {tipo!r} não suportada."
        )

    coordenadas = geometria.get("coordinates")

    if not isinstance(coordenadas, list) or not coordenadas:
        raise ValueError(
            f"Feição {indice}: geometria sem coordenadas."
        )

    return geometria


def ler_ponto(
    valor: Any,
    *,
    indice_feicao: int,
    indice_ponto: int,
) -> PontoGeoJSON:
    if not isinstance(valor, dict):
        raise ValueError(
            f"Feição {indice_feicao}, ponto {indice_ponto}: "
            "o ponto não é um objeto JSON."
        )

    ordem = inteiro_seguro(
        valor.get("ordem"),
        indice_ponto,
    )

    if ordem is None or ordem <= 0:
        raise ValueError(
            f"Feição {indice_feicao}, ponto {indice_ponto}: "
            f"ordem inválida {valor.get('ordem')!r}."
        )

    referencia = texto_limpo(
        valor.get("referencia"),
        "Ponto sem referência",
    )

    lat = float_seguro(valor.get("lat"))
    lon = float_seguro(valor.get("lon"))

    if lat is not None and not -90 <= lat <= 90:
        raise ValueError(
            f"Feição {indice_feicao}, ponto {indice_ponto}: "
            f"latitude inválida {lat}."
        )

    if lon is not None and not -180 <= lon <= 180:
        raise ValueError(
            f"Feição {indice_feicao}, ponto {indice_ponto}: "
            f"longitude inválida {lon}."
        )

    coordenadas = normalizar_texto_opcional(
        valor.get("coordenadas")
    )

    if coordenadas is None and lat is not None and lon is not None:
        coordenadas = f"{lat:.6f}, {lon:.6f}"

    return PontoGeoJSON(
        ordem=ordem,
        referencia=referencia,
        coordenadas=coordenadas,
        lat=lat,
        lon=lon,
        lado_via=normalizar_texto_opcional(
            valor.get("lado_via")
        ),
        logradouro=normalizar_texto_opcional(
            valor.get("logradouro")
        ),
        direcao_seguir=normalizar_texto_opcional(
            valor.get("direcao_seguir")
        ),
    )


def carregar_geojson(caminho: Path) -> tuple[list[TrechoGeoJSON], list[str]]:
    with caminho.open("r", encoding="utf-8-sig") as arquivo:
        dados = json.load(arquivo)

    if not isinstance(dados, dict):
        raise ValueError("O arquivo não contém um objeto GeoJSON.")

    if dados.get("type") != "FeatureCollection":
        raise ValueError(
            "O arquivo precisa ser um GeoJSON do tipo FeatureCollection."
        )

    feicoes = dados.get("features")

    if not isinstance(feicoes, list):
        raise ValueError("O GeoJSON não possui uma lista de feições.")

    trechos: list[TrechoGeoJSON] = []
    avisos: list[str] = []
    chaves_encontradas: set[tuple[str, str]] = set()

    for indice_feicao, feicao in enumerate(feicoes, start=1):
        if not isinstance(feicao, dict):
            raise ValueError(
                f"Feição {indice_feicao}: conteúdo inválido."
            )

        propriedades = feicao.get("properties")

        if not isinstance(propriedades, dict):
            raise ValueError(
                f"Feição {indice_feicao}: properties ausente."
            )

        nome_rota = texto_limpo(propriedades.get("nome_rota"))
        regiao = texto_limpo(propriedades.get("regiao"))
        trecho = normalizar_trecho(propriedades.get("trecho"))

        if not nome_rota:
            raise ValueError(
                f"Feição {indice_feicao}: nome_rota vazio."
            )

        if not regiao:
            raise ValueError(
                f"Feição {indice_feicao}: regiao vazia."
            )

        geometria = validar_geometria(
            feicao.get("geometry"),
            indice_feicao,
        )

        pontos_brutos = propriedades.get("pontos_notaveis")

        if not isinstance(pontos_brutos, list):
            raise ValueError(
                f"Feição {indice_feicao} ({nome_rota} - {trecho}): "
                "pontos_notaveis precisa ser uma lista JSON válida."
            )

        pontos = tuple(
            ler_ponto(
                ponto,
                indice_feicao=indice_feicao,
                indice_ponto=indice_ponto,
            )
            for indice_ponto, ponto in enumerate(
                pontos_brutos,
                start=1,
            )
        )

        ordens = [ponto.ordem for ponto in pontos]

        if len(ordens) != len(set(ordens)):
            raise ValueError(
                f"Feição {indice_feicao} ({nome_rota} - {trecho}): "
                "existem ordens de pontos duplicadas."
            )

        total_informado = inteiro_seguro(
            propriedades.get("total_pontos"),
            len(pontos),
        )

        if total_informado != len(pontos):
            avisos.append(
                f"{nome_rota} - {trecho}: total_pontos="
                f"{total_informado}, mas a lista possui {len(pontos)}. "
                "O importador usará a quantidade real da lista."
            )

        trecho_geojson = TrechoGeoJSON(
            nome_rota=nome_rota,
            regiao=regiao,
            trecho=trecho,
            total_pontos=len(pontos),
            pontos=tuple(sorted(pontos, key=lambda item: item.ordem)),
            geometria=geometria,
        )

        if trecho_geojson.chave in chaves_encontradas:
            raise ValueError(
                f"O GeoJSON possui a rota duplicada: "
                f"{nome_rota} - {trecho}."
            )

        chaves_encontradas.add(trecho_geojson.chave)
        trechos.append(trecho_geojson)

    return trechos, avisos


# ==========================================
# HELPERS DE BANCO
# ==========================================


def verificar_tabelas() -> None:
    resultado = db.session.execute(
        SQL_TABELAS_OBRIGATORIAS
    ).mappings().one()

    faltantes = [
        nome
        for nome, valor in resultado.items()
        if valor is None
    ]

    if faltantes:
        raise RuntimeError(
            "As tabelas obrigatórias não existem: "
            + ", ".join(faltantes)
        )


def buscar_rotas_existentes(
    trecho: TrechoGeoJSON,
) -> list[dict[str, Any]]:
    registros = (
        db.session.execute(
            SQL_BUSCAR_ROTAS_EXISTENTES,
            {
                "nome_rota": trecho.nome_rota,
                "trecho": trecho.trecho,
            },
        )
        .mappings()
        .all()
    )

    return [dict(registro) for registro in registros]


def identificador_sql(valor: str) -> str:
    return '"' + valor.replace('"', '""') + '"'


def chaves_estrangeiras_da_rota() -> list[dict[str, str]]:
    return [
        dict(registro)
        for registro in db.session.execute(
            SQL_CHAVES_ESTRANGEIRAS_ROTA
        ).mappings().all()
    ]


def atualizar_referencias_duplicada(
    rota_duplicada_id: int,
    rota_canonica_id: int,
    chaves_estrangeiras: list[dict[str, str]],
) -> None:
    for chave in chaves_estrangeiras:
        esquema = chave["esquema"]
        tabela = chave["tabela"]
        coluna = chave["coluna"]

        if (
            esquema == "semed"
            and tabela == "rotas_pontos_notaveis"
            and coluna == "rota_id"
        ):
            continue

        comando = text(
            "UPDATE "
            f"{identificador_sql(esquema)}."
            f"{identificador_sql(tabela)} "
            f"SET {identificador_sql(coluna)} = :rota_canonica_id "
            f"WHERE {identificador_sql(coluna)} = :rota_duplicada_id"
        )

        db.session.execute(
            comando,
            {
                "rota_canonica_id": rota_canonica_id,
                "rota_duplicada_id": rota_duplicada_id,
            },
        )


def inserir_ou_atualizar_rota(
    trecho: TrechoGeoJSON,
    registros_existentes: list[dict[str, Any]],
    chaves_estrangeiras: list[dict[str, str]],
) -> tuple[int, int, str]:
    parametros = {
        "nome_rota": trecho.nome_rota,
        "regiao": trecho.regiao,
        "trecho": trecho.trecho,
        "total_pontos": trecho.total_pontos,
        "geometria_geojson": json.dumps(
            trecho.geometria,
            ensure_ascii=False,
        ),
    }

    if not registros_existentes:
        rota_id = db.session.execute(
            SQL_INSERIR_ROTA,
            parametros,
        ).scalar_one()

        status = "INSERIDA"
        duplicadas_removidas = 0

    else:
        rota_id = int(registros_existentes[0]["id"])
        duplicadas = registros_existentes[1:]

        for duplicada in duplicadas:
            duplicada_id = int(duplicada["id"])

            atualizar_referencias_duplicada(
                duplicada_id,
                rota_id,
                chaves_estrangeiras,
            )

            db.session.execute(
                SQL_EXCLUIR_PONTOS_ROTA,
                {"rota_id": duplicada_id},
            )

            db.session.execute(
                SQL_EXCLUIR_ROTA,
                {"rota_id": duplicada_id},
            )

        db.session.execute(
            SQL_ATUALIZAR_ROTA,
            {
                **parametros,
                "rota_id": rota_id,
            },
        )

        duplicadas_removidas = len(duplicadas)
        status = (
            "CONSOLIDADA"
            if duplicadas_removidas
            else "ATUALIZADA"
        )

    db.session.execute(
        SQL_EXCLUIR_PONTOS_ROTA,
        {"rota_id": rota_id},
    )

    for ponto in trecho.pontos:
        db.session.execute(
            SQL_INSERIR_PONTO,
            {
                "rota_id": rota_id,
                "ordem": ponto.ordem,
                "referencia": ponto.referencia,
                "coordenadas": ponto.coordenadas,
                "lat": ponto.lat,
                "lon": ponto.lon,
                "lado_via": ponto.lado_via,
                "logradouro": ponto.logradouro,
                "direcao_seguir": ponto.direcao_seguir,
            },
        )

    return rota_id, duplicadas_removidas, status


# ==========================================
# BACKUP E RELATÓRIOS
# ==========================================


def calcular_sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()

    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)

    return resumo.hexdigest()


def valor_json(valor: Any) -> Any:
    if valor is None:
        return None

    if isinstance(valor, Decimal):
        return str(valor)

    if hasattr(valor, "isoformat"):
        return valor.isoformat()

    return valor


def criar_backup(
    trechos: list[TrechoGeoJSON],
    destino: Path,
    arquivo_geojson: Path,
) -> Path:
    destino.mkdir(parents=True, exist_ok=True)

    momento = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = destino / f"backup_rotas_antes_importacao_{momento}.json"

    rotas_backup: list[dict[str, Any]] = []
    ids_incluidos: set[int] = set()

    for trecho in trechos:
        for registro in buscar_rotas_existentes(trecho):
            rota_id = int(registro["id"])

            if rota_id in ids_incluidos:
                continue

            pontos = [
                {
                    chave: valor_json(valor)
                    for chave, valor in dict(ponto).items()
                }
                for ponto in db.session.execute(
                    SQL_PONTOS_BACKUP,
                    {"rota_id": rota_id},
                ).mappings().all()
            ]

            rotas_backup.append(
                {
                    "rota": {
                        chave: valor_json(valor)
                        for chave, valor in registro.items()
                    },
                    "pontos": pontos,
                }
            )

            ids_incluidos.add(rota_id)

    conteudo = {
        "gerado_em": datetime.now().isoformat(),
        "arquivo_geojson": str(arquivo_geojson),
        "sha256_geojson": calcular_sha256(arquivo_geojson),
        "total_rotas_backup": len(rotas_backup),
        "rotas": rotas_backup,
    }

    with caminho.open("w", encoding="utf-8") as arquivo:
        json.dump(
            conteudo,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    return caminho


def escrever_relatorio(
    resultados: list[ResultadoImportacao],
    destino: Path,
) -> Path:
    destino.mkdir(parents=True, exist_ok=True)

    momento = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = destino / f"relatorio_importacao_rotas_{momento}.csv"

    with caminho.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=[
                "nome_rota",
                "regiao",
                "trecho",
                "status",
                "rota_id",
                "total_pontos",
                "duplicadas_removidas",
                "mensagem",
            ],
            delimiter=";",
        )

        escritor.writeheader()

        for resultado in resultados:
            escritor.writerow(
                {
                    "nome_rota": resultado.nome_rota,
                    "regiao": resultado.regiao,
                    "trecho": resultado.trecho,
                    "status": resultado.status,
                    "rota_id": resultado.rota_id or "",
                    "total_pontos": resultado.total_pontos,
                    "duplicadas_removidas": resultado.duplicadas_removidas,
                    "mensagem": resultado.mensagem,
                }
            )

    return caminho


def escrever_avisos(
    avisos: list[str],
    destino: Path,
) -> Path | None:
    if not avisos:
        return None

    destino.mkdir(parents=True, exist_ok=True)
    momento = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = destino / f"avisos_importacao_rotas_{momento}.txt"
    caminho.write_text("\n".join(avisos), encoding="utf-8")
    return caminho


# ==========================================
# COMANDO FLASK
# ==========================================


def registrar_comandos_rotas_geojson(app: Flask) -> None:
    @app.cli.command("importar-rotas-geojson")
    @click.option(
        "--arquivo",
        type=click.Path(
            path_type=Path,
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
        required=True,
        help="Arquivo GeoJSON com as rotas e os pontos notáveis.",
    )
    @click.option(
        "--aplicar",
        is_flag=True,
        help=(
            "Grava as alterações no banco. Sem esta opção, o comando "
            "apenas valida e simula a importação."
        ),
    )
    @click.option(
        "--rota",
        default=None,
        help="Processa somente um nome de rota específico.",
    )
    @click.option(
        "--regiao",
        default=None,
        help="Processa somente uma região específica.",
    )
    @click.option(
        "--relatorios",
        type=click.Path(
            path_type=Path,
            file_okay=False,
            dir_okay=True,
        ),
        default=Path("instance/relatorios/rotas_geojson"),
        show_default=True,
        help="Pasta de relatórios da importação.",
    )
    @click.option(
        "--backups",
        type=click.Path(
            path_type=Path,
            file_okay=False,
            dir_okay=True,
        ),
        default=Path("instance/backups/rotas_geojson"),
        show_default=True,
        help="Pasta do backup anterior à consolidação.",
    )
    @click.option(
        "--sem-indice-unico",
        is_flag=True,
        help="Não tenta criar o índice que bloqueia novas duplicidades.",
    )
    def importar_rotas_geojson(
        arquivo: Path,
        aplicar: bool,
        rota: str | None,
        regiao: str | None,
        relatorios: Path,
        backups: Path,
        sem_indice_unico: bool,
    ) -> None:
        """Importa geometrias e pontos, preservando IDs e consolidando duplicadas."""

        projeto_raiz = Path(current_app.root_path).resolve()

        if not arquivo.is_absolute():
            arquivo = (projeto_raiz / arquivo).resolve()

        if not relatorios.is_absolute():
            relatorios = (projeto_raiz / relatorios).resolve()

        if not backups.is_absolute():
            backups = (projeto_raiz / backups).resolve()

        click.echo("\nValidação do GeoJSON")
        click.echo(f"Arquivo: {arquivo}")

        try:
            trechos, avisos = carregar_geojson(arquivo)
        except (OSError, json.JSONDecodeError, ValueError) as erro:
            raise click.ClickException(str(erro)) from erro

        filtro_rota = texto_limpo(rota).casefold() if rota else None
        filtro_regiao = texto_limpo(regiao).casefold() if regiao else None

        if filtro_rota:
            trechos = [
                item
                for item in trechos
                if item.nome_rota.casefold() == filtro_rota
            ]

        if filtro_regiao:
            trechos = [
                item
                for item in trechos
                if item.regiao.casefold() == filtro_regiao
            ]

        if not trechos:
            raise click.ClickException(
                "Nenhuma feição corresponde aos filtros informados."
            )

        nomes_rotas = {item.nome_rota for item in trechos}
        total_pontos = sum(item.total_pontos for item in trechos)
        sem_coordenadas = sum(
            1
            for item in trechos
            for ponto in item.pontos
            if ponto.lat is None or ponto.lon is None
        )

        click.echo(f"Feições válidas: {len(trechos)}")
        click.echo(f"Rotas distintas: {len(nomes_rotas)}")
        click.echo(f"Pontos notáveis: {total_pontos}")
        click.echo(f"Pontos sem latitude/longitude: {sem_coordenadas}")
        click.echo(f"SHA-256: {calcular_sha256(arquivo)}")

        try:
            verificar_tabelas()
        except (RuntimeError, SQLAlchemyError) as erro:
            db.session.rollback()
            raise click.ClickException(str(erro)) from erro

        resultados: list[ResultadoImportacao] = []

        for trecho in trechos:
            existentes = buscar_rotas_existentes(trecho)

            if not existentes:
                status = "VALIDADO_NOVO"
                mensagem = "Será criada uma nova linha em rotas_geral."
            elif len(existentes) == 1:
                status = "VALIDADO_ATUALIZAR"
                mensagem = (
                    f"Será preservado o ID {existentes[0]['id']} e os pontos "
                    "serão substituídos pelos dados válidos do GeoJSON."
                )
            else:
                status = "VALIDADO_CONSOLIDAR"
                ids = ", ".join(str(item["id"]) for item in existentes)
                mensagem = (
                    f"Existem {len(existentes)} registros ({ids}). "
                    f"Será preservado o ID {existentes[0]['id']} e os demais "
                    "serão consolidados."
                )

            resultados.append(
                ResultadoImportacao(
                    nome_rota=trecho.nome_rota,
                    regiao=trecho.regiao,
                    trecho=trecho.trecho,
                    status=status,
                    rota_id=(
                        int(existentes[0]["id"])
                        if existentes
                        else None
                    ),
                    total_pontos=trecho.total_pontos,
                    duplicadas_removidas=max(0, len(existentes) - 1),
                    mensagem=mensagem,
                )
            )

        relatorio_validacao = escrever_relatorio(
            resultados,
            relatorios,
        )
        arquivo_avisos = escrever_avisos(
            avisos,
            relatorios,
        )

        click.echo(f"Relatório da validação: {relatorio_validacao}")

        if arquivo_avisos:
            click.echo(f"Avisos: {arquivo_avisos}")

        if not aplicar:
            db.session.rollback()
            click.echo(
                "\nNenhuma alteração foi gravada. "
                "Execute novamente com --aplicar após conferir o relatório.\n"
            )
            return

        click.echo("\nCriando backup anterior à importação...")

        try:
            caminho_backup = criar_backup(
                trechos,
                backups,
                arquivo,
            )
            click.echo(f"Backup: {caminho_backup}")

            chaves_estrangeiras = chaves_estrangeiras_da_rota()
            resultados_aplicacao: list[ResultadoImportacao] = []

            for indice, trecho in enumerate(trechos, start=1):
                click.echo(
                    f"[{indice}/{len(trechos)}] "
                    f"{trecho.nome_rota} — {trecho.trecho}"
                )

                existentes = buscar_rotas_existentes(trecho)

                rota_id, duplicadas_removidas, status = (
                    inserir_ou_atualizar_rota(
                        trecho,
                        existentes,
                        chaves_estrangeiras,
                    )
                )

                resultados_aplicacao.append(
                    ResultadoImportacao(
                        nome_rota=trecho.nome_rota,
                        regiao=trecho.regiao,
                        trecho=trecho.trecho,
                        status=status,
                        rota_id=rota_id,
                        total_pontos=trecho.total_pontos,
                        duplicadas_removidas=duplicadas_removidas,
                    )
                )

            duplicidades_restantes = [
                dict(item)
                for item in db.session.execute(
                    SQL_DUPLICIDADES_RESTANTES
                ).mappings().all()
            ]

            mensagem_indice = ""

            if not sem_indice_unico:
                if duplicidades_restantes:
                    mensagem_indice = (
                        "O índice único não foi criado porque ainda existem "
                        f"{len(duplicidades_restantes)} chaves duplicadas fora "
                        "do conjunto importado."
                    )
                    avisos.append(mensagem_indice)
                else:
                    db.session.execute(SQL_CRIAR_INDICE_UNICO)
                    mensagem_indice = (
                        "Índice único de nome_rota + trecho criado/verificado."
                    )

            inconsistencias: list[str] = []

            for trecho in trechos:
                validacoes = db.session.execute(
                    SQL_VALIDAR_IMPORTACAO,
                    {
                        "nome_rota": trecho.nome_rota,
                        "trecho": trecho.trecho,
                    },
                ).mappings().all()

                if len(validacoes) != 1:
                    inconsistencias.append(
                        f"{trecho.nome_rota} - {trecho.trecho}: "
                        f"foram encontrados {len(validacoes)} registros."
                    )
                    continue

                validacao = validacoes[0]

                if (
                    int(validacao["pontos_importados"])
                    != trecho.total_pontos
                ):
                    inconsistencias.append(
                        f"{trecho.nome_rota} - {trecho.trecho}: "
                        f"esperados {trecho.total_pontos}, encontrados "
                        f"{validacao['pontos_importados']}."
                    )

            if inconsistencias:
                raise RuntimeError(
                    "A validação posterior encontrou inconsistências:\n"
                    + "\n".join(inconsistencias)
                )

            db.session.commit()

            relatorio_aplicacao = escrever_relatorio(
                resultados_aplicacao,
                relatorios,
            )

            arquivo_avisos = escrever_avisos(
                avisos,
                relatorios,
            )

            inseridas = sum(
                item.status == "INSERIDA"
                for item in resultados_aplicacao
            )
            atualizadas = sum(
                item.status == "ATUALIZADA"
                for item in resultados_aplicacao
            )
            consolidadas = sum(
                item.status == "CONSOLIDADA"
                for item in resultados_aplicacao
            )
            duplicadas_removidas = sum(
                item.duplicadas_removidas
                for item in resultados_aplicacao
            )

            click.echo("\nImportação concluída")
            click.echo(f"Feições inseridas: {inseridas}")
            click.echo(f"Feições atualizadas: {atualizadas}")
            click.echo(f"Feições consolidadas: {consolidadas}")
            click.echo(
                f"Registros duplicados removidos: {duplicadas_removidas}"
            )
            click.echo(f"Pontos importados: {total_pontos}")
            click.echo(mensagem_indice)
            click.echo(f"Relatório: {relatorio_aplicacao}")

            if arquivo_avisos:
                click.echo(f"Avisos: {arquivo_avisos}")

            click.echo("")

        except Exception as erro:
            db.session.rollback()
            current_app.logger.exception(
                "Erro ao importar rotas do GeoJSON %s.",
                arquivo,
            )
            raise click.ClickException(str(erro)) from erro
