from __future__ import annotations

import json
from pathlib import Path

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

rotas_bp = Blueprint(
    "rotas",
    __name__
)


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

        osrm_url = current_app.config.get(
            "OSRM_BASE_URL",
            "https://router.project-osrm.org",
        )
        timeout = int(current_app.config.get("OSRM_TIMEOUT", 45))
        importado = importar_docx(
            caminho,
            osrm_base_url=osrm_url,
            timeout=timeout,
        )
        dados = importado.para_dict()
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

    numero_linha = str(rota.get("numero_linha") or "").strip()
    try:
        nome_rota = nome_rota_banco(numero_linha)
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400

    regiao = normalizar_regiao_banco(str(rota.get("regiao") or ""))
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

        db.session.commit()
        return jsonify({
            "sucesso": True,
            "mensagem": f"{nome_rota} importada com sucesso.",
            "registros": alterados,
        })

    except (ValueError, TypeError, KeyError) as exc:
        db.session.rollback()
        return jsonify({"sucesso": False, "erro": str(exc)}), 422
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha de banco ao salvar rota importada")
        return jsonify({
            "sucesso": False,
            "erro": "O banco recusou a atualização. Nenhum trecho foi salvo.",
        }), 500
