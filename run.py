# ==========================================
# RUN.PY
# PONTO DE ENTRADA DA APLICAÇÃO
# ==========================================

from __future__ import annotations

from datetime import timezone
from importlib import import_module
from importlib.util import find_spec
from zoneinfo import ZoneInfo

import click

from flask import (
    Flask,
    flash,
    g,
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
from routes.arborizacao import arborizacao_bp
from routes.cadastro_territorial import cadastro_territorial_bp
from routes.auth import auth_bp
from routes.escolas import escolas_bp
from routes.home import home_bp
from routes.memorial import memorial_bp
from routes.requisicoes import requisicoes_bp
from routes.rotas import rotas_bp
from routes.semdu import semdu_bp
from routes.setores import setores_bp

from servicos.acessos_modulos import (
    MODULO_CADASTRO_TERRITORIAL,
    MODULO_SEMDU,
    MODULO_SEMED,
    UsuarioContextual,
    obter_acesso_modulo,
)


app = Flask(__name__)

app.config.from_object(
    Config
)

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
# FLASK-MIGRATE
# ==========================================

def incluir_nome_na_migracao(
    name,
    type_,
    parent_names,
):
    # As camadas do schema semdu são geridas
    # diretamente no PostgreSQL/PostGIS.
    # O Alembic continua cuidando somente
    # dos modelos ORM do schema semed.
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


@login_manager.user_loader
def carregar_usuario(
    usuario_id,
):
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

    if (
        usuario is None
        or not usuario.ativo
    ):
        return None

    return UsuarioContextual(
        usuario
    )


@login_manager.unauthorized_handler
def usuario_nao_autorizado():
    if request.path.startswith(
        "/api/"
    ):
        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Autenticação necessária."
                ),
            }
        ), 401

    flash(
        "Faça login para acessar o sistema.",
        "aviso",
    )

    destino = (
        request.full_path
        if request.query_string
        else request.path
    )

    return redirect(
        url_for(
            "auth.login",
            next=destino,
        )
    )


# ==========================================
# PROTEÇÃO GLOBAL E MÓDULO DA REQUISIÇÃO
# ==========================================

ENDPOINTS_PUBLICOS = {
    "auth.login",
    "semdu.login_compativel",
    "static",
}

ENDPOINTS_SEM_MODULO = {
    "auth.login",
    "auth.logout",
    "home.seletor_modulos",
    "home.home",
    "home.entrar_modulo",
    "semdu.login_compativel",
    "static",
}


def identificar_modulo_requisicao():
    endpoint = request.endpoint

    if (
        endpoint is None
        or endpoint in ENDPOINTS_SEM_MODULO
    ):
        return None

    if (
        request.path == "/cadastro-territorial"
        or request.path.startswith(
            "/cadastro-territorial/"
        )
        or request.path.startswith(
            "/api/cadastro-territorial/"
        )
    ):
        return MODULO_CADASTRO_TERRITORIAL

    if (
        request.path == "/semdu"
        or request.path.startswith(
            "/semdu/"
        )
        or request.path.startswith(
            "/api/semdu/"
        )
    ):
        return MODULO_SEMDU

    return MODULO_SEMED


@app.before_request
def preparar_acesso_requisicao():
    endpoint = request.endpoint

    g.modulo_requisicao = (
        identificar_modulo_requisicao()
    )

    if endpoint is None:
        return None

    if endpoint in ENDPOINTS_PUBLICOS:
        return None

    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    modulo = g.modulo_requisicao

    if modulo is None:
        return None

    acesso = obter_acesso_modulo(
        current_user,
        modulo,
    )

    if acesso is not None:
        g.acesso_modulo = acesso
        return None

    mensagem = (
        "Seu usuário não possui acesso "
        f"ao módulo {modulo}."
    )

    if request.path.startswith(
        "/api/"
    ):
        return jsonify(
            {
                "sucesso": False,
                "erro": mensagem,
                "modulo": modulo,
            }
        ), 403

    flash(
        mensagem,
        "erro",
    )

    return redirect(
        url_for("home.seletor_modulos")
    )


# ==========================================
# BLUEPRINTS PRINCIPAIS
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
    semdu_bp
)

app.register_blueprint(
    arborizacao_bp
)

app.register_blueprint(
    cadastro_territorial_bp
)


# ==========================================
# COMPLEMENTOS OPCIONAIS JÁ USADOS NA SEMED
# ==========================================

def registrar_blueprint_opcional(
    modulo_importacao: str,
    nome_atributo: str,
) -> None:
    if find_spec(
        modulo_importacao
    ) is None:
        return

    modulo = import_module(
        modulo_importacao
    )

    blueprint = getattr(
        modulo,
        nome_atributo,
    )

    app.register_blueprint(
        blueprint
    )


registrar_blueprint_opcional(
    "routes.busca_mapa",
    "busca_mapa_bp",
)

registrar_blueprint_opcional(
    "routes.rotas_pcd",
    "rotas_pcd_bp",
)


# ==========================================
# COMANDOS
# ==========================================

def registrar_comando(
    modulo_importacao: str,
    nome_funcao: str,
    *,
    obrigatorio: bool = False,
) -> None:
    if find_spec(
        modulo_importacao
    ) is None:
        if obrigatorio:
            raise RuntimeError(
                (
                    "Módulo obrigatório não encontrado: "
                    f"{modulo_importacao}"
                )
            )
        return

    modulo = import_module(
        modulo_importacao
    )

    funcao = getattr(
        modulo,
        nome_funcao,
    )

    funcao(
        app
    )


registrar_comando(
    "comandos.setores",
    "registrar_comandos_setores",
    obrigatorio=True,
)

registrar_comando(
    "comandos.modulos",
    "registrar_comandos_modulos",
    obrigatorio=True,
)

registrar_comando(
    "comandos.arborizacao",
    "registrar_comandos_arborizacao",
    obrigatorio=True,
)

registrar_comando(
    "comandos.ortofotos_semdu",
    "registrar_comandos_ortofotos_semdu",
    obrigatorio=True,
)

registrar_comando(
    "comandos.cadastro_territorial",
    "registrar_comandos_cadastro_territorial",
    obrigatorio=True,
)

registrar_comando(
    "comandos.memoriais",
    "registrar_comandos_memoriais",
)

registrar_comando(
    "comandos.rotas_geojson",
    "registrar_comandos_rotas_geojson",
)


# ==========================================
# CRIAÇÃO DO PRIMEIRO ADMINISTRADOR
# ==========================================

@app.cli.command(
    "criar-admin"
)
def criar_admin():
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

    email = Usuario.normalizar_email(
        click.prompt(
            "E-mail",
            default="",
            show_default=False,
        )
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
            db.select(Usuario).where(
                Usuario.login == login
            )
        )
        .scalar_one_or_none()
    )

    if usuario_existente:
        raise click.ClickException(
            "Já existe um usuário com esse login."
        )

    if email:
        email_existente = (
            db.session.execute(
                db.select(Usuario).where(
                    Usuario.email == email
                )
            )
            .scalar_one_or_none()
        )

        if email_existente:
            raise click.ClickException(
                "Já existe um usuário com esse e-mail."
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
            "Não foi possível criar o administrador."
        ) from erro

    click.echo(
        "\nAdministrador criado com sucesso."
    )

    click.echo(
        f"Login: {administrador.login}"
    )


if __name__ == "__main__":
    app.run(
        debug=app.config["DEBUG"]
    )
