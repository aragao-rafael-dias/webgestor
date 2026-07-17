// ==========================================
// REQUISICOES
// ==========================================

import {
    apiGet,
    apiPost
} from "./api.js";

import {
    tocarBip
} from "./audio.js";

import {
    historicoRequisicoes,
    historicoVazio
} from "./templates/historico.js";

import {
    carregando,
    erro
} from "./templates/ui.js";


let setoresDisponiveisCache = null;


function obterPerfilUsuario() {
    return String(
        document.body?.dataset?.perfilUsuario
        ?? ""
    )
        .trim()
        .toUpperCase();
}


export function usuarioPodeResponder() {
    return obterPerfilUsuario() === "SETOR";
}


export function usuarioPodeCadastrarRequisicao() {
    return obterPerfilUsuario() === "DIRETOR";
}


async function carregarSetoresDisponiveis() {
    if (Array.isArray(setoresDisponiveisCache)) {
        return setoresDisponiveisCache;
    }

    const resultado = await apiGet(
        "/api/requisicoes/setores-disponiveis"
    );

    setoresDisponiveisCache =
        Array.isArray(resultado)
            ? resultado
            : [];

    return setoresDisponiveisCache;
}


function rotuloSetor(setor) {
    const nome = String(
        setor?.nome_completo
        || setor?.nome
        || `Setor ${setor?.id ?? ""}`
    ).trim();

    const setorPai = String(
        setor?.setor_pai
        || ""
    ).trim();

    if (
        setorPai
        && !nome.includes(setorPai)
    ) {
        return `${setorPai} — ${nome}`;
    }

    return nome;
}


async function preencherSelectSetores(
    select,
    {
        valorSelecionado = "",
        textoInicial = "Selecione o setor responsável"
    } = {}
) {
    if (!select) {
        return false;
    }

    select.disabled = true;
    select.innerHTML = `
        <option value="">
            Carregando setores...
        </option>
    `;

    try {
        const setores =
            await carregarSetoresDisponiveis();

        select.innerHTML = "";

        const opcaoInicial =
            document.createElement(
                "option"
            );

        opcaoInicial.value = "";
        opcaoInicial.textContent =
            setores.length > 0
                ? textoInicial
                : "Nenhum setor disponível";

        select.appendChild(
            opcaoInicial
        );

        setores.forEach(
            setor => {
                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    String(setor.id);

                option.textContent =
                    rotuloSetor(setor);

                select.appendChild(
                    option
                );
            }
        );

        select.disabled =
            setores.length === 0;

        if (
            valorSelecionado
            && setores.some(
                setor =>
                    String(setor.id)
                    === String(valorSelecionado)
            )
        ) {
            select.value =
                String(valorSelecionado);
        }

        return setores.length > 0;

    } catch (errorSetores) {
        console.error(
            "Erro ao carregar setores:",
            errorSetores
        );

        select.innerHTML = `
            <option value="">
                Erro ao carregar setores
            </option>
        `;

        select.disabled = true;
        return false;
    }
}


export async function prepararFormularioRequisicaoEscola(
    escolaId
) {
    const select =
        document.getElementById(
            `setor-nova-req-${escolaId}`
        );

    return preencherSelectSetores(
        select
    );
}


function notificarAlteracaoRequisicoes(
    escolaId = null
) {
    window.dispatchEvent(
        new CustomEvent(
            "websig:requisicao-alterada",
            {
                detail: {
                    escolaId:
                        escolaId === null
                            ? null
                            : String(escolaId)
                }
            }
        )
    );
}


export async function carregarRequisicoes(
    escolaId
) {
    const statusEl =
        document.getElementById(
            "status-requisicoes"
        );

    if (!statusEl) {
        return;
    }

    statusEl.innerHTML = carregando(
        "Buscando requisições..."
    );

    try {
        const data = await apiGet(
            `/api/escolas/${
                encodeURIComponent(escolaId)
            }/requisicoes`
        );

        if (
            !Array.isArray(data)
            || data.length === 0
        ) {
            statusEl.innerHTML =
                historicoVazio();
            return;
        }

        const pendentes = data.filter(
            requisicao =>
                requisicao.status
                === "Pendente"
        );

        const respondidas = data.filter(
            requisicao =>
                requisicao.status
                === "Respondida"
        );

        const podeResponder =
            usuarioPodeResponder();

        statusEl.innerHTML =
            historicoRequisicoes(
                pendentes,
                respondidas,
                podeResponder
            );

        if (podeResponder) {
            statusEl
                .querySelectorAll(
                    ".btn-responder"
                )
                .forEach(
                    botao => {
                        botao.addEventListener(
                            "click",
                            () => {
                                responderRequisicao(
                                    botao.dataset.id,
                                    escolaId
                                );
                            }
                        );
                    }
                );
        }

    } catch (errorCarregamento) {
        console.error(
            "Erro ao carregar requisições:",
            errorCarregamento
        );

        statusEl.innerHTML = erro(
            errorCarregamento.message
            || "Erro ao carregar histórico."
        );
    }
}


