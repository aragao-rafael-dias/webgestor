# ==========================================
# ROTAS ADMINISTRATIVAS
# ==========================================

from collections import defaultdict
from datetime import date

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    url_for,
)

from flask_login import current_user
from flask_wtf import FlaskForm

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from wtforms import (
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
)

from wtforms.validators import (
    DataRequired,
    EqualTo,
    Length,
    Optional,
)

from models import (
    Escola,
    Setor,
    Usuario,
    UsuarioEscola,
    UsuarioSetor,
    db,
)

from permissoes import admin_required

from servicos.setores import (
    ErroVinculoSetor,
    sincronizar_setores_usuario,
)


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


# ==========================================
# FORMULÁRIO
# ==========================================

class NovoUsuarioForm(FlaskForm):

    nome = StringField(
        "Nome completo",
        validators=[
            DataRequired(
                message=(
                    "Informe o nome completo."
                )
            ),
            Length(
                min=3,
                max=150,
                message=(
                    "O nome deve possuir entre "
                    "3 e 150 caracteres."
                ),
            ),
        ],
    )

    login = StringField(
        "Login",
        validators=[
            DataRequired(
                message="Informe o login."
            ),
            Length(
                min=3,
                max=80,
                message=(
                    "O login deve possuir entre "
                    "3 e 80 caracteres."
                ),
            ),
        ],
    )

    email = StringField(
        "E-mail",
        validators=[
            Optional(),
            Length(
                max=254,
                message=(
                    "O e-mail é muito longo."
                ),
            ),
        ],
    )

    perfil = SelectField(
        "Perfil",
        choices=[
            (
                Usuario.PERFIL_DIRETOR,
                "Diretor",
            ),
            (
                Usuario.PERFIL_SETOR,
                "Usuário de setor",
            ),
            (
                Usuario.PERFIL_AUDITOR,
                "Auditor",
            ),
            (
                Usuario.PERFIL_ADMIN,
                "Administrador",
            ),
        ],
        default=Usuario.PERFIL_DIRETOR,
        validators=[
            DataRequired(
                message=(
                    "Selecione o perfil."
                )
            ),
        ],
    )

    escolas_ids = SelectMultipleField(
        "Escolas vinculadas",
        coerce=int,
        validators=[
            Optional(),
        ],
    )

    setores_ids = SelectMultipleField(
        "Setores vinculados",
        coerce=int,
        validators=[
            Optional(),
        ],
    )

    setor_principal_id = SelectField(
        "Setor principal",
        validators=[
            Optional(),
        ],
    )

    senha = PasswordField(
        "Senha temporária",
        validators=[
            DataRequired(
                message=(
                    "Informe uma senha temporária."
                )
            ),
            Length(
                min=12,
                max=128,
                message=(
                    "A senha deve possuir entre "
                    "12 e 128 caracteres."
                ),
            ),
        ],
    )

    confirmar_senha = PasswordField(
        "Confirmar senha",
        validators=[
            DataRequired(
                message=(
                    "Confirme a senha."
                )
            ),
            EqualTo(
                "senha",
                message=(
                    "As senhas não coincidem."
                ),
            ),
        ],
    )

    submit = SubmitField(
        "Criar usuário"
    )


# ==========================================
# OPÇÕES DE ESCOLAS
# ==========================================

def carregar_escolas():
    return (
        db.session.execute(
            db.select(Escola)
            .where(
                Escola.nome.is_not(None)
            )
            .order_by(
                Escola.nome.asc()
            )
        )
        .scalars()
        .all()
    )


def montar_opcoes_escolas(
    escolas,
):
    return [
        (
            escola.id,
            (
                escola.nome.strip()
                if escola.nome
                else f"Escola {escola.id}"
            ),
        )
        for escola in escolas
    ]


# ==========================================
# OPÇÕES HIERÁRQUICAS DE SETORES
# ==========================================

def carregar_setores():
    return (
        db.session.execute(
            db.select(Setor)
            .where(
                Setor.ativo.is_(True)
            )
            .order_by(
                Setor.ordem.asc(),
                Setor.nome.asc(),
            )
        )
        .scalars()
        .all()
    )


