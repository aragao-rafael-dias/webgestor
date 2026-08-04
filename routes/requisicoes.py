# ==========================================
# REQUISIÇÕES BIDIRECIONAIS
#
# Fluxos permitidos:
#   ESCOLA -> SETOR
#   ESCOLA -> ESCOLA
#   SETOR  -> ESCOLA
#
# Um destinatário pode responder ou encaminhar.
# O histórico é preservado em
# semed.requisicoes_movimentacoes.
# ==========================================

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
)
from flask_login import current_user, login_required
from sqlalchemy import bindparam, func, text

from models import (
    Escola,
    Setor,
    Usuario,
    UsuarioEscola,
    UsuarioSetor,
    db,
)


requisicoes_bp = Blueprint(
    "requisicoes",
    __name__,
)


TIPO_ESCOLA = "ESCOLA"
TIPO_SETOR = "SETOR"

STATUS_PENDENTE = "Pendente"
STATUS_RESPONDIDA = "Respondida"

PERFIS_CONSULTA = {
    Usuario.PERFIL_ADMIN,
    Usuario.PERFIL_AUDITOR,
    Usuario.PERFIL_DIRETOR,
    Usuario.PERFIL_SETOR,
}


SQL_LISTAR_REQUISICOES = text(
    """
    SELECT
        r.id,
        r.escola_id,
        r.setor_id,
        r.tipo,
        r.descricao,
        r.status,
        r.data_criacao,
        r.resposta_semed,
        r.respondido_por_id,
        r.data_resposta,
        r.origem_tipo,
        r.origem_escola_id,
        r.origem_setor_id,
        r.destino_tipo,
        r.destino_escola_id,
        r.destino_setor_id,
        r.criado_por_id,
        r.atualizado_em
    FROM semed.requisicoes AS r
    ORDER BY
        r.data_criacao DESC,
        r.id DESC
    """
)


SQL_BUSCAR_REQUISICAO = text(
    """
    SELECT
        r.id,
        r.escola_id,
        r.setor_id,
        r.tipo,
        r.descricao,
        r.status,
        r.data_criacao,
        r.resposta_semed,
        r.respondido_por_id,
        r.data_resposta,
        r.origem_tipo,
        r.origem_escola_id,
        r.origem_setor_id,
        r.destino_tipo,
        r.destino_escola_id,
        r.destino_setor_id,
        r.criado_por_id,
        r.atualizado_em
    FROM semed.requisicoes AS r
    WHERE r.id = :requisicao_id
    LIMIT 1
    """
)


SQL_INSERIR_REQUISICAO = text(
    """
    INSERT INTO semed.requisicoes (
        escola_id,
        setor_id,
        tipo,
        descricao,
        status,
        origem_tipo,
        origem_escola_id,
        origem_setor_id,
        destino_tipo,
        destino_escola_id,
        destino_setor_id,
        criado_por_id,
        atualizado_em
    ) VALUES (
        :escola_id,
        :setor_id,
        :tipo,
        :descricao,
        :status,
        :origem_tipo,
        :origem_escola_id,
        :origem_setor_id,
        :destino_tipo,
        :destino_escola_id,
        :destino_setor_id,
        :criado_por_id,
        NOW()
    )
    RETURNING id
    """
)


SQL_ATUALIZAR_DESTINO = text(
    """
    UPDATE semed.requisicoes
    SET
        escola_id = :escola_id_legado,
        setor_id = :setor_id_legado,
        destino_tipo = :destino_tipo,
        destino_escola_id = :destino_escola_id,
        destino_setor_id = :destino_setor_id,
        atualizado_em = NOW()
    WHERE id = :requisicao_id
    """
)


SQL_RESPONDER_REQUISICAO = text(
    """
    UPDATE semed.requisicoes
    SET
        resposta_semed = :resposta,
        status = :status,
        respondido_por_id = :respondido_por_id,
        data_resposta = :data_resposta,
        atualizado_em = NOW()
    WHERE id = :requisicao_id
    """
)


SQL_INSERIR_MOVIMENTACAO = text(
    """
    INSERT INTO semed.requisicoes_movimentacoes (
        requisicao_id,
        tipo,
        usuario_id,
        origem_tipo,
        origem_escola_id,
        origem_setor_id,
        destino_tipo,
        destino_escola_id,
        destino_setor_id,
        mensagem
    ) VALUES (
        :requisicao_id,
        :tipo,
        :usuario_id,
        :origem_tipo,
        :origem_escola_id,
        :origem_setor_id,
        :destino_tipo,
        :destino_escola_id,
        :destino_setor_id,
        :mensagem
    )
    """
)