export async function enviarRequisicao(
    escolaId,
    setorId,
    descricao
) {
    if (!usuarioPodeCadastrarRequisicao()) {
        throw new Error(
            "Somente diretores podem cadastrar requisições."
        );
    }

    const idEscola = String(
        escolaId ?? ""
    ).trim();

    const idSetor = String(
        setorId ?? ""
    ).trim();

    const texto = String(
        descricao ?? ""
    ).trim();

    if (!idEscola) {
        throw new Error(
            "Selecione uma escola."
        );
    }

    if (!idSetor) {
        throw new Error(
            "Selecione o setor responsável."
        );
    }

    if (!texto) {
        throw new Error(
            "Digite uma descrição."
        );
    }

    if (texto.length > 5000) {
        throw new Error(
            "A descrição não pode ultrapassar 5.000 caracteres."
        );
    }

    const escolaIdNumerico =
        Number(idEscola);

    const setorIdNumerico =
        Number(idSetor);

    if (
        !Number.isInteger(escolaIdNumerico)
        || escolaIdNumerico <= 0
    ) {
        throw new Error(
            "A escola informada é inválida."
        );
    }

    if (
        !Number.isInteger(setorIdNumerico)
        || setorIdNumerico <= 0
    ) {
        throw new Error(
            "O setor informado é inválido."
        );
    }

    const resultado = await apiPost(
        "/api/requisicoes",
        {
            escola_id: escolaIdNumerico,
            setor_id: setorIdNumerico,
            descricao: texto
        }
    );

    await tocarBip("nova");
    notificarAlteracaoRequisicoes(idEscola);

    return resultado;
}


export async function novaRequisicao(
    escolaId
) {
    if (!usuarioPodeCadastrarRequisicao()) {
        alert(
            "Somente diretores podem cadastrar requisições."
        );
        return;
    }

    const selectSetor =
        document.getElementById(
            `setor-nova-req-${escolaId}`
        );

    const textarea =
        document.getElementById(
            `texto-nova-req-${escolaId}`
        );

    const botao =
        document.getElementById(
            `btn-nova-req-${escolaId}`
        );

    if (!selectSetor || !textarea) {
        return;
    }

    const setorId =
        selectSetor.value;

    const descricao =
        textarea.value.trim();

    if (!setorId) {
        alert(
            "Selecione o setor responsável."
        );
        selectSetor.focus();
        return;
    }

    if (!descricao) {
        alert(
            "Digite uma descrição."
        );
        textarea.focus();
        return;
    }

    const textoOriginalBotao =
        botao?.textContent
        ?? "+ Nova Requisição";

    if (botao) {
        botao.disabled = true;
        botao.textContent =
            "Salvando...";
    }

    try {
        await enviarRequisicao(
            escolaId,
            setorId,
            descricao
        );

        textarea.value = "";
        selectSetor.value = "";

        await carregarRequisicoes(
            escolaId
        );

        alert(
            "Requisição cadastrada com sucesso."
        );

    } catch (errorCriacao) {
        console.error(
            "Erro ao salvar requisição:",
            errorCriacao
        );

        alert(
            errorCriacao.message
            || "Erro ao salvar requisição."
        );

    } finally {
        if (botao) {
            botao.disabled = false;
            botao.textContent =
                textoOriginalBotao;
        }
    }
}


