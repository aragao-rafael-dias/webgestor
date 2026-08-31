from __future__ import annotations

import click
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import Usuario, db
from servicos.funcoes_semdu import FUNCAO_ENG_AMBIENTAL


SQL_DEFINIR = text(
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
        fim_vinculo = NULL,
        atualizado_em = NOW()
    """
)

SQL_REVOGAR = text(
    """
    UPDATE semdu.usuarios_funcoes
    SET
        ativo = FALSE,
        fim_vinculo = CURRENT_DATE,
        atualizado_em = NOW()
    WHERE usuario_id = :usuario_id
      AND funcao_codigo = :funcao_codigo
      AND ativo IS TRUE
    """
)

SQL_LISTAR = text(
    """
    SELECT
        u.login,
        u.nome,
        f.funcao_codigo,
        f.funcao_nome,
        f.ativo,
        f.inicio_vinculo,
        f.fim_vinculo
    FROM semdu.usuarios_funcoes AS f
    INNER JOIN semed.usuarios AS u
        ON u.id = f.usuario_id
    ORDER BY u.login, f.funcao_codigo
    """
)


def _usuario(login: str):
    return db.session.execute(
        db.select(Usuario).where(
            Usuario.login == Usuario.normalizar_login(login)
        )
    ).scalar_one_or_none()


def registrar_comandos_arborizacao(app):
    @app.cli.command("definir-funcao-semdu")
    @click.option("--login", required=True)
    @click.option(
        "--funcao",
        default=FUNCAO_ENG_AMBIENTAL,
        show_default=True,
        type=click.Choice(
            [FUNCAO_ENG_AMBIENTAL],
            case_sensitive=False,
        ),
    )
    def definir_funcao_semdu(login: str, funcao: str):
        usuario = _usuario(login)
        if usuario is None:
            raise click.ClickException("Usuário não encontrado.")

        funcao = funcao.upper()

        try:
            db.session.execute(
                SQL_DEFINIR,
                {
                    "usuario_id": usuario.id,
                    "funcao_codigo": funcao,
                    "funcao_nome": "Eng. Ambiental",
                },
            )
            db.session.commit()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível definir a função SEMDU."
            ) from erro

        click.echo(
            f"Função definida: {usuario.login} -> {funcao}."
        )

    @app.cli.command("revogar-funcao-semdu")
    @click.option("--login", required=True)
    @click.option(
        "--funcao",
        default=FUNCAO_ENG_AMBIENTAL,
        show_default=True,
        type=click.Choice(
            [FUNCAO_ENG_AMBIENTAL],
            case_sensitive=False,
        ),
    )
    def revogar_funcao_semdu(login: str, funcao: str):
        usuario = _usuario(login)
        if usuario is None:
            raise click.ClickException("Usuário não encontrado.")

        try:
            resultado = db.session.execute(
                SQL_REVOGAR,
                {
                    "usuario_id": usuario.id,
                    "funcao_codigo": funcao.upper(),
                },
            )
            db.session.commit()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível revogar a função."
            ) from erro

        if resultado.rowcount == 0:
            click.echo("Nenhuma função ativa foi encontrada.")
            return

        click.echo(
            f"Função revogada: {usuario.login} -> {funcao.upper()}."
        )

    @app.cli.command("listar-funcoes-semdu")
    def listar_funcoes_semdu():
        try:
            registros = db.session.execute(
                SQL_LISTAR
            ).mappings().all()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível listar as funções SEMDU."
            ) from erro

        if not registros:
            click.echo("Nenhuma função SEMDU cadastrada.")
            return

        click.echo("LOGIN | FUNÇÃO | ATIVO")
        for item in registros:
            click.echo(
                f"{item['login']} | {item['funcao_codigo']} | "
                f"{'SIM' if item['ativo'] else 'NÃO'}"
            )
