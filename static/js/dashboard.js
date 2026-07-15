// ==========================================
// DASHBOARD.JS
// ==========================================

import { apiGet } from "./api.js";
import { AppState } from "./state.js";
import { responderRequisicaoGeral } from "./requisicoes.js";
import {
    dashboard,
    tituloPendentes,
    tituloRespondidas,
    cardPendente,
    cardRespondida,
    fimDashboard
} from "./templates/dashboard.js";
import { dashboardLoading, erro } from "./templates/ui.js";

export async function carregarVisaoGeral() {
    const painel = document.getElementById("info-escola");

    if (!painel) {
        return;
    }

    painel.innerHTML = dashboardLoading();

    try {
        const data = await apiGet("/api/requisicoes/todas");
        const requisicoes = Array.isArray(data) ? data : [];

        const pendentes = requisicoes.filter(
            (req) => req.status === "Pendente"
        );
        const respondidas = requisicoes.filter(
            (req) => req.status === "Respondida"
        );

        const total = requisicoes.length;
        const percentualPendente = total === 0
            ? 0
            : (pendentes.length / total) * 100;

        let html = dashboard({
            total,
            pendentes: pendentes.length,
            respondidas: respondidas.length,
            percentualPendente
        });

        if (pendentes.length > 0) {
            html += tituloPendentes(pendentes.length);

            pendentes.forEach((req) => {
                const escola =
                    AppState.escolas[req.escola_id] ??
                    `Escola #${req.escola_id}`;

                html += cardPendente({
                    id: req.id,
                    escola,
                    descricao: req.descricao
                });
            });
        }

        if (respondidas.length > 0) {
            html += tituloRespondidas(respondidas.length);

            respondidas.forEach((req) => {
                const escola =
                    AppState.escolas[req.escola_id] ??
                    `Escola #${req.escola_id}`;

                html += cardRespondida({
                    id: req.id,
                    escola,
                    resposta: req.resposta_semed
                });
            });
        }

        html += fimDashboard();
        painel.innerHTML = html;

        painel
            .querySelectorAll(".btn-responder-geral")
            .forEach((botao) => {
                botao.addEventListener("click", () => {
                    responderRequisicaoGeral(
                        botao.dataset.id,
                        carregarVisaoGeral
                    );
                });
            });
    } catch (errorDashboard) {
        console.error("Erro ao carregar Dashboard:", errorDashboard);
        painel.innerHTML = erro("Erro ao carregar Dashboard.");
    }
}
