from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests
from docx import Document

from servicos.memoriais_docx import extrair_metadados_docx, texto_limpo


@dataclass
class PontoItinerario:
    ordem: int
    referencia: str
    lat: float
    lon: float
    lado_via: str = ""
    logradouro: str = ""
    direcao_seguir: str = ""

    @property
    def coordenadas(self) -> str:
        return f"({self.lat:.6f}, {self.lon:.6f})"

    def para_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["coordenadas"] = self.coordenadas
        return dados


@dataclass
class TrechoImportado:
    trecho: str
    pontos: list[PontoItinerario] = field(default_factory=list)
    geometria: dict[str, Any] | None = None
    distancia_roteada_km: float | None = None
    duracao_roteada_min: float | None = None

    def para_dict(self) -> dict[str, Any]:
        return {
            "trecho": self.trecho,
            "pontos": [ponto.para_dict() for ponto in self.pontos],
            "geometria": self.geometria,
            "distancia_roteada_km": self.distancia_roteada_km,
            "duracao_roteada_min": self.duracao_roteada_min,
        }


@dataclass
class MemorialRotaImportado:
    numero_linha: str
    nome_rota: str
    regiao: str
    linha: str
    km_ida_documento: float | None
    km_volta_documento: float | None
    trechos: dict[str, TrechoImportado]
    avisos: list[str] = field(default_factory=list)

    def para_dict(self) -> dict[str, Any]:
        return {
            "numero_linha": self.numero_linha,
            "nome_rota": self.nome_rota,
            "regiao": self.regiao,
            "linha": self.linha,
            "km_ida_documento": self.km_ida_documento,
            "km_volta_documento": self.km_volta_documento,
            "trechos": {
                nome: trecho.para_dict()
                for nome, trecho in self.trechos.items()
            },
            "avisos": list(self.avisos),
        }


def nome_rota_banco(numero_linha: str) -> str:
    codigo = texto_limpo(numero_linha)
    codigo = re.sub(r"^Rota", "", codigo, flags=re.IGNORECASE)
    codigo = codigo.replace(".", "_")
    codigo = re.sub(r"^([A-Za-z]+)-(\d+)$", r"\1_\2", codigo)
    codigo = re.sub(r"\s+", "", codigo)
    if not codigo:
        raise ValueError("Número da linha não identificado no memorial.")
    return f"Rota{codigo}"


def _texto_itinerario(documento: Document) -> str:
    candidatos: list[str] = []
    for tabela in documento.tables:
        for linha in tabela.rows:
            vistos: set[str] = set()
            for celula in linha.cells:
                texto = celula.text or ""
                chave = texto.strip()
                if not chave or chave in vistos:
                    continue
                vistos.add(chave)
                if "ITINERÁRIO DA LINHA" in chave.upper() or "ITINERARIO DA LINHA" in chave.upper():
                    candidatos.append(chave)
    if not candidatos:
        raise ValueError("O memorial não possui a seção 'Itinerário da Linha'.")
    return max(candidatos, key=len)


def _extrair_regiao(documento: Document) -> str:
    for tabela in documento.tables:
        for linha in tabela.rows[:2]:
            for celula in linha.cells:
                match = re.search(r"(?mi)^\s*Região\s*:\s*([^\n\r]+)", celula.text or "")
                if match:
                    return texto_limpo(match.group(1))
    return ""


def _limpar_linha_itinerario(linha: str) -> str:
    linha = texto_limpo(linha)
    linha = re.sub(r"^[•·▪◦\-*]+\s*", "", linha)
    linha = re.sub(r"^[➡➜➔➤→]\ufe0f?\s*", "", linha)
    return linha.strip()


def _novo_ponto(match: re.Match[str]) -> PontoItinerario:
    return PontoItinerario(
        ordem=int(match.group(1)),
        referencia=texto_limpo(match.group(2)),
        lat=0.0,
        lon=0.0,
    )


