from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any

from flask import abort, current_app, g, has_request_context, session
from flask_login import UserMixin, current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


MODULO_GERAL = "GERAL"
MODULO_SEMED = "SEMED"
MODULO_SEMDU = "SEMDU"
MODULO_CADASTRO_TERRITORIAL = "CADASTRO_TERRITORIAL"

MODULOS_SISTEMA = (
    MODULO_SEMED,
    MODULO_SEMDU,
    MODULO_CADASTRO_TERRITORIAL,
)

PERFIL_ADMIN = "ADMIN"
PERFIL_AUDITOR = "AUDITOR"
PERFIL_DIRETOR = "DIRETOR"
PERFIL_SETOR = "SETOR"
PERFIL_USUARIO = "USUARIO"

PERFIS_VALIDOS = {
    PERFIL_ADMIN,
    PERFIL_AUDITOR,
    PERFIL_DIRETOR,
    PERFIL_SETOR,
    PERFIL_USUARIO,
}

PERFIS_POR_MODULO = {
    MODULO_GERAL: {
        PERFIL_ADMIN,
        PERFIL_AUDITOR,
    },
    MODULO_SEMED: {
        PERFIL_ADMIN,
        PERFIL_AUDITOR,
        PERFIL_DIRETOR,
        PERFIL_SETOR,
        PERFIL_USUARIO,
    },
    MODULO_SEMDU: {
        PERFIL_ADMIN,
        PERFIL_AUDITOR,
        PERFIL_USUARIO,
    },
    MODULO_CADASTRO_TERRITORIAL: {
        PERFIL_ADMIN,
        PERFIL_AUDITOR,
        PERFIL_USUARIO,
    },
}


SQL_ACESSOS = text(
    """
    SELECT
        modulo,
        perfil
    FROM semed.usuarios_acessos_modulos
    WHERE usuario_id = :usuario_id
      AND ativo IS TRUE
      AND inicio_vinculo <= CURRENT_DATE
      AND (
          fim_vinculo IS NULL
          OR fim_vinculo >= CURRENT_DATE
      )
    ORDER BY
        CASE modulo
            WHEN 'GERAL' THEN 1
            ELSE 2
        END,
        id
    """
)


@dataclass(frozen=True)
class AcessoModulo:
    modulo: str
    perfil: str
    origem: str

    @property
    def administrador(self) -> bool:
        return self.perfil == PERFIL_ADMIN

    @property
    def auditor(self) -> bool:
        return self.perfil == PERFIL_AUDITOR

    @property
    def somente_leitura(self) -> bool:
        return self.auditor


def normalizar(valor: Any) -> str:
    return str(valor or "").strip().upper()


def validar_modulo_perfil(
    modulo: str,
    perfil: str,
) -> tuple[str, str]:
    modulo = normalizar(modulo)
    perfil = normalizar(perfil)

    if modulo not in PERFIS_POR_MODULO:
        raise ValueError(
            f"Módulo inválido: {modulo or '(vazio)'}."
        )

    if perfil not in PERFIS_POR_MODULO[modulo]:
        permitidos = ", ".join(
            sorted(PERFIS_POR_MODULO[modulo])
        )
        raise ValueError(
            f"O perfil {perfil or '(vazio)'} não é permitido "
            f"no módulo {modulo}. Use: {permitidos}."
        )

    return modulo, perfil


def _usuario_real(usuario):
    return getattr(usuario, "usuario_real", usuario)


def _cache_requisicao() -> dict:
    if not has_request_context():
        return {}

    cache = getattr(
        g,
        "_cache_acessos_modulos",
        None,
    )

    if cache is None:
        cache = {}
        g._cache_acessos_modulos = cache

    return cache


def listar_acessos(
    usuario_id: int,
) -> list[dict[str, str]]:
    usuario_id = int(usuario_id)
    cache = _cache_requisicao()

    if usuario_id in cache:
        return list(cache[usuario_id])

    try:
        registros = (
            db.session.execute(
                SQL_ACESSOS,
                {"usuario_id": usuario_id},
            )
            .mappings()
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao consultar os acessos modulares "
            "do usuário %s.",
            usuario_id,
        )
        registros = []

    acessos = [
        {
            "modulo": normalizar(item["modulo"]),
            "perfil": normalizar(item["perfil"]),
        }
        for item in registros
    ]

    if has_request_context():
        cache[usuario_id] = list(acessos)

    return acessos


def limpar_cache_acessos(
    usuario_id: int | None = None,
) -> None:
    if not has_request_context():
        return

    cache = _cache_requisicao()

    if usuario_id is None:
        cache.clear()
        return

    cache.pop(int(usuario_id), None)


