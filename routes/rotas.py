from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db
from servicos.importacao_rotas_memorial import (
    importar_docx,
    nome_rota_banco,
    normalizar_regiao_banco,
    pontos_para_json,
    salvar_upload_temporario,
    validar_geojson_linha,
)
from servicos.memoriais_docx import extrair_metadados_docx

rotas_bp = Blueprint("rotas", __name__)


SQL_ROTAS_EXISTENTES = text("""
    SELECT
        id,
        nome_rota,
        regiao,
        trecho,
        total_pontos,
        CASE WHEN geom IS NULL THEN 0 ELSE ST_NPoints(geom) END AS vertices,
        CASE
            WHEN geom IS NULL OR ST_IsEmpty(geom) OR ST_SRID(geom) <= 0
                THEN NULL
            ELSE ROUND((ST_Length(ST_Transform(ST_Force2D(geom), 31984)) / 1000.0)::numeric, 3)
        END AS extensao_km,
        CASE
            WHEN geom IS NULL OR ST_IsEmpty(geom) OR ST_SRID(geom) <= 0
                THEN NULL
            WHEN ST_SRID(geom) = 4326
                THEN ST_AsGeoJSON(ST_Force2D(geom))::jsonb
            ELSE ST_AsGeoJSON(ST_Transform(ST_Force2D(geom), 4326))::jsonb
        END AS geometria
    FROM semed.rotas_geral
    WHERE LOWER(BTRIM(nome_rota)) = LOWER(BTRIM(:nome_rota))
    ORDER BY
        CASE UPPER(BTRIM(trecho))
            WHEN 'IDA' THEN 1
            WHEN 'VOLTA' THEN 2
            ELSE 3
        END,
        id
""")

SQL_BUSCAR_IDS_TRECHO = text("""
    SELECT id
    FROM semed.rotas_geral
    WHERE LOWER(BTRIM(nome_rota)) = LOWER(BTRIM(:nome_rota))
      AND UPPER(BTRIM(trecho)) = :trecho
    ORDER BY id
""")

SQL_ATUALIZAR_TRECHO = text("""
    UPDATE semed.rotas_geral
    SET
        geom = ST_SetSRID(ST_GeomFromGeoJSON(:geom_geojson), 4326),
        regiao = CASE WHEN BTRIM(:regiao) <> '' THEN :regiao ELSE regiao END,
        total_pontos = :total_pontos,
        pontos_notaveis = :pontos_notaveis
    WHERE id = :rota_id
    RETURNING id
""")

SQL_INSERIR_TRECHO = text("""
    INSERT INTO semed.rotas_geral (
        geom,
        nome_rota,
        regiao,
        trecho,
        total_pontos,
        pontos_notaveis
    ) VALUES (
        ST_SetSRID(ST_GeomFromGeoJSON(:geom_geojson), 4326),
        :nome_rota,
        :regiao,
        :trecho_exibicao,
        :total_pontos,
        :pontos_notaveis
    )
    RETURNING id
""")

SQL_VALIDAR_TRECHO = text("""
    SELECT
        id,
        nome_rota,
        trecho,
        ST_SRID(geom) AS srid,
        ST_IsValid(geom) AS valida,
        ST_NPoints(geom) AS vertices
    FROM semed.rotas_geral
    WHERE id = :rota_id
""")

SQL_TABELA_MEMORIAIS = text("SELECT to_regclass('semed.rotas_memoriais')")
SQL_COLUNAS_MEMORIAIS = text("""
    SELECT column_name, data_type, udt_name
    FROM information_schema.columns
    WHERE table_schema = 'semed'
      AND table_name = 'rotas_memoriais'
""")
SQL_CONTAR_MEMORIAL = text("""
    SELECT COUNT(*)
    FROM semed.rotas_memoriais
    WHERE LOWER(BTRIM(codigo_rota)) = LOWER(BTRIM(:codigo_rota))
""")