SQL_MOVIMENTACOES = text(
    """
    SELECT
        m.id,
        m.requisicao_id,
        m.tipo,
        m.usuario_id,
        m.origem_tipo,
        m.origem_escola_id,
        m.origem_setor_id,
        m.destino_tipo,
        m.destino_escola_id,
        m.destino_setor_id,
        m.mensagem,
        m.criado_em
    FROM semed.requisicoes_movimentacoes AS m
    WHERE m.requisicao_id IN :requisicao_ids
    ORDER BY
        m.criado_em ASC,
        m.id ASC
    """
).bindparams(
    bindparam(
        "requisicao_ids",
        expanding=True,
    )
)


# ==========================================
# HELPERS
# ==========================================


def texto_limpo(
    valor: Any,
    padrao: str = "",
) -> str:
    if valor is None:
        return padrao

    texto_valor = str(valor).strip()
    return texto_valor or padrao



def inteiro_positivo(
    valor: Any,
) -> int | None:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None

    return numero if numero > 0 else None



def normalizar_tipo_entidade(
    valor: Any,
) -> str:
    tipo = texto_limpo(valor).upper()
    return tipo if tipo in {TIPO_ESCOLA, TIPO_SETOR} else ""



def data_iso(valor: Any) -> str | None:
    return valor.isoformat() if valor else None



def usuario_ativo() -> bool:
    return bool(
        current_user.is_authenticated
        and current_user.ativo
    )



def ids_escolas_ativas_usuario() -> set[int]:
    if (
        not usuario_ativo()
        or current_user.perfil
        != Usuario.PERFIL_DIRETOR
    ):
        return set()

    linhas = db.session.execute(
        db.select(
            UsuarioEscola.escola_id
        ).where(
            UsuarioEscola.usuario_id
            == current_user.id,
            UsuarioEscola.ativo.is_(True),
            UsuarioEscola.inicio_vinculo
            <= func.current_date(),
            (
                UsuarioEscola.fim_vinculo.is_(None)
                | (
                    UsuarioEscola.fim_vinculo
                    >= func.current_date()
                )
            ),
        )
    ).scalars().all()

    return {
        int(escola_id)
        for escola_id in linhas
    }



def ids_setores_ativos_usuario() -> set[int]:
    if (
        not usuario_ativo()
        or current_user.perfil
        != Usuario.PERFIL_SETOR
    ):
        return set()

    linhas = db.session.execute(
        db.select(
            UsuarioSetor.setor_id
        ).join(
            Setor,
            Setor.id == UsuarioSetor.setor_id,
        ).where(
            UsuarioSetor.usuario_id
            == current_user.id,
            UsuarioSetor.ativo.is_(True),
            UsuarioSetor.inicio_vinculo
            <= func.current_date(),
            (
                UsuarioSetor.fim_vinculo.is_(None)
                | (
                    UsuarioSetor.fim_vinculo
                    >= func.current_date()
                )
            ),
            Setor.ativo.is_(True),
        )
    ).scalars().all()

    return {
        int(setor_id)
        for setor_id in linhas
    }



def usuario_controla_entidade(
    tipo: str,
    entidade_id: int | None,
    *,
    escolas_usuario: set[int] | None = None,
    setores_usuario: set[int] | None = None,
) -> bool:
    if entidade_id is None:
        return False

    if tipo == TIPO_ESCOLA:
        escolas = (
            escolas_usuario
            if escolas_usuario is not None
            else ids_escolas_ativas_usuario()
        )
        return entidade_id in escolas

    if tipo == TIPO_SETOR:
        setores = (
            setores_usuario
            if setores_usuario is not None
            else ids_setores_ativos_usuario()
        )
        return entidade_id in setores

    return False



def entidade_existe(
    tipo: str,
    entidade_id: int,
) -> bool:
    if tipo == TIPO_ESCOLA:
        return db.session.get(
            Escola,
            entidade_id,
        ) is not None

    if tipo == TIPO_SETOR:
        setor = db.session.get(
            Setor,
            entidade_id,
        )
        return bool(
            setor is not None
            and setor.ativo
        )

    return False



