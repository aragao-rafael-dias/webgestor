from flask import Blueprint
from flask import jsonify
from flask import request

from models import db
from models import Requisicao

requisicoes_bp = Blueprint(
    "requisicoes",
    __name__
)


@requisicoes_bp.route(
    "/api/requisicoes",
    methods=["POST"]
)
def criar_requisicao():

    dados = request.get_json()

    nova_req = Requisicao(
        escola_id=dados["escola_id"],
        descricao=dados["descricao"],
        status="Pendente"
    )

    db.session.add(nova_req)
    db.session.commit()

    return jsonify(
        {
            "mensagem":
            "Requisição criada com sucesso!"
        }
    ), 201


@requisicoes_bp.route(
    "/api/requisicoes/<int:req_id>/responder",
    methods=["POST"]
)
def responder_requisicao(req_id):

    dados = request.get_json()

    req = Requisicao.query.get(req_id)

    if not req:

        return jsonify(
            {
                "erro":
                "Requisição não encontrada"
            }
        ), 404

    req.resposta_semed = dados.get("resposta")
    req.status = "Respondida"

    db.session.commit()

    return jsonify(
        {
            "mensagem":
            "Requisição respondida com sucesso!"
        }
    ), 200


@requisicoes_bp.route(
    "/api/requisicoes/todas",
    methods=["GET"]
)
def get_todas_requisicoes():

    requisicoes = (
        Requisicao.query
        .order_by(
            Requisicao.data_criacao.desc()
        )
        .all()
    )

    dados = [

        {
            "id": req.id,
            "escola_id": req.escola_id,
            "descricao": req.descricao,
            "status": req.status,
            "resposta_semed": req.resposta_semed
        }

        for req in requisicoes

    ]

    return jsonify(dados)