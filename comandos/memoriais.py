# ==========================================
# COMANDOS DE MEMORIAIS EM LOTE
# ==========================================

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import click
from flask import Flask, current_app
from sqlalchemy import text
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from models import db
from routes.memorial import (
    buscar_dados_memorial,
    buscar_pontos_normalizados,
    buscar_trechos,
    gerar_pdf_memorial,
    montar_contexto,
    texto_limpo,
)
from servicos.memoriais_docx import (
    MetadadosMemorialDocx,
    extrair_metadados_docx,
)


SQL_ROTA_POR_CODIGO = text(
    """
    SELECT id, nome_rota, regiao
    FROM semed.rotas_geral
    WHERE LOWER(BTRIM(nome_rota)) = LOWER(BTRIM(:codigo_rota))
    ORDER BY
        CASE UPPER(TRIM(trecho))
            WHEN 'IDA' THEN 1
            WHEN 'VOLTA' THEN 2
            ELSE 3
        END,
        id
    LIMIT 1
    """
)

SQL_TODAS_ROTAS = text(
    """
    SELECT DISTINCT ON (LOWER(BTRIM(nome_rota)))
        id,
        nome_rota,
        regiao
    FROM semed.rotas_geral
    WHERE nome_rota IS NOT NULL
      AND BTRIM(nome_rota) <> ''
    ORDER BY
        LOWER(BTRIM(nome_rota)),
        CASE UPPER(TRIM(trecho))
            WHEN 'IDA' THEN 1
            WHEN 'VOLTA' THEN 2
            ELSE 3
        END,
        id
    """
)

SQL_METADATA_EXISTE = text(
    """
    SELECT id
    FROM semed.rotas_memoriais
    WHERE LOWER(BTRIM(codigo_rota)) = LOWER(BTRIM(:codigo_rota))
    LIMIT 1
    """
)

COLUNAS_METADATA = (
    "codigo_rota",
    "numero_linha",
    "linha",
    "km_ida",
    "km_volta",
    "turnos_ativos",
    "horarios",
    "tipo_veiculo",
    "quantidade_veiculos",
    "onibus_pcd",
    "inicio",
    "termino",
    "rede_ensino",
    "redes_ensino",
    "localizacao",
    "areas",
    "intermunicipal",
    "assistente_mobilidade",
    "assistente_nome",
    "veiculo_placa",
    "motorista",
    "contato",
    "escolas_atendidas",
    "observacao",
    "responsavel_tecnico",
    "crea",
    "executora",
)

SQL_UPSERT_METADATA_SOBRESCREVENDO = text(
    """
    INSERT INTO semed.rotas_memoriais (
        codigo_rota, numero_linha, linha, km_ida, km_volta,
        turnos_ativos, horarios, tipo_veiculo, quantidade_veiculos,
        onibus_pcd, inicio, termino, rede_ensino, redes_ensino, localizacao, areas,
        intermunicipal, assistente_mobilidade, assistente_nome,
        veiculo_placa, motorista, contato, escolas_atendidas,
        observacao, responsavel_tecnico, crea, executora
    ) VALUES (
        :codigo_rota, :numero_linha, :linha, :km_ida, :km_volta,
        CAST(:turnos_ativos AS jsonb), CAST(:horarios AS jsonb),
        :tipo_veiculo, :quantidade_veiculos, :onibus_pcd,
        :inicio, :termino, :rede_ensino, CAST(:redes_ensino AS jsonb), :localizacao,
        CAST(:areas AS jsonb), :intermunicipal,
        :assistente_mobilidade, :assistente_nome,
        :veiculo_placa, :motorista, :contato,
        CAST(:escolas_atendidas AS jsonb), :observacao,
        :responsavel_tecnico, :crea, :executora
    )
    ON CONFLICT (codigo_rota)
    DO UPDATE SET
        numero_linha = EXCLUDED.numero_linha,
        linha = EXCLUDED.linha,
        km_ida = EXCLUDED.km_ida,
        km_volta = EXCLUDED.km_volta,
        turnos_ativos = EXCLUDED.turnos_ativos,
        horarios = EXCLUDED.horarios,
        tipo_veiculo = EXCLUDED.tipo_veiculo,
        quantidade_veiculos = EXCLUDED.quantidade_veiculos,
        onibus_pcd = EXCLUDED.onibus_pcd,
        inicio = EXCLUDED.inicio,
        termino = EXCLUDED.termino,
        rede_ensino = EXCLUDED.rede_ensino,
        redes_ensino = EXCLUDED.redes_ensino,
        localizacao = EXCLUDED.localizacao,
        areas = EXCLUDED.areas,
        intermunicipal = EXCLUDED.intermunicipal,
        assistente_mobilidade = EXCLUDED.assistente_mobilidade,
        assistente_nome = EXCLUDED.assistente_nome,
        veiculo_placa = EXCLUDED.veiculo_placa,
        motorista = EXCLUDED.motorista,
        contato = EXCLUDED.contato,
        escolas_atendidas = EXCLUDED.escolas_atendidas,
        observacao = EXCLUDED.observacao,
        responsavel_tecnico = EXCLUDED.responsavel_tecnico,
        crea = EXCLUDED.crea,
        executora = EXCLUDED.executora,
        atualizado_em = NOW()
    """
)

