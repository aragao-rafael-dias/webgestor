from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from flask import current_app
from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import linemerge, unary_union
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


EXTENSOES_DIRETAS = {".geojson", ".json"}
EXTENSOES_OGR = {
    ".gpkg",
    ".kml",
    ".kmz",
    ".shp",
    ".zip",
    ".gml",
    ".gpx",
    ".dxf",
}
EXTENSOES_ACEITAS = EXTENSOES_DIRETAS | EXTENSOES_OGR


class ErroImportacaoGeoespacial(ValueError):
    pass


def _ogr2ogr_candidatos() -> list[Path]:
    configurado = str(
        current_app.config.get("OGR2OGR_PATH")
        or os.environ.get("OGR2OGR_PATH")
        or ""
    ).strip()

    candidatos: list[Path] = []

    if configurado:
        candidatos.append(Path(configurado))

    localizado = shutil.which("ogr2ogr")
    if localizado:
        candidatos.append(Path(localizado))

    if os.name == "nt":
        candidatos.extend(
            [
                Path(r"C:\OSGeo4W\bin\ogr2ogr.exe"),
                Path(r"C:\OSGeo4W64\bin\ogr2ogr.exe"),
            ]
        )

        programas = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ]

        for raiz in programas:
            if not raiz.exists():
                continue

            for pasta_qgis in sorted(
                raiz.glob("QGIS*"),
                reverse=True,
            ):
                candidatos.extend(
                    [
                        pasta_qgis / "bin" / "ogr2ogr.exe",
                        pasta_qgis / "apps" / "gdal" / "bin" / "ogr2ogr.exe",
                    ]
                )

    vistos: set[str] = set()
    resultado: list[Path] = []

    for candidato in candidatos:
        chave = str(candidato).lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(candidato)

    return resultado


def localizar_ogr2ogr() -> Path:
    for candidato in _ogr2ogr_candidatos():
        if candidato.exists() and candidato.is_file():
            return candidato

    raise ErroImportacaoGeoespacial(
        "Não foi possível localizar o ogr2ogr. Instale o QGIS ou defina "
        "OGR2OGR_PATH com o caminho completo do executável."
    )


def _extrair_zip_seguro(
    arquivo_zip: Path,
    destino: Path,
) -> None:
    with zipfile.ZipFile(arquivo_zip, "r") as pacote:
        for item in pacote.infolist():
            caminho = destino / item.filename
            caminho_resolvido = caminho.resolve()

            if destino.resolve() not in caminho_resolvido.parents and caminho_resolvido != destino.resolve():
                raise ErroImportacaoGeoespacial(
                    "O arquivo compactado contém um caminho inseguro."
                )

        pacote.extractall(destino)


def _fonte_para_ogr(
    caminho: Path,
    pasta_temporaria: Path,
) -> Path:
    if caminho.suffix.lower() != ".zip":
        return caminho

    extraidos = pasta_temporaria / "extraidos"
    extraidos.mkdir(parents=True, exist_ok=True)
    _extrair_zip_seguro(caminho, extraidos)

    shapefiles = list(extraidos.rglob("*.shp"))

    if not shapefiles:
        raise ErroImportacaoGeoespacial(
            "O ZIP não contém um arquivo .shp. Para importar Shapefile, "
            "compacte no mesmo ZIP os arquivos .shp, .shx, .dbf e .prj."
        )

    if len(shapefiles) > 1:
        raise ErroImportacaoGeoespacial(
            "O ZIP contém mais de um Shapefile. Envie apenas a camada do logradouro."
        )

    return shapefiles[0]


def _converter_com_ogr(
    origem: Path,
    destino_geojson: Path,
) -> None:
    ogr2ogr = localizar_ogr2ogr()

    comando = [
        str(ogr2ogr),
        "-f",
        "GeoJSON",
        str(destino_geojson),
        str(origem),
        "-t_srs",
        "EPSG:4326",
        "-dim",
        "XY",
        "-skipfailures",
    ]

    processo = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    if processo.returncode != 0 or not destino_geojson.exists():
        detalhes = (
            processo.stderr.strip()
            or processo.stdout.strip()
            or "Falha desconhecida do ogr2ogr."
        )

        raise ErroImportacaoGeoespacial(
            "Não foi possível converter o arquivo geoespacial: "
            + detalhes[:1200]
        )


