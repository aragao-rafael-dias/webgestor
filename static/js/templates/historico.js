// ==========================================
// TEMPLATE DO HISTÓRICO DE REQUISIÇÕES
// ==========================================

import {
    escapeHtml
} from "../utils.js";


function dataVisivel(valor) {
    if (!valor) {
        return "";
    }

    const data = new Date(valor);

    if (Number.isNaN(data.getTime())) {
        return String(valor);
    }

    return data.toLocaleString(
        "pt-BR"
    );
}


function entidadeVisivel(entidade) {
    if (!entidade) {
        return "Não classificado";
    }

    const icone = entidade.tipo === "SETOR"
        ? "🏢"
        : "🏫";

    return `${icone} ${escapeHtml(
        entidade.nome
        || `${entidade.tipo} #${entidade.id}`
    )}`;
}


function movimentoHtml(movimento) {
    const rotulos = {
        CRIACAO: "Criação",
        ENCAMINHAMENTO: "Encaminhamento",
        RESPOSTA: "Resposta"
    };

    const origem = entidadeVisivel(
        movimento.origem
    );

    const destino = entidadeVisivel(
        movimento.destino
    );

    return `
        <li class="req-movimento req-movimento--${
            String(movimento.tipo || "").toLowerCase()
        }">
            <div class="req-movimento-cabecalho">
                <strong>
                    ${escapeHtml(
                        rotulos[movimento.tipo]
                        || movimento.tipo
                        || "Movimentação"
                    )}
                </strong>

                <small>
                    ${escapeHtml(
                        dataVisivel(
                            movimento.criado_em
                        )
                    )}
                </small>
            </div>

            <div class="req-movimento-fluxo">
                ${origem}
                <span>→</span>
                ${destino}
            </div>

            ${
                movimento.usuario
                    ? `
                        <small class="req-movimento-usuario">
                            Por ${escapeHtml(
                                movimento.usuario
                            )}
                        </small>
                    `
                    : ""
            }

            ${
                movimento.mensagem
                    ? `
                        <p>
                            ${escapeHtml(
                                movimento.mensagem
                            )}
                        </p>
                    `
                    : ""
            }
        </li>
    `;
}


function controlesHtml(requisicao) {
    const permissoes =
        requisicao.permissoes ?? {};

    let html = "";

    if (permissoes.pode_encaminhar) {
        html += `
            <section class="req-acao">
                <h5>Encaminhar para outra escola</h5>

                <select
                    id="encaminhar-destino-${requisicao.id}"
                    class="req-select"
                    data-select-encaminhamento="1"
                    data-requisicao-id="${requisicao.id}"
                >
                    <option value="">
                        Carregando escolas...
                    </option>
                </select>

                <textarea
                    id="encaminhar-observacao-${requisicao.id}"
                    rows="2"
                    maxlength="5000"
                    class="req-textarea"
                    placeholder="Observação do encaminhamento"
                ></textarea>

                <button
                    type="button"
                    class="btn-encaminhar-requisicao"
                    data-id="${requisicao.id}"
                >
                    Encaminhar
                </button>
            </section>
        `;
    }

    if (permissoes.pode_responder) {
        html += `
            <section class="req-acao">
                <h5>Responder e concluir</h5>

                <textarea
                    id="resposta-req-${requisicao.id}"
                    rows="3"
                    maxlength="5000"
                    class="req-textarea txt-resposta"
                    data-id="${requisicao.id}"
                    placeholder="Digite a resposta"
                ></textarea>

                <button
                    type="button"
                    class="btn-responder"
                    data-id="${requisicao.id}"
                >
                    Responder e concluir
                </button>
            </section>
        `;
    }

    return html;
}


function requisicaoHtml(requisicao) {
    const respondida =
        requisicao.status === "Respondida";

    const movimentos = Array.isArray(
        requisicao.movimentacoes
    )
        ? requisicao.movimentacoes
        : [];

    return `
        <article class="req-card ${
            respondida
                ? "req-card--respondida"
                : "req-card--pendente"
        }">
            <header class="req-card-cabecalho">
                <div>
                    <strong>
                        Requisição #${requisicao.id}
                    </strong>

                    <span class="req-status">
                        ${escapeHtml(
                            requisicao.status
                            || "Pendente"
                        )}
                    </span>
                </div>

                <small>
                    ${escapeHtml(
                        dataVisivel(
                            requisicao.data_criacao
                        )
                    )}
                </small>
            </header>

            <div class="req-fluxo-atual">
                <span>
                    ${entidadeVisivel(
                        requisicao.origem
                    )}
                </span>

                <strong>→</strong>

                <span>
                    ${entidadeVisivel(
                        requisicao.destino
                    )}
                </span>
            </div>

            <div class="req-descricao">
                <strong>Solicitação</strong>
                <p>
                    ${escapeHtml(
                        requisicao.descricao
                        || ""
                    )}
                </p>
            </div>

            ${
                respondida
                    ? `
                        <div class="req-resposta">
                            <strong>Resposta</strong>
                            <p>
                                ${escapeHtml(
                                    requisicao.resposta
                                    || requisicao.resposta_semed
                                    || ""
                                )}
                            </p>

                            ${
                                requisicao.respondido_por
                                    ? `
                                        <small>
                                            Respondido por
                                            ${escapeHtml(
                                                requisicao.respondido_por
                                            )}
                                        </small>
                                    `
                                    : ""
                            }
                        </div>
                    `
                    : controlesHtml(requisicao)
            }

            <details class="req-historico">
                <summary>
                    Histórico do fluxo
                    (${movimentos.length})
                </summary>

                <ol>
                    ${movimentos.map(
                        movimentoHtml
                    ).join("")}
                </ol>
            </details>
        </article>
    `;
}


export function historicoVazio() {
    return `
        <div class="req-vazio">
            Nenhuma requisição encontrada.
        </div>
    `;
}


export function historicoRequisicoes(
    requisicoes
) {
    const lista = Array.isArray(
        requisicoes
    )
        ? requisicoes
        : [];

    if (lista.length === 0) {
        return historicoVazio();
    }

    const pendentes = lista.filter(
        item => item.status !== "Respondida"
    );

    const respondidas = lista.filter(
        item => item.status === "Respondida"
    );

    return `
        <details open class="req-grupo">
            <summary>
                🚨 Pendentes (${pendentes.length})
            </summary>

            <div class="req-lista">
                ${
                    pendentes.length
                        ? pendentes.map(
                            requisicaoHtml
                        ).join("")
                        : historicoVazio()
                }
            </div>
        </details>

        <details class="req-grupo">
            <summary>
                ✅ Respondidas (${respondidas.length})
            </summary>

            <div class="req-lista">
                ${
                    respondidas.length
                        ? respondidas.map(
                            requisicaoHtml
                        ).join("")
                        : historicoVazio()
                }
            </div>
        </details>
    `;
}