SQL_UPSERT_METADATA_PRESERVANDO = text(
    """
    INSERT INTO semed.rotas_memoriais (
        codigo_rota, numero_linha, linha, km_ida, km_volta,
        turnos_ativos, horarios, tipo_veiculo, quantidade_veiculos,
        onibus_pcd, inicio, termino, rede_ensino, redes_ensino, localizacao, areas,
        intermunicipal, assistente_mobilidade, assistente_nome,
        veiculo_placa, motorista, contato, escolas_atendidas,
        observacao, responsavel_tecnico, crea, executora
    ) VALUES (
        :codigo_rota, :numero_linha, :linha, :km_ida, :km_volta,
        CAST(:turnos_ativos AS jsonb), CAST(:horarios AS jsonb),
        :tipo_veiculo, :quantidade_veiculos, :onibus_pcd,
        :inicio, :termino, :rede_ensino, CAST(:redes_ensino AS jsonb), :localizacao,
        CAST(:areas AS jsonb), :intermunicipal,
        :assistente_mobilidade, :assistente_nome,
        :veiculo_placa, :motorista, :contato,
        CAST(:escolas_atendidas AS jsonb), :observacao,
        :responsavel_tecnico, :crea, :executora
    )
    ON CONFLICT (codigo_rota)
    DO UPDATE SET
        numero_linha = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.numero_linha), ''), EXCLUDED.numero_linha),
        linha = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.linha), ''), EXCLUDED.linha),
        km_ida = COALESCE(semed.rotas_memoriais.km_ida, EXCLUDED.km_ida),
        km_volta = COALESCE(semed.rotas_memoriais.km_volta, EXCLUDED.km_volta),
        turnos_ativos = CASE WHEN semed.rotas_memoriais.turnos_ativos = '[]'::jsonb THEN EXCLUDED.turnos_ativos ELSE semed.rotas_memoriais.turnos_ativos END,
        horarios = CASE WHEN semed.rotas_memoriais.horarios = '{}'::jsonb THEN EXCLUDED.horarios ELSE semed.rotas_memoriais.horarios END,
        tipo_veiculo = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.tipo_veiculo), ''), EXCLUDED.tipo_veiculo),
        quantidade_veiculos = COALESCE(semed.rotas_memoriais.quantidade_veiculos, EXCLUDED.quantidade_veiculos),
        onibus_pcd = EXCLUDED.onibus_pcd,
        inicio = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.inicio), ''), EXCLUDED.inicio),
        termino = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.termino), ''), EXCLUDED.termino),
        rede_ensino = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.rede_ensino), ''), EXCLUDED.rede_ensino),
        redes_ensino = CASE WHEN semed.rotas_memoriais.redes_ensino = '[]'::jsonb THEN EXCLUDED.redes_ensino ELSE semed.rotas_memoriais.redes_ensino END,
        localizacao = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.localizacao), ''), EXCLUDED.localizacao),
        areas = CASE WHEN semed.rotas_memoriais.areas = '[]'::jsonb THEN EXCLUDED.areas ELSE semed.rotas_memoriais.areas END,
        intermunicipal = EXCLUDED.intermunicipal,
        assistente_mobilidade = EXCLUDED.assistente_mobilidade,
        assistente_nome = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.assistente_nome), ''), EXCLUDED.assistente_nome),
        veiculo_placa = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.veiculo_placa), ''), EXCLUDED.veiculo_placa),
        motorista = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.motorista), ''), EXCLUDED.motorista),
        contato = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.contato), ''), EXCLUDED.contato),
        escolas_atendidas = CASE WHEN semed.rotas_memoriais.escolas_atendidas = '[]'::jsonb THEN EXCLUDED.escolas_atendidas ELSE semed.rotas_memoriais.escolas_atendidas END,
        observacao = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.observacao), ''), EXCLUDED.observacao),
        responsavel_tecnico = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.responsavel_tecnico), ''), EXCLUDED.responsavel_tecnico),
        crea = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.crea), ''), EXCLUDED.crea),
        executora = COALESCE(NULLIF(BTRIM(semed.rotas_memoriais.executora), ''), EXCLUDED.executora),
        atualizado_em = NOW()
    """
)

