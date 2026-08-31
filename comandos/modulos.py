from __future__ import annotations

import click
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import Usuario, db
from servicos.acessos_modulos import (
    MODULO_GERAL,
    MODULO_CADASTRO_TERRITORIAL,
    MODULO_SEMDU,
    MODULO_SEMED,
    PERFIL_ADMIN,
    PERFIL_AUDITOR,
    PERFIL_DIRETOR,
    PERFIL_SETOR,
    PERFIL_USUARIO,
    validar_modulo_perfil,
)


MODULOS = (
    MODULO_GERAL,
    MODULO_SEMED,
    MODULO_SEMDU,
    MODULO_CADASTRO_TERRITORIAL,
)

PERFIS = (
    PERFIL_ADMIN,
    PERFIL_AUDITOR,
    PERFIL_DIRETOR,
    PERFIL_SETOR,
    PERFIL_USUARIO,
)


SQL_UPSERT = text(
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
    ON CONFLICT (
        usuario_id,
        modulo
    )
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


SQL_REVOGAR = text(
    """
    UPDATE semed.usuarios_acessos_modulos
    SET
        ativo = FALSE,
        fim_vinculo = CURRENT_DATE,
        atualizado_em = NOW()
    WHERE usuario_id = :usuario_id
      AND modulo = :modulo
    """
)


SQL_LISTAR = text(
    """
    SELECT
        u.login,
        u.nome,
        a.modulo,
        a.perfil,
        a.ativo,
        a.inicio_vinculo,
        a.fim_vinculo
    FROM semed.usuarios_acessos_modulos AS a
    INNER JOIN semed.usuarios AS u
        ON u.id = a.usuario_id
    ORDER BY
        u.login,
        a.modulo
    """
)


def _buscar_usuario(
    login: str,
):
    return (
        db.session.execute(
            db.select(Usuario).where(
                Usuario.login
                == Usuario.normalizar_login(
                    login
                )
            )
        )
        .scalar_one_or_none()
    )


def registrar_comandos_modulos(
    app,
):
    @app.cli.command(
        "definir-acesso-modulo"
    )
    @click.option(
        "--login",
        required=True,
        help="Login já existente em semed.usuarios.",
    )
    @click.option(
        "--modulo",
        required=True,
        type=click.Choice(
            MODULOS,
            case_sensitive=False,
        ),
    )
    @click.option(
        "--perfil",
        required=True,
        type=click.Choice(
            PERFIS,
            case_sensitive=False,
        ),
    )
    def definir_acesso_modulo(
        login,
        modulo,
        perfil,
    ):
        try:
            modulo, perfil = validar_modulo_perfil(
                modulo,
                perfil,
            )
        except ValueError as erro:
            raise click.ClickException(
                str(erro)
            ) from erro

        usuario = _buscar_usuario(
            login
        )

        if usuario is None:
            raise click.ClickException(
                "Usuário não encontrado."
            )

        try:
            db.session.execute(
                SQL_UPSERT,
                {
                    "usuario_id": usuario.id,
                    "modulo": modulo,
                    "perfil": perfil,
                },
            )
            db.session.commit()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível definir o acesso."
            ) from erro

        click.echo(
            (
                "Acesso definido: "
                f"{usuario.login} -> "
                f"{modulo}/{perfil}."
            )
        )

    @app.cli.command(
        "revogar-acesso-modulo"
    )
    @click.option(
        "--login",
        required=True,
    )
    @click.option(
        "--modulo",
        required=True,
        type=click.Choice(
            MODULOS,
            case_sensitive=False,
        ),
    )
    def revogar_acesso_modulo(
        login,
        modulo,
    ):
        usuario = _buscar_usuario(
            login
        )

        if usuario is None:
            raise click.ClickException(
                "Usuário não encontrado."
            )

        modulo = str(
            modulo
        ).upper()

        try:
            resultado = db.session.execute(
                SQL_REVOGAR,
                {
                    "usuario_id": usuario.id,
                    "modulo": modulo,
                },
            )
            db.session.commit()
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível revogar o acesso."
            ) from erro

        if resultado.rowcount == 0:
            click.echo(
                "Nenhum vínculo foi encontrado."
            )
            return

        click.echo(
            (
                "Acesso revogado: "
                f"{usuario.login} -> {modulo}."
            )
        )

    @app.cli.command(
        "listar-acessos-modulos"
    )
    def listar_acessos_modulos():
        try:
            registros = (
                db.session.execute(
                    SQL_LISTAR
                )
                .mappings()
                .all()
            )
        except SQLAlchemyError as erro:
            db.session.rollback()
            raise click.ClickException(
                "Não foi possível listar os acessos."
            ) from erro

        if not registros:
            click.echo(
                "Nenhum acesso modular cadastrado."
            )
            return

        click.echo(
            "LOGIN | MÓDULO | PERFIL | ATIVO"
        )

        for item in registros:
            click.echo(
                (
                    f"{item['login']} | "
                    f"{item['modulo']} | "
                    f"{item['perfil']} | "
                    f"{'SIM' if item['ativo'] else 'NÃO'}"
                )
            )
