// ==========================================
// TEMPLATES DO DASHBOARD
// ==========================================

import { escapeHtml } from "../utils.js";

export function dashboard({
    total,
    pendentes,
    respondidas,
    percentualPendente
}) {
    const percentual = Math.max(
        0,
        Math.min(100, Number(percentualPendente) || 0)
    );

    return `
        <div style="text-align:center;margin-bottom:20px;">
            <h3 style="margin-bottom:5px;">
                Status Geral (${escapeHtml(total)} Requisições)
            </h3>

            <div
                style="background:conic-gradient(#ffff00 0% ${percentual}%,#4caf50 ${percentual}% 100%);width:130px;height:130px;border-radius:50%;margin:15px auto;border:3px solid #eee;box-shadow:0 4px 8px rgba(0,0,0,.10);"
            ></div>

            <div style="display:flex;justify-content:space-around;font-weight:bold;margin-top:10px;">
                <span style="color:#800000;">
                    🚨 ${escapeHtml(pendentes)} Pendentes
                </span>

                <span style="color:#388e3c;">
                    ✅ ${escapeHtml(respondidas)} Respondidas
                </span>
            </div>
        </div>

        <hr>

        <div id="dashboard-lista" style="max-height:400px;overflow-y:auto;padding-right:5px;">
    `;
}

export function tituloPendentes(total) {
    return `
        <h4 style="color:#800000;margin-top:10px;">
            Últimas Pendentes (${escapeHtml(total)})
        </h4>
    `;
}

export function tituloRespondidas(total) {
    return `
        <h4 style="color:#388e3c;margin-top:20px;">
            Últimas Respondidas (${escapeHtml(total)})
        </h4>
    `;
}

export function cardPendente({
    id,
    escola,
    descricao
}) {
    const idSeguro = escapeHtml(id);

    return `
        <details style="margin-bottom:8px;">
            <summary style="background:#fff9c4;border-left:4px solid #ffff00;padding:8px;border-radius:4px;cursor:pointer;list-style:none;font-size:.9em;">
                <strong>${escapeHtml(escola)}</strong>
                (Req #${idSeguro})
                <br>
                <em>"${escapeHtml(descricao)}"</em>
            </summary>

            <div style="padding:10px;background:#fafafa;border:1px solid #eee;border-top:none;margin-top:-2px;">
                <textarea
                    class="txt-resposta-geral"
                    data-id="${idSeguro}"
                    rows="2"
                    style="width:100%;padding:5px;box-sizing:border-box;"
                    placeholder="Digite a resposta da SEMED..."
                ></textarea>

                <button
                    type="button"
                    class="btn-responder-geral"
                    data-id="${idSeguro}"
                    style="margin-top:5px;background:#4caf50;color:white;border:none;padding:5px 10px;border-radius:3px;cursor:pointer;"
                >
                    Responder e Concluir
                </button>
            </div>
        </details>
    `;
}

export function cardRespondida({
    id,
    escola,
    resposta
}) {
    return `
        <div style="background:#e8f5e9;border-left:4px solid #4caf50;padding:8px;margin-bottom:8px;border-radius:4px;font-size:.9em;">
            <strong>${escapeHtml(escola)}</strong>
            (Req #${escapeHtml(id)})
            <br>
            <span style="color:#800000;">
                Resp: ${escapeHtml(resposta || "Sem resposta registrada")}
            </span>
        </div>
    `;
}

export function fimDashboard() {
    return "</div>";
}
