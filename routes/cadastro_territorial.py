from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)
from flask_login import current_user
from shapely.geometry import LineString, mapping, shape
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from models import db
from servicos.acessos_modulos import (
    MODULO_CADASTRO_TERRITORIAL,
    acesso_modulo_required,
)
from servicos.funcoes_cadastro_territorial import (
    FUNCAO_FISCAL,
    ORGAO_SEMDU,
    ORGAO_SEMFAZ,
    fiscal_orgao_required,
    obter_permissoes_usuario,
    usuario_possui_funcao,
)
from servicos.importacao_logradouros import (
    ErroImportacaoGeoespacial,
    importar_arquivo_logradouro,
)
from servicos.oficio_logradouro import (
    gerar_oficio_logradouro,
)


cadastro_territorial_bp = Blueprint(
    "cadastro_territorial",
    __name__,
)

STATUS_RASCUNHO = "RASCUNHO"
STATUS_AUTORIZADA = "PLANEJADA_AUTORIZADA"
STATUS_LIBERADA = "PLANEJADA_LIBERADA"
STATUS_DEVOLVIDA = "DEVOLVIDA_AJUSTES"
STATUS_CANCELADA = "CANCELADA"

STATUS_VALIDOS = {
    STATUS_RASCUNHO,
    STATUS_AUTORIZADA,
    STATUS_LIBERADA,
    STATUS_DEVOLVIDA,
    STATUS_CANCELADA,
}

STATUS_EDITAVEIS_SEMDU = {
    STATUS_RASCUNHO,
    STATUS_DEVOLVIDA,
}

TIPOS_LOGRADOURO = {
    "RUA": "Rua",
    "AVENIDA": "Avenida",
    "TRAVESSA": "Travessa",
    "ALAMEDA": "Alameda",
    "ESTRADA": "Estrada",
    "VIA": "Via",
    "BECO": "Beco",
    "PRACA": "Praça",
    "OUTRO": "Outro",
}

TIPOS_DOCUMENTO = {
    "CONSOLIDACAO": "Comprovação da consolidação",
    "FOTOGRAFIA": "Fotografia",
    "ATO_ADMINISTRATIVO": "Ato administrativo",
    "PLANTA": "Planta ou croqui",
    "DECLARACAO": "Declaração",
    "LEVANTAMENTO": "Levantamento geoespacial",
    "OUTRO": "Outro documento",
}

EXTENSOES_DOCUMENTOS = {
    ".pdf",
    ".doc",
    ".docx",
    ".odt",
    ".xls",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".zip",
    ".geojson",
    ".json",
    ".kml",
    ".kmz",
    ".gpkg",
}

MAX_DOCUMENTO_BYTES = 25 * 1024 * 1024


SQL_LISTAR_LOGRADOUROS = text(
    """
    WITH limite AS (
        SELECT ST_Transform(
            ST_MakeEnvelope(
                CAST(:oeste AS DOUBLE PRECISION),
                CAST(:sul AS DOUBLE PRECISION),
                CAST(:leste AS DOUBLE PRECISION),
                CAST(:norte AS DOUBLE PRECISION),
                4326
            ),
            31984
        ) AS geom
    )
    SELECT jsonb_build_object(
        'type', 'Feature',
        'geometry',
            ST_AsGeoJSON(
                ST_Transform(
                    ST_Force2D(l.geom),
                    4326
                )
            )::jsonb,
        'properties',
            jsonb_build_object(
                'id', l.id,
                'protocolo', l.protocolo,
                'nome_completo', l.nome_completo,
                'tipo_logradouro', l.tipo_logradouro,
                'nome_proposto', l.nome_proposto,
                'bairro', l.bairro,
                'localidade', l.localidade,
                'status', l.status,
                'extensao_m', l.extensao_m,
                'largura_m', l.largura_m,
                'coordenada_inicial', l.coordenada_inicial,
                'coordenada_final', l.coordenada_final,
                'criado_em', l.criado_em,
                'autorizado_em', l.autorizado_em,
                'liberado_em', l.liberado_em,
                'criado_por_nome', uc.nome,
                'autorizado_por_nome', ua.nome,
                'liberado_por_nome', ul.nome,
                'documentos', (
                    SELECT COUNT(*)
                    FROM cadastro_territorial.logradouros_documentos AS d
                    WHERE d.logradouro_id = l.id
                      AND d.ativo IS TRUE
                )
            )
    ) AS feature
    FROM cadastro_territorial.logradouros AS l
    LEFT JOIN semed.usuarios AS uc
        ON uc.id = l.criado_por_usuario_id
    LEFT JOIN semed.usuarios AS ua
        ON ua.id = l.autorizado_por_usuario_id
    LEFT JOIN semed.usuarios AS ul
        ON ul.id = l.liberado_por_usuario_id
    CROSS JOIN limite
    WHERE l.ativo IS TRUE
      AND l.status <> 'CANCELADA'
      AND (
          CAST(:mostrar_rascunhos AS BOOLEAN) IS TRUE
          OR l.status NOT IN (
              'RASCUNHO',
              'DEVOLVIDA_AJUSTES'
          )
      )
      AND ST_Intersects(
          l.geom,
          limite.geom
      )
    ORDER BY
        CASE l.status
            WHEN 'PLANEJADA_AUTORIZADA' THEN 1
            WHEN 'DEVOLVIDA_AJUSTES' THEN 2
            WHEN 'RASCUNHO' THEN 3
            WHEN 'PLANEJADA_LIBERADA' THEN 4
            ELSE 5
        END,
        l.atualizado_em DESC,
        l.id DESC
    LIMIT CAST(:limite AS INTEGER)
    """
)


