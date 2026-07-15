from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

from config import Config
from models import db

from routes.home import home_bp
from routes.escolas import escolas_bp
from routes.requisicoes import requisicoes_bp
from routes.rotas import rotas_bp
from routes.memorial import memorial_bp


app = Flask(__name__)
app.config.from_object(Config)


# ==========================================
# EXTENSÕES
# ==========================================

db.init_app(app)

migrate = Migrate()

migrate.init_app(
    app,
    db,
    include_schemas=True,
)

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.session_protection = "strong"


# ==========================================
# BLUEPRINTS
# ==========================================

app.register_blueprint(home_bp)
app.register_blueprint(escolas_bp)
app.register_blueprint(requisicoes_bp)
app.register_blueprint(rotas_bp)
app.register_blueprint(memorial_bp)


# ==========================================
# EXECUÇÃO LOCAL
# ==========================================

if __name__ == "__main__":
    app.run(
        debug=app.config["DEBUG"]
    )