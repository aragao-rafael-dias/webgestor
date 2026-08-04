# ==========================================
# EXTRAÇÃO DOS METADADOS DOS MEMORIAIS DOCX
# ==========================================

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, fields
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from docx import Document


TURNOS = ("MANHÃ", "TARDE", "NOITE", "INTEGRAL")
TIPOS_VEICULO = (
    "ÔNIBUS",
    "MICRO-ÔNIBUS 4X4",
    "MICRO-ÔNIBUS",
    "VAN",
)
REDES_ENSINO = ("MUNICIPAL", "ESTADUAL", "FEDERAL")
AREAS = ("URBANA", "RURAL")

# Mantido como fallback para documentos em que a marcação seja texto.
MARCADOS_TEXTO = ("☒", "☑", "■", "▣", "X", "[X]", "[x]")

# Nos memoriais fornecidos, os checkboxes são formas VML. O python-docx
# não inclui essas formas em cell.text; por isso elas precisam ser lidas
# diretamente do XML interno do DOCX.
VML_RECT = "{urn:schemas-microsoft-com:vml}rect"


@dataclass(frozen=True)
class MarcacaoForma:
    x: float
    y: float
    marcada: bool


@dataclass
class MetadadosMemorialDocx:
    codigo_rota: str
    numero_linha: str = ""
    linha: str = ""
    km_ida: Decimal | None = None
    km_volta: Decimal | None = None
    turnos_ativos: list[str] = field(default_factory=list)
    horarios: dict[str, dict[str, str]] = field(default_factory=dict)
    tipo_veiculo: str | None = None
    quantidade_veiculos: int | None = None
    onibus_pcd: bool | None = None
    inicio: str = ""
    termino: str = ""

    # A ficha admite mais de uma rede marcada. Mantemos também o campo
    # singular para compatibilidade com bancos/rotas anteriores.
    redes_ensino: list[str] = field(default_factory=list)
    rede_ensino: str | None = None

    localizacao: str = ""
    areas: list[str] = field(default_factory=list)
    intermunicipal: bool | None = None
    assistente_mobilidade: bool | None = None
    assistente_nome: str = ""
    veiculo_placa: str = ""
    motorista: str = ""
    contato: str = ""
    escolas_atendidas: list[str] = field(default_factory=list)
    observacao: str = ""
    responsavel_tecnico: str = ""
    crea: str = ""
    executora: str = "Topocart"
    avisos: list[str] = field(default_factory=list)

    def tem_dados_relevantes(self) -> bool:
        return bool(
            self.numero_linha
            and self.linha
            and self.km_ida is not None
            and self.km_volta is not None
            and self.turnos_ativos
            and self.inicio
            and self.termino
        )

    def campos_preenchidos(self) -> list[str]:
        ignorar = {"codigo_rota", "avisos"}
        resultado: list[str] = []

        for campo in fields(self):
            if campo.name in ignorar:
                continue

            valor = getattr(self, campo.name)
            if valor not in (None, "", [], {}):
                resultado.append(campo.name)

        return resultado


# ==========================================
# TEXTO E NÚMEROS
# ==========================================


def texto_limpo(valor: Any) -> str:
    if valor is None:
        return ""

    texto = str(valor).replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()


def texto_sem_ponto_final(valor: Any) -> str:
    return texto_limpo(valor).rstrip(". ")


def texto_sem_acentos(valor: Any) -> str:
    texto = unicodedata.normalize("NFD", texto_limpo(valor))
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )
    return texto.upper()


def decimal_seguro(valor: Any) -> Decimal | None:
    texto = texto_limpo(valor).replace(",", ".")
    if not texto or re.fullmatch(r"[-–—]+", texto):
        return None

    correspondencia = re.search(r"\d+(?:\.\d+)?", texto)
    if not correspondencia:
        return None

    try:
        return Decimal(correspondencia.group(0))
    except (InvalidOperation, ValueError):
        return None


def linhas_celula(celula) -> str:
    linhas = [
        texto_limpo(linha)
        for linha in celula.text.splitlines()
        if texto_limpo(linha)
    ]
    return "\n".join(linhas)


def textos_unicos_linha(linha) -> list[str]:
    resultado: list[str] = []
    vistos: set[str] = set()

    for celula in linha.cells:
        texto = linhas_celula(celula)
        if texto not in vistos:
            resultado.append(texto)
            vistos.add(texto)

    return resultado


