from __future__ import annotations

from datetime import datetime, timezone
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import FlaskForm
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from wtforms import (
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Length,
)

from models import Usuario, db


auth_bp = Blueprint(
    "auth",
    __name__,
)


class LoginForm(FlaskForm):
    login = StringField(
        "Login",
        validators=[
            DataRequired(
                message="Informe o login."
            ),
            Length(
                max=80,
                message=(
                    "O login deve possuir no máximo "
                    "80 caracteres."
                ),
            ),
        ],
    )

    senha = PasswordField(
        "Senha",
        validators=[
            DataRequired(
                message="Informe a senha."
            ),
            Length(
                max=128,
                message=(
                    "A senha deve possuir no máximo "
                    "128 caracteres."
                ),
            ),
        ],
    )

    entrar = SubmitField(
        "Entrar"
    )


class LogoutForm(FlaskForm):
    sair = SubmitField(
        "Sair"
    )



@auth_bp.app_context_processor
def disponibilizar_formulario_logout():
    return {
        "logout_form": LogoutForm()
    }


@auth_bp.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    if current_user.is_authenticated:
        return redirect(
            url_for("home.seletor_modulos")
        )

    formulario = LoginForm()

    if formulario.validate_on_submit():
        login_normalizado = (
            Usuario.normalizar_login(
                formulario.login.data
            )
        )

        usuario = (
            db.session.execute(
                select(Usuario).where(
                    Usuario.login
                    == login_normalizado
                )
            )
            .scalar_one_or_none()
        )

        credenciais_validas = (
            usuario is not None
            and usuario.ativo
            and usuario.verificar_senha(
                formulario.senha.data
            )
        )

        if not credenciais_validas:
            flash(
                "Login ou senha inválidos.",
                "erro",
            )
            return render_template(
                "login.html",
                form=formulario,
            )

        try:
            usuario.ultimo_acesso_em = datetime.now(
                timezone.utc
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash(
                (
                    "Não foi possível iniciar a "
                    "sessão. Tente novamente."
                ),
                "erro",
            )
            return render_template(
                "login.html",
                form=formulario,
            )

        login_user(
            usuario,
            remember=False,
        )

        session.pop(
            "modulo_atual",
            None,
        )

        # A primeira página autenticada é sempre
        # o seletor. A troca de secretaria ocorre
        # somente depois da escolha explícita.
        return redirect(
            url_for("home.seletor_modulos")
        )

    return render_template(
        "login.html",
        form=formulario,
    )


@auth_bp.post("/logout")
@login_required
def logout():
    formulario = LogoutForm()

    if not formulario.validate_on_submit():
        abort(400)

    session.pop(
        "modulo_atual",
        None,
    )

    logout_user()

    flash(
        "Você saiu do sistema.",
        "sucesso",
    )

    return redirect(
        url_for("auth.login")
    )
