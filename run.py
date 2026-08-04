# ==========================================
# RUN.PY
# PONTO DE ENTRADA DA APLICAÇÃO
# ==========================================

from datetime import timezone
from zoneinfo import ZoneInfo

import click

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    request,
    url_for,
)

from flask_login import (
    LoginManager,
    current_user,
)

from flask_migrate import Migrate

from config import Config

from models import (
    Usuario,
    db,
)

from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.escolas import escolas_bp
from routes.home import home_bp
from routes.memorial import memorial_bp
from routes.requisicoes import requisicoes_bp
from routes.rotas import rotas_bp
from routes.setores import setores_bp
from routes.busca_mapa import busca_mapa_bp
from routes.rotas_pcd import (rotas_pcd_bp)

# ==========================================
# CRIAÇÃO DA APLICAÇÃO
# ==========================================

app = Flask(__name__)

app.config.from_object(
    Config
)

# ==========================================
# BANCO DE DADOS
# ==========================================

db.init_app(
    app
)


# ==========================================
# FUSO HORÁRIO
# ==========================================

fuso_local = ZoneInfo(
    app.config["APP_TIMEZONE"]
)


@app.template_filter(
    "data_hora_local"
)
def data_hora_local(valor):
    """
    Converte um horário UTC para o
    fuso configurado na aplicação.
    """

    if valor is None:
        return "Nunca acessou"

    if valor.tzinfo is None:
        valor = valor.replace(
            tzinfo=timezone.utc
        )

    valor_local = valor.astimezone(
        fuso_local
    )

    return valor_local.strftime(
        "%d/%m/%Y %H:%M"
    )


# ==========================================
# FILTRO DAS MIGRAÇÕES
# ==========================================

def incluir_nome_na_migracao(
    name,
    type_,
    parent_names,
):
    """
    Permite que o Alembic examine somente
    o schema e as tabelas pertencentes
    à aplicação WebSIG.
    """

    if type_ == "schema":
        return name == "semed"

    if type_ == "table":
        nome_com_schema = parent_names.get(
            "schema_qualified_table_name"
        )

        return (
            nome_com_schema
            in db.metadata.tables
        )

    return True


# ==========================================
# FLASK-MIGRATE
# ==========================================

migrate = Migrate(
    app,
    db,
    include_schemas=True,
    include_name=incluir_nome_na_migracao,
    compare_type=True,
)


# ==========================================
# FLASK-LOGIN
# ==========================================

login_manager = LoginManager()

login_manager.init_app(
    app
)

login_manager.session_protection = (
    "strong"
)

login_manager.login_view = (
    "auth.login"
)

login_manager.login_message = (
    "Faça login para acessar o sistema."
)

login_manager.login_message_category = (
    "aviso"
)


# ==========================================
# CARREGAMENTO DO USUÁRIO
# ==========================================

