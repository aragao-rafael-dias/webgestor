# ==========================================
# ROTAS DE SETORES
# ==========================================

from functools import wraps

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)

from flask_login import (
    current_user,
    login_required,
)

from sqlalchemy import func

from models import (
    Setor,
    Usuario,
    UsuarioSetor,
    db,
)

from servicos.setores import (
    ErroVinculoSetor,
    obter_vinculos_ativos_usuario,
    sincronizar_setores_usuario,
)


setores_bp = Blueprint(
    "setores",
    __name__,
)


# ==========================================
# PERMISSÃO ADMINISTRATIVA
# ==========================================

def apenas_admin(funcao):
    @wraps(funcao)
    @login_required
    def funcao_protegida(
        *args,
        **kwargs,
    ):
        if (
            not current_user.ativo
            or current_user.perfil
            != Usuario.PERFIL_ADMIN
        ):
            return jsonify({
                "sucesso": False,
                "erro": (
                    "Acesso permitido somente "
                    "a administradores."
                ),
            }), 403

        return funcao(
            *args,
            **kwargs,
        )

    return funcao_protegida


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def serializar_setor(
    setor,
    incluir_dados_websig=False,
):
    dados = {
        "id": setor.id,
        "nome": setor.nome,
        "nome_completo":
            setor.nome_completo,
        "sigla": setor.sigla,
        "tipo": setor.tipo,
        "setor_pai_id":
            setor.setor_pai_id,
        "setor_pai": (
            setor.setor_pai.nome
            if setor.setor_pai
            else None
        ),
        "descricao":
            setor.descricao,
        "competencias":
            setor.competencias or [],
        "imagem_url":
            setor.imagem_url,
        "ativo":
            setor.ativo,
        "ordem":
            setor.ordem,
    }

    if incluir_dados_websig:
        dados["dados_websig"] = (
            setor.dados_websig or {}
        )

    return dados


def normalizar_sigla(valor):
    sigla = str(
        valor or ""
    ).strip().upper()

    return sigla or None


def normalizar_tipo(valor):
    tipo = str(
        valor or Setor.TIPO_OUTRO
    ).strip().upper()

    if tipo not in Setor.TIPOS_VALIDOS:
        tipos = ", ".join(
            Setor.TIPOS_VALIDOS
        )

        raise ValueError(
            "Tipo de setor inválido. "
            f"Tipos aceitos: {tipos}."
        )

    return tipo


def converter_setor_pai_id(
    valor,
):
    if valor in (
        None,
        "",
    ):
        return None

    try:
        setor_pai_id = int(valor)

    except (
        TypeError,
        ValueError,
    ) as erro:
        raise ValueError(
            "O setor superior informado "
            "é inválido."
        ) from erro

    if setor_pai_id <= 0:
        raise ValueError(
            "O setor superior informado "
            "é inválido."
        )

    return setor_pai_id


def converter_ordem(valor):
    if valor in (
        None,
        "",
    ):
        return 0

    try:
        return int(valor)

    except (
        TypeError,
        ValueError,
    ) as erro:
        raise ValueError(
            "A ordem informada é inválida."
        ) from erro


def converter_booleano(
    valor,
    padrao=True,
):
    if valor is None:
        return padrao

    if isinstance(valor, bool):
        return valor

    texto = str(valor).strip().lower()

    if texto in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }:
        return True

    if texto in {
        "0",
        "false",
        "nao",
        "não",
        "no",
        "off",
    }:
        return False

    raise ValueError(
        "O valor do campo ativo é inválido."
    )


def validar_setor_pai(
    setor_pai_id,
    setor_atual_id=None,
):
    if setor_pai_id is None:
        return None

    if (
        setor_atual_id is not None
        and setor_pai_id
        == setor_atual_id
    ):
        raise ValueError(
            "Um setor não pode ser superior "
            "a ele próprio."
        )

    setor_pai = db.session.get(
        Setor,
        setor_pai_id,
    )

    if setor_pai is None:
        raise ValueError(
            "O setor superior não foi encontrado."
        )

    return setor_pai


def validar_sigla_unica(
    sigla,
    setor_atual_id=None,
):
    if sigla is None:
        return

    consulta = db.select(
        Setor.id
    ).where(
        func.lower(Setor.sigla)
        == sigla.lower()
    )

    if setor_atual_id is not None:
        consulta = consulta.where(
            Setor.id
            != setor_atual_id
        )

    existente = (
        db.session.execute(
            consulta.limit(1)
        )
        .scalar_one_or_none()
    )

    if existente is not None:
        raise ValueError(
            "Já existe um setor com essa sigla."
        )


# ==========================================
# LISTA PÚBLICA AOS AUTENTICADOS
# ==========================================

@setores_bp.get(
    "/api/setores"
)
@login_required
def listar_setores():
    setores = (
        db.session.execute(
            db.select(Setor)
            .where(
                Setor.ativo.is_(True)
            )
            .order_by(
                Setor.ordem.asc(),
                Setor.nome.asc(),
            )
        )
        .scalars()
        .all()
    )

    return jsonify([
        serializar_setor(setor)
        for setor in setores
    ])


