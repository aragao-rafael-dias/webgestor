from flask_sqlalchemy import SQLAlchemy
from geoalchemy2 import Geometry

db = SQLAlchemy()

class Escola(db.Model):
    __tablename__ = 'escolas'
    __table_args__ = {'schema': 'semed'}

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    diretor = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    geom = db.Column(Geometry(geometry_type='POINT', srid=4326))

class RotaGeral(db.Model):
    __tablename__ = 'rotas_geral'
    __table_args__ = {'schema': 'semed'}

    id = db.Column(db.Integer, primary_key=True)
    nome_rota = db.Column(db.String(100))
    regiao = db.Column(db.String(100))
    trecho = db.Column(db.String(50))
    total_pontos = db.Column(db.Integer)
    pontos_notaveis = db.Column(db.JSON)
    geom = db.Column(Geometry(geometry_type='MULTILINESTRING', srid=4326))

class Requisicao(db.Model):
    __tablename__ = 'requisicoes'
    __table_args__ = {'schema': 'semed'}

    id = db.Column(db.Integer, primary_key=True)
    escola_id = db.Column(db.Integer, db.ForeignKey('semed.escolas.id'), nullable=False)
    tipo = db.Column(db.String(50))
    descricao = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pendente')
    data_criacao = db.Column(db.DateTime, server_default=db.func.now())
    resposta_semed = db.Column(db.Text)

    escola = db.relationship('Escola', backref='requisicoes')