def nome_entidade(
    tipo: str | None,
    entidade_id: int | None,
    cache: dict[tuple[str, int], str],
) -> str | None:
    if not tipo or entidade_id is None:
        return None

    chave = (tipo, entidade_id)

    if chave in cache:
        return cache[chave]

    nome = None

    if tipo == TIPO_ESCOLA:
        escola = db.session.get(
            Escola,
            entidade_id,
        )
        nome = (
            escola.nome
            if escola
            else None
        )

    elif tipo == TIPO_SETOR:
        setor = db.session.get(
            Setor,
            entidade_id,
        )
        if setor:
            nome = (
                setor.nome_completo
                or setor.nome
            )

    cache[chave] = (
        nome
        or f"{tipo.title()} #{entidade_id}"
    )

    return cache[chave]



def id_entidade_linha(
    linha: dict[str, Any],
    prefixo: str,
) -> int | None:
    tipo = linha.get(
        f"{prefixo}_tipo"
    )

    if tipo == TIPO_ESCOLA:
        return linha.get(
            f"{prefixo}_escola_id"
        )

    if tipo == TIPO_SETOR:
        return linha.get(
            f"{prefixo}_setor_id"
        )

    return None



def entidade_da_linha(
    linha: dict[str, Any],
    prefixo: str,
    cache_nomes: dict[tuple[str, int], str],
) -> dict[str, Any] | None:
    tipo = linha.get(
        f"{prefixo}_tipo"
    )
    entidade_id = id_entidade_linha(
        linha,
        prefixo,
    )

    if not tipo or entidade_id is None:
        return None

    return {
        "tipo": tipo,
        "id": entidade_id,
        "nome": nome_entidade(
            tipo,
            entidade_id,
            cache_nomes,
        ),
    }



def buscar_requisicao(
    requisicao_id: int,
) -> dict[str, Any] | None:
    linha = db.session.execute(
        SQL_BUSCAR_REQUISICAO,
        {
            "requisicao_id":
                requisicao_id,
        },
    ).mappings().first()

    return dict(linha) if linha else None



