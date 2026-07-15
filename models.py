from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from geoalchemy2 import Geometry
from sqlalchemy.orm import validates


db = SQLAlchemy()

password_hasher = PasswordHasher()


# ==========================================
# ESCOLAS
# ==========================================

class Escola(db.Model):
    __tablename__ = "escolas"

    __table_args__ = {
        "schema": "semed",
    }

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    geom = db.Column(
        Geometry(
            geometry_type="POINT",
            srid=31984,
        ),
        nullable=True,
    )

    fid = db.Column(
        db.BigInteger,
        nullable=True,
    )

    nome = db.Column(
        db.String,
        nullable=True,
    )

    bairro_povoado_assentamento = db.Column(
        db.String,
        nullable=True,
    )

    logradouro = db.Column(
        db.String,
        nullable=True,
    )

    tipo_de_escola = db.Column(
        db.String,
        nullable=True,
    )

    turno = db.Column(
        db.String,
        nullable=True,
    )

    numero_de_porta = db.Column(
        db.String,
        nullable=True,
    )

    observacao = db.Column(
        db.String,
        nullable=True,
    )

    vinculos_usuarios = db.relationship(
        "UsuarioEscola",
        back_populates="escola",
        lazy="selectin",
    )

# ==========================================
# ROTAS
# ==========================================

class RotaGeral(db.Model):
    __tablename__ = "rotas_geral"
    __table_args__ = {
        "schema": "semed"
    }

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    nome_rota = db.Column(
        db.String(100),
    )

    regiao = db.Column(
        db.String(100),
    )

    trecho = db.Column(
        db.String(50),
    )

    total_pontos = db.Column(
        db.Integer,
    )

    pontos_notaveis = db.Column(
        db.JSON,
    )

    geom = db.Column(
        Geometry(
            geometry_type="MULTILINESTRING",
            srid=4326,
        )
    )


# ==========================================
# REQUISIÇÕES
# ==========================================

class Requisicao(db.Model):
    __tablename__ = "requisicoes"
    __table_args__ = {
        "schema": "semed"
    }

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    escola_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.escolas.id"
        ),
        nullable=False,
    )

    tipo = db.Column(
        db.String(50),
    )

    descricao = db.Column(
        db.Text,
        nullable=False,
    )

    status = db.Column(
        db.String(20),
        default="Pendente",
    )

    data_criacao = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
    )

    resposta_semed = db.Column(
        db.Text,
    )

    escola = db.relationship(
        "Escola",
        backref="requisicoes",
    )


# ==========================================
# USUÁRIOS
# ==========================================

class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    PERFIL_ADMIN = "ADMIN"
    PERFIL_DIRETOR = "DIRETOR"
    PERFIL_SETOR = "SETOR"
    PERFIL_AUDITOR = "AUDITOR"

    PERFIS_PERMITIDOS = {
        PERFIL_ADMIN,
        PERFIL_DIRETOR,
        PERFIL_SETOR,
        PERFIL_AUDITOR,
    }

    __table_args__ = (
        db.CheckConstraint(
            (
                "perfil IN "
                "('ADMIN', 'DIRETOR', 'SETOR', 'AUDITOR')"
            ),
            name="ck_usuarios_perfil",
        ),
        {
            "schema": "semed"
        },
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    nome = db.Column(
        db.String(150),
        nullable=False,
    )

    login = db.Column(
        db.String(80),
        nullable=False,
        unique=True,
        index=True,
    )

    email = db.Column(
        db.String(150),
        nullable=True,
        unique=True,
        index=True,
    )

    senha_hash = db.Column(
        db.Text,
        nullable=False,
    )

    perfil = db.Column(
        db.String(20),
        nullable=False,
    )

    ativo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )

    deve_trocar_senha = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )

    ultimo_acesso_em = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    criado_em = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )

    atualizado_em = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )
    vinculos_escolas = db.relationship(
    "UsuarioEscola",
    back_populates="usuario",
    lazy="selectin",
    )

    @property
    def escolas_ativas(self):
        return [
        vinculo.escola
        for vinculo in self.vinculos_escolas
        if vinculo.ativo
        and vinculo.fim_vinculo is None
        ]

    @property
    def is_active(self):
        """
        Propriedade utilizada pelo Flask-Login.

        Contas inativas não poderão iniciar sessão.
        """
        return self.ativo

    @staticmethod
    def normalizar_login(login):
        if login is None:
            return ""

        return login.strip().lower()

    @staticmethod
    def normalizar_email(email):
        if email is None:
            return None

        email_normalizado = email.strip().lower()

        return email_normalizado or None

    @validates("login")
    def validar_login(self, chave, login):
        login_normalizado = self.normalizar_login(
            login
        )

        if not login_normalizado:
            raise ValueError(
                "O login não pode ficar vazio."
            )

        return login_normalizado

    @validates("email")
    def validar_email(self, chave, email):
        return self.normalizar_email(email)

    @validates("perfil")
    def validar_perfil(self, chave, perfil):
        perfil_normalizado = (
            perfil.strip().upper()
            if perfil
            else ""
        )

        if (
            perfil_normalizado
            not in self.PERFIS_PERMITIDOS
        ):
            raise ValueError(
                "Perfil de usuário inválido."
            )

        return perfil_normalizado

    def definir_senha(self, senha):
        if not isinstance(senha, str):
            raise ValueError(
                "A senha precisa ser um texto."
            )

        if len(senha) < 12:
            raise ValueError(
                "A senha deve possuir pelo menos "
                "12 caracteres."
            )

        if len(senha) > 128:
            raise ValueError(
                "A senha deve possuir no máximo "
                "128 caracteres."
            )

        self.senha_hash = password_hasher.hash(
            senha
        )

    def verificar_senha(self, senha):
        if not senha or not self.senha_hash:
            return False

        try:
            senha_valida = password_hasher.verify(
                self.senha_hash,
                senha,
            )

            if (
                senha_valida
                and password_hasher.check_needs_rehash(
                    self.senha_hash
                )
            ):
                self.senha_hash = (
                    password_hasher.hash(senha)
                )

            return senha_valida

        except (
            InvalidHashError,
            VerificationError,
        ):
            return False
        
# ==========================================
# VÍNCULOS ENTRE USUÁRIOS E ESCOLAS
# ==========================================

class UsuarioEscola(db.Model):
    __tablename__ = "usuarios_escolas"

    __table_args__ = (
        db.CheckConstraint(
            (
                "fim_vinculo IS NULL "
                "OR fim_vinculo >= inicio_vinculo"
            ),
            name="ck_usuarios_escolas_periodo",
        ),
        db.Index(
            "ix_usuarios_escolas_usuario_id",
            "usuario_id",
        ),
        db.Index(
            "ix_usuarios_escolas_escola_id",
            "escola_id",
        ),
        db.Index(
            "ix_usuarios_escolas_ativo",
            "ativo",
        ),
        {
            "schema": "semed"
        },
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.usuarios.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    escola_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.escolas.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    ativo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )

    inicio_vinculo = db.Column(
        db.Date,
        nullable=False,
        server_default=db.func.current_date(),
    )

    fim_vinculo = db.Column(
        db.Date,
        nullable=True,
    )

    criado_em = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )

    atualizado_em = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    usuario = db.relationship(
        "Usuario",
        back_populates="vinculos_escolas",
    )

    escola = db.relationship(
        "Escola",
        back_populates="vinculos_usuarios",
    )

    def encerrar(self, data_fim=None):
        self.ativo = False
        self.fim_vinculo = (
            data_fim
            or db.func.current_date()
        )