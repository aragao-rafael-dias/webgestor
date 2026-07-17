# ==========================================
# ROTAS DE REQUISIÇÕES
# ==========================================

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import and_, exists, false, func, select

from models import (
    Requisicao,
    Setor,
    Usuario,
    UsuarioEscola,
    UsuarioSetor,
    db,
)
from permissoes import diretor_pode_acessar_escola
from servicos.setores import usuario_pertence_ao_setor


requisicoes_bp = Blueprint("requisicoes", __name__)


def consulta_escolas_ativas_diretor():
    return select(UsuarioEscola.escola_id).where(
        UsuarioEscola.usuario_id == current_user.id,
        UsuarioEscola.ativo.is_(True),
        UsuarioEscola.inicio_vinculo <= func.current_date(),
        (
            UsuarioEscola.fim_vinculo.is_(None)
            | (UsuarioEscola.fim_vinculo >= func.current_date())
        ),
    )


def consulta_setores_ativos_usuario():
    return select(UsuarioSetor.setor_id).where(
        UsuarioSetor.usuario_id == current_user.id,
        UsuarioSetor.ativo.is_(True),
        UsuarioSetor.inicio_vinculo <= func.current_date(),
        (
            UsuarioSetor.fim_vinculo.is_(None)
            | (UsuarioSetor.fim_vinculo >= func.current_date())
        ),
    )


def aplicar_escopo_requisicoes(consulta):
    perfil = current_user.perfil

    if perfil in {
        Usuario.PERFIL_ADMIN,
        Usuario.PERFIL_AUDITOR,
    }:
        return consulta

    if perfil == Usuario.PERFIL_DIRETOR:
        return consulta.where(
            Requisicao.escola_id.in_(consulta_escolas_ativas_diretor())
        )

    if perfil == Usuario.PERFIL_SETOR:
        return consulta.where(
            Requisicao.setor_id.in_(consulta_setores_ativos_usuario())
        )

    return consulta.where(false())


def usuario_pode_consultar_requisicoes():
    return (
        current_user.is_authenticated
        and current_user.ativo
        and current_user.perfil
        in {
            Usuario.PERFIL_ADMIN,
            Usuario.PERFIL_AUDITOR,
            Usuario.PERFIL_DIRETOR,
            Usuario.PERFIL_SETOR,
        }
    )


def serializar_requisicao(requisicao):
    return {
        "id": requisicao.id,
        "escola_id": requisicao.escola_id,
        "setor_id": requisicao.setor_id,
        "setor": requisicao.setor.nome if requisicao.setor else None,
        "setor_sigla": requisicao.setor.sigla if requisicao.setor else None,
        "tipo": requisicao.tipo,
        "descricao": requisicao.descricao,
        "status": requisicao.status,
        "resposta_semed": requisicao.resposta_semed,
        "respondido_por_id": requisicao.respondido_por_id,
        "respondido_por": (
            requisicao.respondido_por.nome
            if requisicao.respondido_por
            else None
        ),
        "data_criacao": (
            requisicao.data_criacao.isoformat()
            if requisicao.data_criacao
            else None
        ),
        "data_resposta": (
            requisicao.data_resposta.isoformat()
            if requisicao.data_resposta
            else None
        ),
    }


@requisicoes_bp.get("/api/requisicoes/setores-disponiveis")
@login_required
def setores_disponiveis():
    setores = (
        db.session.execute(
            db.select(Setor)
            .where(Setor.ativo.is_(True))
            .order_by(Setor.ordem.asc(), Setor.nome.asc())
        )
        .scalars()
        .all()
    )

    return jsonify(
        [
            {
                "id": setor.id,
                "nome": setor.nome,
                "nome_completo": setor.nome_completo,
                "sigla": setor.sigla,
                "tipo": setor.tipo,
                "setor_pai_id": setor.setor_pai_id,
                "setor_pai": setor.setor_pai.nome if setor.setor_pai else None,
            }
            for setor in setores
        ]
    )


@requisicoes_bp.get("/api/escolas/<int:escola_id>/requisicoes")
@login_required
def get_requisicoes(escola_id):
    if not usuario_pode_consultar_requisicoes():
        return jsonify({
            "sucesso": False,
            "erro": "Você não possui permissão para consultar requisições.",
        }), 403

    if (
        current_user.perfil == Usuario.PERFIL_DIRETOR
        and not diretor_pode_acessar_escola(escola_id)
    ):
        return jsonify({
            "sucesso": False,
            "erro": "Você não possui vínculo ativo com esta escola.",
        }), 403

    consulta = (
        db.select(Requisicao)
        .where(Requisicao.escola_id == escola_id)
        .order_by(Requisicao.data_criacao.desc())
    )
    consulta = aplicar_escopo_requisicoes(consulta)

    requisicoes = db.session.execute(consulta).scalars().all()

    return jsonify([
        serializar_requisicao(requisicao)
        for requisicao in requisicoes
    ])