PADRAO_NUMERO_REGIAO = re.compile(r"\d+")
EXTENSOES_LEGADAS = {".docx", ".doc", ".pdf"}


@dataclass(frozen=True)
class RotaLote:
    codigo: str
    rota_id: int
    regiao: str
    pasta_relativa: Path
    arquivo_legado: Path | None = None


@dataclass
class ResultadoGeracao:
    codigo: str
    regiao: str
    status: str
    arquivo: str = ""
    mensagem: str = ""
    bytes_pdf: int = 0


@dataclass
class ResultadoImportacao:
    codigo: str
    regiao: str
    status: str
    arquivo: str = ""
    campos: str = ""
    avisos: str = ""
    mensagem: str = ""


def normalizar_codigo_rota(valor: str) -> str:
    texto = texto_limpo(valor)
    if texto.lower().startswith("memorial_"):
        texto = texto[len("Memorial_"):]
    return texto


def normalizar_regiao(valor: object) -> str:
    correspondencia = PADRAO_NUMERO_REGIAO.search(texto_limpo(valor))
    return correspondencia.group(0).zfill(2) if correspondencia else "SEM_REGIAO"


def pasta_regiao_padrao(regiao: str) -> str:
    return f"REGIÃO {normalizar_regiao(regiao)} OK"


def descobrir_codigo_no_arquivo(caminho: Path) -> str:
    nome = caminho.stem
    if nome.lower().startswith("memorial_"):
        return nome[len("Memorial_"):]
    return normalizar_codigo_rota(nome)


def arquivo_temporario(caminho: Path) -> bool:
    nome = caminho.name.lower()
    return nome.startswith("~$") or nome.startswith(".~lock") or nome.endswith(".tmp")


def listar_arquivos_legados(origem: Path) -> list[Path]:
    return sorted(
        caminho
        for caminho in origem.rglob("*")
        if caminho.is_file()
        and caminho.suffix.lower() in EXTENSOES_LEGADAS
        and not arquivo_temporario(caminho)
    )


def listar_docx(origem: Path) -> list[Path]:
    return sorted(
        caminho
        for caminho in origem.rglob("*.docx")
        if caminho.is_file() and not arquivo_temporario(caminho)
    )


def buscar_rota_por_codigo(codigo: str):
    return (
        db.session.execute(SQL_ROTA_POR_CODIGO, {"codigo_rota": codigo})
        .mappings()
        .first()
    )


def metadata_existe(codigo: str) -> bool:
    return (
        db.session.execute(SQL_METADATA_EXISTE, {"codigo_rota": codigo})
        .scalar_one_or_none()
        is not None
    )