def buscar_movimentacoes(
    requisicao_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    resultado: dict[
        int,
        list[dict[str, Any]],
    ] = defaultdict(list)

    if not requisicao_ids:
        return resultado

    linhas = db.session.execute(
        SQL_MOVIMENTACOES,
        {
            "requisicao_ids":
                requisicao_ids,
        },
    ).mappings().all()

    for linha in linhas:
        resultado[
            int(linha["requisicao_id"])
        ].append(dict(linha))

    return resultado



def usuario_participa_linha(
    linha: dict[str, Any],
    movimentacoes: list[dict[str, Any]],
    escolas_usuario: set[int],
    setores_usuario: set[int],
) -> bool:
    perfil = current_user.perfil

    if perfil in {
        Usuario.PERFIL_ADMIN,
        Usuario.PERFIL_AUDITOR,
    }:
        return True

    if perfil == Usuario.PERFIL_DIRETOR:
        ids = escolas_usuario
        if not ids:
            return False

        if (
            linha.get("origem_escola_id") in ids
            or linha.get("destino_escola_id") in ids
        ):
            return True

        return any(
            movimento.get("origem_escola_id") in ids
            or movimento.get("destino_escola_id") in ids
            for movimento in movimentacoes
        )

    if perfil == Usuario.PERFIL_SETOR:
        ids = setores_usuario
        if not ids:
            return False

        if (
            linha.get("origem_setor_id") in ids
            or linha.get("destino_setor_id") in ids
        ):
            return True

        return any(
            movimento.get("origem_setor_id") in ids
            or movimento.get("destino_setor_id") in ids
            for movimento in movimentacoes
        )

    return False



def serializar_movimentacao(
    movimento: dict[str, Any],
    cache_nomes: dict[tuple[str, int], str],
    cache_usuarios: dict[int, str],
) -> dict[str, Any]:
    usuario_id = movimento.get("usuario_id")
    usuario_nome = None

    if usuario_id:
        if usuario_id not in cache_usuarios:
            usuario = db.session.get(
                Usuario,
                usuario_id,
            )
            cache_usuarios[usuario_id] = (
                usuario.nome
                if usuario
                else f"Usuário #{usuario_id}"
            )

        usuario_nome = cache_usuarios[usuario_id]

    return {
        "id": movimento.get("id"),
        "tipo": movimento.get("tipo"),
        "usuario_id": usuario_id,
        "usuario": usuario_nome,
        "origem": entidade_da_linha(
            movimento,
            "origem",
            cache_nomes,
        ),
        "destino": entidade_da_linha(
            movimento,
            "destino",
            cache_nomes,
        ),
        "mensagem": movimento.get("mensagem"),
        "criado_em": data_iso(
            movimento.get("criado_em")
        ),
    }



def serializar_requisicao(
    linha: dict[str, Any],
    movimentacoes: list[dict[str, Any]],
    escolas_usuario: set[int],
    setores_usuario: set[int],
    cache_nomes: dict[tuple[str, int], str],
    cache_usuarios: dict[int, str],
) -> dict[str, Any]:
    destino_tipo = linha.get("destino_tipo")
    destino_id = id_entidade_linha(
        linha,
        "destino",
    )

    pendente = (
        linha.get("status")
        == STATUS_PENDENTE
    )

    controla_destino = (
        pendente
        and usuario_controla_entidade(
            destino_tipo,
            destino_id,
            escolas_usuario=escolas_usuario,
            setores_usuario=setores_usuario,
        )
    )

    pode_encaminhar = (
        controla_destino
        and destino_tipo
        in {TIPO_ESCOLA, TIPO_SETOR}
    )

    origem = entidade_da_linha(
        linha,
        "origem",
        cache_nomes,
    )
    destino = entidade_da_linha(
        linha,
        "destino",
        cache_nomes,
    )

    movimentacoes_serializadas = [
        serializar_movimentacao(
            movimento,
            cache_nomes,
            cache_usuarios,
        )
        for movimento in movimentacoes
    ]

    respondido_por_id = linha.get(
        "respondido_por_id"
    )
    respondido_por = None

    if respondido_por_id:
        if respondido_por_id not in cache_usuarios:
            usuario = db.session.get(
                Usuario,
                respondido_por_id,
            )
            cache_usuarios[respondido_por_id] = (
                usuario.nome
                if usuario
                else f"Usuário #{respondido_por_id}"
            )

        respondido_por = cache_usuarios[
            respondido_por_id
        ]

    return {
        "id": linha.get("id"),

        # Campos legados preservados.
        "escola_id": linha.get("escola_id"),
        "setor_id": linha.get("setor_id"),

        "tipo": linha.get("tipo"),
        "descricao": linha.get("descricao"),
        "status": linha.get("status"),
        "resposta_semed": linha.get("resposta_semed"),
        "resposta": linha.get("resposta_semed"),
        "respondido_por_id": respondido_por_id,
        "respondido_por": respondido_por,
        "data_criacao": data_iso(
            linha.get("data_criacao")
        ),
        "data_resposta": data_iso(
            linha.get("data_resposta")
        ),
        "origem": origem,
        "destino": destino,
        "movimentacoes": movimentacoes_serializadas,
        "permissoes": {
            "pode_responder": controla_destino,
            "pode_encaminhar": pode_encaminhar,
            "tipos_destino_encaminhamento": (
                [TIPO_ESCOLA]
                if pode_encaminhar
                else []
            ),
        },
    }



def listar_requisicoes_visiveis() -> list[dict[str, Any]]:
    if (
        not usuario_ativo()
        or current_user.perfil
        not in PERFIS_CONSULTA
    ):
        return []

    linhas = [
        dict(linha)
        for linha in db.session.execute(
            SQL_LISTAR_REQUISICOES
        ).mappings().all()
    ]

    ids = [
        int(linha["id"])
        for linha in linhas
    ]

    movimentos_por_requisicao = (
        buscar_movimentacoes(ids)
    )

    escolas_usuario = (
        ids_escolas_ativas_usuario()
    )
    setores_usuario = (
        ids_setores_ativos_usuario()
    )

    cache_nomes: dict[
        tuple[str, int],
        str,
    ] = {}
    cache_usuarios: dict[int, str] = {}

    resultado = []

    for linha in linhas:
        movimentos = movimentos_por_requisicao.get(
            int(linha["id"]),
            [],
        )

        if not usuario_participa_linha(
            linha,
            movimentos,
            escolas_usuario,
            setores_usuario,
        ):
            continue

        resultado.append(
            serializar_requisicao(
                linha,
                movimentos,
                escolas_usuario,
                setores_usuario,
                cache_nomes,
                cache_usuarios,
            )
        )

    return resultado



def validar_criacao(
    origem_tipo: str,
    origem_id: int,
    destino_tipo: str,
    destino_id: int,
) -> str | None:
    perfil = current_user.perfil

    if perfil == Usuario.PERFIL_DIRETOR:
        if origem_tipo != TIPO_ESCOLA:
            return (
                "Diretores somente podem enviar "
                "requisições a partir de uma escola."
            )

        if origem_id not in ids_escolas_ativas_usuario():
            return (
                "Você não possui vínculo ativo "
                "com a escola de origem."
            )

        if destino_tipo not in {
            TIPO_ESCOLA,
            TIPO_SETOR,
        }:
            return "Destino inválido para uma escola."

    elif perfil == Usuario.PERFIL_SETOR:
        if origem_tipo != TIPO_SETOR:
            return (
                "Usuários de setor somente podem "
                "enviar a partir de um setor vinculado."
            )

        if origem_id not in ids_setores_ativos_usuario():
            return (
                "Você não possui vínculo ativo "
                "com o setor de origem."
            )

        if destino_tipo != TIPO_ESCOLA:
            return (
                "Setores podem encaminhar "
                "requisições para escolas."
            )

    else:
        return (
            "Seu perfil não pode cadastrar "
            "requisições."
        )

    if (
        origem_tipo == destino_tipo
        and origem_id == destino_id
    ):
        return (
            "A origem e o destino não podem "
            "ser a mesma unidade."
        )

    if not entidade_existe(
        origem_tipo,
        origem_id,
    ):
        return "A origem informada não existe ou está inativa."

    if not entidade_existe(
        destino_tipo,
        destino_id,
    ):
        return "O destino informado não existe ou está inativo."

    return None



def inserir_movimentacao(
    *,
    requisicao_id: int,
    tipo: str,
    origem_tipo: str | None,
    origem_id: int | None,
    destino_tipo: str | None,
    destino_id: int | None,
    mensagem: str | None,
) -> None:
    db.session.execute(
        SQL_INSERIR_MOVIMENTACAO,
        {
            "requisicao_id": requisicao_id,
            "tipo": tipo,
            "usuario_id": current_user.id,
            "origem_tipo": origem_tipo,
            "origem_escola_id": (
                origem_id
                if origem_tipo == TIPO_ESCOLA
                else None
            ),
            "origem_setor_id": (
                origem_id
                if origem_tipo == TIPO_SETOR
                else None
            ),
            "destino_tipo": destino_tipo,
            "destino_escola_id": (
                destino_id
                if destino_tipo == TIPO_ESCOLA
                else None
            ),
            "destino_setor_id": (
                destino_id
                if destino_tipo == TIPO_SETOR
                else None
            ),
            "mensagem": mensagem,
        },
    )


# ==========================================
# OPÇÕES
# ==========================================


@requisicoes_bp.get(
    "/api/requisicoes/escolas-disponiveis"
)
@login_required
def escolas_disponiveis():
    escolas = db.session.execute(
        db.select(
            Escola.id,
            Escola.nome,
        ).order_by(
            Escola.nome.asc()
        )
    ).all()

    return jsonify([
        {
            "id": escola_id,
            "nome": nome or f"Escola {escola_id}",
        }
        for escola_id, nome in escolas
    ])


@requisicoes_bp.get(
    "/api/requisicoes/setores-disponiveis"
)
@login_required
def setores_disponiveis():
    setores = db.session.execute(
        db.select(Setor).where(
            Setor.ativo.is_(True)
        ).order_by(
            Setor.ordem.asc(),
            Setor.nome.asc(),
        )
    ).scalars().all()

    return jsonify([
        {
            "id": setor.id,
            "nome": setor.nome,
            "nome_completo": setor.nome_completo,
            "sigla": setor.sigla,
            "tipo": setor.tipo,
            "setor_pai_id": setor.setor_pai_id,
            "setor_pai": (
                setor.setor_pai.nome
                if setor.setor_pai
                else None
            ),
        }
        for setor in setores
    ])


# ==========================================
# LISTAGENS
# ==========================================


@requisicoes_bp.get(
    "/api/requisicoes/todas"
)
@login_required
def get_todas_requisicoes():
    if (
        not usuario_ativo()
        or current_user.perfil
        not in PERFIS_CONSULTA
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Você não possui permissão "
                "para consultar requisições."
            ),
        }), 403

    return jsonify(
        listar_requisicoes_visiveis()
    )


