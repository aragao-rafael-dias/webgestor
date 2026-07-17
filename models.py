from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from geoalchemy2 import Geometry
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import JSONB


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

    __table_args__ = (
        db.Index(
            "ix_requisicoes_escola_status",
            "escola_id",
            "status",
        ),
        db.Index(
            "ix_requisicoes_setor_status",
            "setor_id",
            "status",
        ),
        {
            "schema": "semed",
        },
    )

    STATUS_PENDENTE = "Pendente"
    STATUS_RESPONDIDA = "Respondida"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    escola_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.escolas.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    setor_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.setores.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    tipo = db.Column(
        db.String(50),
        nullable=True,
    )

    descricao = db.Column(
        db.Text,
        nullable=False,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default=STATUS_PENDENTE,
        server_default=STATUS_PENDENTE,
    )

    data_criacao = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    resposta_semed = db.Column(
        db.Text,
        nullable=True,
    )

    respondido_por_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    data_resposta = db.Column(
        db.DateTime,
        nullable=True,
    )

    escola = db.relationship(
        "Escola",
        backref=db.backref(
            "requisicoes",
            lazy="dynamic",
        ),
    )

    setor = db.relationship(
        "Setor",
        back_populates="requisicoes",
        foreign_keys=[setor_id],
    )

    respondido_por = db.relationship(
        "Usuario",
        foreign_keys=[respondido_por_id],
        backref=db.backref(
            "requisicoes_respondidas",
            lazy="dynamic",
        ),
    )

    def __repr__(self):
        return (
            f"<Requisicao id={self.id} "
            f"escola_id={self.escola_id} "
            f"setor_id={self.setor_id} "
            f"status={self.status!r}>"
        )

    @property
    def pendente(self):
        return (
            self.status
            == self.STATUS_PENDENTE
        )

    @property
    def respondida(self):
        return (
            self.status
            == self.STATUS_RESPONDIDA
        )

    def para_dict(self):
        return {
            "id": self.id,
            "escola_id":
                self.escola_id,
            "setor_id":
                self.setor_id,
            "setor": (
                self.setor.nome
                if self.setor
                else None
            ),
            "tipo":
                self.tipo,
            "descricao":
                self.descricao,
            "status":
                self.status,
            "data_criacao": (
                self.data_criacao.isoformat()
                if self.data_criacao
                else None
            ),
            "resposta_semed":
                self.resposta_semed,
            "respondido_por_id":
                self.respondido_por_id,
            "respondido_por": (
                getattr(
                    self.respondido_por,
                    "nome",
                    None,
                )
                if self.respondido_por
                else None
            ),
            "data_resposta": (
                self.data_resposta.isoformat()
                if self.data_resposta
                else None
            ),
        }


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

    criado_por_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
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
    criado_por = db.relationship(
    "Usuario",
    remote_side=[id],
    foreign_keys=[criado_por_id],
    back_populates="usuarios_criados",
    )
    usuarios_criados = db.relationship(
        "Usuario",
        foreign_keys="Usuario.criado_por_id",
        back_populates="criado_por",
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

# ==========================================
# SETORES DA SECRETARIA
# ==========================================

class Setor(db.Model):
    __tablename__ = "setores"

    __table_args__ = (
        db.UniqueConstraint(
            "sigla",
            name="uq_setores_sigla",
        ),
        db.Index(
            "ix_setores_ativo_ordem",
            "ativo",
            "ordem",
        ),
        {
            "schema": "semed",
        },
    )

    TIPO_DEPARTAMENTO = "DEPARTAMENTO"
    TIPO_COORDENACAO = "COORDENACAO"
    TIPO_NUCLEO = "NUCLEO"
    TIPO_ASSESSORIA = "ASSESSORIA"
    TIPO_CONSELHO = "CONSELHO"
    TIPO_GABINETE = "GABINETE"
    TIPO_SECRETARIA = "SECRETARIA"
    TIPO_OUTRO = "OUTRO"

    TIPOS_VALIDOS = (
        TIPO_DEPARTAMENTO,
        TIPO_COORDENACAO,
        TIPO_NUCLEO,
        TIPO_ASSESSORIA,
        TIPO_CONSELHO,
        TIPO_GABINETE,
        TIPO_SECRETARIA,
        TIPO_OUTRO,
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    nome = db.Column(
        db.String(180),
        nullable=False,
    )

    sigla = db.Column(
        db.String(30),
        nullable=True,
    )

    tipo = db.Column(
        db.String(30),
        nullable=False,
        default=TIPO_OUTRO,
        server_default=TIPO_OUTRO,
    )

    setor_pai_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.setores.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    descricao = db.Column(
        db.Text,
        nullable=True,
    )

    competencias = db.Column(
        JSONB,
        nullable=False,
        default=list,
        server_default=db.text(
            "'[]'::jsonb"
        ),
    )

    imagem_url = db.Column(
        db.String(500),
        nullable=True,
    )

    dados_websig = db.Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=db.text(
            "'{}'::jsonb"
        ),
    )

    ativo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )

    ordem = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    criado_em = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    atualizado_em = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    setor_pai = db.relationship(
        "Setor",
        remote_side=[id],
        back_populates="setores_filhos",
        foreign_keys=[setor_pai_id],
    )

    setores_filhos = db.relationship(
        "Setor",
        back_populates="setor_pai",
        foreign_keys=[setor_pai_id],
        lazy="selectin",
    )

    requisicoes = db.relationship(
        "Requisicao",
        back_populates="setor",
        lazy="dynamic",
    )

    vinculos_usuarios = db.relationship(
        "UsuarioSetor",
        back_populates="setor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return (
            f"<Setor id={self.id} "
            f"nome={self.nome!r}>"
        )

    @property
    def nome_completo(self):
        if self.sigla:
            return f"{self.nome} ({self.sigla})"

        return self.nome

    def para_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "nome_completo":
                self.nome_completo,
            "sigla": self.sigla,
            "tipo": self.tipo,
            "setor_pai_id":
                self.setor_pai_id,
            "descricao":
                self.descricao,
            "competencias":
                self.competencias or [],
            "imagem_url":
                self.imagem_url,
            "dados_websig":
                self.dados_websig or {},
            "ativo":
                self.ativo,
            "ordem":
                self.ordem,
        }
    