SQL_DETALHE_LOGRADOURO = text(
    """
    SELECT
        l.id,
        l.protocolo,
        l.tipo_logradouro,
        l.nome_proposto,
        l.nome_completo,
        l.bairro,
        l.localidade,
        l.cep,
        l.codigo_municipal,
        l.largura_m,
        l.extensao_m,
        l.descricao,
        l.memorial_descritivo,
        l.coordenada_inicial,
        l.coordenada_final,
        l.status,
        l.observacoes_semdu,
        l.observacoes_semfaz,
        l.justificativa_devolucao,
        l.oficio_numero,
        l.oficio_ano,
        l.criado_em,
        l.atualizado_em,
        l.autorizado_em,
        l.liberado_em,
        l.devolvido_em,
        uc.nome AS criado_por_nome,
        uu.nome AS atualizado_por_nome,
        ua.nome AS autorizado_por_nome,
        ul.nome AS liberado_por_nome,
        ud.nome AS devolvido_por_nome,
        ST_AsGeoJSON(
            ST_Transform(
                ST_Force2D(l.geom),
                4326
            )
        )::jsonb AS geometry
    FROM cadastro_territorial.logradouros AS l
    LEFT JOIN semed.usuarios AS uc
        ON uc.id = l.criado_por_usuario_id
    LEFT JOIN semed.usuarios AS uu
        ON uu.id = l.atualizado_por_usuario_id
    LEFT JOIN semed.usuarios AS ua
        ON ua.id = l.autorizado_por_usuario_id
    LEFT JOIN semed.usuarios AS ul
        ON ul.id = l.liberado_por_usuario_id
    LEFT JOIN semed.usuarios AS ud
        ON ud.id = l.devolvido_por_usuario_id
    WHERE l.id = CAST(:logradouro_id AS BIGINT)
      AND l.ativo IS TRUE
    """
)


SQL_DOCUMENTOS = text(
    """
    SELECT
        d.id,
        d.tipo_documento,
        d.nome_original,
        d.mime_type,
        d.tamanho_bytes,
        d.sha256,
        d.observacao,
        d.orgao_origem,
        d.criado_em,
        u.nome AS enviado_por_nome
    FROM cadastro_territorial.logradouros_documentos AS d
    LEFT JOIN semed.usuarios AS u
        ON u.id = d.enviado_por_usuario_id
    WHERE d.logradouro_id = CAST(:logradouro_id AS BIGINT)
      AND d.ativo IS TRUE
    ORDER BY d.criado_em DESC, d.id DESC
    """
)


SQL_OFICIOS = text(
    """
    SELECT
        id,
        numero,
        ano,
        caminho_pdf,
        caminho_docx,
        sha256_pdf,
        sha256_docx,
        criado_em
    FROM cadastro_territorial.logradouros_oficios
    WHERE logradouro_id = CAST(:logradouro_id AS BIGINT)
      AND ativo IS TRUE
    ORDER BY criado_em DESC, id DESC
    """
)


def _texto(
    valor: Any,
    limite: int = 4000,
    *,
    obrigatorio: bool = False,
) -> str | None:
    resultado = str(valor or "").strip()

    if not resultado:
        if obrigatorio:
            abort(
                400,
                description="Campo obrigatório não informado.",
            )
        return None

    return resultado[:limite]


def _numero(
    valor: Any,
    *,
    minimo: float | None = None,
    maximo: float | None = None,
) -> float | None:
    if valor in (None, ""):
        return None

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        abort(
            400,
            description="Valor numérico inválido.",
        )

    if not math.isfinite(numero):
        abort(
            400,
            description="Valor numérico inválido.",
        )

    if minimo is not None and numero < minimo:
        abort(
            400,
            description=f"O valor mínimo permitido é {minimo}.",
        )

    if maximo is not None and numero > maximo:
        abort(
            400,
            description=f"O valor máximo permitido é {maximo}.",
        )

    return numero


def _bbox() -> tuple[float, float, float, float]:
    valor = str(
        request.args.get("bbox")
        or ""
    ).strip()

    if not valor:
        return -180.0, -90.0, 180.0, 90.0

    partes = valor.split(",")

    if len(partes) != 4:
        abort(
            400,
            description="bbox deve ser oeste,sul,leste,norte.",
        )

    try:
        oeste, sul, leste, norte = map(float, partes)
    except ValueError:
        abort(
            400,
            description="bbox inválido.",
        )

    if (
        oeste >= leste
        or sul >= norte
        or oeste < -180
        or leste > 180
        or sul < -90
        or norte > 90
    ):
        abort(
            400,
            description="bbox inválido.",
        )

    return oeste, sul, leste, norte


def _limite() -> int:
    try:
        valor = int(
            request.args.get(
                "limite",
                5000,
            )
        )
    except (TypeError, ValueError):
        valor = 5000

    return max(
        1,
        min(valor, 10000),
    )


def _geometry_line_string(
    valor: Any,
) -> dict[str, Any]:
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            abort(
                400,
                description="A geometria não contém JSON válido.",
            )

    if not isinstance(valor, dict):
        abort(
            400,
            description="Geometria obrigatória.",
        )

    geometria_json = (
        valor.get("geometry")
        if valor.get("type") == "Feature"
        else valor
    )

    try:
        geometria = shape(geometria_json)
    except Exception:
        abort(
            400,
            description="Geometria inválida.",
        )

    if geometria.is_empty:
        abort(
            400,
            description="A geometria está vazia.",
        )

    if not isinstance(geometria, LineString):
        abort(
            400,
            description=(
                "O eixo do logradouro deve ser uma única linha contínua."
            ),
        )

    if len(geometria.coords) < 2:
        abort(
            400,
            description="A linha precisa possuir pelo menos dois vértices.",
        )

    for longitude, latitude, *_ in geometria.coords:
        if not (
            -180 <= float(longitude) <= 180
            and -90 <= float(latitude) <= 90
        ):
            abort(
                400,
                description=(
                    "A geometria precisa estar em latitude e longitude "
                    "EPSG:4326."
                ),
            )

    return mapping(geometria)


def _tipo_logradouro(
    valor: Any,
) -> str:
    tipo = str(valor or "RUA").strip().upper()

    if tipo not in TIPOS_LOGRADOURO:
        abort(
            400,
            description="Tipo de logradouro inválido.",
        )

    return tipo


def _nome_completo(
    tipo_logradouro: str,
    nome_proposto: str,
) -> str:
    prefixo = TIPOS_LOGRADOURO[tipo_logradouro]

    if tipo_logradouro == "OUTRO":
        return nome_proposto

    nome_normalizado = nome_proposto.strip()

    if nome_normalizado.lower().startswith(
        prefixo.lower() + " "
    ):
        return nome_normalizado

    return f"{prefixo} {nome_normalizado}"