def valor_na_linha(rotulo: str, texto: str) -> str:
    padrao = rf"(?mi)^[ \t]*{rotulo}[ \t]*:[ \t]*([^\n\r]*)"
    correspondencia = re.search(padrao, texto)
    if not correspondencia:
        return ""
    return texto_limpo(correspondencia.group(1))


def valor_na_linha_ou_seguinte(rotulo: str, texto: str) -> str:
    padrao = rf"(?mi)^[ \t]*{rotulo}[ \t]*:[ \t]*([^\n\r]*)"
    correspondencia = re.search(padrao, texto)
    if not correspondencia:
        return ""

    valor = texto_limpo(correspondencia.group(1))
    if valor:
        return valor

    restante = texto[correspondencia.end():]
    for linha in restante.splitlines():
        linha = texto_limpo(linha)
        if not linha:
            continue
        if re.match(r"^[\wÀ-ÿº()/ .-]+:[ \t]*$", linha):
            return ""
        return linha

    return ""


def valor_ate_final(rotulo: str, texto: str) -> str:
    padrao = rf"(?mis)^[ \t]*{rotulo}[ \t]*:[ \t]*(.*)\Z"
    correspondencia = re.search(padrao, texto)
    if not correspondencia:
        return ""

    valor = correspondencia.group(1).replace("\n", " ")
    return texto_limpo(valor)


def normalizar_turno(valor: str) -> str:
    valor = unicodedata.normalize("NFC", valor).upper()
    return valor if valor in TURNOS else valor


# ==========================================
# CHECKBOXES EM FORMAS VML
# ==========================================


def _valor_pt(estilo: str, propriedade: str) -> float:
    correspondencia = re.search(
        rf"(?:^|;){re.escape(propriedade)}:"
        rf"([-+]?\d+(?:\.\d+)?)pt",
        estilo or "",
        flags=re.IGNORECASE,
    )
    if not correspondencia:
        return 0.0
    return float(correspondencia.group(1))


def _forma_marcada(retangulo) -> bool:
    cor = texto_limpo(retangulo.get("fillcolor")).lower()
    cor = cor.split("[")[0].strip()

    return cor in {
        "black",
        "#000000",
        "000000",
        "rgb(0,0,0)",
    }


def _marcacoes_elemento(elemento) -> list[MarcacaoForma]:
    resultado: list[MarcacaoForma] = []

    for retangulo in elemento.iter(VML_RECT):
        estilo = retangulo.get("style") or ""
        resultado.append(
            MarcacaoForma(
                x=_valor_pt(estilo, "margin-left"),
                y=_valor_pt(estilo, "margin-top"),
                marcada=_forma_marcada(retangulo),
            )
        )

    return resultado


def _marcacoes_celula(celula) -> list[MarcacaoForma]:
    return _marcacoes_elemento(celula._tc)


def _marcacoes_paragrafo(paragrafo) -> list[MarcacaoForma]:
    return _marcacoes_elemento(paragrafo._p)


def _deduplicar_por_x(
    marcacoes: Iterable[MarcacaoForma],
    tolerancia: float = 3.5,
) -> list[MarcacaoForma]:
    grupos: list[list[MarcacaoForma]] = []

    for marcacao in sorted(marcacoes, key=lambda item: item.x):
        grupo = next(
            (
                existente
                for existente in grupos
                if abs(existente[0].x - marcacao.x) <= tolerancia
            ),
            None,
        )

        if grupo is None:
            grupos.append([marcacao])
        else:
            grupo.append(marcacao)

    resultado: list[MarcacaoForma] = []

    for grupo in grupos:
        resultado.append(
            MarcacaoForma(
                x=sum(item.x for item in grupo) / len(grupo),
                y=sum(item.y for item in grupo) / len(grupo),
                marcada=any(item.marcada for item in grupo),
            )
        )

    return sorted(resultado, key=lambda item: item.x)


def _selecoes_por_formas(
    marcacoes: Iterable[MarcacaoForma],
    opcoes: tuple[str, ...],
) -> list[str]:
    formas = _deduplicar_por_x(marcacoes)

    # Nos 116 memoriais analisados as posições seguem o mesmo modelo.
    # Caso um documento futuro esteja incompleto, usamos somente as formas
    # disponíveis e registramos o aviso no chamador.
    return [
        opcao
        for opcao, forma in zip(opcoes, formas)
        if forma.marcada
    ]


