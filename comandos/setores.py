# ==========================================
# COMANDO DE CARGA DOS SETORES
# ==========================================

import click

from sqlalchemy import func

from models import (
    Setor,
    db,
)


ESTRUTURA_SETORES = {
    "nome": (
        "Secretaria Municipal "
        "da Educação"
    ),
    "tipo": "SECRETARIA",
    "filhos": [
        {
            "nome": "Gabinete da Secretária",
            "tipo": "GABINETE",
        },
        {
            "nome": "Secretaria Adjunta",
            "tipo": "SECRETARIA",
        },
        {
            "nome": (
                "Conselho Municipal "
                "de Educação"
            ),
            "tipo": "CONSELHO",
        },
        {
            "nome": (
                "Conselho de Alimentação "
                "Escolar"
            ),
            "tipo": "CONSELHO",
        },
        {
            "nome": (
                "Conselho de Acompanhamento "
                "e Controle Social do FUNDEB"
            ),
            "tipo": "CONSELHO",
        },
        {
            "nome": "Assessoria de Gabinete",
            "tipo": "ASSESSORIA",
        },
        {
            "nome": "Conselho Escolar",
            "tipo": "CONSELHO",
        },
        {
            "nome": "Assessoria Técnica",
            "tipo": "ASSESSORIA",
        },
        {
            "nome": (
                "Assessoria Especial "
                "Extraordinária"
            ),
            "tipo": "ASSESSORIA",
        },
        {
            "nome": (
                "Departamento Administrativo"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação "
                        "de Patrimônio"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Comunicação "
                        "e Tecnologia"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Departamento de "
                "Gestão Educacional"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação da "
                        "Educação Infantil"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação do Ensino "
                        "Fundamental Anos Iniciais"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação do Ensino "
                        "Fundamental Anos Finais"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação da Educação "
                        "em Tempo Integral"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação da Educação "
                        "de Jovens e Adultos"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Programas "
                        "e Projetos Educacionais"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de "
                        "Educação Especial"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Departamento de "
                "Recursos Humanos"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação de Pessoal"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Processamento "
                        "de Dados e Controle "
                        "de Despesas"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Departamento de "
                "Alimentação Escolar"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação de Programas "
                        "de Alimentação Escolar"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Nutrição"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Departamento de "
                "Planejamento Estratégico"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação de Monitoramento "
                        "e Avaliação dos Resultados "
                        "da Aprendizagem"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Busca Ativa"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Formação "
                        "Continuada e Desenvolvimento "
                        "Profissional"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Controle "
                        "e Documentação Escolar"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": "Departamento Pedagógico",
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação dos Programas "
                        "de Bolsa e Assistência "
                        "ao Estudante"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Gestão "
                        "Democrática e Apoio aos "
                        "Grêmios Estudantis"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Arte-Educação"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Cultura "
                        "e Esporte"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Departamento de "
                "Transporte Escolar"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação de Fiscalização "
                        "e Controle de Rotas"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Projetos "
                        "de Transporte Escolar"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": "Departamento Financeiro",
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação de Finanças"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de "
                        "Prestação de Contas"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Orçamento"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Departamento de Gestão "
                "de Unidades Escolares"
            ),
            "tipo": "DEPARTAMENTO",
            "filhos": [
                {
                    "nome": (
                        "Coordenação dos "
                        "Anos Iniciais"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação dos "
                        "Anos Finais"
                    ),
                    "tipo": "COORDENACAO",
                },
                {
                    "nome": (
                        "Coordenação de Desenvolvimento "
                        "das Unidades Escolares"
                    ),
                    "tipo": "COORDENACAO",
                },
            ],
        },
        {
            "nome": (
                "Núcleo de Apoio Psicossocial"
            ),
            "tipo": "NUCLEO",
        },
        {
            "nome": (
                "Núcleo de Atendimento "
                "Educacional Especializado"
            ),
            "tipo": "NUCLEO",
        },
    ],
}


def registrar_comandos_setores(
    app,
):
    @app.cli.command(
        "carregar-setores"
    )
    def carregar_setores():
        """
        Cria ou atualiza a estrutura inicial
        dos setores da Secretaria.
        """

        click.echo(
            "\nCarregando setores...\n"
        )

        quantidade_criada = 0
        quantidade_atualizada = 0

        def salvar_item(
            item,
            setor_pai=None,
            ordem=0,
        ):
            nonlocal quantidade_criada
            nonlocal quantidade_atualizada

            nome = item["nome"].strip()
            tipo = item["tipo"].strip()

            setor = (
                db.session.execute(
                    db.select(Setor)
                    .where(
                        func.lower(Setor.nome)
                        == nome.lower()
                    )
                )
                .scalar_one_or_none()
            )

            if setor is None:
                setor = Setor(
                    nome=nome,
                    tipo=tipo,
                    setor_pai_id=(
                        setor_pai.id
                        if setor_pai
                        else None
                    ),
                    competencias=[],
                    dados_websig={},
                    ativo=True,
                    ordem=ordem,
                )

                db.session.add(
                    setor
                )

                db.session.flush()

                quantidade_criada += 1

                click.echo(
                    f"[CRIADO] {nome}"
                )

            else:
                setor.tipo = tipo
                setor.setor_pai_id = (
                    setor_pai.id
                    if setor_pai
                    else None
                )
                setor.ativo = True
                setor.ordem = ordem

                quantidade_atualizada += 1

                click.echo(
                    f"[ATUALIZADO] {nome}"
                )

            filhos = item.get(
                "filhos",
                [],
            )

            for indice, filho in enumerate(
                filhos,
                start=1,
            ):
                salvar_item(
                    filho,
                    setor_pai=setor,
                    ordem=indice,
                )

            return setor

        try:
            salvar_item(
                ESTRUTURA_SETORES,
                setor_pai=None,
                ordem=0,
            )

            db.session.commit()

        except Exception as erro:
            db.session.rollback()

            raise click.ClickException(
                "Não foi possível carregar "
                "os setores."
            ) from erro

        click.echo(
            "\nCarga concluída."
        )

        click.echo(
            f"Criados: {quantidade_criada}"
        )

        click.echo(
            f"Atualizados: {quantidade_atualizada}"
        )