export async function responderRequisicao(
    reqId,
    escolaId
) {
    if (!usuarioPodeResponder()) {
        alert(
            "Somente usuários dos setores podem responder requisições."
        );
        return;
    }

    const seletor =
        CSS.escape(String(reqId));

    const textarea =
        document.querySelector(
            `.txt-resposta[data-id="${seletor}"]`
        );

    if (!textarea) {
        return;
    }

    const resposta =
        textarea.value.trim();

    if (!resposta) {
        alert(
            "A resposta não pode ficar vazia."
        );
        textarea.focus();
        return;
    }

    if (resposta.length > 5000) {
        alert(
            "A resposta não pode ultrapassar 5.000 caracteres."
        );
        textarea.focus();
        return;
    }

    const botao =
        document.querySelector(
            `.btn-responder[data-id="${seletor}"]`
        );

    const textoOriginal =
        botao?.textContent
        ?? "Responder e concluir";

    if (botao) {
        botao.disabled = true;
        botao.textContent =
            "Enviando...";
    }

    try {
        await apiPost(
            `/api/requisicoes/${
                encodeURIComponent(reqId)
            }/responder`,
            { resposta }
        );

        await tocarBip("resposta");
        notificarAlteracaoRequisicoes(escolaId);
        await carregarRequisicoes(escolaId);

    } catch (errorResposta) {
        console.error(
            "Erro ao responder requisição:",
            errorResposta
        );

        alert(
            errorResposta.message
            || "Erro ao responder."
        );

    } finally {
        if (botao?.isConnected) {
            botao.disabled = false;
            botao.textContent =
                textoOriginal;
        }
    }
}


export async function responderRequisicaoGeral(
    reqId,
    aoConcluir = null
) {
    if (!usuarioPodeResponder()) {
        alert(
            "Somente usuários dos setores podem responder requisições."
        );
        return;
    }

    const seletor =
        CSS.escape(String(reqId));

    const textarea =
        document.querySelector(
            `.txt-resposta-geral[data-id="${seletor}"]`
        );

    if (!textarea) {
        return;
    }

    const resposta =
        textarea.value.trim();

    if (!resposta) {
        alert(
            "A resposta não pode ficar vazia."
        );
        textarea.focus();
        return;
    }

    if (resposta.length > 5000) {
        alert(
            "A resposta não pode ultrapassar 5.000 caracteres."
        );
        textarea.focus();
        return;
    }

    const botao =
        document.querySelector(
            `.btn-responder-geral[data-id="${seletor}"]`
        );

    const textoOriginal =
        botao?.textContent
        ?? "Responder e concluir";

    if (botao) {
        botao.disabled = true;
        botao.textContent =
            "Enviando...";
    }

    try {
        await apiPost(
            `/api/requisicoes/${
                encodeURIComponent(reqId)
            }/responder`,
            { resposta }
        );

        await tocarBip("resposta");
        notificarAlteracaoRequisicoes();

        if (typeof aoConcluir === "function") {
            await aoConcluir();
        }

    } catch (errorResposta) {
        console.error(
            "Erro ao responder requisição:",
            errorResposta
        );

        alert(
            errorResposta.message
            || "Erro ao responder."
        );

    } finally {
        if (botao?.isConnected) {
            botao.disabled = false;
            botao.textContent =
                textoOriginal;
        }
    }
}