def _booleano_por_formas(
    marcacoes: Iterable[MarcacaoForma],
) -> bool | None:
    formas = _deduplicar_por_x(marcacoes)
    if not formas:
        return None

    # O checkbox da esquerda representa Sim e o da direita representa Não.
    if len(formas) >= 2:
        esquerda = formas[0]
        direita = formas[-1]

        if esquerda.marcada and not direita.marcada:
            return True
        if direita.marcada and not esquerda.marcada:
            return False
        if esquerda.marcada and direita.marcada:
            # Documento inconsistente; não inventamos o valor.
            return None
        return None

    # Quando só uma forma foi preservada, a posição permite identificar
    # a opção no modelo original.
    forma = formas[0]
    if not forma.marcada:
        return None
    return forma.x < 25.0


def _opcao_marcada_texto(
    texto: str,
    opcoes: tuple[str, ...],
) -> str | None:
    for opcao in opcoes:
        padrao = (
            rf"(?:{'|'.join(map(re.escape, MARCADOS_TEXTO))})"
            rf"[ \t]*{re.escape(opcao)}"
        )
        if re.search(padrao, texto, flags=re.IGNORECASE):
            return opcao.upper()
    return None


def _booleano_marcado_texto(texto: str) -> bool | None:
    sim = _opcao_marcada_texto(texto, ("SIM",))
    nao = _opcao_marcada_texto(texto, ("NÃO", "NAO"))

    if sim:
        return True
    if nao:
        return False
    return None


def _extrair_tipo_veiculo(tabela) -> str | None:
    formas = _marcacoes_celula(tabela.rows[1].cells[1])
    selecionadas = _selecoes_por_formas(formas, TIPOS_VEICULO)
    return selecionadas[0] if selecionadas else None


def _extrair_quantidade_veiculos(tabela) -> int | None:
    marcacoes = list(_marcacoes_celula(tabela.rows[2].cells[0]))

    # Quatro das cinco formas são frequentemente ancoradas no início da
    # célula da linha seguinte com margin-top negativo.
    for marcacao in _marcacoes_celula(tabela.rows[3].cells[0]):
        if marcacao.y < -10:
            marcacoes.append(marcacao)

    formas = _deduplicar_por_x(marcacoes)

    for numero, forma in enumerate(formas[:5], start=1):
        if forma.marcada:
            return numero

    return None


def _extrair_onibus_pcd(tabela) -> bool | None:
    return _booleano_por_formas(
        _marcacoes_celula(tabela.rows[2].cells[1])
    )


def _extrair_redes_ensino(tabela) -> list[str]:
    return _selecoes_por_formas(
        _marcacoes_celula(tabela.rows[3].cells[1]),
        REDES_ENSINO,
    )


def _extrair_areas(tabela) -> list[str]:
    celula = tabela.rows[4].cells[0]
    marcacoes: list[MarcacaoForma] = []
    dentro_area = False

    for paragrafo in celula.paragraphs:
        texto = texto_sem_acentos(paragrafo.text)

        if "AREA URBANA/AREA RURAL" in texto:
            dentro_area = True
            continue

        if "INTERMUNICIPAL" in texto:
            break

        if dentro_area:
            marcacoes.extend(_marcacoes_paragrafo(paragrafo))

    return _selecoes_por_formas(marcacoes, AREAS)


def _extrair_intermunicipal(tabela) -> bool | None:
    celula = tabela.rows[4].cells[0]
    marcacoes_area_ids: set[tuple[float, float, bool]] = set()
    marcacoes_candidatas: list[MarcacaoForma] = []
    dentro_area = False
    depois_intermunicipal = False

    for paragrafo in celula.paragraphs:
        texto = texto_sem_acentos(paragrafo.text)
        formas = _marcacoes_paragrafo(paragrafo)

        if "AREA URBANA/AREA RURAL" in texto:
            dentro_area = True
            continue

        if "INTERMUNICIPAL" in texto:
            dentro_area = False
            depois_intermunicipal = True
            continue

        if dentro_area:
            for forma in formas:
                marcacoes_area_ids.add((forma.x, forma.y, forma.marcada))
            continue

        # Algumas formas do campo Intermunicipal ficaram ancoradas em um
        # parágrafo anterior da mesma célula. Mantemos as posições típicas.
        if depois_intermunicipal or formas:
            marcacoes_candidatas.extend(formas)

    # Em parte dos DOCX, uma forma está ancorada na primeira célula com
    # margin-top muito grande, embora seja exibida no campo Intermunicipal.
    for forma in _marcacoes_celula(tabela.rows[0].cells[0]):
        if forma.y > 300 and -10 <= forma.x <= 65:
            marcacoes_candidatas.append(forma)

    # Em outros documentos, a segunda forma está ancorada na linha seguinte
    # com margin-top negativo.
    for forma in _marcacoes_celula(tabela.rows[5].cells[0]):
        if forma.y < -10 and -10 <= forma.x <= 65:
            marcacoes_candidatas.append(forma)

    filtradas = [
        forma
        for forma in marcacoes_candidatas
        if -10 <= forma.x <= 65
        and (forma.x, forma.y, forma.marcada) not in marcacoes_area_ids
    ]

    return _booleano_por_formas(filtradas)