@requisicoes_bp.get(
    "/api/escolas/<int:escola_id>/requisicoes"
)
@login_required
def get_requisicoes_escola(
    escola_id: int,
):
    if (
        current_user.perfil
        == Usuario.PERFIL_DIRETOR
        and escola_id
        not in ids_escolas_ativas_usuario()
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Você não possui vínculo ativo "
                "com esta escola."
            ),
        }), 403

    requisicoes = [
        requisicao
        for requisicao in listar_requisicoes_visiveis()
        if any(
            entidade
            and entidade.get("tipo") == TIPO_ESCOLA
            and entidade.get("id") == escola_id
            for entidade in (
                requisicao.get("origem"),
                requisicao.get("destino"),
            )
        )
        or any(
            any(
                entidade
                and entidade.get("tipo") == TIPO_ESCOLA
                and entidade.get("id") == escola_id
                for entidade in (
                    movimento.get("origem"),
                    movimento.get("destino"),
                )
            )
            for movimento in requisicao.get(
                "movimentacoes",
                [],
            )
        )
    ]

    return jsonify(requisicoes)


@requisicoes_bp.get(
    "/api/setores/<int:setor_id>/requisicoes"
)
@login_required
def get_requisicoes_setor(
    setor_id: int,
):
    if (
        current_user.perfil
        == Usuario.PERFIL_SETOR
        and setor_id
        not in ids_setores_ativos_usuario()
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Você não possui vínculo ativo "
                "com este setor."
            ),
        }), 403

    requisicoes = [
        requisicao
        for requisicao in listar_requisicoes_visiveis()
        if any(
            entidade
            and entidade.get("tipo") == TIPO_SETOR
            and entidade.get("id") == setor_id
            for entidade in (
                requisicao.get("origem"),
                requisicao.get("destino"),
            )
        )
        or any(
            any(
                entidade
                and entidade.get("tipo") == TIPO_SETOR
                and entidade.get("id") == setor_id
                for entidade in (
                    movimento.get("origem"),
                    movimento.get("destino"),
                )
            )
            for movimento in requisicao.get(
                "movimentacoes",
                [],
            )
        )
    ]

    return jsonify(requisicoes)