CAMPOS_MEMORIAL = (
    "numero_linha",
    "linha",
    "km_ida",
    "km_volta",
    "turnos_ativos",
    "horarios",
    "tipo_veiculo",
    "quantidade_veiculos",
    "onibus_pcd",
    "inicio",
    "termino",
    "rede_ensino",
    "redes_ensino",
    "localizacao",
    "areas",
    "intermunicipal",
    "assistente_mobilidade",
    "assistente_nome",
    "veiculo_placa",
    "motorista",
    "contato",
    "escolas_atendidas",
    "observacao",
    "responsavel_tecnico",
    "crea",
    "executora",
)
CAMPOS_JSON_MEMORIAL = {
    "turnos_ativos",
    "horarios",
    "redes_ensino",
    "areas",
    "escolas_atendidas",
}
TURNOS_VALIDOS = ("MANHÃ", "TARDE", "NOITE", "INTEGRAL")


def _somente_admin() -> None:
    if getattr(current_user, "perfil", None) != "ADMIN":
        abort(403)


def _existentes_para_json(nome_rota: str) -> list[dict]:
    linhas = db.session.execute(
        SQL_ROTAS_EXISTENTES,
        {"nome_rota": nome_rota},
    ).mappings().all()
    return [dict(linha) for linha in linhas]


def _id_trecho_existente(nome_rota: str, trecho: str) -> int | None:
    ids = list(
        db.session.execute(
            SQL_BUSCAR_IDS_TRECHO,
            {"nome_rota": nome_rota, "trecho": trecho},
        ).scalars()
    )
    if len(ids) > 1:
        raise ValueError(
            f"Existem {len(ids)} registros de {trecho} para {nome_rota}. "
            "Corrija a duplicidade antes de importar o memorial."
        )
    return int(ids[0]) if ids else None


def _decimal_para_float(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _metadados_docx_para_formulario(caminho: Path) -> dict[str, Any]:
    dados = extrair_metadados_docx(caminho)
    return {
        "numero_linha": dados.numero_linha,
        "linha": dados.linha,
        "km_ida": _decimal_para_float(dados.km_ida),
        "km_volta": _decimal_para_float(dados.km_volta),
        "turnos_ativos": list(dados.turnos_ativos),
        "horarios": dict(dados.horarios),
        "tipo_veiculo": dados.tipo_veiculo or "",
        "quantidade_veiculos": dados.quantidade_veiculos,
        "onibus_pcd": dados.onibus_pcd,
        "inicio": dados.inicio,
        "termino": dados.termino,
        "rede_ensino": dados.rede_ensino or "",
        "redes_ensino": list(dados.redes_ensino),
        "localizacao": dados.localizacao,
        "areas": list(dados.areas),
        "intermunicipal": dados.intermunicipal,
        "assistente_mobilidade": dados.assistente_mobilidade,
        "assistente_nome": dados.assistente_nome,
        "veiculo_placa": dados.veiculo_placa,
        "motorista": dados.motorista,
        "contato": dados.contato,
        "escolas_atendidas": list(dados.escolas_atendidas),
        "observacao": dados.observacao,
        "responsavel_tecnico": dados.responsavel_tecnico,
        "crea": dados.crea,
        "executora": dados.executora or "Topocart",
    }


def _texto(valor: Any, limite: int = 2000) -> str:
    return str(valor or "").strip()[:limite]


def _booleano_opcional(valor: Any) -> bool | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return valor
    texto_valor = str(valor).strip().lower()
    if texto_valor in {"1", "true", "sim", "s", "yes", "on"}:
        return True
    if texto_valor in {"0", "false", "não", "nao", "n", "no", "off"}:
        return False
    raise ValueError(f"Valor booleano inválido: {valor}.")


def _lista_textos(valor: Any, limite_itens: int = 100) -> list[str]:
    if not isinstance(valor, list):
        return []
    resultado: list[str] = []
    vistos: set[str] = set()
    for item in valor[:limite_itens]:
        texto_item = _texto(item, 500)
        chave = texto_item.casefold()
        if texto_item and chave not in vistos:
            resultado.append(texto_item)
            vistos.add(chave)
    return resultado


def _numero_opcional(valor: Any, nome: str) -> float | None:
    if valor in (None, ""):
        return None
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome} precisa ser um número válido.") from exc
    if numero < 0:
        raise ValueError(f"{nome} não pode ser negativo.")
    return round(numero, 3)