def _extrair_assistente_mobilidade(tabela) -> bool | None:
    celula = tabela.rows[4].cells[1]
    marcacoes: list[MarcacaoForma] = []

    for paragrafo in celula.paragraphs:
        texto = texto_limpo(paragrafo.text)
        if re.match(r"^1\.", texto):
            break
        marcacoes.extend(_marcacoes_paragrafo(paragrafo))

    return _booleano_por_formas(marcacoes)


# ==========================================
# CAMPOS TEXTUAIS
# ==========================================


def codigo_do_nome(caminho_docx: Path) -> str:
    nome = caminho_docx.stem
    if nome.lower().startswith("memorial_"):
        return nome[len("Memorial_"):]
    return nome


def extrair_quilometragem(
    texto: str,
) -> tuple[list[str], Decimal | None, Decimal | None]:
    ativos: list[str] = []
    pares: list[tuple[str, Decimal | None, Decimal | None]] = []

    for linha in texto.splitlines():
        correspondencia = re.search(
            r"(Manhã|Tarde|Noite|Integral)\s+(.*)$",
            linha,
            flags=re.IGNORECASE,
        )
        if not correspondencia:
            continue

        turno = normalizar_turno(correspondencia.group(1))
        valores = re.findall(
            r"(?:\d+(?:[.,]\d+)?|[-–—])",
            correspondencia.group(2),
        )

        ida = decimal_seguro(valores[0]) if len(valores) >= 1 else None
        volta = decimal_seguro(valores[1]) if len(valores) >= 2 else None

        if ida is not None or volta is not None:
            ativos.append(turno)
            pares.append((turno, ida, volta))

    km_ida = next(
        (ida for _, ida, _ in pares if ida is not None),
        None,
    )
    km_volta = next(
        (volta for _, _, volta in pares if volta is not None),
        None,
    )

    return ativos, km_ida, km_volta


def extrair_horarios(texto: str) -> dict[str, dict[str, str]]:
    horarios: dict[str, dict[str, str]] = {}

    for linha in texto.splitlines():
        correspondencia = re.search(
            r"(Manhã|Tarde|Noite|Integral)\s+(.*)$",
            linha,
            flags=re.IGNORECASE,
        )
        if not correspondencia:
            continue

        turno = normalizar_turno(correspondencia.group(1))
        horas = re.findall(r"\b\d{1,2}:\d{2}\b", correspondencia.group(2))

        if horas:
            horarios[turno] = {
                "horario": "",
                "inicio_aulas": horas[0],
                "termino_aulas": horas[1] if len(horas) >= 2 else "",
            }

    return horarios


def extrair_escolas(texto: str) -> list[str]:
    valor = valor_ate_final(r"Escola\(s\) Atendidas", texto)
    if not valor:
        return []

    escolas: list[str] = []
    vistos: set[str] = set()

    for escola in valor.split("/"):
        escola = texto_sem_ponto_final(escola)
        chave = escola.casefold()
        if escola and chave not in vistos:
            escolas.append(escola)
            vistos.add(chave)

    return escolas


# ==========================================
# EXTRAÇÃO PRINCIPAL
# ==========================================