def _carregar_geojson(caminho: Path) -> dict[str, Any]:
    try:
        return json.loads(
            caminho.read_text(
                encoding="utf-8-sig"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as erro:
        raise ErroImportacaoGeoespacial(
            "O arquivo GeoJSON não pôde ser lido."
        ) from erro


def _geometrias_do_geojson(
    documento: dict[str, Any],
) -> list:
    tipo = str(documento.get("type") or "").strip()

    if tipo == "FeatureCollection":
        geometrias = [
            item.get("geometry")
            for item in documento.get("features") or []
            if isinstance(item, dict)
            and item.get("geometry")
        ]
    elif tipo == "Feature":
        geometrias = [documento.get("geometry")]
    else:
        geometrias = [documento]

    linhas = []

    for geometria_json in geometrias:
        if not geometria_json:
            continue

        try:
            geometria = shape(geometria_json)
        except Exception as erro:
            raise ErroImportacaoGeoespacial(
                "Uma das geometrias do arquivo é inválida."
            ) from erro

        if geometria.is_empty:
            continue

        if isinstance(geometria, LineString):
            linhas.append(geometria)
        elif isinstance(geometria, MultiLineString):
            linhas.extend(list(geometria.geoms))
        else:
            raise ErroImportacaoGeoespacial(
                "A camada deve conter linhas. Foram encontrados elementos "
                f"do tipo {geometria.geom_type}."
            )

    if not linhas:
        raise ErroImportacaoGeoespacial(
            "Nenhuma geometria linear foi encontrada no arquivo."
        )

    return linhas


def _unificar_linhas(linhas: list) -> LineString:
    if len(linhas) == 1:
        combinada = linhas[0]
    else:
        uniao = unary_union(linhas)
        combinada = (
            uniao
            if isinstance(uniao, LineString)
            else linemerge(uniao)
        )

    if isinstance(combinada, LineString):
        linha = combinada
    elif isinstance(combinada, MultiLineString):
        partes = sorted(
            combinada.geoms,
            key=lambda item: item.length,
            reverse=True,
        )

        if len(partes) == 1:
            linha = partes[0]
        else:
            raise ErroImportacaoGeoespacial(
                "A importação resultou em trechos desconectados. Una os segmentos "
                "no QGIS ou envie somente o eixo contínuo da rua."
            )
    else:
        raise ErroImportacaoGeoespacial(
            "Não foi possível transformar a camada em uma única linha contínua."
        )

    if len(linha.coords) < 2:
        raise ErroImportacaoGeoespacial(
            "A linha precisa possuir pelo menos dois vértices."
        )

    min_x, min_y, max_x, max_y = linha.bounds

    if not (
        -180 <= min_x <= 180
        and -180 <= max_x <= 180
        and -90 <= min_y <= 90
        and -90 <= max_y <= 90
    ):
        raise ErroImportacaoGeoespacial(
            "As coordenadas não estão em EPSG:4326. Instale/configure o "
            "ogr2ogr para que o sistema transforme automaticamente o CRS "
            "do arquivo exportado pelo QGIS."
        )

    return linha


def importar_arquivo_logradouro(
    arquivo: FileStorage,
) -> dict[str, Any]:
    nome_original = str(arquivo.filename or "").strip()

    if not nome_original:
        raise ErroImportacaoGeoespacial(
            "Selecione um arquivo para importar."
        )

    nome_seguro = secure_filename(nome_original)
    extensao = Path(nome_seguro).suffix.lower()

    if extensao not in EXTENSOES_ACEITAS:
        raise ErroImportacaoGeoespacial(
            "Formato não suportado. Use GeoJSON, SHP compactado em ZIP, "
            "GPKG, KML, KMZ, GML, GPX ou DXF."
        )

    with tempfile.TemporaryDirectory(
        prefix="cadastro_territorial_"
    ) as pasta:
        pasta_temporaria = Path(pasta)
        entrada = pasta_temporaria / nome_seguro
        arquivo.save(entrada)

        if entrada.stat().st_size <= 0:
            raise ErroImportacaoGeoespacial(
                "O arquivo enviado está vazio."
            )

        if extensao in EXTENSOES_DIRETAS:
            ogr_disponivel = any(
                candidato.exists()
                and candidato.is_file()
                for candidato in _ogr2ogr_candidatos()
            )

            if ogr_disponivel:
                geojson_path = pasta_temporaria / "convertido.geojson"
                _converter_com_ogr(
                    entrada,
                    geojson_path,
                )
            else:
                geojson_path = entrada
        else:
            fonte = _fonte_para_ogr(
                entrada,
                pasta_temporaria,
            )
            geojson_path = pasta_temporaria / "convertido.geojson"
            _converter_com_ogr(
                fonte,
                geojson_path,
            )

        documento = _carregar_geojson(
            geojson_path
        )
        linhas = _geometrias_do_geojson(
            documento
        )
        linha = _unificar_linhas(
            linhas
        )

        return {
            "type": "Feature",
            "properties": {
                "arquivo_origem": nome_original,
                "vertices": len(linha.coords),
            },
            "geometry": mapping(linha),
        }
