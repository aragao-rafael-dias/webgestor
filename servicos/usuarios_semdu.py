from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import text

from models import Usuario, db
from servicos.acessos_modulos import MODULO_SEMDU, PERFIL_USUARIO
from servicos.funcoes_semdu import FUNCAO_ENG_AMBIENTAL, FUNCAO_FISCAL


SQL_UPSERT_ACESSO_SEMDU = text(
    """
    INSERT INTO semed.usuarios_acessos_modulos (
        usuario_id,
        modulo,
        perfil,
        ativo,
        inicio_vinculo,
        fim_vinculo,
        atualizado_em
    ) VALUES (
        :usuario_id,
        :modulo,
        :perfil,
        TRUE,
        CURRENT_DATE,
        NULL,
        NOW()
    )
    ON CONFLICT (usuario_id, modulo)
    DO UPDATE SET
        perfil = EXCLUDED.perfil,
        ativo = TRUE,
        inicio_vinculo = LEAST(
            semed.usuarios_acessos_modulos.inicio_vinculo,
            CURRENT_DATE
        ),
        fim_vinculo = NULL,
        atualizado_em = NOW()
    """
)

SQL_UPSERT_FUNCAO_SEMDU = text(
    """
    INSERT INTO semdu.usuarios_funcoes (
        usuario_id,
        funcao_codigo,
        funcao_nome,
        ativo,
        inicio_vinculo,
        fim_vinculo,
        atualizado_em
    ) VALUES (
        :usuario_id,
        :funcao_codigo,
        :funcao_nome,
        TRUE,
        CURRENT_DATE,
        NULL,
        NOW()
    )
    ON CONFLICT (usuario_id, funcao_codigo)
    DO UPDATE SET
        funcao_nome = EXCLUDED.funcao_nome,
        ativo = TRUE,
        inicio_vinculo = LEAST(
            semdu.usuarios_funcoes.inicio_vinculo,
            CURRENT_DATE
        ),
        fim_vinculo = NULL,
        atualizado_em = NOW()
    """
)

SQL_REVOGAR_FUNCOES_SEMDU = text(
    """
    UPDATE semdu.usuarios_funcoes
    SET
        ativo = FALSE,
        fim_vinculo = CURRENT_DATE,
        atualizado_em = NOW()
    WHERE usuario_id = :usuario_id
      AND funcao_codigo IN ('FISCAL', 'ENG_AMBIENTAL')
      AND ativo IS TRUE
    """
)

SQL_UPSERT_FISCAL_CADASTRO = text(
    """
    INSERT INTO cadastro_territorial.usuarios_funcoes (
        usuario_id,
        orgao,
        funcao,
        ativo,
        inicio_vinculo,
        fim_vinculo,
        designado_por_usuario_id,
        atualizado_em
    ) VALUES (
        :usuario_id,
        'SEMDU',
        'FISCAL',
        TRUE,
        CURRENT_DATE,
        NULL,
        :designado_por_id,
        NOW()
    )
    ON CONFLICT (usuario_id, orgao, funcao)
    DO UPDATE SET
        ativo = TRUE,
        inicio_vinculo = LEAST(
            cadastro_territorial.usuarios_funcoes.inicio_vinculo,
            CURRENT_DATE
        ),
        fim_vinculo = NULL,
        designado_por_usuario_id = EXCLUDED.designado_por_usuario_id,
        atualizado_em = NOW()
    """
)

SQL_REVOGAR_FISCAL_CADASTRO = text(
    """
    UPDATE cadastro_territorial.usuarios_funcoes
    SET
        ativo = FALSE,
        fim_vinculo = CURRENT_DATE,
        atualizado_em = NOW()
    WHERE usuario_id = :usuario_id
      AND orgao = 'SEMDU'
      AND funcao = 'FISCAL'
      AND ativo IS TRUE
    """
)

SQL_LISTAR_FUNCOES_SEMDU = text(
    """
    SELECT
        uf.usuario_id,
        uf.funcao_codigo
    FROM semdu.usuarios_funcoes AS uf
    INNER JOIN semed.usuarios AS u
        ON u.id = uf.usuario_id
    WHERE u.perfil = 'SEMDU'
      AND uf.ativo IS TRUE
      AND uf.inicio_vinculo <= CURRENT_DATE
      AND (
          uf.fim_vinculo IS NULL
          OR uf.fim_vinculo >= CURRENT_DATE
      )
    ORDER BY uf.usuario_id, uf.funcao_codigo
    """
)