# ==========================================
# CRIAÇÃO
# ==========================================


@requisicoes_bp.post(
    "/api/requisicoes"
)
@login_required
def criar_requisicao():
    if not usuario_ativo():
        return jsonify({
            "sucesso": False,
            "erro": "Usuário inativo.",
        }), 403

    dados = request.get_json(
        silent=True
    ) or {}

    # Compatibilidade com o formulário antigo:
    # escola_id + setor_id.
    origem_tipo = normalizar_tipo_entidade(
        dados.get("origem_tipo")
        or (
            TIPO_ESCOLA
            if dados.get("escola_id")
            else ""
        )
    )
    origem_id = inteiro_positivo(
        dados.get("origem_id")
        or dados.get("escola_id")
    )

    destino_tipo = normalizar_tipo_entidade(
        dados.get("destino_tipo")
        or (
            TIPO_SETOR
            if dados.get("setor_id")
            else ""
        )
    )
    destino_id = inteiro_positivo(
        dados.get("destino_id")
        or dados.get("setor_id")
    )

    if (
        not origem_tipo
        or origem_id is None
        or not destino_tipo
        or destino_id is None
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Informe uma origem e um "
                "destino válidos."
            ),
        }), 400

    descricao = texto_limpo(
        dados.get("descricao")
    )
    tipo_requisicao = texto_limpo(
        dados.get("tipo")
    ) or None

    if not descricao:
        return jsonify({
            "sucesso": False,
            "erro": (
                "A descrição da requisição "
                "é obrigatória."
            ),
        }), 400

    if len(descricao) > 5000:
        return jsonify({
            "sucesso": False,
            "erro": (
                "A descrição não pode ultrapassar "
                "5.000 caracteres."
            ),
        }), 400

    erro_validacao = validar_criacao(
        origem_tipo,
        origem_id,
        destino_tipo,
        destino_id,
    )

    if erro_validacao:
        return jsonify({
            "sucesso": False,
            "erro": erro_validacao,
        }), 403

    escola_id_legado = (
        origem_id
        if origem_tipo == TIPO_ESCOLA
        else destino_id
    )

    setor_id_legado = (
        destino_id
        if destino_tipo == TIPO_SETOR
        else (
            origem_id
            if origem_tipo == TIPO_SETOR
            else None
        )
    )

    try:
        requisicao_id = db.session.execute(
            SQL_INSERIR_REQUISICAO,
            {
                "escola_id": escola_id_legado,
                "setor_id": setor_id_legado,
                "tipo": tipo_requisicao,
                "descricao": descricao,
                "status": STATUS_PENDENTE,
                "origem_tipo": origem_tipo,
                "origem_escola_id": (
                    origem_id
                    if origem_tipo == TIPO_ESCOLA
                    else None
                ),
                "origem_setor_id": (
                    origem_id
                    if origem_tipo == TIPO_SETOR
                    else None
                ),
                "destino_tipo": destino_tipo,
                "destino_escola_id": (
                    destino_id
                    if destino_tipo == TIPO_ESCOLA
                    else None
                ),
                "destino_setor_id": (
                    destino_id
                    if destino_tipo == TIPO_SETOR
                    else None
                ),
                "criado_por_id": current_user.id,
            },
        ).scalar_one()

        inserir_movimentacao(
            requisicao_id=requisicao_id,
            tipo="CRIACAO",
            origem_tipo=origem_tipo,
            origem_id=origem_id,
            destino_tipo=destino_tipo,
            destino_id=destino_id,
            mensagem=descricao,
        )

        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao criar requisição."
        )
        return jsonify({
            "sucesso": False,
            "erro": (
                "Não foi possível cadastrar "
                "a requisição."
            ),
        }), 500

    requisicao = next(
        (
            item
            for item in listar_requisicoes_visiveis()
            if item.get("id") == requisicao_id
        ),
        None,
    )

    return jsonify({
        "sucesso": True,
        "mensagem": (
            "Requisição cadastrada "
            "com sucesso."
        ),
        "requisicao": requisicao,
    }), 201