@requisicoes_bp.post("/api/requisicoes")
@login_required
def criar_requisicao():
    if (
        not current_user.ativo
        or current_user.perfil != Usuario.PERFIL_DIRETOR
    ):
        return jsonify({
            "sucesso": False,
            "erro": "Somente diretores podem cadastrar requisições.",
        }), 403

    dados = request.get_json(silent=True) or {}

    try:
        escola_id = int(dados.get("escola_id"))
    except (TypeError, ValueError):
        return jsonify({
            "sucesso": False,
            "erro": "Informe uma escola válida.",
        }), 400

    try:
        setor_id = int(dados.get("setor_id"))
    except (TypeError, ValueError):
        return jsonify({
            "sucesso": False,
            "erro": "Selecione o setor responsável.",
        }), 400

    descricao = str(dados.get("descricao") or "").strip()
    tipo = str(dados.get("tipo") or "").strip() or None

    if not descricao:
        return jsonify({
            "sucesso": False,
            "erro": "A descrição da requisição é obrigatória.",
        }), 400

    if len(descricao) > 5000:
        return jsonify({
            "sucesso": False,
            "erro": "A descrição não pode ultrapassar 5.000 caracteres.",
        }), 400

    if not diretor_pode_acessar_escola(escola_id):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Você não possui autorização para cadastrar requisições "
                "nesta escola."
            ),
        }), 403

    setor = db.session.get(Setor, setor_id)

    if setor is None or not setor.ativo:
        return jsonify({
            "sucesso": False,
            "erro": "O setor selecionado não existe ou está inativo.",
        }), 400

    nova_requisicao = Requisicao(
        escola_id=escola_id,
        setor_id=setor.id,
        tipo=tipo,
        descricao=descricao,
        status=Requisicao.STATUS_PENDENTE,
    )

    try:
        db.session.add(nova_requisicao)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Erro ao criar requisição.")
        return jsonify({
            "sucesso": False,
            "erro": "Não foi possível cadastrar a requisição.",
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": "Requisição cadastrada com sucesso.",
        "requisicao": serializar_requisicao(nova_requisicao),
    }), 201


@requisicoes_bp.post("/api/requisicoes/<int:req_id>/responder")
@login_required
def responder_requisicao(req_id):
    if (
        not current_user.ativo
        or current_user.perfil != Usuario.PERFIL_SETOR
    ):
        return jsonify({
            "sucesso": False,
            "erro": "Somente usuários dos setores podem responder requisições.",
        }), 403

    dados = request.get_json(silent=True) or {}
    resposta = str(dados.get("resposta") or "").strip()

    if not resposta:
        return jsonify({
            "sucesso": False,
            "erro": "A resposta não pode ficar vazia.",
        }), 400

    if len(resposta) > 5000:
        return jsonify({
            "sucesso": False,
            "erro": "A resposta não pode ultrapassar 5.000 caracteres.",
        }), 400

    requisicao = db.session.get(Requisicao, req_id)

    if requisicao is None:
        return jsonify({
            "sucesso": False,
            "erro": "Requisição não encontrada.",
        }), 404

    if requisicao.setor_id is None:
        return jsonify({
            "sucesso": False,
            "erro": "Esta requisição antiga ainda não possui setor responsável.",
        }), 409

    if not usuario_pertence_ao_setor(
        current_user.id,
        requisicao.setor_id,
    ):
        return jsonify({
            "sucesso": False,
            "erro": "Esta requisição pertence a outro setor.",
        }), 403

    if requisicao.status == Requisicao.STATUS_RESPONDIDA:
        return jsonify({
            "sucesso": False,
            "erro": "Esta requisição já foi respondida.",
        }), 409

    try:
        requisicao.resposta_semed = resposta
        requisicao.status = Requisicao.STATUS_RESPONDIDA
        requisicao.respondido_por_id = current_user.id
        requisicao.data_resposta = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao responder requisição %s.",
            req_id,
        )
        return jsonify({
            "sucesso": False,
            "erro": "Não foi possível responder a requisição.",
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": "Requisição respondida com sucesso.",
        "requisicao": serializar_requisicao(requisicao),
    }), 200


@requisicoes_bp.get("/api/requisicoes/todas")
@login_required
def get_todas_requisicoes():
    if not usuario_pode_consultar_requisicoes():
        return jsonify({
            "sucesso": False,
            "erro": "Você não possui permissão para consultar requisições.",
        }), 403

    consulta = db.select(Requisicao).order_by(
        Requisicao.data_criacao.desc()
    )
    consulta = aplicar_escopo_requisicoes(consulta)

    requisicoes = db.session.execute(consulta).scalars().all()

    return jsonify([
        serializar_requisicao(requisicao)
        for requisicao in requisicoes
    ])


@requisicoes_bp.get("/api/requisicoes/alertas")
@login_required
def alertas_requisicoes():
    if not usuario_pode_consultar_requisicoes():
        return jsonify({
            "sucesso": False,
            "erro": "Você não possui permissão para consultar alertas.",
        }), 403

    consulta = (
        select(
            Requisicao.escola_id,
            func.count(Requisicao.id).label("quantidade"),
        )
        .where(Requisicao.status == Requisicao.STATUS_PENDENTE)
    )

    if current_user.perfil == Usuario.PERFIL_DIRETOR:
        vinculo_ativo = exists().where(
            and_(
                UsuarioEscola.usuario_id == current_user.id,
                UsuarioEscola.escola_id == Requisicao.escola_id,
                UsuarioEscola.ativo.is_(True),
                UsuarioEscola.inicio_vinculo <= func.current_date(),
                (
                    UsuarioEscola.fim_vinculo.is_(None)
                    | (UsuarioEscola.fim_vinculo >= func.current_date())
                ),
            )
        )
        consulta = consulta.where(vinculo_ativo)

    elif current_user.perfil == Usuario.PERFIL_SETOR:
        consulta = consulta.where(
            Requisicao.setor_id.in_(consulta_setores_ativos_usuario())
        )

    consulta = consulta.group_by(Requisicao.escola_id)
    resultado = db.session.execute(consulta).all()

    return jsonify([
        {
            "escola_id": escola_id,
            "quantidade": quantidade,
        }
        for escola_id, quantidade in resultado
    ])
