from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, Optional

from models import Usuario, db
from servicos.acessos_modulos import MODULO_SEMDU, obter_acesso_modulo
from servicos.funcoes_semdu import FUNCAO_ENG_AMBIENTAL, FUNCAO_FISCAL
from servicos.usuarios_semdu import (
    buscar_usuario_semdu,
    criar_usuario_semdu,
    listar_funcoes_por_usuario,
    listar_usuarios_semdu,
    sincronizar_funcoes_usuario,
)


semdu_usuarios_bp = Blueprint(
    "semdu_usuarios",
    __name__,
)


class NovoUsuarioSemduForm(FlaskForm):
    nome = StringField(
        "Nome completo",
        validators=[
            DataRequired(message="Informe o nome completo."),
            Length(
                min=3,
                max=150,
                message="O nome deve possuir entre 3 e 150 caracteres.",
            ),
        ],
    )
    login = StringField(
        "Login",
        validators=[
            DataRequired(message="Informe o login."),
            Length(
                min=3,
                max=80,
                message="O login deve possuir entre 3 e 80 caracteres.",
            ),
        ],
    )
    email = StringField(
        "E-mail",
        validators=[
            Optional(),
            Length(max=150, message="O e-mail é muito longo."),
        ],
    )
    senha = PasswordField(
        "Senha temporária",
        validators=[
            DataRequired(message="Informe uma senha temporária."),
            Length(
                min=12,
                max=128,
                message="A senha deve possuir entre 12 e 128 caracteres.",
            ),
        ],
    )
    confirmar_senha = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired(message="Confirme a senha."),
            EqualTo("senha", message="As senhas não coincidem."),
        ],
    )
    fiscal = BooleanField("Fiscal da SEMDU")
    eng_ambiental = BooleanField("Engenharia Ambiental")
    submit = SubmitField("Criar usuário")


class AcaoUsuarioForm(FlaskForm):
    submit = SubmitField("Salvar")


def semdu_admin_required(funcao):
    @wraps(funcao)
    def protegida(*args, **kwargs):
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()

        acesso = obter_acesso_modulo(current_user, MODULO_SEMDU)
        if acesso is None or not acesso.administrador:
            abort(
                403,
                description=(
                    "Somente administradores da SEMDU podem gerenciar "
                    "usuários deste módulo."
                ),
            )
        return funcao(*args, **kwargs)

    return protegida


def _login_ja_existe(login: str) -> bool:
    return (
        db.session.execute(
            db.select(Usuario.id).where(
                Usuario.login == Usuario.normalizar_login(login)
            )
        ).scalar_one_or_none()
        is not None
    )


def _email_ja_existe(email: str | None) -> bool:
    email = Usuario.normalizar_email(email)
    if not email:
        return False
    return (
        db.session.execute(
            db.select(Usuario.id).where(Usuario.email == email)
        ).scalar_one_or_none()
        is not None
    )


def _funcoes_formulario(form: NovoUsuarioSemduForm) -> set[str]:
    funcoes = set()
    if form.fiscal.data:
        funcoes.add(FUNCAO_FISCAL)
    if form.eng_ambiental.data:
        funcoes.add(FUNCAO_ENG_AMBIENTAL)
    return funcoes


@semdu_usuarios_bp.route(
    "/semdu/usuarios",
    methods=["GET", "POST"],
)
@semdu_admin_required
def usuarios():
    form = NovoUsuarioSemduForm()
    acao_form = AcaoUsuarioForm()

    if form.validate_on_submit():
        login = Usuario.normalizar_login(form.login.data)
        email = Usuario.normalizar_email(form.email.data)

        if _login_ja_existe(login):
            form.login.errors.append("Já existe um usuário com esse login.")
        if _email_ja_existe(email):
            form.email.errors.append("Já existe um usuário com esse e-mail.")

        if not form.login.errors and not form.email.errors:
            try:
                usuario = criar_usuario_semdu(
                    nome=form.nome.data,
                    login=login,
                    email=email,
                    senha=form.senha.data,
                    criado_por_id=current_user.id,
                    funcoes=_funcoes_formulario(form),
                )
                db.session.commit()
            except ValueError as erro:
                db.session.rollback()
                form.senha.errors.append(str(erro))
            except IntegrityError:
                db.session.rollback()
                current_app.logger.exception(
                    "Erro de integridade ao criar usuário SEMDU."
                )
                flash(
                    "Não foi possível criar o usuário. Confira login e e-mail.",
                    "erro",
                )
            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception(
                    "Erro de banco ao criar usuário SEMDU."
                )
                flash(
                    "Não foi possível criar o usuário da SEMDU no banco de dados.",
                    "erro",
                )
            else:
                flash(
                    f"Usuário {usuario.login} criado com sucesso para a SEMDU.",
                    "sucesso",
                )
                return redirect(url_for("semdu_usuarios.usuarios"))

    usuarios_semdu = listar_usuarios_semdu()
    funcoes_por_usuario = listar_funcoes_por_usuario(usuarios_semdu)

    return render_template(
        "semdu/usuarios.html",
        form=form,
        acao_form=acao_form,
        usuarios=usuarios_semdu,
        funcoes_por_usuario=funcoes_por_usuario,
        FUNCAO_FISCAL=FUNCAO_FISCAL,
        FUNCAO_ENG_AMBIENTAL=FUNCAO_ENG_AMBIENTAL,
    )


@semdu_usuarios_bp.post(
    "/semdu/usuarios/<int:usuario_id>/funcoes"
)
@semdu_admin_required
def atualizar_funcoes(usuario_id: int):
    form = AcaoUsuarioForm()
    if not form.validate_on_submit():
        abort(400, description="Formulário inválido ou token CSRF expirado.")

    usuario = buscar_usuario_semdu(usuario_id)
    if usuario is None:
        abort(404, description="Usuário SEMDU não encontrado.")

    funcoes = set()
    if request.form.get("fiscal") == "1":
        funcoes.add(FUNCAO_FISCAL)
    if request.form.get("eng_ambiental") == "1":
        funcoes.add(FUNCAO_ENG_AMBIENTAL)

    try:
        sincronizar_funcoes_usuario(
            usuario.id,
            funcoes,
            designado_por_id=current_user.id,
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao atualizar funções SEMDU do usuário %s.",
            usuario.id,
        )
        flash("Não foi possível atualizar as permissões.", "erro")
    else:
        flash(
            f"Permissões de {usuario.nome} atualizadas.",
            "sucesso",
        )

    return redirect(url_for("semdu_usuarios.usuarios"))


@semdu_usuarios_bp.post(
    "/semdu/usuarios/<int:usuario_id>/status"
)
@semdu_admin_required
def alternar_status(usuario_id: int):
    form = AcaoUsuarioForm()
    if not form.validate_on_submit():
        abort(400, description="Formulário inválido ou token CSRF expirado.")

    usuario = buscar_usuario_semdu(usuario_id)
    if usuario is None:
        abort(404, description="Usuário SEMDU não encontrado.")

    usuario.ativo = not usuario.ativo
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao alterar status do usuário SEMDU %s.",
            usuario.id,
        )
        flash("Não foi possível alterar o status do usuário.", "erro")
    else:
        estado = "ativado" if usuario.ativo else "desativado"
        flash(f"Usuário {usuario.login} {estado}.", "sucesso")

    return redirect(url_for("semdu_usuarios.usuarios"))
