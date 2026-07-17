// ==========================================
// TEMPLATE DO HISTÓRICO DE REQUISIÇÕES
// ==========================================

import {
    escapeHtml
} from "../utils.js";


function templatePendentes(
    pendentes,
    podeResponder
) {
    if (
        !Array.isArray(pendentes)
        || pendentes.length === 0
    ) {
        return `
            <p class="historico-vazio">
                Nenhuma requisição pendente.
            </p>
        `;
    }

    return pendentes
        .map(
            requisicao => {
                const idSeguro =
                    escapeHtml(
                        String(requisicao.id)
                    );

                const descricaoSegura =
                    escapeHtml(
                        String(
                            requisicao.descricao
                            ?? ""
                        )
                    );

                const controlesResposta =
                    podeResponder
                        ? `
                            <div
                                class="controles-resposta"
                            >
                                <label
                                    for="resposta-req-${idSeguro}"
                                >
                                    Resposta do setor
                                </label>

                                <textarea
                                    id="resposta-req-${idSeguro}"
                                    class="txt-resposta"
                                    data-id="${idSeguro}"
                                    rows="3"
                                    maxlength="5000"
                                    placeholder="Digite a resposta do setor"
                                ></textarea>

                                <button
                                    type="button"
                                    class="btn-responder"
                                    data-id="${idSeguro}"
                                >
                                    Responder e concluir
                                </button>
                            </div>
                        `
                        : `
                            <div
                                class="aviso-aguardando-setor"
                            >
                                Aguardando análise e resposta
                                do setor responsável.
                            </div>
                        `;

                return `
                    <article
                        class="item-requisicao pendente"
                    >
                        <strong>
                            Requisição #${idSeguro}
                        </strong>

                        <p>
                            ${descricaoSegura}
                        </p>

                        ${controlesResposta}
                    </article>
                `;
            }
        )
        .join("");
}


function templateRespondidas(
    respondidas
) {
    if (
        !Array.isArray(respondidas)
        || respondidas.length === 0
    ) {
        return `
            <p class="historico-vazio">
                Nenhuma requisição respondida.
            </p>
        `;
    }

    return respondidas
        .map(
            requisicao => {
                const idSeguro =
                    escapeHtml(
                        String(requisicao.id)
                    );

                const descricaoSegura =
                    escapeHtml(
                        String(
                            requisicao.descricao
                            ?? ""
                        )
                    );

                const respostaSegura =
                    escapeHtml(
                        String(
                            requisicao.resposta_semed
                            ?? "Resposta não informada"
                        )
                    );

                return `
                    <article
                        class="item-requisicao respondida"
                    >
                        <strong>
                            Requisição #${idSeguro}
                        </strong>

                        <p>
                            <strong>
                                Solicitação:
                            </strong>

                            ${descricaoSegura}
                        </p>

                        <p class="resposta-semed">
                            <strong>
                                Resposta:
                            </strong>

                            ${respostaSegura}
                        </p>
                    </article>
                `;
            }
        )
        .join("");
}


export function historicoRequisicoes(
    pendentes = [],
    respondidas = [],
    podeResponder = false
) {
    const listaPendentes =
        Array.isArray(pendentes)
            ? pendentes
            : [];

    const listaRespondidas =
        Array.isArray(respondidas)
            ? respondidas
            : [];

    return `
        <details
            class="grupo-requisicoes"
            open
        >
            <summary
                class="titulo-requisicoes-pendentes"
            >
                Pendentes
                (${listaPendentes.length})
            </summary>

            <div class="lista-requisicoes">
                ${
                    templatePendentes(
                        listaPendentes,
                        podeResponder
                    )
                }
            </div>
        </details>

        <details
            class="grupo-requisicoes"
        >
            <summary
                class="titulo-requisicoes-respondidas"
            >
                Respondidas
                (${listaRespondidas.length})
            </summary>

            <div class="lista-requisicoes">
                ${
                    templateRespondidas(
                        listaRespondidas
                    )
                }
            </div>
        </details>
    `;
}


export function historicoVazio() {
    return `
        <div class="historico-vazio">
            Nenhuma requisição encontrada
            nesta escola.
        </div>
    `;
}