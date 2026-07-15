// ==========================================
// COMPONENTES GENÉRICOS DE UI
// ==========================================

import { escapeHtml } from "../utils.js";

export function carregando(texto = "Carregando...") {
    return `
        <div style="padding:20px;text-align:center;color:#666;font-style:italic;">
            ${escapeHtml(texto)}
        </div>
    `;
}

export function erro(msg = "Ocorreu um erro.") {
    return `
        <div style="padding:20px;text-align:center;color:#c62828;font-weight:bold;">
            ${escapeHtml(msg)}
        </div>
    `;
}

export function dashboardLoading() {
    return `
        <h3 style="text-align:center;color:#800000;">
            📊 Visão Geral da Rede
        </h3>

        <p style="text-align:center;font-style:italic;">
            Carregando panorama...
        </p>
    `;
}

export function mensagem(texto) {
    return `
        <div style="padding:15px;text-align:center;">
            ${escapeHtml(texto)}
        </div>
    `;
}