# ==========================================
# SETORES DO USUÁRIO AUTENTICADO
# ==========================================

@setores_bp.get(
    "/api/meus-setores"
)
@login_required
def meus_setores():
    if (
        current_user.perfil
        != Usuario.PERFIL_SETOR
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "O usuário autenticado não "
                "possui perfil de setor."
            ),
        }), 403

    vinculos = obter_vinculos_ativos_usuario(
        current_user.id
    )

    return jsonify([
        {
            **serializar_setor(
                vinculo.setor,
                incluir_dados_websig=True,
            ),
            "principal":
                vinculo.principal,
            "inicio_vinculo": (
                vinculo.inicio_vinculo
                .isoformat()
                if vinculo.inicio_vinculo
                else None
            ),
        }
        for vinculo in vinculos
    ])


# ==========================================
# ADMIN: LISTAR TODOS OS SETORES
# ==========================================

@setores_bp.get(
    "/api/admin/setores"
)
@apenas_admin
def admin_listar_setores():
    setores = (
        db.session.execute(
            db.select(Setor)
            .order_by(
                Setor.ativo.desc(),
                Setor.ordem.asc(),
                Setor.nome.asc(),
            )
        )
        .scalars()
        .all()
    )

    return jsonify([
        serializar_setor(
            setor,
            incluir_dados_websig=True,
        )
        for setor in setores
    ])


# ==========================================
# ADMIN: CRIAR SETOR
# ==========================================

@setores_bp.post(
    "/api/admin/setores"
)
@apenas_admin
def admin_criar_setor():
    dados = request.get_json(
        silent=True
    ) or {}

    nome = str(
        dados.get("nome")
        or ""
    ).strip()

    if not nome:
        return jsonify({
            "sucesso": False,
            "erro": (
                "O nome do setor é obrigatório."
            ),
        }), 400

    if len(nome) > 180:
        return jsonify({
            "sucesso": False,
            "erro": (
                "O nome do setor não pode "
                "ultrapassar 180 caracteres."
            ),
        }), 400

    try:
        sigla = normalizar_sigla(
            dados.get("sigla")
        )

        tipo = normalizar_tipo(
            dados.get("tipo")
        )

        setor_pai_id = (
            converter_setor_pai_id(
                dados.get("setor_pai_id")
            )
        )

        ordem = converter_ordem(
            dados.get("ordem")
        )

        ativo = converter_booleano(
            dados.get("ativo"),
            padrao=True,
        )

        validar_sigla_unica(
            sigla
        )

        validar_setor_pai(
            setor_pai_id
        )

    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "erro": str(erro),
        }), 400

    descricao = str(
        dados.get("descricao")
        or ""
    ).strip() or None

    competencias = dados.get(
        "competencias"
    ) or []

    dados_websig = dados.get(
        "dados_websig"
    ) or {}

    if not isinstance(
        competencias,
        list,
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "As competências precisam "
                "ser enviadas em uma lista."
            ),
        }), 400

    if not isinstance(
        dados_websig,
        dict,
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Os dados do WebSIG precisam "
                "ser enviados como objeto."
            ),
        }), 400

    setor = Setor(
        nome=nome,
        sigla=sigla,
        tipo=tipo,
        setor_pai_id=setor_pai_id,
        descricao=descricao,
        competencias=competencias,
        imagem_url=(
            str(
                dados.get("imagem_url")
                or ""
            ).strip()
            or None
        ),
        dados_websig=dados_websig,
        ativo=ativo,
        ordem=ordem,
    )

    try:
        db.session.add(
            setor
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao criar setor."
        )

        return jsonify({
            "sucesso": False,
            "erro": (
                "Não foi possível cadastrar "
                "o setor."
            ),
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": (
            "Setor cadastrado com sucesso."
        ),
        "setor": serializar_setor(
            setor,
            incluir_dados_websig=True,
        ),
    }), 201


# ==========================================
# ADMIN: ATUALIZAR SETOR
# ==========================================

