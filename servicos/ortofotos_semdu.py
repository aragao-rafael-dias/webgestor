from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_MOSAICO = RAIZ_PROJETO / "mosaico"
PASTA_COG = (
    RAIZ_PROJETO
    / "instance"
    / "ortofotos_semdu"
)

TRANSPARENTE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class ConfiguracaoOrtofoto:
    id: str
    titulo: str
    descricao: str
    resolucao: str
    origem_padrao: Path
    cog_padrao: Path
    variavel_origem: str
    variavel_cog: str
    max_zoom_nativo: int

    @property
    def origem(self) -> Path:
        return Path(
            os.getenv(
                self.variavel_origem,
                str(self.origem_padrao),
            )
        ).expanduser()

    @property
    def cog(self) -> Path:
        return Path(
            os.getenv(
                self.variavel_cog,
                str(self.cog_padrao),
            )
        ).expanduser()


ORTOFOTOS: dict[str, ConfiguracaoOrtofoto] = {
    "satelite_15cm": ConfiguracaoOrtofoto(
        id="satelite_15cm",
        titulo="Imagem de satélite 2025 — 15 cm",
        descricao=(
            "Imagem de satélite municipal com resolução espacial "
            "aproximada de 15 centímetros."
        ),
        resolucao="15 cm",
        origem_padrao=(
            PASTA_MOSAICO
            / "img-sat_pml_2025_15cm.ecw"
        ),
        cog_padrao=(
            PASTA_COG
            / "img-sat_pml_2025_15cm_webmercator_cog.tif"
        ),
        variavel_origem="SEMDU_ORTOFOTO_15CM_ORIGEM",
        variavel_cog="SEMDU_ORTOFOTO_15CM_COG",
        max_zoom_nativo=22,
    ),
    "ortofoto_8cm": ConfiguracaoOrtofoto(
        id="ortofoto_8cm",
        titulo="Ortofoto municipal 2025 — 8 cm",
        descricao=(
            "Mosaico ortorretificado municipal com resolução "
            "espacial aproximada de 8 centímetros."
        ),
        resolucao="8 cm",
        origem_padrao=(
            PASTA_MOSAICO
            / "mosaico_pml_8cm_2025.ecw"
        ),
        cog_padrao=(
            PASTA_COG
            / "mosaico_pml_8cm_2025_webmercator_cog.tif"
        ),
        variavel_origem="SEMDU_ORTOFOTO_8CM_ORIGEM",
        variavel_cog="SEMDU_ORTOFOTO_8CM_COG",
        max_zoom_nativo=23,
    ),
}


def obter_configuracao(
    id_ortofoto: str,
) -> ConfiguracaoOrtofoto:
    try:
        return ORTOFOTOS[str(id_ortofoto)]
    except KeyError as erro:
        raise KeyError(
            "Ortofoto não cadastrada."
        ) from erro


def _importar_rasterio():
    try:
        import rasterio
        from rasterio.warp import transform_bounds
    except ImportError as erro:
        raise RuntimeError(
            "Instale as dependências do WebSIG SEMDU: "
            "python -m pip install -r "
            "requirements-semdu-websig.txt"
        ) from erro

    return rasterio, transform_bounds


def _driver_ecw_disponivel() -> bool:
    try:
        rasterio, _ = _importar_rasterio()

        with rasterio.Env() as ambiente:
            drivers = ambiente.drivers()

        return "ECW" in drivers
    except Exception:
        return False


def _arquivo_servico(
    configuracao: ConfiguracaoOrtofoto,
) -> tuple[Path | None, str, str]:
    """
    Retorna arquivo, modo e motivo.

    O COG é sempre priorizado. O ECW direto só é usado quando o
    Rasterio/GDAL da aplicação possui o driver ECW habilitado.
    """
    if configuracao.cog.is_file():
        return (
            configuracao.cog,
            "COG",
            "",
        )

    if configuracao.origem.is_file():
        if _driver_ecw_disponivel():
            return (
                configuracao.origem,
                "ECW_DIRETO",
                "",
            )

        return (
            None,
            "INDISPONIVEL",
            (
                "O ECW existe, mas o GDAL usado pelo servidor não "
                "possui o driver ECW. Execute o comando de preparo "
                "para gerar o COG de publicação."
            ),
        )

    return (
        None,
        "INDISPONIVEL",
        (
            "Arquivo de origem não localizado em "
            f"{configuracao.origem}."
        ),
    )


