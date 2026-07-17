# ==========================================
# ROTAS DE ESCOLAS E PAINEL CONTEXTUAL
# ==========================================

import json

from flask import Blueprint, jsonify
from flask_login import current_user, login_required
from sqlalchemy import func, text

from models import (
    Escola,
    EscolaPainel,
    Requisicao,
    Setor,
    Usuario,
    UsuarioEscola,
    UsuarioSetor,
    db,
)


escolas_bp = Blueprint("escolas", __name__)


def primeiro_valor(dados, *chaves):
    for chave in chaves:
        valor = dados.get(chave)
        if valor not in (None, "", [], {}):
            return valor
    return None


def contagens_requisicoes_por_campo(campo, ids):
    resultado = {
        item_id: {
            "total": 0,
            "pendentes": 0,
            "respondidas": 0,
        }
        for item_id in ids
    }

    if not ids:
        return resultado

    linhas = (
        db.session.execute(
            db.select(
                campo,
                Requisicao.status,
                func.count(Requisicao.id),
            )
            .where(campo.in_(ids))
            .group_by(campo, Requisicao.status)
        )
        .all()
    )

    for item_id, status, quantidade in linhas:
        if item_id not in resultado:
            continue

        resultado[item_id]["total"] += quantidade

        if status == Requisicao.STATUS_PENDENTE:
            resultado[item_id]["pendentes"] += quantidade
        elif status == Requisicao.STATUS_RESPONDIDA:
            resultado[item_id]["respondidas"] += quantidade

    return resultado


def serializar_escola_painel(escola, painel, contagens):
    dados_websig = (
        painel.dados_websig
        if painel and isinstance(painel.dados_websig, dict)
        else {}
    )

    endereco = ", ".join(
        str(parte).strip()
        for parte in (
            escola.logradouro,
            escola.numero_de_porta,
            escola.bairro_povoado_assentamento,
        )
        if parte not in (None, "")
    ) or None

    return {
        "id": escola.id,
        "nome": escola.nome or f"Escola {escola.id}",
        "imagem_url": painel.imagem_url if painel else None,
        "tipo_de_escola": escola.tipo_de_escola,
        "turno": escola.turno,
        "endereco": endereco,
        "bairro": escola.bairro_povoado_assentamento,
        "logradouro": escola.logradouro,
        "numero_de_porta": escola.numero_de_porta,
        "observacao": escola.observacao,
        "alunos": primeiro_valor(
            dados_websig,
            "alunos",
            "quantidade_alunos",
            "total_alunos",
            "matriculas",
            "quantidade_matriculas",
        ),
        "turmas": primeiro_valor(
            dados_websig,
            "turmas",
            "quantidade_turmas",
            "total_turmas",
        ),
        "modalidades": primeiro_valor(
            dados_websig,
            "modalidades",
            "modalidade",
            "etapas",
        ),
        "telefone": primeiro_valor(
            dados_websig,
            "telefone",
            "telefone_escola",
        ),
        "diretor": primeiro_valor(
            dados_websig,
            "diretor",
            "nome_diretor",
        ),
        "codigo_inep": primeiro_valor(
            dados_websig,
            "codigo_inep",
            "inep",
            "codigo",
        ),
        "dados_websig": dados_websig,
        "requisicoes": contagens,
    }


def serializar_setor_painel(vinculo, setor, contagens):
    return {
        "id": setor.id,
        "nome": setor.nome,
        "nome_completo": setor.nome_completo,
        "sigla": setor.sigla,
        "tipo": setor.tipo,
        "principal": vinculo.principal,
        "setor_pai": setor.setor_pai.nome if setor.setor_pai else None,
        "descricao": setor.descricao,
        "competencias": setor.competencias or [],
        "imagem_url": setor.imagem_url,
        "dados_websig": setor.dados_websig or {},
        "requisicoes": contagens,
    }


