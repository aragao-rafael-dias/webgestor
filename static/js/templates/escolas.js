// ==========================================
// TEMPLATE DA FICHA DA ESCOLA
// ==========================================

import {
    escapeHtml
} from "../utils.js";


export function fichaEscola({
    id,
    nome,
    diretor,
    telefone,
    podeCriarRequisicao = false
}) {
    const idSeguro = String(id)
        .replace(/\D/g, "");

    const nomeSeguro = escapeHtml(
        nome ?? "Escola sem nome"
    );

    const diretorSeguro = escapeHtml(
        diretor ?? "Não informado"
    );

    const telefoneSeguro = escapeHtml(
        telefone ?? "Não informado"
    );

    const formularioRequisicao =
        podeCriarRequisicao
            ? `
                <hr>

                <section class="bloco-nova-requisicao">
                    <h4>Nova Requisição</h4>

                    <label
                        for="setor-nova-req-${idSeguro}"
                        class="label-campo-requisicao"
                    >
                        Setor responsável
                    </label>

                    <select
                        id="setor-nova-req-${idSeguro}"
                        class="campo-setor-requisicao"
                        required
                    >
                        <option value="">
                            Carregando setores...
                        </option>
                    </select>

                    <small class="aviso-setores-esqueleto">
                        A requisição será exibida somente
                        aos usuários vinculados ao setor
                        escolhido.
                    </small>

                    <textarea
                        id="texto-nova-req-${idSeguro}"
                        rows="4"
                        maxlength="5000"
                        class="campo-nova-requisicao"
                        placeholder="Registre a sua requisição à SEMED aqui!"
                    ></textarea>

                    <small class="ajuda-nova-requisicao">
                        Descreva de forma clara o problema
                        ou a necessidade da escola.
                    </small>

                    <button
                        type="button"
                        id="btn-nova-req-${idSeguro}"
                        class="btn-requisicao"
                        data-id="${idSeguro}"
                    >
                        + Nova Requisição
                    </button>
                </section>
            `
            : `
                <hr>

                <div class="aviso-requisicao-restrita">
                    Somente o diretor vinculado a esta escola
                    pode cadastrar uma nova requisição.
                </div>
            `;

    return `
        <button
            type="button"
            id="btn-voltar-dashboard"
            class="btn-voltar-dashboard"
        >
            ✖ Fechar Ficha da Escola
        </button>

        <h3 class="titulo-ficha-escola">
            ${nomeSeguro}
        </h3>

        <div class="dados-ficha-escola">
            <p>
                <strong>Diretor:</strong>
                ${diretorSeguro}
            </p>

            <p>
                <strong>Telefone:</strong>
                ${telefoneSeguro}
            </p>
        </div>

        ${formularioRequisicao}

        <hr>

        <section class="bloco-historico-requisicoes">
            <h4>Histórico de Requisições</h4>

            <div id="status-requisicoes">
                <em>Carregando requisições...</em>
            </div>
        </section>
    `;
}


export function escolaNaoEncontrada() {
    return `
        <div class="escola-nao-encontrada">
            <strong>
                Escola não encontrada.
            </strong>

            <p>
                Não foi possível carregar os dados
                desta unidade de ensino.
            </p>
        </div>
    `;
}
