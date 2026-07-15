// ==========================================
// TEMPLATES DO HISTÓRICO DA ESCOLA
// ==========================================

import { escapeHtml } from "../utils.js";

export function historicoRequisicoes(pendentes, respondidas) {
    let html = `
        <details open>
            <summary style="cursor:pointer;font-weight:bold;background:#ffff00;color:#800000;padding:8px;border-radius:5px;">
                🚨 PENDENTES (${pendentes.length})
            </summary>

            <div style="padding:10px;background:#fff;border:1px solid #ccc;border-top:none;">
    `;

    if (pendentes.length === 0) {
        html += "<p>Nenhuma requisição pendente.</p>";
    }

    pendentes.forEach((req) => {
        html += cardHistoricoPendente(req);
    });

    html += `
            </div>
        </details>

        <details style="margin-top:10px;">
            <summary style="cursor:pointer;font-weight:bold;background:#c8e6c9;padding:8px;border-radius:5px;">
                ✅ RESPONDIDAS (${respondidas.length})
            </summary>

            <div style="padding:10px;background:#fff;border:1px solid #ccc;border-top:none;">
    `;

    if (respondidas.length === 0) {
        html += "<p>Nenhuma requisição respondida.</p>";
    }

    respondidas.forEach((req) => {
        html += cardHistoricoRespondida(req);
    });

    html += `
            </div>
        </details>
    `;

    return html;
}

export function cardHistoricoPendente(req) {
    const idSeguro = escapeHtml(req.id);

    return `
        <div style="margin-bottom:15px;padding-bottom:10px;border-bottom:1px dashed #ccc;">
            <strong style="color:#d32f2f;">
                Req #${idSeguro}
            </strong>

            <p style="margin:5px 0;">
                <em>"${escapeHtml(req.descricao)}"</em>
            </p>

            <textarea
                class="txt-resposta"
                data-id="${idSeguro}"
                rows="2"
                style="width:100%;margin-top:5px;box-sizing:border-box;"
                placeholder="Digite a resposta da SEMED..."
            ></textarea>

            <button
                type="button"
                class="btn-responder"
                data-id="${idSeguro}"
                style="margin-top:5px;background:#4caf50;color:white;border:none;padding:6px 10px;border-radius:4px;cursor:pointer;"
            >
                Responder e Concluir
            </button>
        </div>
    `;
}

export function cardHistoricoRespondida(req) {
    return `
        <div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px dashed #ccc;">
            <strong style="color:#388e3c;">
                Req #${escapeHtml(req.id)}
            </strong>

            <p style="margin:5px 0;">
                <strong>Pedido:</strong>
                <em>"${escapeHtml(req.descricao)}"</em>
            </p>

            <p style="margin:5px 0;color:#800000;">
                <strong>Resposta SEMED:</strong>
                ${escapeHtml(req.resposta_semed || "Sem resposta registrada")}
            </p>
        </div>
    `;
}

export function historicoVazio() {
    return `
        <p style="text-align:center;padding:15px;">
            Nenhuma requisição encontrada nesta unidade de ensino.
        </p>
    `;
}
