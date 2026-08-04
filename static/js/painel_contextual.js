// ==========================================
// PAINEL CONTEXTUAL DO LADO DIREITO
// ==========================================

import {
    apiGet
} from "./api.js";

import {
    escapeHtml
} from "./utils.js";

import {
    AppState
} from "./state.js";


import {
    carregarRequisicoesSetor,
    novaRequisicaoSetor,
    prepararFormularioRequisicaoSetor
} from "./requisicoes.js";


let dadosPainel = null;
let itemSelecionadoId = null;
let eventosRegistrados = false;


function obterOuCriarPainel() {
    let painel =
        document.getElementById(
            "painel-contextual"
        );

    if (painel) {
        return painel;
    }

    const container =
        document.getElementById(
            "container"
        );

    if (!container) {
        return null;
    }

    painel = document.createElement(
        "aside"
    );

    painel.id = "painel-contextual";
    painel.setAttribute(
        "aria-label",
        "Informações contextuais do usuário"
    );

    painel.innerHTML = `
        <div class="painel-contextual-cabecalho">
            <div>
                <small>PAINEL CONTEXTUAL</small>
                <h2 id="painel-contextual-titulo">
                    Informações
                </h2>
            </div>

            <button
                type="button"
                id="btn-recarregar-painel-contextual"
                title="Atualizar painel"
                aria-label="Atualizar painel"
            >
                ↻
            </button>
        </div>

        <div
            id="painel-contextual-conteudo"
            class="painel-contextual-conteudo"
        >
            <p class="painel-contextual-carregando">
                Carregando informações...
            </p>
        </div>
    `;

    container.appendChild(painel);

    painel
        .querySelector(
            "#btn-recarregar-painel-contextual"
        )
        ?.addEventListener(
            "click",
            carregarPainelContextual
        );

    window.setTimeout(
        () => AppState.map?.invalidateSize(),
        0
    );

    return painel;
}


function valorVisivel(
    valor,
    fallback = "Não informado"
) {
    if (
        valor === null
        || valor === undefined
        || valor === ""
    ) {
        return fallback;
    }

    if (Array.isArray(valor)) {
        return valor.length > 0
            ? valor.join(", ")
            : fallback;
    }

    return String(valor);
}


function linhaInformacao(
    rotulo,
    valor
) {
    return `
        <div class="painel-contextual-linha">
            <span>${escapeHtml(rotulo)}</span>
            <strong>
                ${escapeHtml(valorVisivel(valor))}
            </strong>
        </div>
    `;
}


function cardContagens(
    requisicoes = {}
) {
    return `
        <div class="painel-contextual-metricas">
            <div>
                <strong>${Number(requisicoes.total || 0)}</strong>
                <span>Total</span>
            </div>

            <div>
                <strong>${Number(requisicoes.pendentes || 0)}</strong>
                <span>Pendentes</span>
            </div>

            <div>
                <strong>${Number(requisicoes.respondidas || 0)}</strong>
                <span>Respondidas</span>
            </div>
        </div>
    `;
}


function imagemCabecalho(
    url,
    textoAlternativo
) {
    const endereco = String(
        url || ""
    ).trim();

    if (!endereco) {
        return `
            <div class="painel-contextual-imagem-vazia">
                🏫
            </div>
        `;
    }

    return `
        <img
            class="painel-contextual-imagem"
            src="${escapeHtml(endereco)}"
            alt="${escapeHtml(textoAlternativo)}"
            loading="lazy"
        >
    `;
}


function seletorItens(
    itens,
    selecionadoId
) {
    if (!Array.isArray(itens) || itens.length <= 1) {
        return "";
    }

    return `
        <label
            class="painel-contextual-seletor-label"
            for="painel-contextual-seletor"
        >
            Selecionar
        </label>

        <select
            id="painel-contextual-seletor"
            class="painel-contextual-seletor"
        >
            ${itens.map(
                item => `
                    <option
                        value="${escapeHtml(String(item.id))}"
                        ${
                            String(item.id) === String(selecionadoId)
                                ? "selected"
                                : ""
                        }
                    >
                        ${escapeHtml(
                            item.nome_completo
                            || item.nome
                            || `Item ${item.id}`
                        )}
                    </option>
                `
            ).join("")}
        </select>
    `;
}


