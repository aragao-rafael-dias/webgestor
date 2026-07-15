from flask import Blueprint, send_file, abort
from sqlalchemy import text
from xhtml2pdf import pisa
from flask import render_template

from models import db

import json
import ast
import io
import base64
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


memorial_bp = Blueprint(
    "memorial",
    __name__
)

@memorial_bp.route(
    "/api/rotas/<int:rota_id>/memorial",
    methods=["GET"]
)

def gerar_memorial(rota_id):

    # =====================================================
    # BUSCA DOS DADOS DA ROTA
    # =====================================================

    sql_rota = text("""

        WITH normalized AS (

            SELECT *,

                to_json(pontos_notaveis) AS pontos_notaveis_json,

                CASE

                    WHEN ST_SRID(geom) = 31984
                        THEN geom

                    WHEN ST_SRID(geom) = 4326
                        THEN ST_Transform(geom,31984)

                    ELSE

                        CASE

                            WHEN ST_X(ST_Centroid(geom)) > 100000

                                THEN ST_SetSRID(
                                    geom,
                                    31984
                                )

                            ELSE

                                ST_Transform(
                                    ST_SetSRID(
                                        geom,
                                        4326
                                    ),
                                    31984
                                )

                        END

                END AS geom_utm

            FROM semed.rotas_geral

            WHERE id = :id

        )

        SELECT *,
               ST_Length(geom_utm) AS extensao_total

        FROM normalized;

    """)

    resultado = db.session.execute(
        sql_rota,
        {
            "id": rota_id
        }
    ).mappings().fetchone()

    if not resultado:

        abort(
            404,
            description="Rota não encontrada."
        )

    nome_rota = resultado.get(
        "nome_rota",
        f"#{rota_id}"
    )

    regiao = resultado.get(
        "regiao",
        "Não informada"
    )

    trecho = resultado.get(
        "trecho",
        "Não informado"
    )

    total_pontos = resultado.get(
        "total_pontos",
        0
    )

    extensao_total = resultado.get(
        "extensao_total",
        0
    )

    # =====================================================
    # TRATAMENTO ROBUSTO DO JSON
    # =====================================================

    pontos_notaveis_raw = (
        resultado.get("pontos_notaveis_json")
        or
        resultado.get("pontos_notaveis")
    )

    pontos_notaveis = []

    if pontos_notaveis_raw:

        if isinstance(
            pontos_notaveis_raw,
            str
        ):

            texto_limpo = (
                pontos_notaveis_raw.strip()
            )

            if texto_limpo:

                try:

                    pontos_notaveis = json.loads(
                        texto_limpo
                    )

                except json.JSONDecodeError:

                    try:

                        pontos_notaveis = json.loads(
                            texto_limpo.replace(
                                "'",
                                '"'
                            )
                        )

                    except:

                        try:

                            pontos_notaveis = (
                                ast.literal_eval(
                                    texto_limpo
                                )
                            )

                        except Exception as e:

                            print(
                                "\n" +
                                "=" * 40
                            )

                            print(
                                "⚠️ ERRO AO LER PONTOS NOTÁVEIS"
                            )

                            print(
                                repr(texto_limpo)
                            )

                            print(e)

                            print(
                                "=" * 40 +
                                "\n"
                            )

                            pontos_notaveis = []

        elif isinstance(
            pontos_notaveis_raw,
            list
        ):

            pontos_notaveis = (
                pontos_notaveis_raw
            )

        elif isinstance(
            pontos_notaveis_raw,
            dict
        ):

            pontos_notaveis = [
                pontos_notaveis_raw
            ]
                
# =====================================================
# BUSCA DOS PONTOS DA GEOMETRIA
# =====================================================

    sql_pontos = text("""

        WITH normalized AS (

            SELECT
                id,

                CASE

                    WHEN ST_SRID(geom) = 31984
                        THEN geom

                    WHEN ST_SRID(geom) = 4326
                        THEN ST_Transform(
                            geom,
                            31984
                        )

                    ELSE

                        CASE

                            WHEN ST_X(ST_Centroid(geom)) > 100000

                                THEN ST_SetSRID(
                                    geom,
                                    31984
                                )

                            ELSE

                                ST_Transform(
                                    ST_SetSRID(
                                        geom,
                                        4326
                                    ),
                                    31984
                                )

                        END

                END AS geom_utm

            FROM semed.rotas_geral

            WHERE id = :id

        ),

        dumped AS (

            SELECT
                (ST_DumpPoints(geom_utm)).path AS path,
                (ST_DumpPoints(geom_utm)).geom AS pt_geom

            FROM normalized

        )

        SELECT

            ST_X(pt_geom) AS coord_e,
            ST_Y(pt_geom) AS coord_n

        FROM dumped;

    """)

    pontos_geom = db.session.execute(
        sql_pontos,
        {
            "id": rota_id
        }
    ).mappings().fetchall()

    x_coords = []
    y_coords = []

    for ponto in pontos_geom:

        x_coords.append(
            ponto["coord_e"]
        )

        y_coords.append(
            ponto["coord_n"]
        )

# =====================================================
# GERAÇÃO DO CROQUI
# =====================================================

    if x_coords and y_coords:

        plt.figure(
            figsize=(7, 4)
        )

        plt.plot(
            x_coords,
            y_coords,
            color="#800000",
            linewidth=3.5
        )

        plt.fill(
            x_coords,
            y_coords,
            alpha=0.25,
            color="#ffffff"
        )

        plt.title(
            f"Croqui Geométrico - {nome_rota}",
            fontsize=11,
            color="#800000",
            fontweight="bold"
        )

        plt.axis("equal")

        plt.grid(
            True,
            linestyle="--",
            alpha=0.5,
            color="#cccccc"
        )

        plt.xlabel("Coord. E (X)")
        plt.ylabel("Coord. N (Y)")

        plt.ticklabel_format(
            useOffset=False,
            style="plain"
        )

        plt.tight_layout()

        img_io = io.BytesIO()

        plt.savefig(
            img_io,
            format="png",
            dpi=150,
            bbox_inches="tight"
        )

        plt.close()

        img_io.seek(0)

        mapa_base64 = base64.b64encode(
            img_io.read()
        ).decode("utf-8")

    else:

        mapa_base64 = ""

    # =====================================================
    # HTML DO PDF
    # =====================================================

    html_content = render_template(
        "memorial.html",
        nome_rota=nome_rota,
        regiao=regiao,
        trecho=trecho,
        total_pontos=total_pontos,
        extensao_total=extensao_total,
        mapa_base64=mapa_base64,
        pontos_notaveis=pontos_notaveis
    )
    # =====================================================
    # GERAÇÃO DO PDF
    # =====================================================

    pdf_io = io.BytesIO()

    pisa_status = pisa.CreatePDF(
        io.StringIO(html_content),
        dest=pdf_io
    )

    pdf_io.seek(0)

    if pisa_status.err:

        abort(
            500,
            description="Erro interno ao gerar o PDF."
        )

    return send_file(
        pdf_io,
        download_name=f"Memorial_{nome_rota}.pdf",
        as_attachment=True,
        mimetype="application/pdf"
    )