# ==========================================
# ENCAMINHAMENTO
# ==========================================


@requisicoes_bp.post(
    "/api/requisicoes/<int:requisicao_id>/encaminhar"
)
@login_required
def encaminhar_requisicao(
    requisicao_id: int,
):
    linha = buscar_requisicao(
        requisicao_id
    )

    if linha is None:
        return jsonify({
            "sucesso": False,
            "erro": "Requisição não encontrada.",
        }), 404

    if linha.get("status") == STATUS_RESPONDIDA:
        return jsonify({
            "sucesso": False,
            "erro": (
                "Uma requisição respondida "
                "não pode ser encaminhada."
            ),
        }), 409

    destino_atual_tipo = linha.get(
        "destino_tipo"
    )
    destino_atual_id = id_entidade_linha(
        linha,
        "destino",
    )

    if not usuario_controla_entidade(
        destino_atual_tipo,
        destino_atual_id,
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Somente o destinatário atual "
                "pode encaminhar esta requisição."
            ),
        }), 403

    dados = request.get_json(
        silent=True
    ) or {}

    novo_destino_tipo = normalizar_tipo_entidade(
        dados.get("destino_tipo")
        or TIPO_ESCOLA
    )
    novo_destino_id = inteiro_positivo(
        dados.get("destino_id")
        or dados.get("escola_id")
    )
    observacao = texto_limpo(
        dados.get("observacao")
    )

    # Regras solicitadas:
    # Setor -> Escola e Escola -> outra Escola.
    if novo_destino_tipo != TIPO_ESCOLA:
        return jsonify({
            "sucesso": False,
            "erro": (
                "O encaminhamento deve ter "
                "uma escola como destino."
            ),
        }), 400

    if novo_destino_id is None:
        return jsonify({
            "sucesso": False,
            "erro": "Selecione a escola de destino.",
        }), 400

    if not entidade_existe(
        TIPO_ESCOLA,
        novo_destino_id,
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "A escola de destino não existe."
            ),
        }), 400

    if (
        destino_atual_tipo == TIPO_ESCOLA
        and destino_atual_id == novo_destino_id
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Selecione outra escola "
                "para o encaminhamento."
            ),
        }), 400

    movimentos = buscar_movimentacoes(
        [requisicao_id]
    ).get(requisicao_id, [])

    escolas_que_ja_participaram = {
        escola_id
        for escola_id in (
            linha.get("origem_escola_id"),
            linha.get("destino_escola_id"),
            *[
                movimento.get("origem_escola_id")
                for movimento in movimentos
            ],
            *[
                movimento.get("destino_escola_id")
                for movimento in movimentos
            ],
        )
        if escola_id is not None
    }

    if novo_destino_id in escolas_que_ja_participaram:
        return jsonify({
            "sucesso": False,
            "erro": (
                "Essa escola já participou do fluxo. "
                "Escolha outra unidade para evitar "
                "um ciclo de encaminhamento."
            ),
        }), 409

    escola_id_legado = (
        linha.get("origem_escola_id")
        or novo_destino_id
    )
    setor_id_legado = (
        linha.get("origem_setor_id")
        or linha.get("setor_id")
    )

    try:
        db.session.execute(
            SQL_ATUALIZAR_DESTINO,
            {
                "requisicao_id": requisicao_id,
                "escola_id_legado": escola_id_legado,
                "setor_id_legado": setor_id_legado,
                "destino_tipo": TIPO_ESCOLA,
                "destino_escola_id": novo_destino_id,
                "destino_setor_id": None,
            },
        )

        inserir_movimentacao(
            requisicao_id=requisicao_id,
            tipo="ENCAMINHAMENTO",
            origem_tipo=destino_atual_tipo,
            origem_id=destino_atual_id,
            destino_tipo=TIPO_ESCOLA,
            destino_id=novo_destino_id,
            mensagem=(
                observacao
                or "Requisição encaminhada."
            ),
        )

        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao encaminhar requisição %s.",
            requisicao_id,
        )
        return jsonify({
            "sucesso": False,
            "erro": (
                "Não foi possível encaminhar "
                "a requisição."
            ),
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": (
            "Requisição encaminhada "
            "com sucesso."
        ),
    })