function renderizarEscola(item) {
    const dados =
        item.dados_websig
        && typeof item.dados_websig === "object"
            ? item.dados_websig
            : {};

    const chavesIgnoradas = new Set([
        "alunos",
        "quantidade_alunos",
        "total_alunos",
        "matriculas",
        "quantidade_matriculas",
        "turmas",
        "quantidade_turmas",
        "total_turmas",
        "modalidades",
        "modalidade",
        "etapas",
        "telefone",
        "telefone_escola",
        "diretor",
        "nome_diretor",
        "codigo_inep",
        "inep",
        "codigo"
    ]);

    const dadosExtras = Object
        .entries(dados)
        .filter(
            ([chave, valor]) =>
                !chavesIgnoradas.has(chave)
                && valor !== null
                && valor !== ""
                && !Array.isArray(valor)
                && typeof valor !== "object"
        )
        .slice(0, 8);

    return `
        ${imagemCabecalho(item.imagem_url, item.nome)}

        <h3 class="painel-contextual-nome">
            ${escapeHtml(valorVisivel(item.nome, "Escola"))}
        </h3>

        ${cardContagens(item.requisicoes)}

        <div class="painel-contextual-dados">
            ${linhaInformacao("Código INEP", item.codigo_inep)}
            ${linhaInformacao("Diretor", item.diretor)}
            ${linhaInformacao("Alunos", item.alunos)}
            ${linhaInformacao("Turmas", item.turmas)}
            ${linhaInformacao("Modalidades", item.modalidades)}
            ${linhaInformacao("Turno", item.turno)}
            ${linhaInformacao("Tipo", item.tipo_de_escola)}
            ${linhaInformacao("Telefone", item.telefone)}
            ${linhaInformacao("Endereço", item.endereco)}

            ${dadosExtras.map(
                ([chave, valor]) =>
                    linhaInformacao(
                        chave
                            .replaceAll("_", " ")
                            .replace(
                                /\b\w/g,
                                letra => letra.toUpperCase()
                            ),
                        valor
                    )
            ).join("")}
        </div>
    `;
}


function renderizarSetor(item) {
    const competencias =
        Array.isArray(item.competencias)
            ? item.competencias
            : [];

    return `
        ${imagemCabecalho(item.imagem_url, item.nome)}

        <div class="painel-contextual-identificacao-setor">
            <span>${escapeHtml(item.tipo || "SETOR")}</span>

            ${
                item.principal
                    ? "<strong>Principal</strong>"
                    : ""
            }
        </div>

        <h3 class="painel-contextual-nome">
            ${escapeHtml(
                item.nome_completo
                || item.nome
                || "Setor"
            )}
        </h3>

        ${cardContagens(item.requisicoes)}

        <div class="painel-contextual-dados">
            ${linhaInformacao("Setor superior", item.setor_pai)}
        </div>

        ${
            item.descricao
                ? `
                    <section class="painel-contextual-secao">
                        <h4>Descrição</h4>
                        <p>${escapeHtml(item.descricao)}</p>
                    </section>
                `
                : ""
        }

        ${
            competencias.length > 0
                ? `
                    <section class="painel-contextual-secao">
                        <h4>Competências</h4>
                        <ul>
                            ${competencias.map(
                                competencia => `
                                    <li>
                                        ${escapeHtml(String(competencia))}
                                    </li>
                                `
                            ).join("")}
                        </ul>
                    </section>
                `
                : ""
        }

        <section class="painel-contextual-secao req-form-setor">
            <h4>Nova requisição para escola</h4>

            <label for="escola-destino-setor-${item.id}">
                Escola de destino
            </label>

            <select
                id="escola-destino-setor-${item.id}"
                class="req-select"
            >
                <option value="">
                    Carregando escolas...
                </option>
            </select>

            <textarea
                id="texto-nova-req-setor-${item.id}"
                rows="4"
                maxlength="5000"
                class="req-textarea"
                placeholder="Descreva a solicitação do setor"
            ></textarea>

            <button
                type="button"
                id="btn-nova-req-setor-${item.id}"
                class="btn-requisicao"
            >
                Enviar para escola
            </button>
        </section>

        <section class="painel-contextual-secao">
            <h4>Requisições do setor</h4>

            <div id="status-requisicoes-setor-${item.id}">
                Carregando requisições...
            </div>
        </section>
    `;
}