def extrair_itinerarios(documento: Document) -> dict[str, TrechoImportado]:
    texto = _texto_itinerario(documento)
    trechos = {
        "IDA": TrechoImportado("IDA"),
        "VOLTA": TrechoImportado("VOLTA"),
    }
    trecho_atual: TrechoImportado | None = None
    ponto_atual: PontoItinerario | None = None

    def finalizar_ponto() -> None:
        nonlocal ponto_atual
        if ponto_atual is None or trecho_atual is None:
            return
        if not (-90 <= ponto_atual.lat <= 90 and -180 <= ponto_atual.lon <= 180):
            raise ValueError(
                f"Coordenada inválida no ponto {ponto_atual.ordem} de {trecho_atual.trecho}."
            )
        if ponto_atual.lat == 0.0 and ponto_atual.lon == 0.0:
            raise ValueError(
                f"Coordenada não identificada no ponto {ponto_atual.ordem} de {trecho_atual.trecho}."
            )
        trecho_atual.pontos.append(ponto_atual)
        ponto_atual = None

    for linha_original in texto.splitlines():
        linha = _limpar_linha_itinerario(linha_original)
        if not linha:
            continue

        cabecalho = re.sub(r"[^A-Z]", "", linha.upper())
        if cabecalho == "IDA":
            finalizar_ponto()
            trecho_atual = trechos["IDA"]
            continue
        if cabecalho == "VOLTA":
            finalizar_ponto()
            trecho_atual = trechos["VOLTA"]
            continue
        if trecho_atual is None:
            continue
        if cabecalho in {"INICIO", "TERMINO", "FIM"}:
            continue

        match_ponto = re.match(r"^(\d+)\s*[.)-]\s*(.+)$", linha)
        if match_ponto:
            finalizar_ponto()
            ponto_atual = _novo_ponto(match_ponto)
            continue
        if ponto_atual is None:
            continue

        match_coord = re.search(
            r"COORDENADAS?\s*:\s*\(\s*([-+]?\d+(?:[.,]\d+)?)\s*,\s*([-+]?\d+(?:[.,]\d+)?)\s*\)",
            linha,
            flags=re.IGNORECASE,
        )
        if match_coord:
            ponto_atual.lat = float(match_coord.group(1).replace(",", "."))
            ponto_atual.lon = float(match_coord.group(2).replace(",", "."))
            continue

        match_lado = re.match(r"^LADO\s*:\s*(.*)$", linha, flags=re.IGNORECASE)
        if match_lado:
            ponto_atual.lado_via = texto_limpo(match_lado.group(1)).upper()
            continue

        match_logradouro = re.match(r"^LOGRADOURO\s*:\s*(.*)$", linha, flags=re.IGNORECASE)
        if match_logradouro:
            ponto_atual.logradouro = texto_limpo(match_logradouro.group(1))
            continue

        match_direcao = re.match(r"^(?:DIREÇÃO(?: A SEGUIR)?|DIRECAO(?: A SEGUIR)?)\s*:\s*(.*)$", linha, flags=re.IGNORECASE)
        if match_direcao:
            ponto_atual.direcao_seguir = texto_limpo(match_direcao.group(1))
            continue

        linha_direcao = re.sub(r"^[➡➜➔➤→]\ufe0f?\s*", "", linha).strip()
        if re.search(r"\bKM\b", linha_direcao, flags=re.IGNORECASE) or re.match(
            r"^(EM FRENTE|VIRANDO|SEGUINDO|RETORNANDO|CONTINUANDO)",
            linha_direcao,
            flags=re.IGNORECASE,
        ):
            ponto_atual.direcao_seguir = linha_direcao

    finalizar_ponto()

    for nome, trecho in trechos.items():
        if len(trecho.pontos) < 2:
            raise ValueError(f"O trecho {nome} precisa ter pelo menos dois pontos com coordenadas.")
        ordens = [p.ordem for p in trecho.pontos]
        if len(ordens) != len(set(ordens)):
            raise ValueError(f"Há números de ponto repetidos no trecho {nome}.")

    return trechos


