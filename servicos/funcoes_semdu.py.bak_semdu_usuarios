from __future__ import annotations

from functools import wraps

from flask import abort, current_app, g, has_request_context
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


FUNCAO_ENG_AMBIENTAL = "ENG_AMBIENTAL"


SQL_FUNCOES_USUARIO = text(
    """
    SELECT funcao_codigo
    FROM semdu.usuarios_funcoes
    WHERE usuario_id = :usuario_id
      AND ativo IS TRUE
      AND inicio_vinculo <= CURRENT_DATE
      AND (
          fim_vinculo IS NULL
          OR fim_vinculo >= CURRENT_DATE
      )
    ORDER BY funcao_codigo
    """
)


def normalizar_funcao(valor) -> str:
    return str(valor or "").strip().upper()


def _usuario_real(usuario):
    return getattr(usuario, "usuario_real", usuario)


def _cache_funcoes() -> dict:
    if not has_request_context():
        return {}

    cache = getattr(g, "_cache_funcoes_semdu", None)

    if cache is None:
        cache = {}
        g._cache_funcoes_semdu = cache

    return cache


def listar_funcoes_usuario(usuario) -> set[str]:
    usuario = _usuario_real(usuario)

    if (
        usuario is None
        or not getattr(usuario, "is_authenticated", False)
        or not getattr(usuario, "ativo", False)
    ):
        return set()

    usuario_id = int(usuario.id)
    cache = _cache_funcoes()

    if usuario_id in cache:
        return set(cache[usuario_id])

    try:
        registros = db.session.execute(
            SQL_FUNCOES_USUARIO,
            {"usuario_id": usuario_id},
        ).scalars().all()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao consultar funções SEMDU do usuário %s.",
            usuario_id,
        )
        registros = []

    funcoes = {
        normalizar_funcao(item)
        for item in registros
        if normalizar_funcao(item)
    }

    if has_request_context():
        cache[usuario_id] = set(funcoes)

    return funcoes


def usuario_possui_funcao(usuario, funcao_codigo: str) -> bool:
    return normalizar_funcao(funcao_codigo) in listar_funcoes_usuario(usuario)


def funcao_semdu_required(funcao_codigo: str):
    funcao = normalizar_funcao(funcao_codigo)

    def decorator(funcao_view):
        @wraps(funcao_view)
        def protegida(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()

            if not usuario_possui_funcao(current_user, funcao):
                abort(
                    403,
                    description=(
                        "Esta operação é restrita à função técnica "
                        f"{funcao}."
                    ),
                )

            return funcao_view(*args, **kwargs)

        return protegida

    return decorator