def _calcular_geometria(
    geometria: dict[str, Any],
) -> dict[str, Any]:
    consulta = text(
        """
        WITH entrada AS (
            SELECT ST_SetSRID(
                ST_GeomFromGeoJSON(
                    CAST(:geojson AS TEXT)
                ),
                4326
            ) AS geom
        ),
        linha AS (
            SELECT
                ST_Transform(
                    ST_Force2D(geom),
                    31984
                ) AS geom_utm,
                ST_Force2D(geom) AS geom_4326
            FROM entrada
        ),
        vertices AS (
            SELECT
                dp.path AS caminho,
                dp.geom AS geom
            FROM linha
            CROSS JOIN LATERAL ST_DumpPoints(
                linha.geom_4326
            ) AS dp
        ),
        vertices_numerados AS (
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY caminho
                ) AS ordem,
                geom
            FROM vertices
        )
        SELECT
            ROUND(
                ST_Length(geom_utm)::numeric,
                2
            ) AS extensao_m,
            ST_Y(
                ST_StartPoint(geom_4326)
            ) AS inicio_lat,
            ST_X(
                ST_StartPoint(geom_4326)
            ) AS inicio_lon,
            ST_Y(
                ST_EndPoint(geom_4326)
            ) AS fim_lat,
            ST_X(
                ST_EndPoint(geom_4326)
            ) AS fim_lon,
            ST_NPoints(geom_4326) AS total_vertices,
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'ordem', ordem,
                        'latitude', ST_Y(geom),
                        'longitude', ST_X(geom)
                    )
                    ORDER BY ordem
                )
                FROM vertices_numerados
            ) AS vertices
        FROM linha
        """
    )

    return dict(
        db.session.execute(
            consulta,
            {
                "geojson": json.dumps(
                    geometria,
                    ensure_ascii=False,
                )
            },
        ).mappings().one()
    )


def _coordenada(
    latitude: float,
    longitude: float,
) -> str:
    return f"{latitude:.7f}, {longitude:.7f}"


def _gerar_memorial(
    nome_completo: str,
    metricas: dict[str, Any],
) -> str:
    vertices = list(
        metricas.get("vertices")
        or []
    )
    extensao = float(
        metricas.get("extensao_m")
        or 0
    )

    if not vertices:
        return (
            f"O eixo do logradouro {nome_completo} possui extensão aproximada "
            f"de {extensao:.2f} metros, conforme geometria digital registrada."
        )

    primeiro = vertices[0]
    ultimo = vertices[-1]

    partes = [
        (
            f"Inicia-se o eixo do logradouro {nome_completo} no ponto P01, "
            f"de coordenadas geográficas latitude "
            f"{float(primeiro['latitude']):.7f} e longitude "
            f"{float(primeiro['longitude']):.7f}."
        )
    ]

    intermediarios = vertices[1:-1]

    if intermediarios:
        if len(intermediarios) <= 18:
            descricao_vertices = "; ".join(
                (
                    f"P{indice:02d} ({float(item['latitude']):.7f}, "
                    f"{float(item['longitude']):.7f})"
                )
                for indice, item in enumerate(
                    intermediarios,
                    start=2,
                )
            )

            partes.append(
                "Segue em linha poligonal pelos vértices "
                + descricao_vertices
                + "."
            )
        else:
            partes.append(
                f"Segue em linha poligonal por {len(intermediarios)} vértices "
                "intermediários, integralmente registrados na geometria digital "
                "e no banco geográfico municipal."
            )

    partes.append(
        (
            f"O eixo termina no ponto P{len(vertices):02d}, de coordenadas "
            f"geográficas latitude {float(ultimo['latitude']):.7f} e longitude "
            f"{float(ultimo['longitude']):.7f}, totalizando extensão aproximada "
            f"de {extensao:.2f} metros."
        )
    )

    return " ".join(partes)


def _diretorio_uploads(
    logradouro_id: int,
) -> Path:
    caminho = (
        Path(current_app.instance_path)
        / "uploads"
        / "cadastro_territorial"
        / "logradouros"
        / str(logradouro_id)
    )
    caminho.mkdir(
        parents=True,
        exist_ok=True,
    )
    return caminho


def _diretorio_oficios(
    logradouro_id: int,
) -> Path:
    caminho = (
        Path(current_app.instance_path)
        / "documentos_gerados"
        / "cadastro_territorial"
        / str(logradouro_id)
    )
    caminho.mkdir(
        parents=True,
        exist_ok=True,
    )
    return caminho


def _sha256(caminho: Path) -> str:
    hash_obj = hashlib.sha256()

    with caminho.open("rb") as arquivo:
        for bloco in iter(
            lambda: arquivo.read(1024 * 1024),
            b"",
        ):
            hash_obj.update(bloco)

    return hash_obj.hexdigest()


def _detalhe_logradouro(
    logradouro_id: int,
) -> dict[str, Any]:
    registro = db.session.execute(
        SQL_DETALHE_LOGRADOURO,
        {"logradouro_id": logradouro_id},
    ).mappings().one_or_none()

    if registro is None:
        abort(
            404,
            description="Logradouro não encontrado.",
        )

    detalhe = dict(registro)
    detalhe["documentos"] = [
        dict(item)
        for item in db.session.execute(
            SQL_DOCUMENTOS,
            {"logradouro_id": logradouro_id},
        ).mappings().all()
    ]
    detalhe["oficios"] = [
        dict(item)
        for item in db.session.execute(
            SQL_OFICIOS,
            {"logradouro_id": logradouro_id},
        ).mappings().all()
    ]

    return detalhe


def _verificar_status(
    logradouro_id: int,
    permitidos: set[str],
) -> dict[str, Any]:
    detalhe = _detalhe_logradouro(
        logradouro_id
    )

    if detalhe["status"] not in permitidos:
        abort(
            409,
            description=(
                "A situação atual do logradouro não permite esta operação. "
                f"Situação: {detalhe['status']}."
            ),
        )

    return detalhe


def _registrar_historico(
    logradouro_id: int,
    acao: str,
    status_anterior: str | None,
    status_novo: str | None,
    observacao: str | None = None,
) -> None:
    db.session.execute(
        text(
            """
            INSERT INTO cadastro_territorial.logradouros_historico (
                logradouro_id,
                acao,
                status_anterior,
                status_novo,
                observacao,
                usuario_id,
                criado_em
            ) VALUES (
                CAST(:logradouro_id AS BIGINT),
                CAST(:acao AS VARCHAR),
                CAST(:status_anterior AS VARCHAR),
                CAST(:status_novo AS VARCHAR),
                CAST(:observacao AS TEXT),
                CAST(:usuario_id AS INTEGER),
                NOW()
            )
            """
        ),
        {
            "logradouro_id": logradouro_id,
            "acao": acao,
            "status_anterior": status_anterior,
            "status_novo": status_novo,
            "observacao": observacao,
            "usuario_id": int(current_user.id),
        },
    )