def roteamento_osrm(
    pontos: list[PontoItinerario],
    base_url: str = "https://router.project-osrm.org",
    timeout: int = 45,
) -> tuple[dict[str, Any], float, float]:
    coordenadas = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in pontos)
    url = f"{base_url.rstrip('/')}/route/v1/driving/{coordenadas}"
    resposta = requests.get(
        url,
        params={
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        },
        timeout=timeout,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    if dados.get("code") != "Ok" or not dados.get("routes"):
        mensagem = dados.get("message") or dados.get("code") or "sem rota"
        raise ValueError(f"O roteador não conseguiu calcular o trajeto: {mensagem}.")

    rota = dados["routes"][0]
    geometria = rota.get("geometry")
    if not geometria or geometria.get("type") != "LineString":
        raise ValueError("O roteador retornou uma geometria inválida.")
    return geometria, float(rota.get("distance", 0.0)) / 1000.0, float(rota.get("duration", 0.0)) / 60.0


def importar_docx(
    caminho_docx: Path,
    osrm_base_url: str = "https://router.project-osrm.org",
    timeout: int = 45,
) -> MemorialRotaImportado:
    metadados = extrair_metadados_docx(caminho_docx)
    documento = Document(caminho_docx)
    trechos = extrair_itinerarios(documento)

    avisos = list(metadados.avisos)
    for trecho in trechos.values():
        geometria, distancia, duracao = roteamento_osrm(
            trecho.pontos,
            base_url=osrm_base_url,
            timeout=timeout,
        )
        trecho.geometria = geometria
        trecho.distancia_roteada_km = round(distancia, 3)
        trecho.duracao_roteada_min = round(duracao, 1)

    km_ida = float(metadados.km_ida) if metadados.km_ida is not None else None
    km_volta = float(metadados.km_volta) if metadados.km_volta is not None else None

    for nome, km_doc in (("IDA", km_ida), ("VOLTA", km_volta)):
        km_roteada = trechos[nome].distancia_roteada_km
        if km_doc and km_roteada:
            diferenca = abs(km_roteada - km_doc) / km_doc
            if diferenca >= 0.15:
                avisos.append(
                    f"{nome}: a rota calculada ({km_roteada:.2f} km) difere "
                    f"{diferenca * 100:.0f}% da quilometragem do memorial ({km_doc:.2f} km)."
                )

    return MemorialRotaImportado(
        numero_linha=metadados.numero_linha,
        nome_rota=nome_rota_banco(metadados.numero_linha),
        regiao=_extrair_regiao(documento),
        linha=metadados.linha,
        km_ida_documento=km_ida,
        km_volta_documento=km_volta,
        trechos=trechos,
        avisos=avisos,
    )


def salvar_upload_temporario(arquivo) -> Path:
    nome = (arquivo.filename or "").lower()
    if not nome.endswith(".docx"):
        raise ValueError("Envie um memorial no formato DOCX.")
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temporario:
        arquivo.save(temporario)
        caminho = Path(temporario.name)
    return caminho


def pontos_para_json(pontos: list[dict[str, Any]]) -> str:
    campos = (
        "ordem",
        "referencia",
        "coordenadas",
        "lat",
        "lon",
        "lado_via",
        "logradouro",
        "direcao_seguir",
    )
    normalizados: list[dict[str, Any]] = []
    for ponto in pontos:
        normalizado = {campo: ponto.get(campo, "") for campo in campos}
        normalizado["ordem"] = int(normalizado["ordem"])
        normalizado["lat"] = float(normalizado["lat"])
        normalizado["lon"] = float(normalizado["lon"])
        if not (-90 <= normalizado["lat"] <= 90 and -180 <= normalizado["lon"] <= 180):
            raise ValueError("Há coordenadas fora dos limites válidos.")
        normalizados.append(normalizado)
    if len(normalizados) < 2:
        raise ValueError("Cada trecho precisa ter pelo menos dois pontos.")
    return json.dumps(normalizados, ensure_ascii=False)


def validar_geojson_linha(geometria: Any) -> str:
    if not isinstance(geometria, dict) or geometria.get("type") != "LineString":
        raise ValueError("Geometria de rota inválida.")
    coords = geometria.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise ValueError("A rota precisa ter pelo menos dois vértices.")
    for coordenada in coords:
        if not isinstance(coordenada, list) or len(coordenada) < 2:
            raise ValueError("Vértice inválido na geometria.")
        lon, lat = float(coordenada[0]), float(coordenada[1])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("A geometria possui coordenadas fora dos limites válidos.")
    return json.dumps(geometria, ensure_ascii=False)