# ==========================================
# RESPOSTA
# ==========================================


@requisicoes_bp.post(
    "/api/requisicoes/<int:requisicao_id>/responder"
)
@login_required
def responder_requisicao(
    requisicao_id: int,
):
    linha = buscar_requisicao(
        requisicao_id
    )

    if linha is None:
        return jsonify({
            "sucesso": False,
            "erro": "Requisição não encontrada.",
        }), 404

    if linha.get("status") == STATUS_RESPONDIDA:
        return jsonify({
            "sucesso": False,
            "erro": (
                "Esta requisição já foi respondida."
            ),
        }), 409

    destino_tipo = linha.get("destino_tipo")
    destino_id = id_entidade_linha(
        linha,
        "destino",
    )

    if not usuario_controla_entidade(
        destino_tipo,
        destino_id,
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Somente o destinatário atual "
                "pode responder esta requisição."
            ),
        }), 403

    dados = request.get_json(
        silent=True
    ) or {}
    resposta = texto_limpo(
        dados.get("resposta")
    )

    if not resposta:
        return jsonify({
            "sucesso": False,
            "erro": (
                "A resposta não pode ficar vazia."
            ),
        }), 400

    if len(resposta) > 5000:
        return jsonify({
            "sucesso": False,
            "erro": (
                "A resposta não pode ultrapassar "
                "5.000 caracteres."
            ),
        }), 400

    origem_original_tipo = linha.get(
        "origem_tipo"
    )
    origem_original_id = id_entidade_linha(
        linha,
        "origem",
    )

    try:
        db.session.execute(
            SQL_RESPONDER_REQUISICAO,
            {
                "requisicao_id": requisicao_id,
                "resposta": resposta,
                "status": STATUS_RESPONDIDA,
                "respondido_por_id": current_user.id,
                "data_resposta": (
                    datetime.now(timezone.utc)
                    .replace(tzinfo=None)
                ),
            },
        )

        inserir_movimentacao(
            requisicao_id=requisicao_id,
            tipo="RESPOSTA",
            origem_tipo=destino_tipo,
            origem_id=destino_id,
            destino_tipo=origem_original_tipo,
            destino_id=origem_original_id,
            mensagem=resposta,
        )

        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao responder requisição %s.",
            requisicao_id,
        )
        return jsonify({
            "sucesso": False,
            "erro": (
                "Não foi possível responder "
                "a requisição."
            ),
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": (
            "Requisição respondida "
            "com sucesso."
        ),
    })


# ==========================================
# ALERTAS DAS ESCOLAS
# ==========================================


@requisicoes_bp.get(
    "/api/requisicoes/alertas"
)
@login_required
def alertas_requisicoes():
    requisicoes = listar_requisicoes_visiveis()
    contagens: dict[int, int] = defaultdict(int)

    escolas_permitidas = (
        ids_escolas_ativas_usuario()
        if current_user.perfil
        == Usuario.PERFIL_DIRETOR
        else None
    )

    for requisicao in requisicoes:
        if requisicao.get("status") != STATUS_PENDENTE:
            continue

        ids_escolas = {
            entidade.get("id")
            for entidade in (
                requisicao.get("origem"),
                requisicao.get("destino"),
            )
            if entidade
            and entidade.get("tipo") == TIPO_ESCOLA
        }

        for escola_id in ids_escolas:
            if (
                escolas_permitidas is not None
                and escola_id not in escolas_permitidas
            ):
                continue

            contagens[int(escola_id)] += 1

    return jsonify([
        {
            "escola_id": escola_id,
            "quantidade": quantidade,
        }
        for escola_id, quantidade
        in sorted(contagens.items())
    ])
