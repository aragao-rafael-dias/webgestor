from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
)
from flask_wtf import FlaskForm

from servicos.acessos_modulos import (
    MODULO_CADASTRO_TERRITORIAL,
    MODULO_SEMED,
    MODULO_SEMDU,
    listar_modulos_usuario,
    obter_acesso_modulo,
)


home_bp = Blueprint(
    "home",
    __name__,
)


class ModuloForm(FlaskForm):
    pass


@home_bp.get("/")
@home_bp.get("/modulos")
@login_required
def seletor_modulos():
    session.pop(
        "modulo_atual",
        None,
    )

    return render_template(
        "modulos.html",
        modulos=listar_modulos_usuario(
            current_user
        ),
        form=ModuloForm(),
    )


# Compatibilidade com templates antigos que usam home.home.
@home_bp.get("/inicio")
@login_required
def home():
    return redirect(
        url_for("home.seletor_modulos")
    )


@home_bp.post(
    "/modulos/entrar/<string:modulo>"
)
@login_required
def entrar_modulo(
    modulo: str,
):
    formulario = ModuloForm()

    if not formulario.validate_on_submit():
        abort(400)

    modulo = str(
        modulo or ""
    ).strip().upper()

    destinos = {
        MODULO_SEMED: "home.mapa_semed",
        MODULO_SEMDU: "semdu.mapa",
        MODULO_CADASTRO_TERRITORIAL: "cadastro_territorial.mapa",
    }

    endpoint = destinos.get(
        modulo
    )

    if endpoint is None:
        abort(
            404,
            description="Módulo inexistente.",
        )

    acesso = obter_acesso_modulo(
        current_user,
        modulo,
    )

    if acesso is None:
        flash(
            (
                "Seu usuário não possui acesso "
                f"ao módulo {modulo}."
            ),
            "erro",
        )
        return redirect(
            url_for("home.seletor_modulos")
        )

    session["modulo_atual"] = modulo

    return redirect(
        url_for(endpoint)
    )


@home_bp.get("/semed")
@home_bp.get("/semed/mapa")
@home_bp.get("/mapa")
@login_required
def mapa_semed():
    acesso = obter_acesso_modulo(
        current_user,
        MODULO_SEMED,
    )

    if acesso is None:
        abort(
            403,
            description=(
                "Seu usuário não possui acesso "
                "ao módulo SEMED."
            ),
        )

    session["modulo_atual"] = MODULO_SEMED

    return render_template(
        "index.html",
        acesso_modulo=acesso,
    )