@escolas_bp.get("/api/escolas")
@login_required
def api_escolas():
    sql = text("""
        SELECT jsonb_build_object(
            'type',
            'FeatureCollection',
            'features',
            COALESCE(
                jsonb_agg(features.feature),
                '[]'::jsonb
            )
        )
        FROM (
            SELECT jsonb_build_object(
                'type',
                'Feature',
                'id',
                id,
                'geometry',
                ST_AsGeoJSON(
                    ST_Transform(
                        ST_SetSRID(geom, 31984),
                        4326
                    )
                )::jsonb,
                'properties',
                to_jsonb(inputs) - 'geom'
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
        resultado
        or {
            "type": "FeatureCollection",
            "features": [],
        }
    )


@escolas_bp.get("/api/minhas-escolas")
@login_required
def minhas_escolas():
    if current_user.perfil != Usuario.PERFIL_DIRETOR:
        return jsonify({
            "sucesso": False,
            "erro": "Somente diretores possuem escolas vinculadas.",
        }), 403

    resultado = (
        db.session.execute(
            db.select(Escola.id, Escola.nome)
            .join(
                UsuarioEscola,
                UsuarioEscola.escola_id == Escola.id,
            )
            .where(
                UsuarioEscola.usuario_id == current_user.id,
                UsuarioEscola.ativo.is_(True),
                UsuarioEscola.inicio_vinculo <= func.current_date(),
                (
                    UsuarioEscola.fim_vinculo.is_(None)
                    | (UsuarioEscola.fim_vinculo >= func.current_date())
                ),
            )
            .order_by(Escola.nome.asc())
        )
        .all()
    )

    return jsonify([
        {
            "id": escola_id,
            "nome": nome or f"Escola {escola_id}",
        }
        for escola_id, nome in resultado
    ])


@escolas_bp.get("/api/painel-contextual")
@login_required
def painel_contextual():
    perfil = current_user.perfil

    if perfil == Usuario.PERFIL_DIRETOR:
        linhas = (
            db.session.execute(
                db.select(Escola, EscolaPainel)
                .join(
                    UsuarioEscola,
                    UsuarioEscola.escola_id == Escola.id,
                )
                .outerjoin(
                    EscolaPainel,
                    EscolaPainel.escola_id == Escola.id,
                )
                .where(
                    UsuarioEscola.usuario_id == current_user.id,
                    UsuarioEscola.ativo.is_(True),
                    UsuarioEscola.inicio_vinculo <= func.current_date(),
                    (
                        UsuarioEscola.fim_vinculo.is_(None)
                        | (UsuarioEscola.fim_vinculo >= func.current_date())
                    ),
                )
                .order_by(Escola.nome.asc())
            )
            .all()
        )

        ids = [escola.id for escola, painel in linhas]
        contagens = contagens_requisicoes_por_campo(
            Requisicao.escola_id,
            ids,
        )

        itens = [
            serializar_escola_painel(
                escola,
                painel,
                contagens.get(
                    escola.id,
                    {
                        "total": 0,
                        "pendentes": 0,
                        "respondidas": 0,
                    },
                ),
            )
            for escola, painel in linhas
        ]

        return jsonify({
            "tipo": "DIRETOR",
            "titulo": "Minhas escolas",
            "itens": itens,
            "principal_id": itens[0]["id"] if itens else None,
        })

    if perfil == Usuario.PERFIL_SETOR:
        linhas = (
            db.session.execute(
                db.select(UsuarioSetor, Setor)
                .join(Setor, Setor.id == UsuarioSetor.setor_id)
                .where(
                    UsuarioSetor.usuario_id == current_user.id,
                    UsuarioSetor.ativo.is_(True),
                    UsuarioSetor.inicio_vinculo <= func.current_date(),
                    (
                        UsuarioSetor.fim_vinculo.is_(None)
                        | (UsuarioSetor.fim_vinculo >= func.current_date())
                    ),
                    Setor.ativo.is_(True),
                )
                .order_by(
                    UsuarioSetor.principal.desc(),
                    Setor.ordem.asc(),
                    Setor.nome.asc(),
                )
            )
            .all()
        )

        ids = [setor.id for vinculo, setor in linhas]
        contagens = contagens_requisicoes_por_campo(
            Requisicao.setor_id,
            ids,
        )

        itens = [
            serializar_setor_painel(
                vinculo,
                setor,
                contagens.get(
                    setor.id,
                    {
                        "total": 0,
                        "pendentes": 0,
                        "respondidas": 0,
                    },
                ),
            )
            for vinculo, setor in linhas
        ]

        principal_id = next(
            (item["id"] for item in itens if item["principal"]),
            itens[0]["id"] if itens else None,
        )

        return jsonify({
            "tipo": "SETOR",
            "titulo": "Meus setores",
            "itens": itens,
            "principal_id": principal_id,
        })

    if perfil in {Usuario.PERFIL_ADMIN, Usuario.PERFIL_AUDITOR}:
        total_requisicoes = db.session.execute(
            db.select(func.count(Requisicao.id))
        ).scalar_one()

        pendentes = db.session.execute(
            db.select(func.count(Requisicao.id)).where(
                Requisicao.status == Requisicao.STATUS_PENDENTE
            )
        ).scalar_one()

        respondidas = db.session.execute(
            db.select(func.count(Requisicao.id)).where(
                Requisicao.status == Requisicao.STATUS_RESPONDIDA
            )
        ).scalar_one()

        total_escolas = db.session.execute(
            db.select(func.count(Escola.id))
        ).scalar_one()

        total_setores = db.session.execute(
            db.select(func.count(Setor.id)).where(Setor.ativo.is_(True))
        ).scalar_one()

        return jsonify({
            "tipo": perfil,
            "titulo": (
                "Panorama administrativo"
                if perfil == Usuario.PERFIL_ADMIN
                else "Panorama de auditoria"
            ),
            "resumo": {
                "requisicoes": total_requisicoes,
                "pendentes": pendentes,
                "respondidas": respondidas,
                "escolas": total_escolas,
                "setores": total_setores,
            },
        })

    return jsonify({
        "sucesso": False,
        "erro": "Perfil sem painel contextual.",
    }), 403