# ==========================================
# VÍNCULO ENTRE USUÁRIO E SETOR
# ==========================================

class UsuarioSetor(db.Model):
    __tablename__ = "usuarios_setores"

    __table_args__ = (
        db.UniqueConstraint(
            "usuario_id",
            "setor_id",
            name="uq_usuario_setor",
        ),
        db.Index(
            "ix_usuarios_setores_usuario_ativo",
            "usuario_id",
            "ativo",
        ),
        db.Index(
            "ix_usuarios_setores_setor_ativo",
            "setor_id",
            "ativo",
        ),
        {
            "schema": "semed",
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
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    setor_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.setores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    principal = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false(),
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
        server_default=db.text(
            "CURRENT_DATE"
        ),
    )

    fim_vinculo = db.Column(
        db.Date,
        nullable=True,
    )

    criado_em = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    usuario = db.relationship(
        "Usuario",
        foreign_keys=[usuario_id],
        backref=db.backref(
            "vinculos_setores",
            lazy="selectin",
            cascade="all, delete-orphan",
        ),
    )

    setor = db.relationship(
        "Setor",
        foreign_keys=[setor_id],
        back_populates="vinculos_usuarios",
    )

    def __repr__(self):
        return (
            f"<UsuarioSetor "
            f"usuario_id={self.usuario_id} "
            f"setor_id={self.setor_id}>"
        )

    @property
    def vinculo_atual(self):
        return (
            self.ativo
            and self.fim_vinculo is None
        )

    def para_dict(self):
        return {
            "id": self.id,
            "usuario_id":
                self.usuario_id,
            "setor_id":
                self.setor_id,
            "setor":
                self.setor.nome
                if self.setor
                else None,
            "principal":
                self.principal,
            "ativo":
                self.ativo,
            "inicio_vinculo": (
                self.inicio_vinculo.isoformat()
                if self.inicio_vinculo
                else None
            ),
            "fim_vinculo": (
                self.fim_vinculo.isoformat()
                if self.fim_vinculo
                else None
            ),
        }
    
# ==========================================
# DADOS DO PAINEL DA ESCOLA
# ==========================================

class EscolaPainel(db.Model):
    __tablename__ = "escolas_painel"

    __table_args__ = {
        "schema": "semed",
    }

    escola_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "semed.escolas.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    imagem_url = db.Column(
        db.String(500),
        nullable=True,
    )

    dados_websig = db.Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=db.text(
            "'{}'::jsonb"
        ),
    )

    atualizado_em = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    escola = db.relationship(
        "Escola",
        backref=db.backref(
            "dados_painel",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )

    def __repr__(self):
        return (
            f"<EscolaPainel "
            f"escola_id={self.escola_id}>"
        )

    def para_dict(self):
        return {
            "escola_id":
                self.escola_id,
            "imagem_url":
                self.imagem_url,
            "dados_websig":
                self.dados_websig or {},
            "atualizado_em": (
                self.atualizado_em.isoformat()
                if self.atualizado_em
                else None
            ),
        }