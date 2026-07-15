import os
from datetime import timedelta

from dotenv import load_dotenv
from sqlalchemy import URL


load_dotenv()


def obter_variavel_obrigatoria(nome):
    valor = os.getenv(nome)

    if valor is None or not valor.strip():
        raise RuntimeError(
            f"A variável de ambiente {nome} não foi definida."
        )

    return valor.strip()


def obter_booleano(nome, padrao=False):
    valor = os.getenv(nome)

    if valor is None:
        return padrao

    return valor.strip().lower() in {
        "1",
        "true",
        "yes",
        "sim",
        "on",
    }


class Config:
    # Segurança da aplicação
    SECRET_KEY = obter_variavel_obrigatoria(
        "SECRET_KEY"
    )

    # Banco de dados
    DB_USER = obter_variavel_obrigatoria(
        "DB_USER"
    )

    PASSWORD = obter_variavel_obrigatoria(
        "PASSWORD"
    )

    IP = obter_variavel_obrigatoria(
        "IP"
    )

    PORT = int(
        obter_variavel_obrigatoria("PORT")
    )

    DB_NAME = os.getenv(
        "DB_NAME",
        "SEMDU",
    ).strip()

    SQLALCHEMY_DATABASE_URI = URL.create(
        drivername="postgresql+psycopg",
        username=DB_USER,
        password=PASSWORD,
        host=IP,
        port=PORT,
        database=DB_NAME,
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuração das sessões
    SESSION_COOKIE_NAME = "websig_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = obter_booleano(
        "SESSION_COOKIE_SECURE",
        False,
    )

    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=8
    )

    # Cookie utilizado futuramente pelo "lembrar de mim"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = (
        SESSION_COOKIE_SECURE
    )

    DEBUG = obter_booleano(
        "FLASK_DEBUG",
        False,
    )