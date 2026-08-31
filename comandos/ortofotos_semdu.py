from __future__ import annotations

from pathlib import Path

import click

from servicos.ortofotos_semdu import (
    ORTOFOTOS,
    diagnostico_ortofotos,
    preparar_cog,
)


def _configuracoes_escolhidas(
    resolucao: str,
):
    if resolucao == "15cm":
        return [ORTOFOTOS["satelite_15cm"]]

    if resolucao == "8cm":
        return [ORTOFOTOS["ortofoto_8cm"]]

    return list(
        ORTOFOTOS.values()
    )


def registrar_comandos_ortofotos_semdu(
    app,
) -> None:
    @app.cli.command(
        "diagnosticar-ortofotos-semdu"
    )
    def diagnosticar_ortofotos_semdu():
        """Mostra dependências e disponibilidade das ortofotos."""
        dados = diagnostico_ortofotos()

        click.echo(
            "\nDiagnóstico das ortofotos SEMDU\n"
        )
        click.echo(
            f"Rasterio: {dados['rasterio'] or 'não instalado'}"
        )
        click.echo(
            f"rio-tiler: {dados['rio_tiler'] or 'não instalado'}"
        )
        click.echo(
            "Driver ECW no Python: "
            + (
                "SIM"
                if dados["driver_ecw_no_python"]
                else "NÃO"
            )
        )
        click.echo(
            f"gdalwarp: {dados['gdalwarp'] or 'não localizado'}"
        )

        if dados["rasterio_erro"]:
            click.echo(
                "Erro Rasterio: "
                + dados["rasterio_erro"]
            )

        if dados["rio_tiler_erro"]:
            click.echo(
                "Erro rio-tiler: "
                + dados["rio_tiler_erro"]
            )

        click.echo("")

        for item in dados["ortofotos"]:
            situacao = (
                "DISPONÍVEL"
                if item["disponivel"]
                else "INDISPONÍVEL"
            )
            click.echo(
                f"[{situacao}] {item['titulo']}"
            )
            click.echo(
                f"  Resolução: {item['resolucao']}"
            )
            click.echo(
                "  Origem encontrada: "
                + (
                    "SIM"
                    if item["origem_encontrada"]
                    else "NÃO"
                )
            )
            click.echo(
                "  COG encontrado: "
                + (
                    "SIM"
                    if item["cog_encontrado"]
                    else "NÃO"
                )
            )
            click.echo(
                f"  Publicação: {item['modo_publicacao']}"
            )

            if item["motivo"]:
                click.echo(
                    f"  Observação: {item['motivo']}"
                )

            click.echo("")

    @app.cli.command(
        "preparar-ortofotos-semdu"
    )
    @click.option(
        "--resolucao",
        type=click.Choice(
            [
                "15cm",
                "8cm",
                "todas",
            ],
            case_sensitive=False,
        ),
        default="todas",
        show_default=True,
        help="Ortofoto que será convertida para publicação.",
    )
    @click.option(
        "--gdalwarp",
        type=click.Path(
            path_type=Path,
            dir_okay=False,
        ),
        default=None,
        help="Caminho completo de gdalwarp.exe.",
    )
    @click.option(
        "--origem-15cm",
        type=click.Path(
            path_type=Path,
            dir_okay=False,
        ),
        default=None,
        help="Substitui o caminho padrão do ECW de 15 cm.",
    )
    @click.option(
        "--origem-8cm",
        type=click.Path(
            path_type=Path,
            dir_okay=False,
        ),
        default=None,
        help="Substitui o caminho padrão do ECW de 8 cm.",
    )
    @click.option(
        "--sobrescrever",
        is_flag=True,
        help="Recria COGs já existentes.",
    )
    def preparar_ortofotos_semdu(
        resolucao: str,
        gdalwarp: Path | None,
        origem_15cm: Path | None,
        origem_8cm: Path | None,
        sobrescrever: bool,
    ):
        """Converte os ECWs da SEMDU para COGs de publicação."""
        click.echo(
            "\nPreparação das ortofotos SEMDU\n"
        )

        erros: list[str] = []

        for configuracao in _configuracoes_escolhidas(
            resolucao.lower()
        ):
            origem_alternativa = None

            if configuracao.id == "satelite_15cm":
                origem_alternativa = origem_15cm
            elif configuracao.id == "ortofoto_8cm":
                origem_alternativa = origem_8cm

            click.echo(
                f"Preparando: {configuracao.titulo}"
            )

            try:
                destino = preparar_cog(
                    configuracao,
                    gdalwarp=gdalwarp,
                    sobrescrever=sobrescrever,
                    origem_alternativa=origem_alternativa,
                )
            except Exception as erro:
                erros.append(
                    f"{configuracao.titulo}: {erro}"
                )
                click.secho(
                    f"  ERRO: {erro}",
                    fg="red",
                )
                continue

            click.secho(
                f"  COG criado: {destino}",
                fg="green",
            )

        if erros:
            click.echo("")
            raise click.ClickException(
                "Uma ou mais ortofotos não foram preparadas. "
                "Consulte as mensagens acima."
            )

        click.secho(
            "\nOrtofotos preparadas com sucesso.",
            fg="green",
        )
