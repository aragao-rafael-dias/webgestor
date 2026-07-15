// ==========================================
// TEMPLATE DO POPUP DAS ROTAS
// ==========================================

import { escapeHtml } from "../utils.js";

export function popupRota({
    id,
    nome,
    regiao,
    trecho,
    totalPontos
}) {
    const idSeguro = escapeHtml(id);

    return `
        <div style="font-family:Arial,sans-serif;min-width:220px;">
            <h4 style="margin:0 0 8px;color:#800000;border-bottom:2px solid #800000;padding-bottom:3px;">
                🚌 ${escapeHtml(nome)}
            </h4>

            <p style="margin:4px 0;font-size:13px;">
                <strong>📍 Região:</strong> ${escapeHtml(regiao)}
            </p>

            <p style="margin:4px 0;font-size:13px;">
                <strong>🛤️ Trecho:</strong> ${escapeHtml(trecho)}
            </p>

            <p style="margin:4px 0;font-size:13px;">
                <strong>🛑 Vértices:</strong> ${escapeHtml(totalPontos)}
            </p>

            <button
                type="button"
                class="btn-memorial"
                data-rota="${idSeguro}"
                style="width:100%;margin-top:12px;background:#800000;color:white;border:none;padding:8px;border-radius:4px;cursor:pointer;font-weight:bold;"
            >
                📄 Gerar Memorial (PDF)
            </button>
        </div>
    `;
}