def _normalizar_metadados_recebidos(rota: dict[str, Any]) -> dict[str, Any]:
    origem = rota.get("metadados") or {}
    numero_linha = _texto(rota.get("numero_linha") or origem.get("numero_linha"), 100)
    linha = _texto(origem.get("linha") or rota.get("linha"), 1000)

    quantidade = origem.get("quantidade_veiculos")
    if quantidade in (None, ""):
        quantidade_normalizada = None
    else:
        try:
            quantidade_normalizada = int(quantidade)
        except (TypeError, ValueError) as exc:
            raise ValueError("Quantidade de veículos precisa ser um número inteiro.") from exc
        if not 1 <= quantidade_normalizada <= 99:
            raise ValueError("Quantidade de veículos deve ficar entre 1 e 99.")

    turnos = [
        turno
        for turno in _lista_textos(origem.get("turnos_ativos"), 4)
        if turno.upper() in TURNOS_VALIDOS
    ]
    turnos = [turno.upper() for turno in turnos]

    horarios_origem = origem.get("horarios") if isinstance(origem.get("horarios"), dict) else {}
    horarios: dict[str, dict[str, str]] = {}
    for turno in TURNOS_VALIDOS:
        item = horarios_origem.get(turno) or {}
        if not isinstance(item, dict):
            continue
        horarios[turno] = {
            "horario": _texto(item.get("horario"), 20),
            "inicio_aulas": _texto(item.get("inicio_aulas"), 20),
            "termino_aulas": _texto(item.get("termino_aulas"), 20),
        }

    redes = [item.upper() for item in _lista_textos(origem.get("redes_ensino"), 10)]
    areas = [item.upper() for item in _lista_textos(origem.get("areas"), 10)]

    return {
        "numero_linha": numero_linha,
        "linha": linha,
        "km_ida": _numero_opcional(origem.get("km_ida"), "Km IDA"),
        "km_volta": _numero_opcional(origem.get("km_volta"), "Km VOLTA"),
        "turnos_ativos": turnos,
        "horarios": horarios,
        "tipo_veiculo": _texto(origem.get("tipo_veiculo"), 100).upper(),
        "quantidade_veiculos": quantidade_normalizada,
        "onibus_pcd": _booleano_opcional(origem.get("onibus_pcd")),
        "inicio": _texto(origem.get("inicio"), 1000),
        "termino": _texto(origem.get("termino"), 1000),
        "rede_ensino": redes[0] if redes else "",
        "redes_ensino": redes,
        "localizacao": _texto(origem.get("localizacao"), 500),
        "areas": areas,
        "intermunicipal": _booleano_opcional(origem.get("intermunicipal")),
        "assistente_mobilidade": _booleano_opcional(origem.get("assistente_mobilidade")),
        "assistente_nome": _texto(origem.get("assistente_nome"), 250),
        "veiculo_placa": _texto(origem.get("veiculo_placa"), 150),
        "motorista": _texto(origem.get("motorista"), 250),
        "contato": _texto(origem.get("contato"), 150),
        "escolas_atendidas": _lista_textos(origem.get("escolas_atendidas"), 100),
        "observacao": _texto(origem.get("observacao"), 5000),
        "responsavel_tecnico": _texto(origem.get("responsavel_tecnico"), 250),
        "crea": _texto(origem.get("crea"), 150),
        "executora": _texto(origem.get("executora") or "Topocart", 250),
    }