def _proximo_numero_oficio(
    ano: int,
) -> int:
    return int(
        db.session.execute(
            text(
                """
                INSERT INTO cadastro_territorial.oficios_sequencias (
                    ano,
                    ultimo_numero,
                    atualizado_em
                ) VALUES (
                    CAST(:ano AS INTEGER),
                    1,
                    NOW()
                )
                ON CONFLICT (ano)
                DO UPDATE SET
                    ultimo_numero =
                        cadastro_territorial.oficios_sequencias.ultimo_numero + 1,
                    atualizado_em = NOW()
                RETURNING ultimo_numero
                """
            ),
            {"ano": ano},
        ).scalar_one()
    )


@cadastro_territorial_bp.get(
    "/cadastro-territorial"
)
@cadastro_territorial_bp.get(
    "/cadastro-territorial/mapa"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def mapa():
    session["modulo_atual"] = (
        MODULO_CADASTRO_TERRITORIAL
    )

    return render_template(
        "cadastro_territorial/mapa.html",
        permissoes=obter_permissoes_usuario(
            current_user
        ),
        tipos_logradouro=TIPOS_LOGRADOURO,
        tipos_documento=TIPOS_DOCUMENTO,
    )


@cadastro_territorial_bp.get(
    "/api/cadastro-territorial/permissoes"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def permissoes():
    return jsonify(
        {
            "sucesso": True,
            **obter_permissoes_usuario(
                current_user
            ),
        }
    )


@cadastro_territorial_bp.get(
    "/api/cadastro-territorial/logradouros"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def listar_logradouros():
    oeste, sul, leste, norte = _bbox()
    permissoes_usuario = obter_permissoes_usuario(
        current_user
    )

    feicoes = list(
        db.session.execute(
            SQL_LISTAR_LOGRADOUROS,
            {
                "oeste": oeste,
                "sul": sul,
                "leste": leste,
                "norte": norte,
                "limite": _limite(),
                "mostrar_rascunhos": bool(
                    permissoes_usuario["fiscal_semdu"]
                ),
            },
        ).scalars()
    )

    return jsonify(
        {
            "type": "FeatureCollection",
            "name": "logradouros_planejados",
            "schema": "cadastro_territorial",
            "features": feicoes,
        }
    )


@cadastro_territorial_bp.get(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def obter_logradouro(
    logradouro_id: int,
):
    return jsonify(
        {
            "sucesso": True,
            "logradouro": _detalhe_logradouro(
                logradouro_id
            ),
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/importar"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMDU
)
def importar_geometria():
    arquivo = request.files.get(
        "arquivo"
    )

    if arquivo is None:
        abort(
            400,
            description="Envie o arquivo geoespacial.",
        )

    try:
        feicao = importar_arquivo_logradouro(
            arquivo
        )
        metricas = _calcular_geometria(
            feicao["geometry"]
        )
    except ErroImportacaoGeoespacial as erro:
        abort(
            400,
            description=str(erro),
        )

    return jsonify(
        {
            "sucesso": True,
            "feature": feicao,
            "metricas": metricas,
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/logradouros"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMDU
)
def criar_logradouro():
    corpo = request.get_json(
        silent=True
    ) or {}

    geometria = _geometry_line_string(
        corpo.get("geometry")
    )
    metricas = _calcular_geometria(
        geometria
    )

    tipo = _tipo_logradouro(
        corpo.get("tipo_logradouro")
    )
    nome_proposto = _texto(
        corpo.get("nome_proposto"),
        240,
        obrigatorio=True,
    )
    nome_completo = _nome_completo(
        tipo,
        nome_proposto,
    )

    memorial = _texto(
        corpo.get("memorial_descritivo"),
        30000,
    ) or _gerar_memorial(
        nome_completo,
        metricas,
    )

    try:
        logradouro_id = db.session.execute(
            text(
                """
                INSERT INTO cadastro_territorial.logradouros (
                    tipo_logradouro,
                    nome_proposto,
                    nome_completo,
                    bairro,
                    localidade,
                    cep,
                    codigo_municipal,
                    largura_m,
                    extensao_m,
                    descricao,
                    memorial_descritivo,
                    coordenada_inicial,
                    coordenada_final,
                    status,
                    observacoes_semdu,
                    geom,
                    criado_por_usuario_id,
                    atualizado_por_usuario_id,
                    criado_em,
                    atualizado_em,
                    ativo
                ) VALUES (
                    CAST(:tipo_logradouro AS VARCHAR),
                    CAST(:nome_proposto AS VARCHAR),
                    CAST(:nome_completo AS VARCHAR),
                    CAST(:bairro AS VARCHAR),
                    CAST(:localidade AS VARCHAR),
                    CAST(:cep AS VARCHAR),
                    CAST(:codigo_municipal AS VARCHAR),
                    CAST(:largura_m AS NUMERIC),
                    CAST(:extensao_m AS NUMERIC),
                    CAST(:descricao AS TEXT),
                    CAST(:memorial AS TEXT),
                    CAST(:coordenada_inicial AS VARCHAR),
                    CAST(:coordenada_final AS VARCHAR),
                    'RASCUNHO',
                    CAST(:observacoes_semdu AS TEXT),
                    ST_Transform(
                        ST_SetSRID(
                            ST_GeomFromGeoJSON(
                                CAST(:geojson AS TEXT)
                            ),
                            4326
                        ),
                        31984
                    ),
                    CAST(:usuario_id AS INTEGER),
                    CAST(:usuario_id AS INTEGER),
                    NOW(),
                    NOW(),
                    TRUE
                )
                RETURNING id
                """
            ),
            {
                "tipo_logradouro": tipo,
                "nome_proposto": nome_proposto,
                "nome_completo": nome_completo,
                "bairro": _texto(corpo.get("bairro"), 180),
                "localidade": _texto(corpo.get("localidade"), 180),
                "cep": _texto(corpo.get("cep"), 20),
                "codigo_municipal": _texto(corpo.get("codigo_municipal"), 80),
                "largura_m": _numero(
                    corpo.get("largura_m"),
                    minimo=0.1,
                    maximo=500,
                ),
                "extensao_m": float(metricas["extensao_m"]),
                "descricao": _texto(corpo.get("descricao"), 10000),
                "memorial": memorial,
                "coordenada_inicial": _coordenada(
                    float(metricas["inicio_lat"]),
                    float(metricas["inicio_lon"]),
                ),
                "coordenada_final": _coordenada(
                    float(metricas["fim_lat"]),
                    float(metricas["fim_lon"]),
                ),
                "observacoes_semdu": _texto(corpo.get("observacoes_semdu"), 10000),
                "geojson": json.dumps(
                    geometria,
                    ensure_ascii=False,
                ),
                "usuario_id": int(current_user.id),
            },
        ).scalar_one()

        protocolo = (
            f"CT-{datetime.now(timezone.utc).year}-"
            f"{int(logradouro_id):06d}"
        )

        db.session.execute(
            text(
                """
                UPDATE cadastro_territorial.logradouros
                SET protocolo = CAST(:protocolo AS VARCHAR)
                WHERE id = CAST(:id AS BIGINT)
                """
            ),
            {
                "protocolo": protocolo,
                "id": logradouro_id,
            },
        )

        _registrar_historico(
            int(logradouro_id),
            "CRIACAO",
            None,
            STATUS_RASCUNHO,
            "Logradouro planejado pela SEMDU.",
        )

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao criar logradouro planejado."
        )
        raise

    return jsonify(
        {
            "sucesso": True,
            "id": int(logradouro_id),
            "protocolo": protocolo,
            "mensagem": "Rascunho do logradouro criado.",
        }
    ), 201


@cadastro_territorial_bp.put(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMDU
)
def atualizar_logradouro(
    logradouro_id: int,
):
    detalhe = _verificar_status(
        logradouro_id,
        STATUS_EDITAVEIS_SEMDU,
    )
    corpo = request.get_json(
        silent=True
    ) or {}

    geometria_valor = corpo.get(
        "geometry"
    )

    if geometria_valor:
        geometria = _geometry_line_string(
            geometria_valor
        )
        metricas = _calcular_geometria(
            geometria
        )
    else:
        geometria = detalhe["geometry"]
        metricas = _calcular_geometria(
            geometria
        )

    tipo = _tipo_logradouro(
        corpo.get("tipo_logradouro")
        or detalhe["tipo_logradouro"]
    )
    nome_proposto = _texto(
        corpo.get("nome_proposto")
        or detalhe["nome_proposto"],
        240,
        obrigatorio=True,
    )
    nome_completo = _nome_completo(
        tipo,
        nome_proposto,
    )

    memorial = _texto(
        corpo.get("memorial_descritivo"),
        30000,
    ) or _gerar_memorial(
        nome_completo,
        metricas,
    )

    db.session.execute(
        text(
            """
            UPDATE cadastro_territorial.logradouros
            SET
                tipo_logradouro = CAST(:tipo_logradouro AS VARCHAR),
                nome_proposto = CAST(:nome_proposto AS VARCHAR),
                nome_completo = CAST(:nome_completo AS VARCHAR),
                bairro = CAST(:bairro AS VARCHAR),
                localidade = CAST(:localidade AS VARCHAR),
                cep = CAST(:cep AS VARCHAR),
                codigo_municipal = CAST(:codigo_municipal AS VARCHAR),
                largura_m = CAST(:largura_m AS NUMERIC),
                extensao_m = CAST(:extensao_m AS NUMERIC),
                descricao = CAST(:descricao AS TEXT),
                memorial_descritivo = CAST(:memorial AS TEXT),
                coordenada_inicial = CAST(:coordenada_inicial AS VARCHAR),
                coordenada_final = CAST(:coordenada_final AS VARCHAR),
                observacoes_semdu = CAST(:observacoes_semdu AS TEXT),
                geom = ST_Transform(
                    ST_SetSRID(
                        ST_GeomFromGeoJSON(
                            CAST(:geojson AS TEXT)
                        ),
                        4326
                    ),
                    31984
                ),
                atualizado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                atualizado_em = NOW()
            WHERE id = CAST(:id AS BIGINT)
              AND status IN (
                  'RASCUNHO',
                  'DEVOLVIDA_AJUSTES'
              )
            """
        ),
        {
            "id": logradouro_id,
            "tipo_logradouro": tipo,
            "nome_proposto": nome_proposto,
            "nome_completo": nome_completo,
            "bairro": _texto(corpo.get("bairro"), 180),
            "localidade": _texto(corpo.get("localidade"), 180),
            "cep": _texto(corpo.get("cep"), 20),
            "codigo_municipal": _texto(corpo.get("codigo_municipal"), 80),
            "largura_m": _numero(
                corpo.get("largura_m"),
                minimo=0.1,
                maximo=500,
            ),
            "extensao_m": float(metricas["extensao_m"]),
            "descricao": _texto(corpo.get("descricao"), 10000),
            "memorial": memorial,
            "coordenada_inicial": _coordenada(
                float(metricas["inicio_lat"]),
                float(metricas["inicio_lon"]),
            ),
            "coordenada_final": _coordenada(
                float(metricas["fim_lat"]),
                float(metricas["fim_lon"]),
            ),
            "observacoes_semdu": _texto(corpo.get("observacoes_semdu"), 10000),
            "geojson": json.dumps(
                geometria,
                ensure_ascii=False,
            ),
            "usuario_id": int(current_user.id),
        },
    )

    _registrar_historico(
        logradouro_id,
        "ATUALIZACAO_SEMDU",
        detalhe["status"],
        detalhe["status"],
        "Dados e geometria atualizados pela SEMDU.",
    )

    db.session.commit()

    return jsonify(
        {
            "sucesso": True,
            "mensagem": "Logradouro atualizado.",
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/documentos"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def anexar_documento(
    logradouro_id: int,
):
    permissoes_usuario = obter_permissoes_usuario(
        current_user
    )

    if not permissoes_usuario["anexar_documentos"]:
        abort(
            403,
            description=(
                "Somente Fiscais da SEMDU ou da SEMFAZ podem anexar documentos."
            ),
        )

    detalhe = _detalhe_logradouro(
        logradouro_id
    )

    arquivo = request.files.get(
        "arquivo"
    )

    if arquivo is None or not arquivo.filename:
        abort(
            400,
            description="Selecione o documento.",
        )

    nome_original = str(
        arquivo.filename
    ).strip()
    nome_seguro = secure_filename(
        nome_original
    )
    extensao = Path(
        nome_seguro
    ).suffix.lower()

    if extensao not in EXTENSOES_DOCUMENTOS:
        abort(
            400,
            description="Formato de documento não permitido.",
        )

    tipo_documento = str(
        request.form.get("tipo_documento")
        or "OUTRO"
    ).strip().upper()

    if tipo_documento not in TIPOS_DOCUMENTO:
        abort(
            400,
            description="Tipo de documento inválido.",
        )

    orgao_origem = (
        ORGAO_SEMDU
        if permissoes_usuario["fiscal_semdu"]
        else ORGAO_SEMFAZ
    )

    pasta = _diretorio_uploads(
        logradouro_id
    )
    nome_armazenado = (
        f"{uuid.uuid4().hex}_{nome_seguro}"
    )
    caminho = pasta / nome_armazenado
    arquivo.save(caminho)

    tamanho = caminho.stat().st_size

    if tamanho <= 0:
        caminho.unlink(missing_ok=True)
        abort(
            400,
            description="O documento está vazio.",
        )

    if tamanho > MAX_DOCUMENTO_BYTES:
        caminho.unlink(missing_ok=True)
        abort(
            413,
            description="O documento ultrapassa o limite de 25 MB.",
        )

    mime_type = (
        arquivo.mimetype
        or mimetypes.guess_type(
            nome_original
        )[0]
        or "application/octet-stream"
    )

    caminho_relativo = caminho.relative_to(
        Path(current_app.instance_path)
    ).as_posix()

    documento_id = db.session.execute(
        text(
            """
            INSERT INTO cadastro_territorial.logradouros_documentos (
                logradouro_id,
                tipo_documento,
                nome_original,
                nome_armazenado,
                caminho_relativo,
                mime_type,
                tamanho_bytes,
                sha256,
                observacao,
                orgao_origem,
                enviado_por_usuario_id,
                criado_em,
                ativo
            ) VALUES (
                CAST(:logradouro_id AS BIGINT),
                CAST(:tipo_documento AS VARCHAR),
                CAST(:nome_original AS VARCHAR),
                CAST(:nome_armazenado AS VARCHAR),
                CAST(:caminho_relativo AS TEXT),
                CAST(:mime_type AS VARCHAR),
                CAST(:tamanho_bytes AS BIGINT),
                CAST(:sha256 AS VARCHAR),
                CAST(:observacao AS TEXT),
                CAST(:orgao_origem AS VARCHAR),
                CAST(:usuario_id AS INTEGER),
                NOW(),
                TRUE
            )
            RETURNING id
            """
        ),
        {
            "logradouro_id": logradouro_id,
            "tipo_documento": tipo_documento,
            "nome_original": nome_original,
            "nome_armazenado": nome_armazenado,
            "caminho_relativo": caminho_relativo,
            "mime_type": mime_type,
            "tamanho_bytes": tamanho,
            "sha256": _sha256(caminho),
            "observacao": _texto(
                request.form.get("observacao"),
                2000,
            ),
            "orgao_origem": orgao_origem,
            "usuario_id": int(current_user.id),
        },
    ).scalar_one()

    _registrar_historico(
        logradouro_id,
        "DOCUMENTO_ANEXADO",
        detalhe["status"],
        detalhe["status"],
        f"Documento anexado: {nome_original}.",
    )

    db.session.commit()

    return jsonify(
        {
            "sucesso": True,
            "id": int(documento_id),
            "mensagem": "Documento anexado.",
        }
    ), 201


@cadastro_territorial_bp.get(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/documentos/<int:documento_id>"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def baixar_documento(
    logradouro_id: int,
    documento_id: int,
):
    registro = db.session.execute(
        text(
            """
            SELECT
                nome_original,
                caminho_relativo,
                mime_type
            FROM cadastro_territorial.logradouros_documentos
            WHERE id = CAST(:documento_id AS BIGINT)
              AND logradouro_id = CAST(:logradouro_id AS BIGINT)
              AND ativo IS TRUE
            """
        ),
        {
            "documento_id": documento_id,
            "logradouro_id": logradouro_id,
        },
    ).mappings().one_or_none()

    if registro is None:
        abort(
            404,
            description="Documento não encontrado.",
        )

    caminho = (
        Path(current_app.instance_path)
        / registro["caminho_relativo"]
    ).resolve()
    raiz = Path(
        current_app.instance_path
    ).resolve()

    if raiz not in caminho.parents or not caminho.exists():
        abort(
            404,
            description="Arquivo não encontrado no armazenamento.",
        )

    return send_file(
        caminho,
        mimetype=registro["mime_type"],
        as_attachment=True,
        download_name=registro["nome_original"],
        conditional=True,
    )


@cadastro_territorial_bp.delete(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/documentos/<int:documento_id>"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMDU
)
def remover_documento(
    logradouro_id: int,
    documento_id: int,
):
    detalhe = _verificar_status(
        logradouro_id,
        STATUS_EDITAVEIS_SEMDU,
    )

    resultado = db.session.execute(
        text(
            """
            UPDATE cadastro_territorial.logradouros_documentos
            SET ativo = FALSE
            WHERE id = CAST(:documento_id AS BIGINT)
              AND logradouro_id = CAST(:logradouro_id AS BIGINT)
              AND ativo IS TRUE
            RETURNING nome_original
            """
        ),
        {
            "documento_id": documento_id,
            "logradouro_id": logradouro_id,
        },
    ).scalar_one_or_none()

    if resultado is None:
        db.session.rollback()
        abort(
            404,
            description="Documento não encontrado.",
        )

    _registrar_historico(
        logradouro_id,
        "DOCUMENTO_REMOVIDO",
        detalhe["status"],
        detalhe["status"],
        f"Documento removido: {resultado}.",
    )

    db.session.commit()

    return jsonify(
        {
            "sucesso": True,
            "mensagem": "Documento removido.",
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/autorizar"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMDU
)
def autorizar_logradouro(
    logradouro_id: int,
):
    detalhe = _verificar_status(
        logradouro_id,
        STATUS_EDITAVEIS_SEMDU,
    )
    corpo = request.get_json(
        silent=True
    ) or {}

    documentos = detalhe["documentos"]
    comprovacoes = [
        item
        for item in documentos
        if item["tipo_documento"]
        in {
            "CONSOLIDACAO",
            "FOTOGRAFIA",
            "ATO_ADMINISTRATIVO",
            "PLANTA",
            "DECLARACAO",
            "LEVANTAMENTO",
        }
    ]

    if not comprovacoes:
        abort(
            409,
            description=(
                "Anexe pelo menos um documento que comprove a consolidação "
                "ou a situação física da rua antes de autorizar."
            ),
        )

    if not detalhe.get("memorial_descritivo"):
        abort(
            409,
            description="O memorial descritivo é obrigatório.",
        )

    ano = datetime.now(timezone.utc).year
    numero = _proximo_numero_oficio(
        ano
    )

    bairro_localidade = " / ".join(
        item
        for item in [
            _texto(detalhe.get("bairro"), 180),
            _texto(detalhe.get("localidade"), 180),
        ]
        if item
    )

    dados_oficio = {
        **detalhe,
        "oficio_numero": numero,
        "oficio_ano": ano,
        "data_oficio": date.today(),
        "bairro_localidade": bairro_localidade,
        "anexos": documentos,
        "destinatario_nome": _texto(
            corpo.get("destinatario_nome"),
            240,
        ),
        "destinatario_cargo": _texto(
            corpo.get("destinatario_cargo"),
            240,
        ),
        "assunto": _texto(
            corpo.get("assunto"),
            400,
        ),
        "vocativo": _texto(
            corpo.get("vocativo"),
            240,
        ),
        "assinante_nome": _texto(
            corpo.get("assinante_nome"),
            240,
        ),
        "assinante_cargo": _texto(
            corpo.get("assinante_cargo"),
            240,
        ),
    }

    try:
        arquivos_gerados = gerar_oficio_logradouro(
            dados_oficio,
            _diretorio_oficios(
                logradouro_id
            ),
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Erro ao gerar ofício do logradouro %s.",
            logradouro_id,
        )
        return jsonify(
            {
                "sucesso": False,
                "erro": (
                    "Não foi possível gerar o ofício. "
                    "Confira a imagem do cabeçalho e as dependências "
                    "python-docx e reportlab."
                ),
            }
        ), 500

    raiz_instance = Path(
        current_app.instance_path
    )

    caminho_pdf_relativo = arquivos_gerados[
        "pdf"
    ].relative_to(
        raiz_instance
    ).as_posix()
    caminho_docx_relativo = arquivos_gerados[
        "docx"
    ].relative_to(
        raiz_instance
    ).as_posix()

    try:
        db.session.execute(
            text(
                """
                UPDATE cadastro_territorial.logradouros
                SET
                    status = 'PLANEJADA_AUTORIZADA',
                    oficio_numero = CAST(:numero AS INTEGER),
                    oficio_ano = CAST(:ano AS INTEGER),
                    autorizado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                    autorizado_em = NOW(),
                    atualizado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                    atualizado_em = NOW(),
                    justificativa_devolucao = NULL,
                    devolvido_por_usuario_id = NULL,
                    devolvido_em = NULL
                WHERE id = CAST(:id AS BIGINT)
                  AND status IN (
                      'RASCUNHO',
                      'DEVOLVIDA_AJUSTES'
                  )
                """
            ),
            {
                "numero": numero,
                "ano": ano,
                "usuario_id": int(current_user.id),
                "id": logradouro_id,
            },
        )

        db.session.execute(
            text(
                """
                UPDATE cadastro_territorial.logradouros_oficios
                SET ativo = FALSE
                WHERE logradouro_id = CAST(:logradouro_id AS BIGINT)
                  AND ativo IS TRUE
                """
            ),
            {"logradouro_id": logradouro_id},
        )

        oficio_id = db.session.execute(
            text(
                """
                INSERT INTO cadastro_territorial.logradouros_oficios (
                    logradouro_id,
                    numero,
                    ano,
                    caminho_pdf,
                    caminho_docx,
                    sha256_pdf,
                    sha256_docx,
                    destinatario_nome,
                    destinatario_cargo,
                    assunto,
                    assinante_nome,
                    assinante_cargo,
                    criado_por_usuario_id,
                    criado_em,
                    ativo
                ) VALUES (
                    CAST(:logradouro_id AS BIGINT),
                    CAST(:numero AS INTEGER),
                    CAST(:ano AS INTEGER),
                    CAST(:caminho_pdf AS TEXT),
                    CAST(:caminho_docx AS TEXT),
                    CAST(:sha256_pdf AS VARCHAR),
                    CAST(:sha256_docx AS VARCHAR),
                    CAST(:destinatario_nome AS VARCHAR),
                    CAST(:destinatario_cargo AS VARCHAR),
                    CAST(:assunto AS VARCHAR),
                    CAST(:assinante_nome AS VARCHAR),
                    CAST(:assinante_cargo AS VARCHAR),
                    CAST(:usuario_id AS INTEGER),
                    NOW(),
                    TRUE
                )
                RETURNING id
                """
            ),
            {
                "logradouro_id": logradouro_id,
                "numero": numero,
                "ano": ano,
                "caminho_pdf": caminho_pdf_relativo,
                "caminho_docx": caminho_docx_relativo,
                "sha256_pdf": arquivos_gerados["sha256_pdf"],
                "sha256_docx": arquivos_gerados["sha256_docx"],
                "destinatario_nome": dados_oficio["destinatario_nome"],
                "destinatario_cargo": dados_oficio["destinatario_cargo"],
                "assunto": dados_oficio["assunto"],
                "assinante_nome": dados_oficio["assinante_nome"],
                "assinante_cargo": dados_oficio["assinante_cargo"],
                "usuario_id": int(current_user.id),
            },
        ).scalar_one()

        _registrar_historico(
            logradouro_id,
            "AUTORIZACAO_SEMDU",
            detalhe["status"],
            STATUS_AUTORIZADA,
            f"Ofício nº {numero}/{ano} gerado e encaminhado à SEMFAZ.",
        )

        db.session.commit()
    except Exception:
        db.session.rollback()
        arquivos_gerados["pdf"].unlink(missing_ok=True)
        arquivos_gerados["docx"].unlink(missing_ok=True)
        raise

    return jsonify(
        {
            "sucesso": True,
            "status": STATUS_AUTORIZADA,
            "oficio": {
                "id": int(oficio_id),
                "numero": numero,
                "ano": ano,
            },
            "mensagem": (
                "Logradouro autorizado pela SEMDU e encaminhado à SEMFAZ."
            ),
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/liberar"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMFAZ
)
def liberar_logradouro(
    logradouro_id: int,
):
    detalhe = _verificar_status(
        logradouro_id,
        {STATUS_AUTORIZADA},
    )
    corpo = request.get_json(
        silent=True
    ) or {}
    observacao = _texto(
        corpo.get("observacao"),
        10000,
        obrigatorio=True,
    )

    db.session.execute(
        text(
            """
            UPDATE cadastro_territorial.logradouros
            SET
                status = 'PLANEJADA_LIBERADA',
                observacoes_semfaz = CAST(:observacao AS TEXT),
                liberado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                liberado_em = NOW(),
                atualizado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                atualizado_em = NOW()
            WHERE id = CAST(:id AS BIGINT)
              AND status = 'PLANEJADA_AUTORIZADA'
            """
        ),
        {
            "observacao": observacao,
            "usuario_id": int(current_user.id),
            "id": logradouro_id,
        },
    )

    _registrar_historico(
        logradouro_id,
        "LIBERACAO_SEMFAZ",
        detalhe["status"],
        STATUS_LIBERADA,
        observacao,
    )

    db.session.commit()

    return jsonify(
        {
            "sucesso": True,
            "status": STATUS_LIBERADA,
            "mensagem": "Logradouro liberado pela SEMFAZ.",
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/devolver"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMFAZ
)
def devolver_logradouro(
    logradouro_id: int,
):
    detalhe = _verificar_status(
        logradouro_id,
        {STATUS_AUTORIZADA},
    )
    corpo = request.get_json(
        silent=True
    ) or {}
    motivo = _texto(
        corpo.get("motivo"),
        10000,
        obrigatorio=True,
    )

    db.session.execute(
        text(
            """
            UPDATE cadastro_territorial.logradouros
            SET
                status = 'DEVOLVIDA_AJUSTES',
                justificativa_devolucao = CAST(:motivo AS TEXT),
                devolvido_por_usuario_id = CAST(:usuario_id AS INTEGER),
                devolvido_em = NOW(),
                atualizado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                atualizado_em = NOW()
            WHERE id = CAST(:id AS BIGINT)
              AND status = 'PLANEJADA_AUTORIZADA'
            """
        ),
        {
            "motivo": motivo,
            "usuario_id": int(current_user.id),
            "id": logradouro_id,
        },
    )

    _registrar_historico(
        logradouro_id,
        "DEVOLUCAO_SEMFAZ",
        detalhe["status"],
        STATUS_DEVOLVIDA,
        motivo,
    )

    db.session.commit()

    return jsonify(
        {
            "sucesso": True,
            "status": STATUS_DEVOLVIDA,
            "mensagem": "Processo devolvido à SEMDU para ajustes.",
        }
    )


@cadastro_territorial_bp.post(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/cancelar"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
@fiscal_orgao_required(
    ORGAO_SEMDU
)
def cancelar_logradouro(
    logradouro_id: int,
):
    detalhe = _detalhe_logradouro(
        logradouro_id
    )

    if detalhe["status"] == STATUS_LIBERADA:
        abort(
            409,
            description=(
                "Um logradouro já liberado pela SEMFAZ não pode ser cancelado "
                "por este fluxo."
            ),
        )

    corpo = request.get_json(
        silent=True
    ) or {}
    motivo = _texto(
        corpo.get("motivo"),
        10000,
        obrigatorio=True,
    )

    db.session.execute(
        text(
            """
            UPDATE cadastro_territorial.logradouros
            SET
                status = 'CANCELADA',
                ativo = FALSE,
                observacoes_semdu = CONCAT_WS(
                    E'\n',
                    NULLIF(BTRIM(observacoes_semdu), ''),
                    CAST(:motivo AS TEXT)
                ),
                atualizado_por_usuario_id = CAST(:usuario_id AS INTEGER),
                atualizado_em = NOW()
            WHERE id = CAST(:id AS BIGINT)
              AND ativo IS TRUE
              AND status <> 'PLANEJADA_LIBERADA'
            """
        ),
        {
            "motivo": "Cancelamento: " + motivo,
            "usuario_id": int(current_user.id),
            "id": logradouro_id,
        },
    )

    _registrar_historico(
        logradouro_id,
        "CANCELAMENTO_SEMDU",
        detalhe["status"],
        STATUS_CANCELADA,
        motivo,
    )

    db.session.commit()

    return jsonify(
        {
            "sucesso": True,
            "mensagem": "Planejamento cancelado.",
        }
    )


@cadastro_territorial_bp.get(
    "/api/cadastro-territorial/logradouros/<int:logradouro_id>/oficios/<int:oficio_id>/<string:formato>"
)
@acesso_modulo_required(
    MODULO_CADASTRO_TERRITORIAL
)
def baixar_oficio(
    logradouro_id: int,
    oficio_id: int,
    formato: str,
):
    formato = formato.lower()

    if formato not in {"pdf", "docx"}:
        abort(
            404,
            description="Formato de ofício inválido.",
        )

    registro = db.session.execute(
        text(
            """
            SELECT
                numero,
                ano,
                caminho_pdf,
                caminho_docx
            FROM cadastro_territorial.logradouros_oficios
            WHERE id = CAST(:oficio_id AS BIGINT)
              AND logradouro_id = CAST(:logradouro_id AS BIGINT)
              AND ativo IS TRUE
            """
        ),
        {
            "oficio_id": oficio_id,
            "logradouro_id": logradouro_id,
        },
    ).mappings().one_or_none()

    if registro is None:
        abort(
            404,
            description="Ofício não encontrado.",
        )

    caminho_relativo = registro[
        "caminho_pdf"
        if formato == "pdf"
        else "caminho_docx"
    ]
    caminho = (
        Path(current_app.instance_path)
        / caminho_relativo
    ).resolve()
    raiz = Path(
        current_app.instance_path
    ).resolve()

    if raiz not in caminho.parents or not caminho.exists():
        abort(
            404,
            description="Arquivo do ofício não encontrado.",
        )

    return send_file(
        caminho,
        as_attachment=True,
        download_name=(
            f"Oficio_{registro['numero']}_{registro['ano']}_SEMDU.{formato}"
        ),
        conditional=True,
    )


@cadastro_territorial_bp.errorhandler(
    HTTPException
)
def tratar_erro_http(
    erro: HTTPException,
):
    if request.path.startswith(
        "/api/cadastro-territorial/"
    ):
        return jsonify(
            {
                "sucesso": False,
                "erro": erro.description,
                "codigo": erro.code,
            }
        ), erro.code

    return erro


@cadastro_territorial_bp.errorhandler(
    SQLAlchemyError
)
def tratar_erro_banco(
    erro: SQLAlchemyError,
):
    db.session.rollback()
    current_app.logger.exception(
        "Erro de banco no Cadastro Territorial."
    )

    resposta = {
        "sucesso": False,
        "erro": (
            "O banco de dados não conseguiu concluir a operação."
        ),
    }

    if current_app.debug:
        resposta["detalhes"] = str(
            getattr(erro, "orig", erro)
        )

    return jsonify(resposta), 500