def _metadados_raster(
    caminho: Path,
) -> dict[str, Any]:
    rasterio, transform_bounds = _importar_rasterio()

    with rasterio.open(caminho) as fonte:
        if fonte.crs is None:
            raise RuntimeError(
                "O raster não possui sistema de referência espacial."
            )

        limites = transform_bounds(
            fonte.crs,
            "EPSG:4326",
            *fonte.bounds,
            densify_pts=21,
        )

        return {
            "driver": fonte.driver,
            "crs": fonte.crs.to_string(),
            "largura": int(fonte.width),
            "altura": int(fonte.height),
            "bandas": int(fonte.count),
            "limites": [
                float(limites[0]),
                float(limites[1]),
                float(limites[2]),
                float(limites[3]),
            ],
        }


def catalogar_ortofotos() -> list[dict[str, Any]]:
    catalogo: list[dict[str, Any]] = []

    for configuracao in ORTOFOTOS.values():
        arquivo, modo, motivo = _arquivo_servico(
            configuracao
        )

        metadados: dict[str, Any] = {}
        disponivel = arquivo is not None

        if arquivo is not None:
            try:
                metadados = _metadados_raster(
                    arquivo
                )
            except Exception as erro:
                disponivel = False
                motivo = (
                    "O raster foi localizado, mas não pôde ser "
                    f"aberto: {erro}"
                )

        catalogo.append(
            {
                "id": configuracao.id,
                "titulo": configuracao.titulo,
                "descricao": configuracao.descricao,
                "resolucao": configuracao.resolucao,
                "disponivel": disponivel,
                "modo_publicacao": modo,
                "motivo": motivo,
                "min_zoom": 10,
                "max_zoom": 24,
                "max_zoom_nativo": (
                    configuracao.max_zoom_nativo
                ),
                "atribuicao": (
                    "Prefeitura Municipal de Lagarto — 2025"
                ),
                "origem_encontrada": (
                    configuracao.origem.is_file()
                ),
                "cog_encontrado": (
                    configuracao.cog.is_file()
                ),
                **metadados,
            }
        )

    return catalogo


def caminho_publicacao(
    id_ortofoto: str,
) -> Path:
    configuracao = obter_configuracao(
        id_ortofoto
    )
    arquivo, _, motivo = _arquivo_servico(
        configuracao
    )

    if arquivo is None:
        raise FileNotFoundError(
            motivo
        )

    return arquivo


def renderizar_tile(
    id_ortofoto: str,
    x: int,
    y: int,
    z: int,
) -> tuple[bytes, str, bool]:
    """
    Retorna bytes, MIME type e indicação de tile transparente.
    """
    if not (
        0 <= int(z) <= 24
        and int(x) >= 0
        and int(y) >= 0
    ):
        raise ValueError(
            "Coordenada de tile inválida."
        )

    caminho = caminho_publicacao(
        id_ortofoto
    )

    try:
        import numpy
        from rio_tiler.errors import (
            TileOutsideBounds,
        )
        from rio_tiler.io import Reader
    except ImportError as erro:
        raise RuntimeError(
            "Instale rio-tiler e Rasterio usando "
            "requirements-semdu-websig.txt."
        ) from erro

    try:
        with Reader(str(caminho)) as leitor:
            quantidade_bandas = int(
                leitor.dataset.count
            )

            if quantidade_bandas >= 3:
                indices: int | tuple[int, ...] = (
                    1,
                    2,
                    3,
                )
            else:
                indices = 1

            imagem = leitor.tile(
                int(x),
                int(y),
                int(z),
                tilesize=256,
                indexes=indices,
                resampling_method="bilinear",
            )

            possui_transparencia = bool(
                numpy.any(
                    imagem.mask < 255
                )
            )

            if possui_transparencia:
                return (
                    imagem.render(
                        img_format="PNG"
                    ),
                    "image/png",
                    False,
                )

            return (
                imagem.render(
                    img_format="JPEG",
                    quality=88,
                ),
                "image/jpeg",
                False,
            )
    except TileOutsideBounds:
        return (
            TRANSPARENTE_PNG,
            "image/png",
            True,
        )