def _salvar_metadados_memorial(codigo_rota: str, dados: dict[str, Any]) -> None:
    if not db.session.execute(SQL_TABELA_MEMORIAIS).scalar_one_or_none():
        raise ValueError(
            "A tabela semed.rotas_memoriais ainda não existe. "
            "Execute 'flask db upgrade' antes de salvar a importação."
        )

    colunas = {
        linha["column_name"]: dict(linha)
        for linha in db.session.execute(SQL_COLUNAS_MEMORIAIS).mappings().all()
    }
    obrigatorias = {"codigo_rota", *CAMPOS_MEMORIAL}
    faltantes = sorted(obrigatorias - set(colunas))
    if faltantes:
        raise ValueError(
            "A tabela semed.rotas_memoriais está desatualizada. "
            "Execute 'flask db upgrade'. Campos ausentes: " + ", ".join(faltantes)
        )

    quantidade = db.session.execute(
        SQL_CONTAR_MEMORIAL,
        {"codigo_rota": codigo_rota},
    ).scalar_one()
    if quantidade > 1:
        raise ValueError(
            f"Há {quantidade} registros de memorial para {codigo_rota}. "
            "Corrija a duplicidade antes de importar."
        )

    parametros: dict[str, Any] = {"codigo_rota": codigo_rota}
    expressoes: dict[str, str] = {}
    for campo in CAMPOS_MEMORIAL:
        valor = dados.get(campo)
        tipo = str(colunas[campo].get("data_type") or "").lower()
        udt = str(colunas[campo].get("udt_name") or "").lower()

        if campo in CAMPOS_JSON_MEMORIAL:
            serializado = json.dumps(valor, ensure_ascii=False)
            parametros[campo] = serializado
            if tipo == "jsonb" or udt == "jsonb":
                expressoes[campo] = f"CAST(:{campo} AS jsonb)"
            elif tipo == "json" or udt == "json":
                expressoes[campo] = f"CAST(:{campo} AS json)"
            else:
                expressoes[campo] = f":{campo}"
        else:
            parametros[campo] = valor
            expressoes[campo] = f":{campo}"

    if quantidade == 1:
        atribuicoes = ", ".join(f"{campo} = {expressoes[campo]}" for campo in CAMPOS_MEMORIAL)
        if "atualizado_em" in colunas:
            atribuicoes += ", atualizado_em = NOW()"
        comando = text(
            "UPDATE semed.rotas_memoriais SET "
            + atribuicoes
            + " WHERE LOWER(BTRIM(codigo_rota)) = LOWER(BTRIM(:codigo_rota))"
        )
    else:
        campos = ["codigo_rota", *CAMPOS_MEMORIAL]
        valores = [":codigo_rota", *[expressoes[campo] for campo in CAMPOS_MEMORIAL]]
        comando = text(
            "INSERT INTO semed.rotas_memoriais ("
            + ", ".join(campos)
            + ") VALUES ("
            + ", ".join(valores)
            + ")"
        )

    db.session.execute(comando, parametros)


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
                        ST_AsGeoJSON(ST_Transform(geom, 4326))::jsonb
                    ELSE
                        CASE
                            WHEN ST_X(ST_Centroid(geom)) > 100000 THEN
                                ST_AsGeoJSON(ST_Transform(ST_SetSRID(geom, 31984), 4326))::jsonb
                            ELSE
                                ST_AsGeoJSON(ST_SetSRID(geom, 4326))::jsonb
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
    return jsonify(resultado or {"type": "FeatureCollection", "features": []})


@rotas_bp.route("/rotas/importar-memorial")
@login_required
def importar_memorial():
    _somente_admin()
    return render_template("rotas/importar_memorial.html")


@rotas_bp.route("/api/rotas/importar-memorial/preview", methods=["POST"])
@login_required
def preview_importacao_memorial():
    _somente_admin()

    arquivo = request.files.get("memorial")
    if arquivo is None or not arquivo.filename:
        return jsonify({"sucesso": False, "erro": "Selecione um arquivo DOCX."}), 400

    caminho: Path | None = None
    try:
        limite_bytes = int(current_app.config.get("MEMORIAL_MAX_BYTES", 10 * 1024 * 1024))
        if request.content_length and request.content_length > limite_bytes + (1024 * 1024):
            return jsonify({"sucesso": False, "erro": "O memorial excede o limite de 10 MB."}), 413

        caminho = salvar_upload_temporario(arquivo)
        if caminho.stat().st_size > limite_bytes:
            raise ValueError("O memorial excede o limite de 10 MB.")

        osrm_url = current_app.config.get("OSRM_BASE_URL", "https://router.project-osrm.org")
        timeout = int(current_app.config.get("OSRM_TIMEOUT", 45))
        importado = importar_docx(caminho, osrm_base_url=osrm_url, timeout=timeout)
        dados = importado.para_dict()
        dados["metadados"] = _metadados_docx_para_formulario(caminho)
        dados["registros_existentes"] = _existentes_para_json(importado.nome_rota)

        return jsonify({"sucesso": True, "rota": dados})

    except (ValueError, OSError) as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 422
    except Exception:
        current_app.logger.exception("Falha ao importar memorial DOCX")
        return jsonify({
            "sucesso": False,
            "erro": "Não foi possível processar o memorial ou calcular a rota.",
        }), 500
    finally:
        if caminho is not None:
            try:
                caminho.unlink(missing_ok=True)
            except OSError:
                current_app.logger.warning("Não foi possível remover o DOCX temporário: %s", caminho)