function renderizarResumo(resumo = {}) {
    return `
        <div class="painel-contextual-resumo-geral">
            ${linhaInformacao("Escolas", resumo.escolas)}
            ${linhaInformacao("Setores ativos", resumo.setores)}
            ${linhaInformacao("Requisições", resumo.requisicoes)}
            ${linhaInformacao("Pendentes", resumo.pendentes)}
            ${linhaInformacao("Respondidas", resumo.respondidas)}
        </div>
    `;
}


function renderizarDadosPainel() {
    const painel = obterOuCriarPainel();
    const titulo = painel?.querySelector(
        "#painel-contextual-titulo"
    );
    const conteudo = painel?.querySelector(
        "#painel-contextual-conteudo"
    );

    if (!painel || !titulo || !conteudo || !dadosPainel) {
        return;
    }

    titulo.textContent =
        dadosPainel.titulo
        || "Informações";

    if (
        dadosPainel.tipo === "DIRETOR"
        || dadosPainel.tipo === "SETOR"
    ) {
        const itens =
            Array.isArray(dadosPainel.itens)
                ? dadosPainel.itens
                : [];

        if (itens.length === 0) {
            conteudo.innerHTML = `
                <div class="painel-contextual-vazio">
                    Nenhum vínculo ativo foi encontrado.
                </div>
            `;
            return;
        }

        const selecionado = itens.find(
            item =>
                String(item.id)
                === String(itemSelecionadoId)
        ) || itens[0];

        itemSelecionadoId = selecionado.id;

        conteudo.innerHTML = `
            ${seletorItens(itens, selecionado.id)}
            ${
                dadosPainel.tipo === "DIRETOR"
                    ? renderizarEscola(selecionado)
                    : renderizarSetor(selecionado)
            }
        `;

        conteudo
            .querySelector(
                "#painel-contextual-seletor"
            )
            ?.addEventListener(
                "change",
                evento => {
                    itemSelecionadoId =
                        evento.target.value;
                    renderizarDadosPainel();
                }
            );

        if (dadosPainel.tipo === "SETOR") {
            prepararFormularioRequisicaoSetor(
                selecionado.id
            );

            conteudo
                .querySelector(
                    `#btn-nova-req-setor-${selecionado.id}`
                )
                ?.addEventListener(
                    "click",
                    () => novaRequisicaoSetor(
                        selecionado.id
                    )
                );

            carregarRequisicoesSetor(
                selecionado.id
            );
        }

        return;
    }

    conteudo.innerHTML =
        renderizarResumo(
            dadosPainel.resumo
        );
}


export async function carregarPainelContextual() {
    const painel = obterOuCriarPainel();
    const conteudo = painel?.querySelector(
        "#painel-contextual-conteudo"
    );

    if (!conteudo) {
        return;
    }

    conteudo.innerHTML = `
        <p class="painel-contextual-carregando">
            Carregando informações...
        </p>
    `;

    try {
        dadosPainel = await apiGet(
            "/api/painel-contextual"
        );

        itemSelecionadoId =
            dadosPainel?.principal_id
            ?? itemSelecionadoId;

        renderizarDadosPainel();

    } catch (errorPainel) {
        console.error(
            "Erro ao carregar painel contextual:",
            errorPainel
        );

        conteudo.innerHTML = `
            <div class="painel-contextual-vazio">
                ${escapeHtml(
                    errorPainel.message
                    || "Não foi possível carregar o painel."
                )}
            </div>
        `;
    }
}


export async function inicializarPainelContextual() {
    obterOuCriarPainel();

    if (!eventosRegistrados) {
        eventosRegistrados = true;

        window.addEventListener(
            "websig:requisicao-alterada",
            carregarPainelContextual
        );
    }

    await carregarPainelContextual();

    window.setTimeout(
        () => AppState.map?.invalidateSize(),
        0
    );
}