def parametros_metadata(dados: MetadadosMemorialDocx) -> dict[str, object]:
    return {
        "codigo_rota": dados.codigo_rota,
        "numero_linha": dados.numero_linha or None,
        "linha": dados.linha or None,
        "km_ida": dados.km_ida,
        "km_volta": dados.km_volta,
        "turnos_ativos": json.dumps(dados.turnos_ativos, ensure_ascii=False),
        "horarios": json.dumps(dados.horarios, ensure_ascii=False),
        "tipo_veiculo": dados.tipo_veiculo,
        "quantidade_veiculos": dados.quantidade_veiculos,
        "onibus_pcd": bool(dados.onibus_pcd) if dados.onibus_pcd is not None else False,
        "inicio": dados.inicio or None,
        "termino": dados.termino or None,
        "rede_ensino": dados.rede_ensino,
        "redes_ensino": json.dumps(dados.redes_ensino, ensure_ascii=False),
        "localizacao": dados.localizacao or None,
        "areas": json.dumps(dados.areas, ensure_ascii=False),
        "intermunicipal": bool(dados.intermunicipal) if dados.intermunicipal is not None else False,
        "assistente_mobilidade": bool(dados.assistente_mobilidade) if dados.assistente_mobilidade is not None else False,
        "assistente_nome": dados.assistente_nome or None,
        "veiculo_placa": dados.veiculo_placa or None,
        "motorista": dados.motorista or None,
        "contato": dados.contato or None,
        "escolas_atendidas": json.dumps(dados.escolas_atendidas, ensure_ascii=False),
        "observacao": dados.observacao or None,
        "responsavel_tecnico": dados.responsavel_tecnico or None,
        "crea": dados.crea or None,
        "executora": dados.executora or None,
    }


def salvar_metadata(dados: MetadadosMemorialDocx, sobrescrever: bool) -> str:
    existente = metadata_existe(dados.codigo_rota)
    consulta = SQL_UPSERT_METADATA_SOBRESCREVENDO if sobrescrever else SQL_UPSERT_METADATA_PRESERVANDO
    db.session.execute(consulta, parametros_metadata(dados))
    db.session.commit()
    return "ATUALIZADO" if existente else "INSERIDO"


def listar_rotas_do_banco() -> list[RotaLote]:
    registros = db.session.execute(SQL_TODAS_ROTAS).mappings().all()
    return [
        RotaLote(
            codigo=texto_limpo(registro.get("nome_rota")),
            rota_id=int(registro["id"]),
            regiao=normalizar_regiao(registro.get("regiao")),
            pasta_relativa=Path(pasta_regiao_padrao(registro.get("regiao"))),
        )
        for registro in registros
    ]


def listar_rotas_da_arvore_legada(origem: Path):
    rotas: list[RotaLote] = []
    problemas: list[ResultadoGeracao] = []
    codigos: set[str] = set()

    for arquivo in listar_arquivos_legados(origem):
        codigo = descobrir_codigo_no_arquivo(arquivo)
        if not codigo:
            problemas.append(ResultadoGeracao("", "", "IGNORADO", str(arquivo), "Código não identificado."))
            continue
        if codigo.casefold() in codigos:
            continue

        registro = buscar_rota_por_codigo(codigo)
        if not registro:
            problemas.append(ResultadoGeracao(codigo, "", "NÃO_ENCONTRADA", str(arquivo), "A rota não existe em semed.rotas_geral."))
            continue

        regiao = normalizar_regiao(registro.get("regiao"))
        try:
            pasta = arquivo.parent.relative_to(origem)
        except ValueError:
            pasta = Path(pasta_regiao_padrao(regiao))

        rotas.append(RotaLote(codigo, int(registro["id"]), regiao, pasta, arquivo))
        codigos.add(codigo.casefold())

    return rotas, problemas


def contexto_da_rota(rota: RotaLote):
    registros = buscar_trechos(rota.rota_id)
    if not registros:
        raise RuntimeError("Rota não encontrada no banco de dados.")
    codigo = texto_limpo(registros[0].get("nome_rota"))
    return montar_contexto(
        registros,
        buscar_dados_memorial(codigo),
        buscar_pontos_normalizados(codigo),
    )


def salvar_buffer_pdf(buffer_pdf, destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    buffer_pdf.seek(0)
    with temporario.open("wb") as arquivo:
        while bloco := buffer_pdf.read(1024 * 1024):
            arquivo.write(bloco)
    temporario.replace(destino)
    return destino.stat().st_size


def escrever_csv(caminho: Path, campos: list[str], linhas: list[dict]) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)
    return caminho


