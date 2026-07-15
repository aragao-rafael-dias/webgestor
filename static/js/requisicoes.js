// ==========================================
// REQUISICOES.JS
// ==========================================

import { apiGet, apiPost } from "./api.js";
import { tocarBip } from "./audio.js";
import {
    historicoRequisicoes,
    historicoVazio
} from "./templates/historico.js";
import { carregando, erro } from "./templates/ui.js";

export async function carregarRequisicoes(escolaId) {
    const statusEl = document.getElementById("status-requisicoes");

    if (!statusEl) {
        return;
    }

    statusEl.innerHTML = carregando("Buscando requisições...");

    try {
        const data = await apiGet(
            `/api/escolas/${encodeURIComponent(escolaId)}/requisicoes`
        );

        if (!Array.isArray(data) || data.length === 0) {
            statusEl.innerHTML = historicoVazio();
            return;
        }

        const pendentes = data.filter(
            (req) => req.status === "Pendente"
        );
        const respondidas = data.filter(
            (req) => req.status === "Respondida"
        );

        statusEl.innerHTML = historicoRequisicoes(
            pendentes,
            respondidas
        );

        statusEl
            .querySelectorAll(".btn-responder")
            .forEach((botao) => {
                botao.addEventListener("click", () => {
                    responderRequisicao(
                        botao.dataset.id,
                        escolaId
                    );
                });
            });
    } catch (errorCarregamento) {
        console.error(
            "Erro ao carregar requisições:",
            errorCarregamento
        );
        statusEl.innerHTML = erro(
            "Erro ao carregar histórico."
        );
    }
}

export async function novaRequisicao(escolaId) {
    const textarea = document.getElementById(
        `texto-nova-req-${escolaId}`
    );

    if (!textarea) {
        return;
    }

    const descricao = textarea.value.trim();

    if (!descricao) {
        alert("Digite uma descrição.");
        textarea.focus();
        return;
    }

    try {
        await apiPost("/api/requisicoes", {
            escola_id: escolaId,
            descricao
        });

        await tocarBip("nova");
        textarea.value = "";
        await carregarRequisicoes(escolaId);
    } catch (errorCriacao) {
        console.error("Erro ao salvar requisição:", errorCriacao);
        alert("Erro ao salvar requisição.");
    }
}

export async function responderRequisicao(reqId, escolaId) {
    const textarea = document.querySelector(
        `.txt-resposta[data-id="${CSS.escape(String(reqId))}"]`
    );

    if (!textarea) {
        return;
    }

    const resposta = textarea.value.trim();

    if (!resposta) {
        alert("A resposta não pode ficar vazia.");
        textarea.focus();
        return;
    }

    try {
        await apiPost(
            `/api/requisicoes/${encodeURIComponent(reqId)}/responder`,
            { resposta }
        );

        await tocarBip("resposta");
        await carregarRequisicoes(escolaId);
    } catch (errorResposta) {
        console.error("Erro ao responder requisição:", errorResposta);
        alert("Erro ao responder.");
    }
}

export async function responderRequisicaoGeral(
    reqId,
    aoConcluir = null
) {
    const textarea = document.querySelector(
        `.txt-resposta-geral[data-id="${CSS.escape(String(reqId))}"]`
    );

    if (!textarea) {
        return;
    }

    const resposta = textarea.value.trim();

    if (!resposta) {
        alert("A resposta não pode ficar vazia.");
        textarea.focus();
        return;
    }

    try {
        await apiPost(
            `/api/requisicoes/${encodeURIComponent(reqId)}/responder`,
            { resposta }
        );

        await tocarBip("resposta");

        if (typeof aoConcluir === "function") {
            await aoConcluir();
        }
    } catch (errorResposta) {
        console.error("Erro ao responder requisição:", errorResposta);
        alert("Erro ao responder.");
    }
}