def extrair_metadados_docx(
    caminho_docx: Path,
    codigo_rota: str | None = None,
) -> MetadadosMemorialDocx:
    documento = Document(caminho_docx)

    if not documento.tables:
        raise ValueError("O DOCX não possui a tabela principal do memorial.")

    tabela = documento.tables[0]

    if len(tabela.rows) < 9:
        raise ValueError(
            "A tabela principal não possui a estrutura esperada do memorial."
        )

    linhas = [textos_unicos_linha(linha) for linha in tabela.rows]
    texto_completo = "\n".join("\n".join(linha) for linha in linhas)

    dados = MetadadosMemorialDocx(
        codigo_rota=codigo_rota or codigo_do_nome(caminho_docx),
    )

    linha_0 = linhas[0][0] if linhas and linhas[0] else ""
    dados.numero_linha = valor_na_linha("Número da Linha", linha_0)
    dados.linha = texto_sem_ponto_final(valor_na_linha("Linha", linha_0))

    linha_1_esquerda = linhas[1][0] if len(linhas) > 1 and linhas[1] else ""
    (
        dados.turnos_ativos,
        dados.km_ida,
        dados.km_volta,
    ) = extrair_quilometragem(linha_1_esquerda)

    # Campos representados por formas, invisíveis em cell.text.
    dados.tipo_veiculo = _extrair_tipo_veiculo(tabela)
    dados.quantidade_veiculos = _extrair_quantidade_veiculos(tabela)
    dados.onibus_pcd = _extrair_onibus_pcd(tabela)
    dados.redes_ensino = _extrair_redes_ensino(tabela)
    dados.rede_ensino = (
        dados.redes_ensino[0]
        if dados.redes_ensino
        else None
    )
    dados.areas = _extrair_areas(tabela)
    dados.intermunicipal = _extrair_intermunicipal(tabela)
    dados.assistente_mobilidade = _extrair_assistente_mobilidade(tabela)

    if len(linhas) > 3 and linhas[3]:
        dados.inicio = texto_sem_ponto_final(
            valor_na_linha("Início", linhas[3][0])
        )
        dados.termino = texto_sem_ponto_final(
            valor_na_linha("Término", linhas[3][0])
        )

    if len(linhas) > 4 and linhas[4]:
        texto_localizacao = linhas[4][0]
        dados.localizacao = valor_na_linha_ou_seguinte(
            "Localização",
            texto_localizacao,
        )

        if len(linhas[4]) > 1:
            texto_assistente = linhas[4][1]
            dados.assistente_nome = valor_na_linha("Nome", texto_assistente)

    if len(linhas) > 5 and linhas[5]:
        dados.veiculo_placa = valor_na_linha(
            r"Nº do Veículo / Placa",
            linhas[5][0],
        )

        if len(linhas[5]) > 1:
            dados.motorista = valor_na_linha("Motorista", linhas[5][1])
            dados.contato = valor_na_linha("Contato", linhas[5][1])

    if len(linhas) > 6 and linhas[6]:
        dados.escolas_atendidas = extrair_escolas(linhas[6][0])

    if len(linhas) > 7 and linhas[7]:
        dados.horarios = extrair_horarios(linhas[7][0])

    if len(linhas) > 8 and linhas[8]:
        dados.observacao = valor_ate_final("Observação", linhas[8][0])

    responsavel = re.search(
        r"RESPONSÁVEL TÉCNICO(?:\s+ENGENHEIRO AGRIMENSOR)?\s*:\s*"
        r"(.*?)\s+(?:CREA|Registro Profissional)\s*:",
        texto_completo,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if responsavel:
        dados.responsavel_tecnico = texto_limpo(responsavel.group(1))

    registro = re.search(
        r"(?:CREA|Registro Profissional)\s*:\s*([^\n|]+)",
        texto_completo,
        flags=re.IGNORECASE,
    )
    if registro:
        dados.crea = texto_limpo(registro.group(1))

    obrigatorios = {
        "numero_linha": dados.numero_linha,
        "linha": dados.linha,
        "km_ida": dados.km_ida,
        "km_volta": dados.km_volta,
        "turnos_ativos": dados.turnos_ativos,
        "inicio": dados.inicio,
        "termino": dados.termino,
        "localizacao": dados.localizacao,
        "escolas_atendidas": dados.escolas_atendidas,
        "responsavel_tecnico": dados.responsavel_tecnico,
        "crea": dados.crea,
        "tipo_veiculo": dados.tipo_veiculo,
        "quantidade_veiculos": dados.quantidade_veiculos,
        "onibus_pcd": dados.onibus_pcd,
        "redes_ensino": dados.redes_ensino,
        "areas": dados.areas,
        "assistente_mobilidade": dados.assistente_mobilidade,
    }

    for nome, valor in obrigatorios.items():
        if valor in (None, "", [], {}):
            dados.avisos.append(f"Campo não identificado: {nome}.")

    if dados.intermunicipal is None:
        dados.avisos.append(
            "Intermunicipal sem marcação recuperável no DOCX; "
            "o valor existente no banco será preservado."
        )

    return dados