def relatorio_importacao(destino: Path, resultados: list[ResultadoImportacao]) -> Path:
    agora = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = destino / f"relatorio_importacao_metadados_{agora}.csv"
    return escrever_csv(caminho, ["codigo_rota", "regiao", "status", "arquivo", "campos", "avisos", "mensagem"], [
        {
            "codigo_rota": item.codigo,
            "regiao": item.regiao,
            "status": item.status,
            "arquivo": item.arquivo,
            "campos": item.campos,
            "avisos": item.avisos,
            "mensagem": item.mensagem,
        }
        for item in resultados
    ])


def relatorio_geracao(destino: Path, resultados: list[ResultadoGeracao]) -> Path:
    agora = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho = destino / f"relatorio_memoriais_{agora}.csv"
    return escrever_csv(caminho, ["codigo_rota", "regiao", "status", "arquivo", "bytes_pdf", "mensagem"], [
        {
            "codigo_rota": item.codigo,
            "regiao": item.regiao,
            "status": item.status,
            "arquivo": item.arquivo,
            "bytes_pdf": item.bytes_pdf,
            "mensagem": item.mensagem,
        }
        for item in resultados
    ])


def registrar_comandos_memoriais(app: Flask) -> None:
    @app.cli.command("importar-metadados-memoriais")
    @click.option("--origem", type=click.Path(path_type=Path, file_okay=False), default=Path("scripts/pdf"), show_default=True)
    @click.option("--relatorios", type=click.Path(path_type=Path, file_okay=False), default=Path("scripts/pdf_gerados"), show_default=True)
    @click.option("--regiao", default=None)
    @click.option("--rota", default=None)
    @click.option("--sobrescrever", is_flag=True)
    @click.option("--somente-validar", is_flag=True)
    @click.option("--parar-no-erro", is_flag=True)
    def importar_metadados_memoriais(origem, relatorios, regiao, rota, sobrescrever, somente_validar, parar_no_erro):
        """Importa todos os metadados dos DOCX para semed.rotas_memoriais."""
        raiz = Path(current_app.root_path).resolve()
        origem = origem if origem.is_absolute() else (raiz / origem).resolve()
        relatorios = relatorios if relatorios.is_absolute() else (raiz / relatorios).resolve()
        if not origem.exists():
            raise click.ClickException(f"A pasta de origem não existe: {origem}")

        arquivos = listar_docx(origem)
        filtro_regiao = normalizar_regiao(regiao) if regiao else None
        filtro_rota = normalizar_codigo_rota(rota) if rota else None
        resultados: list[ResultadoImportacao] = []

        click.echo(f"\nDOCX encontrados: {len(arquivos)}")
        for indice, arquivo in enumerate(arquivos, start=1):
            codigo = descobrir_codigo_no_arquivo(arquivo)
            if filtro_rota and codigo.casefold() != filtro_rota.casefold():
                continue

            registro = buscar_rota_por_codigo(codigo)
            regiao_banco = normalizar_regiao(registro.get("regiao") if registro else "")
            if filtro_regiao and regiao_banco != filtro_regiao:
                continue

            click.echo(f"[{indice}/{len(arquivos)}] {codigo}")
            if not registro:
                resultados.append(ResultadoImportacao(codigo, "", "NÃO_ENCONTRADA", str(arquivo), mensagem="A rota não existe em semed.rotas_geral."))
                click.echo("  não encontrada", err=True)
                if parar_no_erro:
                    break
                continue

            try:
                dados = extrair_metadados_docx(arquivo, codigo)
                if not dados.tem_dados_relevantes():
                    status = "SEM_DADOS"
                elif somente_validar:
                    status = "VALIDADO"
                else:
                    status = salvar_metadata(dados, sobrescrever)

                resultados.append(ResultadoImportacao(
                    codigo, regiao_banco, status, str(arquivo),
                    ", ".join(dados.campos_preenchidos()),
                    " | ".join(dados.avisos),
                ))
                click.echo(f"  {status.lower()}")
            except Exception as erro:
                db.session.rollback()
                resultados.append(ResultadoImportacao(codigo, regiao_banco, "ERRO", str(arquivo), mensagem=str(erro)))
                current_app.logger.exception("Erro ao importar %s.", codigo)
                click.echo(f"  erro: {erro}", err=True)
                if parar_no_erro:
                    break

        caminho = relatorio_importacao(relatorios, resultados)
        click.echo(f"\nRelatório: {caminho}")
        pendencias = sum(item.status in {"NÃO_ENCONTRADA", "SEM_DADOS", "ERRO"} for item in resultados)
        if pendencias:
            raise click.ClickException("A importação terminou com pendências.")

    @app.cli.command("gerar-memoriais")
    @click.option("--origem", type=click.Path(path_type=Path, file_okay=False), default=None)
    @click.option("--destino", type=click.Path(path_type=Path, file_okay=False), default=Path("scripts/pdf_gerados"), show_default=True)
    @click.option("--regiao", default=None)
    @click.option("--rota", default=None)
    @click.option("--sobrescrever", is_flag=True)
    @click.option("--exigir-metadados", is_flag=True)
    @click.option("--parar-no-erro", is_flag=True)
    def gerar_memoriais(origem, destino, regiao, rota, sobrescrever, exigir_metadados, parar_no_erro):
        """Gera todos os memoriais, deixando os mapas nas páginas finais."""
        raiz = Path(current_app.root_path).resolve()
        if origem is not None and not origem.is_absolute():
            origem = (raiz / origem).resolve()
        destino = destino if destino.is_absolute() else (raiz / destino).resolve()

        if origem is not None:
            if not origem.exists():
                raise click.ClickException(f"A pasta de origem não existe: {origem}")
            rotas, resultados = listar_rotas_da_arvore_legada(origem)
        else:
            rotas, resultados = listar_rotas_do_banco(), []

        if regiao:
            filtro = normalizar_regiao(regiao)
            rotas = [item for item in rotas if item.regiao == filtro]
        if rota:
            filtro = normalizar_codigo_rota(rota).casefold()
            rotas = [item for item in rotas if item.codigo.casefold() == filtro]

        if not rotas:
            caminho = relatorio_geracao(destino, resultados)
            raise click.ClickException(f"Nenhuma rota localizada. Relatório: {caminho}")

        assets = Path(current_app.static_folder) / "img" / "memorial"
        click.echo(f"\nRotas selecionadas: {len(rotas)}")

        for indice, item in enumerate(rotas, start=1):
            arquivo_saida = destino / item.pasta_relativa / secure_filename(f"Memorial_{item.codigo}.pdf")
            click.echo(f"[{indice}/{len(rotas)}] {item.codigo}")
            if arquivo_saida.exists() and not sobrescrever:
                resultados.append(ResultadoGeracao(item.codigo, item.regiao, "PULADO", str(arquivo_saida), "O PDF já existe.", arquivo_saida.stat().st_size))
                continue

            try:
                contexto = contexto_da_rota(item)
                if exigir_metadados and not contexto.get("tem_metadata"):
                    raise RuntimeError("Não há registro em semed.rotas_memoriais.")
                tamanho = salvar_buffer_pdf(gerar_pdf_memorial(contexto, assets), arquivo_saida)
                resultados.append(ResultadoGeracao(item.codigo, item.regiao, "GERADO", str(arquivo_saida), bytes_pdf=tamanho))
                click.echo(f"  gerado: {arquivo_saida}")
            except HTTPException as erro:
                db.session.rollback()
                mensagem = texto_limpo(erro.description, str(erro))
                resultados.append(ResultadoGeracao(item.codigo, item.regiao, "ERRO", str(arquivo_saida), mensagem))
                click.echo(f"  erro: {mensagem}", err=True)
                if parar_no_erro:
                    break
            except Exception as erro:
                db.session.rollback()
                resultados.append(ResultadoGeracao(item.codigo, item.regiao, "ERRO", str(arquivo_saida), str(erro)))
                current_app.logger.exception("Erro ao gerar %s.", item.codigo)
                click.echo(f"  erro: {erro}", err=True)
                if parar_no_erro:
                    break

        caminho = relatorio_geracao(destino, resultados)
        gerados = sum(item.status == "GERADO" for item in resultados)
        erros = sum(item.status in {"ERRO", "NÃO_ENCONTRADA"} for item in resultados)
        click.echo(f"\nGerados: {gerados}")
        click.echo(f"Erros/pendências: {erros}")
        click.echo(f"Relatório: {caminho}")
        if erros:
            raise click.ClickException("O lote terminou com pendências.")