@rotas_bp.route("/api/rotas/importar-memorial/salvar", methods=["POST"])
@login_required
def salvar_importacao_memorial():
    _somente_admin()
    dados = request.get_json(silent=True) or {}
    rota = dados.get("rota") or {}

    numero_linha = _texto(rota.get("numero_linha"), 100)
    try:
        nome_rota = nome_rota_banco(numero_linha)
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400

    regiao = normalizar_regiao_banco(_texto(rota.get("regiao"), 100))
    alertas = rota.get("alertas_geometria") or []
    if alertas and not bool(dados.get("confirmar_alertas")):
        return jsonify({
            "sucesso": False,
            "erro": "A prévia possui alertas de geometria. Confirme a revisão antes de salvar.",
        }), 409

    trechos = rota.get("trechos") or {}
    if set(trechos) != {"IDA", "VOLTA"}:
        return jsonify({
            "sucesso": False,
            "erro": "O memorial precisa conter os trechos IDA e VOLTA.",
        }), 400

    alterados: list[dict] = []
    try:
        metadados = _normalizar_metadados_recebidos(rota)
        metadados["numero_linha"] = numero_linha

        for nome_trecho in ("IDA", "VOLTA"):
            trecho = trechos[nome_trecho] or {}
            pontos = trecho.get("pontos") or []
            pontos_json = pontos_para_json(pontos)
            geom_json = validar_geojson_linha(trecho.get("geometria"), pontos=pontos)

            existente = _id_trecho_existente(nome_rota, nome_trecho)
            parametros = {
                "nome_rota": nome_rota,
                "regiao": regiao,
                "trecho": nome_trecho,
                "trecho_exibicao": "Ida" if nome_trecho == "IDA" else "Volta",
                "total_pontos": len(pontos),
                "pontos_notaveis": pontos_json,
                "geom_geojson": geom_json,
            }

            if existente is not None:
                parametros["rota_id"] = existente
                rota_id = db.session.execute(SQL_ATUALIZAR_TRECHO, parametros).scalar_one()
                acao = "atualizado"
            else:
                rota_id = db.session.execute(SQL_INSERIR_TRECHO, parametros).scalar_one()
                acao = "criado"

            validacao = db.session.execute(
                SQL_VALIDAR_TRECHO,
                {"rota_id": rota_id},
            ).mappings().one()

            if validacao["srid"] != 4326 or not validacao["valida"]:
                raise ValueError(f"A geometria de {nome_trecho} não passou na validação PostGIS.")

            alterados.append({
                "id": rota_id,
                "trecho": nome_trecho,
                "acao": acao,
                "vertices": validacao["vertices"],
            })

        _salvar_metadados_memorial(nome_rota, metadados)
        db.session.commit()
        return jsonify({
            "sucesso": True,
            "mensagem": f"{nome_rota} e os dados do memorial foram salvos com sucesso.",
            "registros": alterados,
            "metadados_salvos": True,
        })

    except (ValueError, TypeError, KeyError) as exc:
        db.session.rollback()
        return jsonify({"sucesso": False, "erro": str(exc)}), 422
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha de banco ao salvar rota importada")
        return jsonify({
            "sucesso": False,
            "erro": "O banco recusou a atualização. Nenhum trecho ou dado do memorial foi salvo.",
        }), 500
