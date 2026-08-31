from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any

from flask import abort, current_app, g, has_request_context
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


ORGAO_SEMDU = "SEMDU"
ORGAO_SEMFAZ = "SEMFAZ"
ORGAOS_VALIDOS = {
    ORGAO_SEMDU,
    ORGAO_SEMFAZ,
}

FUNCAO_FISCAL = "FISCAL"
FUNCOES_VALIDAS = {
    FUNCAO_FISCAL,
}


SQL_FUNCOES_USUARIO = text(
    """
    SELECT
        orgao,
        funcao
    FROM cadastro_territorial.usuarios_funcoes
    WHERE usuario_id = CAST(:usuario_id AS INTEGER)
      AND ativo IS TRUE
      AND inicio_vinculo <= CURRENT_DATE
      AND (
          fim_vinculo IS NULL
          OR fim_vinculo >= CURRENT_DATE
      )
    ORDER BY orgao, funcao
    """
)


@dataclass(frozen=True)
class FuncaoCadastroTerritorial:
    orgao: str
    funcao: str

    @property
    def fiscal(self) -> bool:
        return self.funcao == FUNCAO_FISCAL


def normalizar(valor: Any) -> str:
    return str(valor or "").strip().upper()


def validar_orgao_funcao(
    orgao: str,
    funcao: str,
) -> tuple[str, str]:
    orgao = normalizar(orgao)
    funcao = normalizar(funcao)

    if orgao not in ORGAOS_VALIDOS:
        raise ValueError(
            f"Órgão inválido: {orgao or '(vazio)'}."
        )

    if funcao not in FUNCOES_VALIDAS:
        raise ValueError(
            f"Função inválida: {funcao or '(vazio)'}."
        )

    return orgao, funcao


def _usuario_real(usuario):
    return getattr(usuario, "usuario_real", usuario)


def _cache_requisicao() -> dict[int, list[dict[str, str]]]:
    if not has_request_context():
        return {}

    cache = getattr(
        g,
        "_cache_funcoes_cadastro_territorial",
        None,
    )

    if cache is None:
        cache = {}
        g._cache_funcoes_cadastro_territorial = cache

    return cache


def listar_funcoes_usuario(
    usuario,
) -> list[dict[str, str]]:
    usuario = _usuario_real(usuario)

    if (
        usuario is None
        or not getattr(usuario, "is_authenticated", False)
        or not getattr(usuario, "ativo", False)
    ):
        return []

    usuario_id = int(usuario.id)
    cache = _cache_requisicao()

    if usuario_id in cache:
        return list(cache[usuario_id])

    try:
        registros = (
            db.session.execute(
                SQL_FUNCOES_USUARIO,
                {"usuario_id": usuario_id},
            )
            .mappings()
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao consultar funções do Cadastro Territorial "
            "para o usuário %s.",
            usuario_id,
        )
        registros = []

    funcoes = [
        {
            "orgao": normalizar(item["orgao"]),
            "funcao": normalizar(item["funcao"]),
        }
        for item in registros
    ]

    if has_request_context():
        cache[usuario_id] = list(funcoes)

    return funcoes


def usuario_possui_funcao(
    usuario,
    orgao: str,
    funcao: str = FUNCAO_FISCAL,
) -> bool:
    orgao, funcao = validar_orgao_funcao(
        orgao,
        funcao,
    )

    return any(
        item["orgao"] == orgao
        and item["funcao"] == funcao
        for item in listar_funcoes_usuario(usuario)
    )


def obter_permissoes_usuario(
    usuario,
) -> dict[str, Any]:
    funcoes = listar_funcoes_usuario(usuario)

    fiscal_semdu = any(
        item["orgao"] == ORGAO_SEMDU
        and item["funcao"] == FUNCAO_FISCAL
        for item in funcoes
    )

    fiscal_semfaz = any(
        item["orgao"] == ORGAO_SEMFAZ
        and item["funcao"] == FUNCAO_FISCAL
        for item in funcoes
    )

    return {
        "visualizar": True,
        "fiscal_semdu": fiscal_semdu,
        "fiscal_semfaz": fiscal_semfaz,
        "planejar": fiscal_semdu,
        "editar_planejamento": fiscal_semdu,
        "autorizar": fiscal_semdu,
        "liberar": fiscal_semfaz,
        "devolver": fiscal_semfaz,
        "anexar_documentos": fiscal_semdu or fiscal_semfaz,
        "funcoes": funcoes,
    }


def fiscal_orgao_required(
    orgao: str,
):
    orgao = normalizar(orgao)

    if orgao not in ORGAOS_VALIDOS:
        raise ValueError(
            f"Órgão inválido: {orgao}."
        )

    def decorator(funcao_view):
        @wraps(funcao_view)
        def protegida(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()

            if not usuario_possui_funcao(
                current_user,
                orgao,
                FUNCAO_FISCAL,
            ):
                abort(
                    403,
                    description=(
                        "A operação é restrita à pessoa com função "
                        f"Fiscal da {orgao}."
                    ),
                )

            return funcao_view(*args, **kwargs)

        return protegida

    return decorator