@setores_bp.put(
    "/api/admin/setores/<int:setor_id>"
)
@apenas_admin
def admin_atualizar_setor(
    setor_id,
):
    setor = db.session.get(
        Setor,
        setor_id,
    )

    if setor is None:
        return jsonify({
            "sucesso": False,
            "erro": "Setor não encontrado.",
        }), 404

    dados = request.get_json(
        silent=True
    ) or {}

    try:
        if "nome" in dados:
            nome = str(
                dados.get("nome")
                or ""
            ).strip()

            if not nome:
                raise ValueError(
                    "O nome do setor é obrigatório."
                )

            if len(nome) > 180:
                raise ValueError(
                    "O nome do setor não pode "
                    "ultrapassar 180 caracteres."
                )

            setor.nome = nome

        if "sigla" in dados:
            sigla = normalizar_sigla(
                dados.get("sigla")
            )

            validar_sigla_unica(
                sigla,
                setor_atual_id=setor.id,
            )

            setor.sigla = sigla

        if "tipo" in dados:
            setor.tipo = normalizar_tipo(
                dados.get("tipo")
            )

        if "setor_pai_id" in dados:
            setor_pai_id = (
                converter_setor_pai_id(
                    dados.get("setor_pai_id")
                )
            )

            validar_setor_pai(
                setor_pai_id,
                setor_atual_id=setor.id,
            )

            setor.setor_pai_id = (
                setor_pai_id
            )

        if "descricao" in dados:
            setor.descricao = (
                str(
                    dados.get("descricao")
                    or ""
                ).strip()
                or None
            )

        if "imagem_url" in dados:
            setor.imagem_url = (
                str(
                    dados.get("imagem_url")
                    or ""
                ).strip()
                or None
            )

        if "competencias" in dados:
            competencias = (
                dados.get("competencias")
                or []
            )

            if not isinstance(
                competencias,
                list,
            ):
                raise ValueError(
                    "As competências precisam "
                    "ser enviadas em uma lista."
                )

            setor.competencias = competencias

        if "dados_websig" in dados:
            dados_websig = (
                dados.get("dados_websig")
                or {}
            )

            if not isinstance(
                dados_websig,
                dict,
            ):
                raise ValueError(
                    "Os dados do WebSIG precisam "
                    "ser enviados como objeto."
                )

            setor.dados_websig = dados_websig

        if "ativo" in dados:
            setor.ativo = converter_booleano(
                dados.get("ativo"),
                padrao=setor.ativo,
            )

        if "ordem" in dados:
            setor.ordem = converter_ordem(
                dados.get("ordem")
            )

        db.session.commit()

    except ValueError as erro:
        db.session.rollback()

        return jsonify({
            "sucesso": False,
            "erro": str(erro),
        }), 400

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao atualizar setor %s.",
            setor_id,
        )

        return jsonify({
            "sucesso": False,
            "erro": (
                "Não foi possível atualizar "
                "o setor."
            ),
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": (
            "Setor atualizado com sucesso."
        ),
        "setor": serializar_setor(
            setor,
            incluir_dados_websig=True,
        ),
    })


# ==========================================
# ADMIN: SETORES DE UM USUÁRIO
# ==========================================

@setores_bp.get(
    "/api/admin/usuarios/"
    "<int:usuario_id>/setores"
)
@apenas_admin
def admin_setores_usuario(
    usuario_id,
):
    usuario = db.session.get(
        Usuario,
        usuario_id,
    )

    if usuario is None:
        return jsonify({
            "sucesso": False,
            "erro": "Usuário não encontrado.",
        }), 404

    vinculos = (
        db.session.execute(
            db.select(UsuarioSetor)
            .join(
                Setor,
                Setor.id
                == UsuarioSetor.setor_id,
            )
            .where(
                UsuarioSetor.usuario_id
                == usuario.id,

                UsuarioSetor.ativo.is_(
                    True
                ),
            )
            .order_by(
                UsuarioSetor.principal.desc(),
                Setor.ordem.asc(),
                Setor.nome.asc(),
            )
        )
        .scalars()
        .all()
    )

    return jsonify({
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "perfil": usuario.perfil,
        },
        "setor_ids": [
            vinculo.setor_id
            for vinculo in vinculos
        ],
        "setor_principal_id": next(
            (
                vinculo.setor_id
                for vinculo in vinculos
                if vinculo.principal
            ),
            None,
        ),
        "setores": [
            {
                **serializar_setor(
                    vinculo.setor
                ),
                "principal":
                    vinculo.principal,
            }
            for vinculo in vinculos
        ],
    })


# ==========================================
# ADMIN: ATRIBUIR SETORES AO USUÁRIO
# ==========================================

@setores_bp.put(
    "/api/admin/usuarios/"
    "<int:usuario_id>/setores"
)
@apenas_admin
def admin_atribuir_setores_usuario(
    usuario_id,
):
    usuario = db.session.get(
        Usuario,
        usuario_id,
    )

    if usuario is None:
        return jsonify({
            "sucesso": False,
            "erro": "Usuário não encontrado.",
        }), 404

    dados = request.get_json(
        silent=True
    ) or {}

    setor_ids = dados.get(
        "setor_ids"
    ) or []

    setor_principal_id = dados.get(
        "setor_principal_id"
    )

    try:
        setores = sincronizar_setores_usuario(
            usuario=usuario,
            setor_ids=setor_ids,
            setor_principal_id=(
                setor_principal_id
            ),
        )

        db.session.commit()

    except ErroVinculoSetor as erro:
        db.session.rollback()

        return jsonify({
            "sucesso": False,
            "erro": str(erro),
        }), 400

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Erro ao atribuir setores "
            "ao usuário %s.",
            usuario_id,
        )

        return jsonify({
            "sucesso": False,
            "erro": (
                "Não foi possível atualizar "
                "os setores do usuário."
            ),
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": (
            "Setores do usuário atualizados "
            "com sucesso."
        ),
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "perfil": usuario.perfil,
        },
        "setores": [
            serializar_setor(setor)
            for setor in setores
        ],
    })