@login_manager.user_loader
def carregar_usuario(usuario_id):
    try:
        id_convertido = int(
            usuario_id
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    usuario = db.session.get(
        Usuario,
        id_convertido,
    )

    if usuario is None:
        return None

    if not usuario.ativo:
        return None

    return usuario


# ==========================================
# ACESSO NÃO AUTORIZADO
# ==========================================

@login_manager.unauthorized_handler
def usuario_nao_autorizado():
    """
    APIs recebem erro JSON 401.

    Páginas normais são redirecionadas
    para a tela de login.
    """

    if request.path.startswith(
        "/api/"
    ):
        return jsonify({
            "sucesso": False,
            "erro": (
                "Autenticação necessária."
            ),
        }), 401

    flash(
        "Faça login para acessar o sistema.",
        "aviso",
    )

    if request.query_string:
        destino = request.full_path
    else:
        destino = request.path

    return redirect(
        url_for(
            "auth.login",
            next=destino,
        )
    )


# ==========================================
# ROTAS PÚBLICAS
# ==========================================

ENDPOINTS_PUBLICOS = {
    "auth.login",
    "static",
}


# ==========================================
# PROTEÇÃO GLOBAL
# ==========================================

@app.before_request
def exigir_autenticacao():
    """
    Bloqueia toda a aplicação por padrão.

    Somente os endpoints declarados em
    ENDPOINTS_PUBLICOS podem ser acessados
    sem login.
    """

    endpoint = request.endpoint

    if endpoint is None:
        return None

    if endpoint in ENDPOINTS_PUBLICOS:
        return None

    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    return None


# ==========================================
# BLUEPRINTS
# ==========================================

app.register_blueprint(
    auth_bp
)

app.register_blueprint(
    home_bp
)

app.register_blueprint(
    escolas_bp
)

app.register_blueprint(
    requisicoes_bp
)

app.register_blueprint(
    rotas_bp
)

app.register_blueprint(
    memorial_bp
)

app.register_blueprint(
    admin_bp
)

app.register_blueprint(
    setores_bp
)

app.register_blueprint(
    busca_mapa_bp
)

app.register_blueprint(
    rotas_pcd_bp
)

from comandos.rotas_geojson import (
    registrar_comandos_rotas_geojson,
)

from comandos.setores import (
    registrar_comandos_setores,
)

registrar_comandos_setores(
    app
)

from comandos.memoriais import (
    registrar_comandos_memoriais,
)

registrar_comandos_memoriais(
    app
)

registrar_comandos_rotas_geojson(
    app
)

# ==========================================
# COMANDOS ADMINISTRATIVOS
# ==========================================

@app.cli.command(
    "criar-admin"
)
def criar_admin():
    """
    Cria um administrador do WebSIG.
    """

    click.echo(
        "\nCriação do administrador do WebSIG\n"
    )

    nome = click.prompt(
        "Nome completo"
    ).strip()

    if not nome:
        raise click.ClickException(
            "O nome não pode ficar vazio."
        )

    login = Usuario.normalizar_login(
        click.prompt(
            "Login"
        )
    )

    email_informado = click.prompt(
        "E-mail",
        default="",
        show_default=False,
    )

    email = Usuario.normalizar_email(
        email_informado
    )

    senha = click.prompt(
        "Senha",
        hide_input=True,
        confirmation_prompt=(
            "Confirme a senha"
        ),
    )

    usuario_existente = (
        db.session.execute(
            db.select(
                Usuario
            ).where(
                Usuario.login == login
            )
        )
        .scalar_one_or_none()
    )

    if usuario_existente:
        raise click.ClickException(
            "Já existe um usuário "
            "com esse login."
        )

    if email:
        email_existente = (
            db.session.execute(
                db.select(
                    Usuario
                ).where(
                    Usuario.email == email
                )
            )
            .scalar_one_or_none()
        )

        if email_existente:
            raise click.ClickException(
                "Já existe um usuário "
                "com esse e-mail."
            )

    administrador = Usuario(
        nome=nome,
        login=login,
        email=email,
        perfil=Usuario.PERFIL_ADMIN,
        ativo=True,
        deve_trocar_senha=False,
    )

    try:
        administrador.definir_senha(
            senha
        )

        db.session.add(
            administrador
        )

        db.session.commit()

    except ValueError as erro:
        db.session.rollback()

        raise click.ClickException(
            str(erro)
        ) from erro

    except Exception as erro:
        db.session.rollback()

        app.logger.exception(
            "Erro ao criar administrador."
        )

        raise click.ClickException(
            "Não foi possível criar "
            "o administrador."
        ) from erro

    click.echo(
        "\nAdministrador criado com sucesso."
    )

    click.echo(
        f"Login: {administrador.login}"
    )


# ==========================================
# EXECUÇÃO LOCAL
# ==========================================

if __name__ == "__main__":
    app.run(
        debug=app.config["DEBUG"]
    )