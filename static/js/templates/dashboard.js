// ==========================================
// TEMPLATES DO DASHBOARD
// ==========================================

import {
    escapeHtml
} from "../utils.js";


export function dashboard({
    total,
    pendentes,
    respondidas,
    percentualPendente
}) {
    const percentual = Math.max(
        0,
        Math.min(
            100,
            Number(percentualPendente) || 0
        )
    );

    return `
        <div
            style="
                text-align:center;
                margin-bottom:20px;
            "
        >
            <h3 style="margin-bottom:5px;">
                Status Geral
                (${escapeHtml(String(total))} Requisições)
            </h3>

            <div
                style="
                    background:
                        conic-gradient(
                            #ffff00 0% ${percentual}%,
                            #4caf50 ${percentual}% 100%
                        );
                    width:130px;
                    height:130px;
                    border-radius:50%;
                    margin:15px auto;
                    border:3px solid #eee;
                    box-shadow:
                        0 4px 8px
                        rgba(0,0,0,.10);
                "
            ></div>

            <div
                style="
                    display:flex;
                    justify-content:space-around;
                    font-weight:bold;
                    margin-top:10px;
                "
            >
                <span style="color:#800000;">
                    🚨
                    ${escapeHtml(String(pendentes))}
                    Pendentes
                </span>

                <span style="color:#388e3c;">
                    ✅
                    ${escapeHtml(String(respondidas))}
                    Respondidas
                </span>
            </div>
        </div>

        <hr>

        <div
            id="dashboard-lista"
            style="
                max-height:400px;
                overflow-y:auto;
                padding-right:5px;
            "
        >
    `;
}


export function tituloPendentes(total) {
    return `
        <h4
            style="
                color:#800000;
                margin-top:10px;
            "
        >
            Últimas Pendentes
            (${escapeHtml(String(total))})
        </h4>
    `;
}


export function tituloRespondidas(total) {
    return `
        <h4
            style="
                color:#388e3c;
                margin-top:20px;
            "
        >
            Últimas Respondidas
            (${escapeHtml(String(total))})
        </h4>
    `;
}


export function cardPendente({
    id,
    escola,
    descricao,
    podeResponder = false
}) {
    const idSeguro =
        escapeHtml(String(id));

    const escolaSegura =
        escapeHtml(
            String(
                escola
                ?? "Escola não identificada"
            )
        );

    const descricaoSegura =
        escapeHtml(
            String(descricao ?? "")
        );

    const controlesResposta =
        podeResponder
            ? `
                <div
                    style="
                        padding:10px;
                        background:#fafafa;
                        border:1px solid #eee;
                        border-top:none;
                        margin-top:-2px;
                    "
                >
                    <label
                        for="resposta-geral-${idSeguro}"
                        style="
                            display:block;
                            margin-bottom:5px;
                            font-weight:bold;
                        "
                    >
                        Resposta do setor
                    </label>

                    <textarea
                        id="resposta-geral-${idSeguro}"
                        class="txt-resposta-geral"
                        data-id="${idSeguro}"
                        rows="3"
                        maxlength="5000"
                        style="
                            width:100%;
                            padding:5px;
                            box-sizing:border-box;
                        "
                        placeholder="Digite a resposta do setor..."
                    ></textarea>

                    <button
                        type="button"
                        class="btn-responder-geral"
                        data-id="${idSeguro}"
                        style="
                            margin-top:5px;
                            background:#4caf50;
                            color:white;
                            border:none;
                            padding:7px 10px;
                            border-radius:3px;
                            cursor:pointer;
                        "
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
        <details style="margin-bottom:8px;">
            <summary
                style="
                    background:#fff9c4;
                    border-left:4px solid #ffff00;
                    padding:8px;
                    border-radius:4px;
                    cursor:pointer;
                    list-style:none;
                    font-size:.9em;
                "
            >
                <strong>
                    ${escolaSegura}
                </strong>

                (Req #${idSeguro})

                <br>

                <em>
                    "${descricaoSegura}"
                </em>
            </summary>

            ${controlesResposta}
        </details>
    `;
}


export function cardRespondida({
    id,
    escola,
    descricao,
    resposta
}) {
    return `
        <div
            style="
                background:#e8f5e9;
                border-left:4px solid #4caf50;
                padding:8px;
                margin-bottom:8px;
                border-radius:4px;
                font-size:.9em;
            "
        >
            <strong>
                ${
                    escapeHtml(
                        String(
                            escola
                            ?? "Escola não identificada"
                        )
                    )
                }
            </strong>

            (Req #${escapeHtml(String(id))})

            <p style="margin:6px 0;">
                <strong>Solicitação:</strong>

                ${
                    escapeHtml(
                        String(descricao ?? "")
                    )
                }
            </p>

            <span style="color:#800000;">
                <strong>Resposta:</strong>

                ${
                    escapeHtml(
                        String(
                            resposta
                            || "Sem resposta registrada"
                        )
                    )
                }
            </span>
        </div>
    `;
}


export function dashboardSemPendentes() {
    return `
        <p class="historico-vazio">
            Nenhuma requisição pendente.
        </p>
    `;
}


export function dashboardSemRespondidas() {
    return `
        <p class="historico-vazio">
            Nenhuma requisição respondida.
        </p>
    `;
}


export function fimDashboard() {
    return "</div>";
}