def montar_opcoes_setores(
    setores,
):
    """
    Monta opções hierárquicas:

    Departamento
    └─ Coordenação
    └─ Núcleo
    """

    setores_por_pai = defaultdict(
        list
    )

    ids_disponiveis = {
        setor.id
        for setor in setores
    }

    for setor in setores:
        setor_pai_id = (
            setor.setor_pai_id
            if setor.setor_pai_id
            in ids_disponiveis
            else None
        )

        setores_por_pai[
            setor_pai_id
        ].append(
            setor
        )

    for lista_setores in (
        setores_por_pai.values()
    ):
        lista_setores.sort(
            key=lambda item: (
                item.ordem,
                item.nome.lower(),
            )
        )

    opcoes = []
    ids_visitados = set()

    def adicionar_filhos(
        setor_pai_id=None,
        nivel=0,
    ):
        for setor in setores_por_pai.get(
            setor_pai_id,
            [],
        ):
            if setor.id in ids_visitados:
                continue

            ids_visitados.add(
                setor.id
            )

            prefixo = (
                "— " * nivel
            )

            rotulo = (
                f"{prefixo}"
                f"{setor.nome_completo}"
            )

            opcoes.append(
                (
                    setor.id,
                    rotulo,
                )
            )

            adicionar_filhos(
                setor.id,
                nivel + 1,
            )

    adicionar_filhos()

    for setor in setores:
        if setor.id in ids_visitados:
            continue

        opcoes.append(
            (
                setor.id,
                setor.nome_completo,
            )
        )

    return opcoes


def configurar_opcoes_formulario(
    form,
    escolas,
    setores,
):
    form.escolas_ids.choices = (
        montar_opcoes_escolas(
            escolas
        )
    )

    opcoes_setores = (
        montar_opcoes_setores(
            setores
        )
    )

    form.setores_ids.choices = (
        opcoes_setores
    )

    form.setor_principal_id.choices = [
        (
            "",
            "Selecione o setor principal",
        ),
        *[
            (
                str(setor_id),
                rotulo,
            )
            for setor_id, rotulo
            in opcoes_setores
        ],
    ]


# ==========================================
# RESUMO DOS VÍNCULOS
# ==========================================

def vinculo_esta_ativo(
    vinculo,
    hoje,
):
    if not vinculo.ativo:
        return False

    if (
        vinculo.inicio_vinculo
        and vinculo.inicio_vinculo
        > hoje
    ):
        return False

    if (
        vinculo.fim_vinculo
        and vinculo.fim_vinculo
        < hoje
    ):
        return False

    return True