def obter_acesso_modulo(
    usuario,
    modulo: str,
) -> AcessoModulo | None:
    usuario = _usuario_real(usuario)

    if (
        usuario is None
        or not getattr(usuario, "is_authenticated", False)
        or not getattr(usuario, "ativo", False)
    ):
        return None

    modulo = normalizar(modulo)

    if modulo not in MODULOS_SISTEMA:
        return None

    acessos = listar_acessos(int(usuario.id))

    for acesso in acessos:
        if acesso["modulo"] == MODULO_GERAL:
            return AcessoModulo(
                modulo=modulo,
                perfil=acesso["perfil"],
                origem=MODULO_GERAL,
            )

    for acesso in acessos:
        if acesso["modulo"] == modulo:
            return AcessoModulo(
                modulo=modulo,
                perfil=acesso["perfil"],
                origem=modulo,
            )

    # O Cadastro Territorial é um módulo compartilhado.
    # Todo usuário ativo pode visualizar; as operações de escrita
    # dependem das funções FISCAL/SEMDU ou FISCAL/SEMFAZ.
    if modulo == MODULO_CADASTRO_TERRITORIAL:
        return AcessoModulo(
            modulo=MODULO_CADASTRO_TERRITORIAL,
            perfil=PERFIL_USUARIO,
            origem="COMPARTILHADO",
        )

    # Compatibilidade com os usuários já existentes.
    # Enquanto todos os vínculos não forem migrados,
    # o perfil antigo continua autorizando somente a SEMED.
    if modulo == MODULO_SEMED:
        perfil_legado = normalizar(
            getattr(usuario, "perfil", "")
        )

        if perfil_legado in PERFIS_POR_MODULO[MODULO_SEMED]:
            return AcessoModulo(
                modulo=MODULO_SEMED,
                perfil=perfil_legado,
                origem="LEGADO",
            )

    return None


def usuario_pode_acessar_modulo(
    usuario,
    modulo: str,
) -> bool:
    return obter_acesso_modulo(
        usuario,
        modulo,
    ) is not None


def perfil_efetivo(
    usuario,
    modulo: str | None = None,
) -> str:
    usuario_real = _usuario_real(usuario)

    if usuario_real is None:
        return ""

    modulo_normalizado = normalizar(modulo)

    if not modulo_normalizado and has_request_context():
        modulo_normalizado = normalizar(
            getattr(g, "modulo_requisicao", "")
            or session.get("modulo_atual")
        )

    if modulo_normalizado in MODULOS_SISTEMA:
        acesso = obter_acesso_modulo(
            usuario_real,
            modulo_normalizado,
        )

        if acesso:
            return acesso.perfil

    return normalizar(
        getattr(usuario_real, "perfil", "")
    )


def listar_modulos_usuario(
    usuario,
) -> list[dict[str, Any]]:
    configuracao = (
        {
            "codigo": MODULO_SEMED,
            "sigla": "SEMED",
            "titulo": "Secretaria Municipal de Educação",
            "descricao": (
                "Rotas escolares, unidades de ensino, "
                "requisições e memoriais."
            ),
            "url_endpoint": "home.mapa_semed",
            "cor": "#800000",
        },
        {
            "codigo": MODULO_SEMDU,
            "sigla": "SEMDU",
            "titulo": "Secretaria Municipal de Desenvolvimento",
            "descricao": (
                "Gestão territorial, planejamento urbano "
                "e camadas geográficas municipais."
            ),
            "url_endpoint": "semdu.mapa",
            "cor": "#232c61",
        },
        {
            "codigo": MODULO_CADASTRO_TERRITORIAL,
            "sigla": "CT",
            "titulo": "Cadastro Territorial",
            "descricao": (
                "Fluxo compartilhado entre SEMDU e SEMFAZ para "
                "planejamento, documentação e liberação de logradouros."
            ),
            "url_endpoint": "cadastro_territorial.mapa",
            "cor": "#315f72",
        },
    )

    resultado = []

    for item in configuracao:
        acesso = obter_acesso_modulo(
            usuario,
            item["codigo"],
        )

        resultado.append(
            {
                **item,
                "disponivel": acesso is not None,
                "perfil": acesso.perfil if acesso else "",
                "origem": acesso.origem if acesso else "",
            }
        )

    return resultado


def acesso_modulo_required(
    modulo: str,
):
    modulo = normalizar(modulo)

    def decorator(funcao):
        @wraps(funcao)
        def protegida(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()

            if obter_acesso_modulo(
                current_user,
                modulo,
            ) is None:
                abort(
                    403,
                    description=(
                        "Seu usuário não possui acesso "
                        f"ao módulo {modulo}."
                    ),
                )

            return funcao(*args, **kwargs)

        return protegida

    return decorator


class UsuarioContextual(UserMixin):
    """
    Adaptador do usuário do Flask-Login.

    O cadastro continua sendo o mesmo objeto Usuario,
    mas a propriedade ``perfil`` passa a refletir o
    módulo da requisição atual. Isso mantém compatíveis
    as rotas antigas da SEMED que já consultam
    ``current_user.perfil``.
    """

    def __init__(self, usuario):
        object.__setattr__(
            self,
            "_usuario",
            usuario,
        )

    @property
    def usuario_real(self):
        return object.__getattribute__(
            self,
            "_usuario",
        )

    @property
    def perfil(self) -> str:
        return perfil_efetivo(
            self.usuario_real
        )

    @property
    def is_active(self) -> bool:
        return bool(
            getattr(
                self.usuario_real,
                "ativo",
                False,
            )
        )

    def get_id(self) -> str:
        return str(self.usuario_real.id)

    def __getattr__(self, nome):
        return getattr(
            self.usuario_real,
            nome,
        )

    def __repr__(self) -> str:
        return (
            "<UsuarioContextual "
            f"id={self.usuario_real.id} "
            f"perfil={self.perfil!r}>"
        )
