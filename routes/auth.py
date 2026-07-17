from urllib.parse import urlsplit
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import FlaskForm
from sqlalchemy import func, select
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


# ==========================================
# FORMULÁRIOS
# ==========================================

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


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def destino_interno_seguro(destino):
    """
    Aceita somente caminhos internos da aplicação.

    Exemplos aceitos:
    /
    /mapa
    /painel?pagina=2

    URLs externas são recusadas.
    """

    if not destino:
        return False

    partes = urlsplit(destino)

    return (
        partes.scheme == ""
        and partes.netloc == ""
        and destino.startswith("/")
        and not destino.startswith("//")
    )


@auth_bp.app_context_processor
def disponibilizar_formulario_logout():
    """
    Disponibiliza logout_form automaticamente
    para os templates da aplicação.
    """

    return {
        "logout_form": LogoutForm()
    }


# ==========================================
# LOGIN
# ==========================================

@auth_bp.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    if current_user.is_authenticated:
        return redirect("/")

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

        destino = request.args.get(
            "next"
        )

        if destino_interno_seguro(destino):
            return redirect(destino)

        return redirect("/")

    return render_template(
        "login.html",
        form=formulario,
    )


# ==========================================
# LOGOUT
# ==========================================

@auth_bp.post("/logout")
@login_required
def logout():
    formulario = LogoutForm()

    if not formulario.validate_on_submit():
        abort(400)

    logout_user()

    flash(
        "Você saiu do sistema.",
        "sucesso",
    )

    return redirect(
        url_for("auth.login")
    )