export async function inicializarCadastroRapido() {
    if (!usuarioPodeCadastrarRequisicao()) {
        return;
    }

    if (
        document.getElementById(
            "cadastro-rapido-requisicao"
        )
    ) {
        return;
    }

    const painelInfo =
        document.getElementById(
            "info-escola"
        );

    if (!painelInfo?.parentNode) {
        return;
    }

    const container =
        document.createElement(
            "section"
        );

    container.id =
        "cadastro-rapido-requisicao";

    container.className =
        "cadastro-rapido-requisicao";

    container.innerHTML = `
        <button
            type="button"
            id="btn-abrir-requisicao-rapida"
            class="btn-abrir-requisicao-rapida"
        >
            + Nova requisição
        </button>

        <form
            id="form-requisicao-rapida"
            class="form-requisicao-rapida"
            hidden
        >
            <h4>Nova requisição</h4>

            <label for="escola-requisicao-rapida">
                Escola
            </label>

            <select
                id="escola-requisicao-rapida"
                required
            >
                <option value="">
                    Carregando escolas...
                </option>
            </select>

            <label for="setor-requisicao-rapida">
                Setor responsável
            </label>

            <select
                id="setor-requisicao-rapida"
                required
            >
                <option value="">
                    Carregando setores...
                </option>
            </select>

            <small class="aviso-setores-esqueleto">
                A requisição ficará disponível apenas
                para os usuários vinculados ao setor
                selecionado.
            </small>

            <label for="descricao-requisicao-rapida">
                Descrição
            </label>

            <textarea
                id="descricao-requisicao-rapida"
                rows="4"
                maxlength="5000"
                required
                placeholder="Descreva a necessidade da escola"
            ></textarea>

            <div class="acoes-requisicao-rapida">
                <button
                    type="button"
                    id="btn-cancelar-requisicao-rapida"
                    class="btn-cancelar-requisicao-rapida"
                >
                    Cancelar
                </button>

                <button
                    type="submit"
                    id="btn-salvar-requisicao-rapida"
                    class="btn-salvar-requisicao-rapida"
                >
                    Cadastrar
                </button>
            </div>
        </form>
    `;

    painelInfo.parentNode.insertBefore(
        container,
        painelInfo
    );

    const botaoAbrir = container.querySelector(
        "#btn-abrir-requisicao-rapida"
    );
    const formulario = container.querySelector(
        "#form-requisicao-rapida"
    );
    const selectEscola = container.querySelector(
        "#escola-requisicao-rapida"
    );
    const selectSetor = container.querySelector(
        "#setor-requisicao-rapida"
    );
    const textarea = container.querySelector(
        "#descricao-requisicao-rapida"
    );
    const botaoCancelar = container.querySelector(
        "#btn-cancelar-requisicao-rapida"
    );
    const botaoSalvar = container.querySelector(
        "#btn-salvar-requisicao-rapida"
    );

    if (
        !botaoAbrir
        || !formulario
        || !selectEscola
        || !selectSetor
        || !textarea
        || !botaoCancelar
        || !botaoSalvar
    ) {
        container.remove();
        return;
    }

    botaoAbrir.addEventListener(
        "click",
        () => {
            botaoAbrir.hidden = true;
            formulario.hidden = false;
            selectEscola.focus();
        }
    );

    botaoCancelar.addEventListener(
        "click",
        () => {
            formulario.hidden = true;
            botaoAbrir.hidden = false;
            formulario.reset();
        }
    );

    let possuiEscolas = false;

    try {
        const escolas = await apiGet(
            "/api/minhas-escolas"
        );

        selectEscola.innerHTML = "";

        const opcaoInicial =
            document.createElement(
                "option"
            );

        opcaoInicial.value = "";

        if (
            !Array.isArray(escolas)
            || escolas.length === 0
        ) {
            opcaoInicial.textContent =
                "Nenhuma escola vinculada";
            selectEscola.appendChild(
                opcaoInicial
            );
            selectEscola.disabled = true;
        } else {
            possuiEscolas = true;
            opcaoInicial.textContent =
                "Selecione uma escola";
            selectEscola.appendChild(
                opcaoInicial
            );

            escolas.forEach(
                escola => {
                    const option =
                        document.createElement(
                            "option"
                        );
                    option.value =
                        String(escola.id);
                    option.textContent =
                        escola.nome
                        || `Escola ${escola.id}`;
                    selectEscola.appendChild(
                        option
                    );
                }
            );
        }

    } catch (errorEscolas) {
        console.error(
            "Erro ao carregar escolas do diretor:",
            errorEscolas
        );
        selectEscola.innerHTML = `
            <option value="">
                Erro ao carregar escolas
            </option>
        `;
        selectEscola.disabled = true;
    }

    const possuiSetores =
        await preencherSelectSetores(
            selectSetor
        );

    botaoSalvar.disabled =
        !possuiEscolas
        || !possuiSetores;

    formulario.addEventListener(
        "submit",
        async evento => {
            evento.preventDefault();

            const escolaId =
                selectEscola.value;
            const setorId =
                selectSetor.value;
            const descricao =
                textarea.value.trim();

            if (!escolaId) {
                alert(
                    "Selecione uma escola."
                );
                selectEscola.focus();
                return;
            }

            if (!setorId) {
                alert(
                    "Selecione o setor responsável."
                );
                selectSetor.focus();
                return;
            }

            if (!descricao) {
                alert(
                    "Digite a descrição da requisição."
                );
                textarea.focus();
                return;
            }

            const textoOriginal =
                botaoSalvar.textContent;

            botaoSalvar.disabled = true;
            botaoSalvar.textContent =
                "Salvando...";

            try {
                await enviarRequisicao(
                    escolaId,
                    setorId,
                    descricao
                );

                formulario.reset();
                formulario.hidden = true;
                botaoAbrir.hidden = false;

                await carregarRequisicoes(
                    escolaId
                );

                alert(
                    "Requisição cadastrada com sucesso."
                );

            } catch (errorCriacao) {
                console.error(
                    "Erro no cadastro rápido:",
                    errorCriacao
                );

                alert(
                    errorCriacao.message
                    || "Não foi possível cadastrar a requisição."
                );

            } finally {
                botaoSalvar.disabled = false;
                botaoSalvar.textContent =
                    textoOriginal;
            }
        }
    );
}