def montar_resumos_vinculos(
    usuarios,
):
    """
    Prepara os vínculos para a listagem
    administrativa sem colocar regras
    complexas dentro do template.
    """

    hoje = date.today()

    usuario_ids = [
        usuario.id
        for usuario in usuarios
    ]

    setores_por_usuario = defaultdict(
        list
    )

    if usuario_ids:
        vinculos_setores = (
            db.session.execute(
                db.select(UsuarioSetor)
                .join(
                    Setor,
                    Setor.id
                    == UsuarioSetor.setor_id,
                )
                .options(
                    selectinload(
                        UsuarioSetor.setor
                    )
                )
                .where(
                    UsuarioSetor.usuario_id.in_(
                        usuario_ids
                    ),
                    UsuarioSetor.ativo.is_(
                        True
                    ),
                    UsuarioSetor.inicio_vinculo
                    <= hoje,
                    or_(
                        UsuarioSetor.fim_vinculo
                        .is_(None),
                        UsuarioSetor.fim_vinculo
                        >= hoje,
                    ),
                )
                .order_by(
                    UsuarioSetor.usuario_id.asc(),
                    UsuarioSetor.principal.desc(),
                    Setor.ordem.asc(),
                    Setor.nome.asc(),
                )
            )
            .scalars()
            .all()
        )

        for vinculo in vinculos_setores:
            setores_por_usuario[
                vinculo.usuario_id
            ].append(
                vinculo
            )

    resumos = {}

    for usuario in usuarios:
        resumo = {
            "tipo": None,
            "itens": [],
        }

        if (
            usuario.perfil
            == Usuario.PERFIL_DIRETOR
        ):
            resumo["tipo"] = "Escolas"

            vinculos_escolas = [
                vinculo
                for vinculo
                in usuario.vinculos_escolas
                if vinculo_esta_ativo(
                    vinculo,
                    hoje,
                )
            ]

            vinculos_escolas.sort(
                key=lambda vinculo: (
                    (
                        vinculo.escola.nome
                        or ""
                    ).lower()
                )
            )

            resumo["itens"] = [
                (
                    vinculo.escola.nome
                    or (
                        f"Escola "
                        f"{vinculo.escola_id}"
                    )
                )
                for vinculo
                in vinculos_escolas
                if vinculo.escola
            ]

        elif (
            usuario.perfil
            == Usuario.PERFIL_SETOR
        ):
            resumo["tipo"] = "Setores"

            for vinculo in (
                setores_por_usuario.get(
                    usuario.id,
                    [],
                )
            ):
                if not vinculo.setor:
                    continue

                nome = (
                    vinculo.setor.nome_completo
                )

                resumo["itens"].append({
                    "nome": nome,
                    "principal":
                        vinculo.principal,
                })

        resumos[
            usuario.id
        ] = resumo

    return resumos


# ==========================================
# VALIDAÇÕES ADMINISTRATIVAS
# ==========================================

def validar_login_unico(
    form,
    login,
):
    usuario_existente = (
        db.session.execute(
            db.select(Usuario).where(
                Usuario.login == login
            )
        )
        .scalar_one_or_none()
    )

    if usuario_existente:
        form.login.errors.append(
            "Já existe um usuário "
            "com esse login."
        )


def validar_email_unico(
    form,
    email,
):
    if not email:
        return

    usuario_existente = (
        db.session.execute(
            db.select(Usuario).where(
                Usuario.email == email
            )
        )
        .scalar_one_or_none()
    )

    if usuario_existente:
        form.email.errors.append(
            "Já existe um usuário "
            "com esse e-mail."
        )


def validar_vinculos_perfil(
    form,
    perfil,
):
    if (
        perfil
        == Usuario.PERFIL_DIRETOR
        and not form.escolas_ids.data
    ):
        form.escolas_ids.errors.append(
            "Selecione ao menos uma escola "
            "para o diretor."
        )

    if (
        perfil
        == Usuario.PERFIL_SETOR
    ):
        if not form.setores_ids.data:
            form.setores_ids.errors.append(
                "Selecione ao menos um setor "
                "para o usuário."
            )

        setor_principal = (
            form.setor_principal_id.data
            or ""
        ).strip()

        if not setor_principal:
            form.setor_principal_id.errors.append(
                "Selecione o setor principal."
            )

        else:
            try:
                setor_principal_id = int(
                    setor_principal
                )

            except (
                TypeError,
                ValueError,
            ):
                form.setor_principal_id.errors.append(
                    "O setor principal "
                    "informado é inválido."
                )

            else:
                if (
                    setor_principal_id
                    not in (
                        form.setores_ids.data
                        or []
                    )
                ):
                    form.setor_principal_id.errors.append(
                        "O setor principal deve "
                        "estar entre os setores "
                        "selecionados."
                    )


def formulario_possui_erros(
    form,
):
    campos = (
        form.nome,
        form.login,
        form.email,
        form.perfil,
        form.escolas_ids,
        form.setores_ids,
        form.setor_principal_id,
        form.senha,
        form.confirmar_senha,
    )

    return any(
        campo.errors
        for campo in campos
    )


# ==========================================
# PÁGINA INICIAL ADMINISTRATIVA
# ==========================================

@admin_bp.get("/")
@admin_required
def inicio():
    return redirect(
        url_for(
            "admin.listar_usuarios"
        )
    )


# ==========================================
# LISTAGEM DE USUÁRIOS
# ==========================================