NOMES_FUNCOES = {
    FUNCAO_FISCAL: "Fiscal",
    FUNCAO_ENG_AMBIENTAL: "Eng. Ambiental",
}

FUNCOES_GERENCIAVEIS = frozenset(NOMES_FUNCOES)


def listar_usuarios_semdu() -> list[Usuario]:
    """Lista somente contas criadas como usuários exclusivos da SEMDU."""
    return (
        db.session.execute(
            db.select(Usuario)
            .where(Usuario.perfil == Usuario.PERFIL_SEMDU)
            .order_by(Usuario.nome.asc(), Usuario.login.asc())
        )
        .scalars()
        .all()
    )


def buscar_usuario_semdu(usuario_id: int) -> Usuario | None:
    usuario = db.session.get(Usuario, int(usuario_id))
    if usuario is None or usuario.perfil != Usuario.PERFIL_SEMDU:
        return None
    return usuario


def listar_funcoes_por_usuario(
    usuarios: Iterable[Usuario],
) -> dict[int, set[str]]:
    ids = [int(usuario.id) for usuario in usuarios]
    if not ids:
        return {}

    registros = db.session.execute(SQL_LISTAR_FUNCOES_SEMDU).mappings().all()

    resultado = {usuario_id: set() for usuario_id in ids}
    for item in registros:
        resultado.setdefault(int(item["usuario_id"]), set()).add(
            str(item["funcao_codigo"]).strip().upper()
        )
    return resultado


def criar_usuario_semdu(
    *,
    nome: str,
    login: str,
    email: str | None,
    senha: str,
    criado_por_id: int,
    funcoes: Iterable[str] = (),
) -> Usuario:
    """
    Cria uma conta exclusiva da SEMDU.

    O perfil legado SEMDU é apenas um marcador para impedir que a conta receba
    acesso à SEMED pelo mecanismo de compatibilidade legado. O acesso efetivo
    ao módulo é sempre SEMDU/USUARIO em usuarios_acessos_modulos.
    """
    usuario = Usuario(
        nome=nome.strip(),
        login=Usuario.normalizar_login(login),
        email=Usuario.normalizar_email(email),
        perfil=Usuario.PERFIL_SEMDU,
        ativo=True,
        deve_trocar_senha=True,
        criado_por_id=int(criado_por_id),
    )
    usuario.definir_senha(senha)

    db.session.add(usuario)
    db.session.flush()

    db.session.execute(
        SQL_UPSERT_ACESSO_SEMDU,
        {
            "usuario_id": usuario.id,
            "modulo": MODULO_SEMDU,
            "perfil": PERFIL_USUARIO,
        },
    )

    sincronizar_funcoes_usuario(
        usuario.id,
        funcoes,
        designado_por_id=int(criado_por_id),
    )
    return usuario


def sincronizar_funcoes_usuario(
    usuario_id: int,
    funcoes: Iterable[str],
    *,
    designado_por_id: int | None = None,
) -> set[str]:
    desejadas = {
        str(funcao or "").strip().upper()
        for funcao in funcoes
        if str(funcao or "").strip().upper() in FUNCOES_GERENCIAVEIS
    }

    # Primeiro revoga as duas funções gerenciáveis e depois reativa somente as
    # selecionadas. Isso deixa a operação idempotente e simples de auditar.
    db.session.execute(
        SQL_REVOGAR_FUNCOES_SEMDU,
        {"usuario_id": int(usuario_id)},
    )

    for funcao in sorted(desejadas):
        db.session.execute(
            SQL_UPSERT_FUNCAO_SEMDU,
            {
                "usuario_id": int(usuario_id),
                "funcao_codigo": funcao,
                "funcao_nome": NOMES_FUNCOES[funcao],
            },
        )

    # Fiscal da SEMDU também recebe as permissões já existentes no Cadastro
    # Territorial compartilhado: planejar, editar, autorizar e anexar docs.
    if FUNCAO_FISCAL in desejadas:
        db.session.execute(
            SQL_UPSERT_FISCAL_CADASTRO,
            {
                "usuario_id": int(usuario_id),
                "designado_por_id": (
                    int(designado_por_id)
                    if designado_por_id is not None
                    else None
                ),
            },
        )
    else:
        db.session.execute(
            SQL_REVOGAR_FISCAL_CADASTRO,
            {"usuario_id": int(usuario_id)},
        )

    return desejadas
