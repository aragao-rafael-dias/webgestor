// ==========================================
// DASHBOARD
// ==========================================

import {
    apiGet
} from "./api.js";

import {
    AppState
} from "./state.js";

import {
    responderRequisicaoGeral,
    usuarioPodeResponder
} from "./requisicoes.js";

import {
    dashboard,
    tituloPendentes,
    tituloRespondidas,
    cardPendente,
    cardRespondida,
    dashboardSemPendentes,
    dashboardSemRespondidas,
    fimDashboard
} from "./templates/dashboard.js";

import {
    carregando,
    erro
} from "./templates/ui.js";


// ==========================================
// NOME DA ESCOLA
// ==========================================

function obterNomeEscola(
    escolaId
) {
    const id =
        String(escolaId ?? "");

    return (
        AppState.escolas?.[id]
        ?? `Escola #${id}`
    );
}


// ==========================================
// VISÃO GERAL
// ==========================================

export async function carregarVisaoGeral() {
    const painel =
        document.getElementById(
            "info-escola"
        );

    if (!painel) {
        return;
    }

    painel.innerHTML = carregando(
        "Carregando panorama..."
    );

    try {
        const resultado = await apiGet(
            "/api/requisicoes/todas"
        );

        const requisicoes =
            Array.isArray(resultado)
                ? resultado
                : [];

        const pendentes =
            requisicoes.filter(
                requisicao =>
                    requisicao.status
                    === "Pendente"
            );

        const respondidas =
            requisicoes.filter(
                requisicao =>
                    requisicao.status
                    === "Respondida"
            );

        const total =
            requisicoes.length;

        const percentualPendente =
            total === 0
                ? 0
                : (
                    pendentes.length
                    / total
                ) * 100;

        const podeResponder =
            usuarioPodeResponder();

        let html = dashboard({
            total,
            pendentes: pendentes.length,
            respondidas: respondidas.length,
            percentualPendente
        });

        html += tituloPendentes(
            pendentes.length
        );

        if (pendentes.length === 0) {
            html +=
                dashboardSemPendentes();

        } else {
            pendentes.forEach(
                requisicao => {
                    html += cardPendente({
                        id: requisicao.id,

                        escola:
                            obterNomeEscola(
                                requisicao.escola_id
                            ),

                        descricao:
                            requisicao.descricao,

                        podeResponder
                    });
                }
            );
        }

        html += tituloRespondidas(
            respondidas.length
        );

        if (respondidas.length === 0) {
            html +=
                dashboardSemRespondidas();

        } else {
            respondidas.forEach(
                requisicao => {
                    html += cardRespondida({
                        id: requisicao.id,

                        escola:
                            obterNomeEscola(
                                requisicao.escola_id
                            ),

                        descricao:
                            requisicao.descricao,

                        resposta:
                            requisicao.resposta_semed
                    });
                }
            );
        }

        html += fimDashboard();

        painel.innerHTML = html;

        if (podeResponder) {
            painel
                .querySelectorAll(
                    ".btn-responder-geral"
                )
                .forEach(
                    botao => {
                        botao.addEventListener(
                            "click",
                            () => {
                                responderRequisicaoGeral(
                                    botao.dataset.id,
                                    carregarVisaoGeral
                                );
                            }
                        );
                    }
                );
        }

    } catch (errorCarregamento) {
        console.error(
            "Erro ao carregar dashboard:",
            errorCarregamento
        );

        painel.innerHTML = erro(
            "Erro ao carregar o dashboard."
        );
    }
}