@admin_bp.get("/usuarios")
@admin_required
def listar_usuarios():

    usuarios = (
        db.session.execute(
            db.select(Usuario)
            .options(
                selectinload(
                    Usuario.criado_por
                ),
                selectinload(
                    Usuario.vinculos_escolas
                ).selectinload(
                    UsuarioEscola.escola
                ),
            )
            .order_by(
                Usuario.nome.asc()
            )
        )
        .scalars()
        .all()
    )

    vinculos_por_usuario = (
        montar_resumos_vinculos(
            usuarios
        )
    )

    return render_template(
        "admin/usuarios.html",
        usuarios=usuarios,
        vinculos_por_usuario=(
            vinculos_por_usuario
        ),
    )


# ==========================================
# CRIAÇÃO DE USUÁRIO
# ==========================================

@admin_bp.route(
    "/usuarios/novo",
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def novo_usuario():

    escolas = carregar_escolas()
    setores = carregar_setores()

    form = NovoUsuarioForm()

    configurar_opcoes_formulario(
        form,
        escolas,
        setores,
    )

    if form.validate_on_submit():

        nome = form.nome.data.strip()

        login = (
            Usuario.normalizar_login(
                form.login.data
            )
        )

        email = (
            Usuario.normalizar_email(
                form.email.data
            )
        )

        perfil = (
            form.perfil.data
            .strip()
            .upper()
        )

        validar_login_unico(
            form,
            login,
        )

        validar_email_unico(
            form,
            email,
        )

        validar_vinculos_perfil(
            form,
            perfil,
        )

        if not formulario_possui_erros(
            form
        ):
            novo_usuario = Usuario(
                nome=nome,
                login=login,
                email=email,
                perfil=perfil,
                ativo=True,
                deve_trocar_senha=True,
                criado_por_id=(
                    current_user.id
                ),
            )

            try:
                novo_usuario.definir_senha(
                    form.senha.data
                )

                db.session.add(
                    novo_usuario
                )

                db.session.flush()

                if (
                    perfil
                    == Usuario.PERFIL_DIRETOR
                ):
                    escolas_ids_unicos = (
                        dict.fromkeys(
                            form.escolas_ids.data
                        )
                    )

                    for escola_id in (
                        escolas_ids_unicos
                    ):
                        vinculo = UsuarioEscola(
                            usuario_id=(
                                novo_usuario.id
                            ),
                            escola_id=escola_id,
                            ativo=True,
                        )

                        db.session.add(
                            vinculo
                        )

                if (
                    perfil
                    == Usuario.PERFIL_SETOR
                ):
                    sincronizar_setores_usuario(
                        usuario=novo_usuario,
                        setor_ids=(
                            form.setores_ids.data
                        ),
                        setor_principal_id=(
                            form
                            .setor_principal_id
                            .data
                        ),
                    )

                db.session.commit()

            except ErroVinculoSetor as erro:
                db.session.rollback()

                form.setores_ids.errors.append(
                    str(erro)
                )

            except ValueError as erro:
                db.session.rollback()

                form.senha.errors.append(
                    str(erro)
                )

            except IntegrityError:
                db.session.rollback()

                current_app.logger.exception(
                    "Erro de integridade ao "
                    "criar usuário."
                )

                flash(
                    (
                        "Não foi possível criar "
                        "o usuário. Confira o "
                        "login, o e-mail e os "
                        "vínculos selecionados."
                    ),
                    "erro",
                )

            except Exception:
                db.session.rollback()

                current_app.logger.exception(
                    "Erro inesperado ao "
                    "criar usuário."
                )

                flash(
                    (
                        "Não foi possível criar "
                        "o usuário."
                    ),
                    "erro",
                )

            else:
                flash(
                    (
                        f"Usuário "
                        f"{novo_usuario.nome} "
                        "criado com sucesso."
                    ),
                    "sucesso",
                )

                return redirect(
                    url_for(
                        "admin.listar_usuarios"
                    )
                )

    return render_template(
        "admin/novo_usuario.html",
        form=form,
    )