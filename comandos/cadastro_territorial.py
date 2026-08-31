from __future__ import annotations

import click
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import Usuario, db
from servicos.funcoes_cadastro_territorial import (
    FUNCAO_FISCAL,
    ORGAO_SEMDU,
    ORGAO_SEMFAZ,
    validar_orgao_funcao,
)


SQL_DEFINIR_FUNCAO = text(
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
        CAST(:usuario_id AS INTEGER),
        CAST(:orgao AS VARCHAR),
        CAST(:funcao AS VARCHAR),
        TRUE,
        CURRENT_DATE,
        NULL,
        CAST(:designado_por AS INTEGER),
        NOW()
    )
    ON CONFLICT (
        usuario_id,
        orgao,
        funcao
    )
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


SQL_REVOGAR_FUNCAO = text(
    """
    UPDATE cadastro_territorial.usuarios_funcoes
    SET
        ativo = FALSE,
        fim_vinculo = CURRENT_DATE,
        atualizado_em = NOW()
    WHERE usuario_id = CAST(:usuario_id AS INTEGER)
      AND orgao = CAST(:orgao AS VARCHAR)
      AND funcao = CAST(:funcao AS VARCHAR)
      AND ativo IS TRUE
    """
)


SQL_LISTAR_FUNCOES = text(
    """
    SELECT
        u.login,
        u.nome,
        f.orgao,
        f.funcao,
        f.ativo,
        f.inicio_vinculo,
        f.fim_vinculo
    FROM cadastro_territorial.usuarios_funcoes AS f
    INNER JOIN semed.usuarios AS u
        ON u.id = f.usuario_id
    ORDER BY
        f.orgao,
        u.login,
        f.funcao
    """
)


def _usuario(login: str):
    return (
        db.session.execute(
            db.select(Usuario).where(
                Usuario.login
                == Usuario.normalizar_login(login)
            )
        )
        .scalar_one_or_none()
    )


def registrar_comandos_cadastro_territorial(app):
    @app.cli.command(
        "definir-fiscal-cadastro"
    )
    @click.option(
        "--login",
        required=True,
        help="Login existente em semed.usuarios.",
    )
    @click.option(
        "--orgao",
        required=True,
        type=click.Choice(
            [ORGAO_SEMDU, ORGAO_SEMFAZ],
            case_sensitive=False,
        ),
    )
    def definir_fiscal_cadastro(
        login: str,
        orgao: str,
    ):
        orgao, funcao = validar_orgao_funcao(
            orgao,
            FUNCAO_FISCAL,
        )
        usuario = _usuario(login)

        if usuario is None:
            raise click.ClickException(
                "Usuário não encontrado."
            )

        try:
            db.session.execute(
                SQL_DEFINIR_FUNCAO,
                {
                    "usuario_id": usuario.id,
                    "orgao": orgao,
                    "funcao": funcao,
                    "designado_por": None,
                },
            )
            db.session.commit()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível definir a função Fiscal."
            ) from erro

        click.echo(
            f"Função definida: {usuario.login} -> {orgao}/FISCAL."
        )

    @app.cli.command(
        "revogar-fiscal-cadastro"
    )
    @click.option(
        "--login",
        required=True,
    )
    @click.option(
        "--orgao",
        required=True,
        type=click.Choice(
            [ORGAO_SEMDU, ORGAO_SEMFAZ],
            case_sensitive=False,
        ),
    )
    def revogar_fiscal_cadastro(
        login: str,
        orgao: str,
    ):
        usuario = _usuario(login)

        if usuario is None:
            raise click.ClickException(
                "Usuário não encontrado."
            )

        orgao, funcao = validar_orgao_funcao(
            orgao,
            FUNCAO_FISCAL,
        )

        try:
            resultado = db.session.execute(
                SQL_REVOGAR_FUNCAO,
                {
                    "usuario_id": usuario.id,
                    "orgao": orgao,
                    "funcao": funcao,
                },
            )
            db.session.commit()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível revogar a função Fiscal."
            ) from erro

        if resultado.rowcount == 0:
            click.echo(
                "Nenhuma função ativa foi encontrada."
            )
            return

        click.echo(
            f"Função revogada: {usuario.login} -> {orgao}/FISCAL."
        )

    @app.cli.command(
        "listar-fiscais-cadastro"
    )
    def listar_fiscais_cadastro():
        try:
            registros = (
                db.session.execute(
                    SQL_LISTAR_FUNCOES
                )
                .mappings()
                .all()
            )
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível listar as funções."
            ) from erro

        if not registros:
            click.echo(
                "Nenhum Fiscal cadastrado."
            )
            return

        click.echo(
            "LOGIN | ÓRGÃO | FUNÇÃO | ATIVO"
        )

        for item in registros:
            click.echo(
                f"{item['login']} | {item['orgao']} | "
                f"{item['funcao']} | "
                f"{'SIM' if item['ativo'] else 'NÃO'}"
            )