def localizar_gdalwarp(
    caminho_informado: str | Path | None = None,
) -> Path | None:
    candidatos: list[Path] = []

    if caminho_informado:
        candidatos.append(
            Path(caminho_informado)
        )

    variavel = os.getenv(
        "GDALWARP_PATH"
    )

    if variavel:
        candidatos.append(
            Path(variavel)
        )

    encontrado_path = shutil.which(
        "gdalwarp"
    )

    if encontrado_path:
        candidatos.append(
            Path(encontrado_path)
        )

    if os.name == "nt":
        arquivos_programas = Path(
            os.getenv(
                "ProgramFiles",
                r"C:\Program Files",
            )
        )

        candidatos.extend(
            sorted(
                arquivos_programas.glob(
                    "QGIS*/bin/gdalwarp.exe"
                ),
                reverse=True,
            )
        )

        candidatos.extend(
            [
                Path(
                    r"C:\OSGeo4W\bin\gdalwarp.exe"
                ),
                Path(
                    r"C:\OSGeo4W64\bin\gdalwarp.exe"
                ),
            ]
        )

    for candidato in candidatos:
        candidato = candidato.expanduser()

        if candidato.is_file():
            return candidato.resolve()

    return None


def preparar_cog(
    configuracao: ConfiguracaoOrtofoto,
    *,
    gdalwarp: str | Path | None = None,
    sobrescrever: bool = False,
    origem_alternativa: str | Path | None = None,
) -> Path:
    origem = (
        Path(origem_alternativa).expanduser()
        if origem_alternativa
        else configuracao.origem
    )
    destino = configuracao.cog

    if not origem.is_file():
        raise FileNotFoundError(
            f"Arquivo de origem não encontrado: {origem}"
        )

    if destino.exists() and not sobrescrever:
        raise FileExistsError(
            "O COG já existe. Use --sobrescrever para recriá-lo: "
            f"{destino}"
        )

    executavel = localizar_gdalwarp(
        gdalwarp
    )

    if executavel is None:
        raise RuntimeError(
            "Não foi possível localizar gdalwarp. Para decodificar "
            "ECW, o computador administrador precisa possuir uma "
            "distribuição GDAL com driver ECW. Os usuários do WebSIG "
            "não precisam instalar QGIS ou GDAL."
        )

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporario = destino.with_suffix(
        ".tmp.tif"
    )

    if temporario.exists():
        temporario.unlink()

    comando = [
        str(executavel),
        "-overwrite",
        "-multi",
        "-wo",
        "NUM_THREADS=ALL_CPUS",
        "-r",
        "bilinear",
        "-t_srs",
        "EPSG:3857",
        "-dstalpha",
        "-of",
        "COG",
        "-co",
        "COMPRESS=JPEG",
        "-co",
        "QUALITY=90",
        "-co",
        "BLOCKSIZE=512",
        "-co",
        "BIGTIFF=YES",
        "-co",
        "NUM_THREADS=ALL_CPUS",
        "-co",
        "OVERVIEWS=AUTO",
        "-co",
        "RESAMPLING=BILINEAR",
        str(origem),
        str(temporario),
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if resultado.returncode != 0:
        temporario.unlink(
            missing_ok=True
        )

        detalhes = (
            resultado.stderr.strip()
            or resultado.stdout.strip()
            or "gdalwarp terminou sem detalhes."
        )

        raise RuntimeError(
            "Falha na conversão ECW → COG. "
            f"Detalhes: {detalhes}"
        )

    if not temporario.is_file():
        raise RuntimeError(
            "A conversão terminou sem gerar o arquivo COG."
        )

    _metadados_raster(
        temporario
    )

    temporario.replace(
        destino
    )

    return destino


def diagnostico_ortofotos() -> dict[str, Any]:
    gdalwarp = localizar_gdalwarp()

    try:
        import rasterio

        versao_rasterio = rasterio.__version__
        with rasterio.Env() as ambiente:
            drivers = ambiente.drivers()
        ecw = "ECW" in drivers
    except Exception as erro:
        versao_rasterio = None
        ecw = False
        erro_rasterio = str(erro)
    else:
        erro_rasterio = ""

    try:
        import rio_tiler

        versao_rio_tiler = rio_tiler.__version__
    except Exception as erro:
        versao_rio_tiler = None
        erro_rio_tiler = str(erro)
    else:
        erro_rio_tiler = ""

    return {
        "rasterio": versao_rasterio,
        "rasterio_erro": erro_rasterio,
        "rio_tiler": versao_rio_tiler,
        "rio_tiler_erro": erro_rio_tiler,
        "driver_ecw_no_python": ecw,
        "gdalwarp": (
            str(gdalwarp)
            if gdalwarp
            else None
        ),
        "ortofotos": catalogar_ortofotos(),
    }
