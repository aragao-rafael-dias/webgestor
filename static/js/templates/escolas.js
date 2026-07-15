// ==========================================
// TEMPLATE DA FICHA DA ESCOLA
// ==========================================

import { escapeHtml } from "../utils.js";

export function fichaEscola({
    id,
    nome,
    diretor,
    telefone
}) {
    const idSeguro = escapeHtml(id);

    return `
        <button
            type="button"
            id="btn-voltar-dashboard"
            style="width:100%;margin-bottom:10px;background:#424242;color:white;border:none;padding:8px;border-radius:4px;cursor:pointer;font-weight:bold;"
        >
            ✖ Fechar Ficha da Escola
        </button>

        <h3 style="color:#800000;">${escapeHtml(nome)}</h3>

        <p><strong>Diretor:</strong> ${escapeHtml(diretor)}</p>
        <p><strong>Telefone:</strong> ${escapeHtml(telefone)}</p>

        <hr>

        <h4>Requisições</h4>

        <textarea
            id="texto-nova-req-${idSeguro}"
            rows="3"
            style="width:100%;padding:5px;border-radius:5px;box-sizing:border-box;"
            placeholder="Registre a sua requisição à SEMED aqui!"
        ></textarea>

        <button
            type="button"
            id="btn-nova-req-${idSeguro}"
            class="btn-requisicao"
            data-id="${idSeguro}"
            style="width:100%;margin-top:5px;background:#4caf50;color:white;border:none;padding:8px;cursor:pointer;border-radius:4px;font-weight:bold;"
        >
            + Nova Requisição
        </button>

        <hr>

        <h4>Histórico de Requisições</h4>

        <div id="status-requisicoes">
            Carregando requisições...
        </div>
    `;
}

export function escolaNaoEncontrada() {
    return `
        <div style="padding:20px;text-align:center;">
            Escola não encontrada.
        </div>
    `;
}
