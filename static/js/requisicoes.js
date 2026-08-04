// ==========================================
// REQUISIÇÕES BIDIRECIONAIS
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


let escolasDisponiveisCache = null;
let setoresDisponiveisCache = null;


function carregarCssFluxo() {
    if (
        document.querySelector(
            'link[data-requisicoes-fluxo="1"]'
        )
    ) {
        return;
    }

    const link =
        document.createElement("link");

    link.rel = "stylesheet";
    link.href =
        "/static/css/requisicoes_fluxo.css";
    link.dataset.requisicoesFluxo = "1";

    document.head.appendChild(link);
}


carregarCssFluxo();


function obterPerfilUsuario() {
    return String(
        document.body?.dataset?.perfilUsuario
        ?? ""
    )
        .trim()
        .toUpperCase();
}


export function usuarioPodeCadastrarRequisicao() {
    return [
        "DIRETOR",
        "SETOR"
    ].includes(
        obterPerfilUsuario()
    );
}


export function usuarioPodeResponder() {
    return [
        "DIRETOR",
        "SETOR"
    ].includes(
        obterPerfilUsuario()
    );
}


async function carregarEscolasDisponiveis() {
    if (Array.isArray(escolasDisponiveisCache)) {
        return escolasDisponiveisCache;
    }

    const resultado = await apiGet(
        "/api/requisicoes/escolas-disponiveis"
    );

    escolasDisponiveisCache =
        Array.isArray(resultado)
            ? resultado
            : [];

    return escolasDisponiveisCache;
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

    const superior = String(
        setor?.setor_pai
        || ""
    ).trim();

    return (
        superior
        && !nome.includes(superior)
    )
        ? `${superior} — ${nome}`
        : nome;
}


async function preencherSelectDestino(
    select,
    tipo,
    {
        excluirId = null,
        textoInicial = "Selecione o destino"
    } = {}
) {
    if (!select) {
        return false;
    }

    select.disabled = true;
    select.innerHTML = `
        <option value="">
            Carregando destinos...
        </option>
    `;

    try {
        const itens = tipo === "SETOR"
            ? await carregarSetoresDisponiveis()
            : await carregarEscolasDisponiveis();

        const filtrados = itens.filter(
            item =>
                String(item.id)
                !== String(excluirId ?? "")
        );

        select.innerHTML = "";

        const inicial =
            document.createElement("option");

        inicial.value = "";
        inicial.textContent = filtrados.length
            ? textoInicial
            : "Nenhum destino disponível";

        select.appendChild(inicial);

        filtrados.forEach(
            item => {
                const opcao =
                    document.createElement("option");

                opcao.value = String(item.id);
                opcao.textContent = tipo === "SETOR"
                    ? rotuloSetor(item)
                    : String(
                        item.nome
                        || `Escola ${item.id}`
                    );

                select.appendChild(opcao);
            }
        );

        select.disabled =
            filtrados.length === 0;

        return filtrados.length > 0;

    } catch (falha) {
        console.error(
            "Erro ao preencher destinos:",
            falha
        );

        select.innerHTML = `
            <option value="">
                Erro ao carregar destinos
            </option>
        `;
        select.disabled = true;
        return false;
    }
}


function notificarAlteracaoRequisicoes(
    entidadeId = null
) {
    window.dispatchEvent(
        new CustomEvent(
            "websig:requisicao-alterada",
            {
                detail: {
                    entidadeId:
                        entidadeId === null
                            ? null
                            : String(entidadeId)
                }
            }
        )
    );
}


async function prepararControlesHistorico(
    container,
    recarregar
) {
    const selects = [
        ...container.querySelectorAll(
            "[data-select-encaminhamento='1']"
        )
    ];

    await Promise.all(
        selects.map(
            select => preencherSelectDestino(
                select,
                "ESCOLA",
                {
                    textoInicial:
                        "Selecione a escola"
                }
            )
        )
    );

    container
        .querySelectorAll(
            ".btn-responder"
        )
        .forEach(
            botao => {
                botao.addEventListener(
                    "click",
                    () => responderRequisicao(
                        Number(botao.dataset.id),
                        recarregar,
                        botao
                    )
                );
            }
        );

    container
        .querySelectorAll(
            ".btn-encaminhar-requisicao"
        )
        .forEach(
            botao => {
                botao.addEventListener(
                    "click",
                    () => encaminharRequisicao(
                        Number(botao.dataset.id),
                        recarregar,
                        botao
                    )
                );
            }
        );
}


async function carregarHistorico(
    url,
    container,
    recarregar
) {
    if (!container) {
        return;
    }

    container.innerHTML = carregando(
        "Buscando requisições..."
    );

    try {
        const dados = await apiGet(url);

        if (!Array.isArray(dados)) {
            container.innerHTML =
                historicoVazio();
            return;
        }

        container.innerHTML =
            historicoRequisicoes(dados);

        await prepararControlesHistorico(
            container,
            recarregar
        );

    } catch (falha) {
        console.error(
            "Erro ao carregar requisições:",
            falha
        );

        container.innerHTML = erro(
            falha.message
            || "Erro ao carregar histórico."
        );
    }
}


export async function carregarRequisicoes(
    escolaId
) {
    const container =
        document.getElementById(
            "status-requisicoes"
        );

    const recarregar = () =>
        carregarRequisicoes(escolaId);

    return carregarHistorico(
        `/api/escolas/${
            encodeURIComponent(escolaId)
        }/requisicoes`,
        container,
        recarregar
    );
}


export async function carregarRequisicoesSetor(
    setorId
) {
    const container =
        document.getElementById(
            `status-requisicoes-setor-${setorId}`
        );

    const recarregar = () =>
        carregarRequisicoesSetor(setorId);

    return carregarHistorico(
        `/api/setores/${
            encodeURIComponent(setorId)
        }/requisicoes`,
        container,
        recarregar
    );
}


export async function prepararFormularioRequisicaoEscola(
    escolaId
) {
    const selectTipo =
        document.getElementById(
            `tipo-destino-nova-req-${escolaId}`
        );

    const selectDestino =
        document.getElementById(
            `destino-nova-req-${escolaId}`
        );

    if (!selectTipo || !selectDestino) {
        return;
    }

    const atualizar = () =>
        preencherSelectDestino(
            selectDestino,
            selectTipo.value,
            {
                excluirId:
                    selectTipo.value === "ESCOLA"
                        ? escolaId
                        : null,
                textoInicial:
                    selectTipo.value === "ESCOLA"
                        ? "Selecione a escola"
                        : "Selecione o setor"
            }
        );

    selectTipo.addEventListener(
        "change",
        atualizar
    );

    await atualizar();
}


export async function novaRequisicao(
    escolaId
) {
    const selectTipo =
        document.getElementById(
            `tipo-destino-nova-req-${escolaId}`
        );

    const selectDestino =
        document.getElementById(
            `destino-nova-req-${escolaId}`
        );

    const textarea =
        document.getElementById(
            `texto-nova-req-${escolaId}`
        );

    const botao =
        document.getElementById(
            `btn-nova-req-${escolaId}`
        );

    const destinoTipo =
        selectTipo?.value;
    const destinoId =
        Number(selectDestino?.value);
    const descricao =
        textarea?.value.trim();

    if (!destinoTipo) {
        alert("Selecione o tipo de destino.");
        return;
    }

    if (!Number.isInteger(destinoId)) {
        alert("Selecione o destino.");
        return;
    }

    if (!descricao) {
        alert("Digite uma descrição.");
        textarea?.focus();
        return;
    }

    const textoOriginal =
        botao?.textContent
        || "+ Nova Requisição";

    if (botao) {
        botao.disabled = true;
        botao.textContent = "Salvando...";
    }

    try {
        await apiPost(
            "/api/requisicoes",
            {
                origem_tipo: "ESCOLA",
                origem_id: Number(escolaId),
                destino_tipo: destinoTipo,
                destino_id: destinoId,
                descricao
            }
        );

        await tocarBip("nova");

        if (textarea) {
            textarea.value = "";
        }
        if (selectDestino) {
            selectDestino.value = "";
        }

        notificarAlteracaoRequisicoes(
            escolaId
        );

        await carregarRequisicoes(
            escolaId
        );

        alert(
            "Requisição cadastrada com sucesso."
        );

    } catch (falha) {
        console.error(
            "Erro ao criar requisição:",
            falha
        );
        alert(
            falha.message
            || "Erro ao salvar requisição."
        );

    } finally {
        if (botao) {
            botao.disabled = false;
            botao.textContent = textoOriginal;
        }
    }
}


export async function prepararFormularioRequisicaoSetor(
    setorId
) {
    const select =
        document.getElementById(
            `escola-destino-setor-${setorId}`
        );

    return preencherSelectDestino(
        select,
        "ESCOLA",
        {
            textoInicial:
                "Selecione a escola de destino"
        }
    );
}


export async function novaRequisicaoSetor(
    setorId
) {
    const select =
        document.getElementById(
            `escola-destino-setor-${setorId}`
        );

    const textarea =
        document.getElementById(
            `texto-nova-req-setor-${setorId}`
        );

    const botao =
        document.getElementById(
            `btn-nova-req-setor-${setorId}`
        );

    const destinoId =
        Number(select?.value);
    const descricao =
        textarea?.value.trim();

    if (!Number.isInteger(destinoId)) {
        alert("Selecione a escola de destino.");
        return;
    }

    if (!descricao) {
        alert("Digite uma descrição.");
        textarea?.focus();
        return;
    }

    const textoOriginal =
        botao?.textContent
        || "Enviar para escola";

    if (botao) {
        botao.disabled = true;
        botao.textContent = "Enviando...";
    }

    try {
        await apiPost(
            "/api/requisicoes",
            {
                origem_tipo: "SETOR",
                origem_id: Number(setorId),
                destino_tipo: "ESCOLA",
                destino_id: destinoId,
                descricao
            }
        );

        await tocarBip("nova");

        if (textarea) {
            textarea.value = "";
        }
        if (select) {
            select.value = "";
        }

        notificarAlteracaoRequisicoes(
            setorId
        );

        await carregarRequisicoesSetor(
            setorId
        );

        alert(
            "Requisição enviada para a escola."
        );

    } catch (falha) {
        console.error(
            "Erro ao enviar requisição do setor:",
            falha
        );
        alert(
            falha.message
            || "Erro ao enviar requisição."
        );

    } finally {
        if (botao) {
            botao.disabled = false;
            botao.textContent = textoOriginal;
        }
    }
}


export async function encaminharRequisicao(
    requisicaoId,
    recarregar,
    botaoOrigem = null
) {
    const card =
        botaoOrigem?.closest(
            ".req-card"
        );

    const select =
        card?.querySelector(
            `[data-select-encaminhamento="1"]`
        )
        ?? document.getElementById(
            `encaminhar-destino-${requisicaoId}`
        );

    const textarea =
        card?.querySelector(
            `#encaminhar-observacao-${requisicaoId}`
        )
        ?? document.getElementById(
            `encaminhar-observacao-${requisicaoId}`
        );

    const destinoId =
        Number(select?.value);

    if (!Number.isInteger(destinoId)) {
        alert("Selecione a escola de destino.");
        return;
    }

    try {
        await apiPost(
            `/api/requisicoes/${requisicaoId}/encaminhar`,
            {
                destino_tipo: "ESCOLA",
                destino_id: destinoId,
                observacao:
                    textarea?.value.trim()
                    || ""
            }
        );

        await tocarBip("nova");
        notificarAlteracaoRequisicoes();

        await recarregar?.();

        alert(
            "Requisição encaminhada com sucesso."
        );

    } catch (falha) {
        console.error(
            "Erro ao encaminhar requisição:",
            falha
        );
        alert(
            falha.message
            || "Erro ao encaminhar."
        );
    }
}


export async function responderRequisicao(
    requisicaoId,
    recarregar,
    botaoOrigem = null
) {
    const card =
        botaoOrigem?.closest(
            ".req-card"
        );

    const textarea =
        card?.querySelector(
            ".txt-resposta"
        )
        ?? document.getElementById(
            `resposta-req-${requisicaoId}`
        );

    const resposta =
        textarea?.value.trim();

    if (!resposta) {
        alert(
            "A resposta não pode ficar vazia."
        );
        textarea?.focus();
        return;
    }

    try {
        await apiPost(
            `/api/requisicoes/${requisicaoId}/responder`,
            { resposta }
        );

        await tocarBip("resposta");
        notificarAlteracaoRequisicoes();

        await recarregar?.();

        alert(
            "Requisição respondida com sucesso."
        );

    } catch (falha) {
        console.error(
            "Erro ao responder requisição:",
            falha
        );
        alert(
            falha.message
            || "Erro ao responder."
        );
    }
}


export async function responderRequisicaoGeral(
    requisicaoId
) {
    const textarea =
        document.getElementById(
            `resposta-geral-req-${requisicaoId}`
        );

    const resposta =
        textarea?.value.trim();

    if (!resposta) {
        alert(
            "A resposta não pode ficar vazia."
        );
        return;
    }

    try {
        await apiPost(
            `/api/requisicoes/${requisicaoId}/responder`,
            { resposta }
        );

        await tocarBip("resposta");
        notificarAlteracaoRequisicoes();

        const modulo = await import(
            "./dashboard.js"
        );

        await modulo.carregarVisaoGeral();

    } catch (falha) {
        console.error(falha);
        alert(
            falha.message
            || "Erro ao responder."
        );
    }
}

// ==========================================
// CADASTRO RÁPIDO NA BARRA LATERAL
// ==========================================

function opcoesSelect(
    itens,
    obterRotulo
) {
    return itens.map(
        item => {
            const option =
                document.createElement(
                    "option"
                );

            option.value =
                String(item.id);

            option.textContent =
                obterRotulo(item);

            return option;
        }
    );
}


async function carregarOrigensCadastroRapido(
    perfil
) {
    if (perfil === "DIRETOR") {
        const escolas = await apiGet(
            "/api/minhas-escolas"
        );

        return {
            tipo: "ESCOLA",
            rotulo: "Escola de origem",
            itens: Array.isArray(escolas)
                ? escolas
                : [],
            obterRotulo(item) {
                return String(
                    item.nome
                    || `Escola ${item.id}`
                );
            }
        };
    }

    if (perfil === "SETOR") {
        const setores = await apiGet(
            "/api/meus-setores"
        );

        return {
            tipo: "SETOR",
            rotulo: "Setor de origem",
            itens: Array.isArray(setores)
                ? setores
                : [],
            obterRotulo(item) {
                return rotuloSetor(item);
            }
        };
    }

    return {
        tipo: "",
        rotulo: "Origem",
        itens: [],
        obterRotulo() {
            return "";
        }
    };
}


async function atualizarDestinosCadastroRapido({
    perfil,
    tipoDestino,
    origemId,
    selectDestino
}) {
    const tipoEfetivo = perfil === "SETOR"
        ? "ESCOLA"
        : tipoDestino;

    const excluirId = (
        tipoEfetivo === "ESCOLA"
        && perfil === "DIRETOR"
    )
        ? origemId
        : null;

    return preencherSelectDestino(
        selectDestino,
        tipoEfetivo,
        {
            excluirId,
            textoInicial:
                tipoEfetivo === "SETOR"
                    ? "Selecione o setor"
                    : "Selecione a escola"
        }
    );
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

    const perfil =
        obterPerfilUsuario();

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
            <h4>
                Nova requisição
            </h4>

            <label
                for="origem-requisicao-rapida"
                id="label-origem-requisicao-rapida"
            >
                Origem
            </label>

            <select
                id="origem-requisicao-rapida"
                required
            >
                <option value="">
                    Carregando origens...
                </option>
            </select>

            ${
                perfil === "DIRETOR"
                    ? `
                        <label
                            for="tipo-destino-requisicao-rapida"
                        >
                            Tipo de destino
                        </label>

                        <select
                            id="tipo-destino-requisicao-rapida"
                            required
                        >
                            <option value="SETOR">
                                Setor da SEMED
                            </option>

                            <option value="ESCOLA">
                                Outra escola
                            </option>
                        </select>
                    `
                    : `
                        <input
                            type="hidden"
                            id="tipo-destino-requisicao-rapida"
                            value="ESCOLA"
                        >
                    `
            }

            <label
                for="destino-requisicao-rapida"
            >
                Destino
            </label>

            <select
                id="destino-requisicao-rapida"
                required
                disabled
            >
                <option value="">
                    Selecione primeiro a origem
                </option>
            </select>

            <label
                for="descricao-requisicao-rapida"
            >
                Descrição
            </label>

            <textarea
                id="descricao-requisicao-rapida"
                rows="4"
                maxlength="5000"
                required
                placeholder="Descreva a solicitação"
            ></textarea>

            <div
                class="acoes-requisicao-rapida"
            >
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

    const botaoAbrir =
        container.querySelector(
            "#btn-abrir-requisicao-rapida"
        );

    const formulario =
        container.querySelector(
            "#form-requisicao-rapida"
        );

    const labelOrigem =
        container.querySelector(
            "#label-origem-requisicao-rapida"
        );

    const selectOrigem =
        container.querySelector(
            "#origem-requisicao-rapida"
        );

    const selectTipoDestino =
        container.querySelector(
            "#tipo-destino-requisicao-rapida"
        );

    const selectDestino =
        container.querySelector(
            "#destino-requisicao-rapida"
        );

    const textarea =
        container.querySelector(
            "#descricao-requisicao-rapida"
        );

    const botaoCancelar =
        container.querySelector(
            "#btn-cancelar-requisicao-rapida"
        );

    const botaoSalvar =
        container.querySelector(
            "#btn-salvar-requisicao-rapida"
        );

    if (
        !botaoAbrir
        || !formulario
        || !selectOrigem
        || !selectTipoDestino
        || !selectDestino
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
            selectOrigem.focus();
        }
    );

    botaoCancelar.addEventListener(
        "click",
        () => {
            formulario.hidden = true;
            botaoAbrir.hidden = false;
            formulario.reset();

            selectDestino.innerHTML = `
                <option value="">
                    Selecione primeiro a origem
                </option>
            `;

            selectDestino.disabled = true;
        }
    );

    let configuracaoOrigem;

    try {
        configuracaoOrigem =
            await carregarOrigensCadastroRapido(
                perfil
            );

        if (labelOrigem) {
            labelOrigem.textContent =
                configuracaoOrigem.rotulo;
        }

        selectOrigem.innerHTML = "";

        const opcaoInicial =
            document.createElement(
                "option"
            );

        opcaoInicial.value = "";

        if (
            configuracaoOrigem
                .itens
                .length === 0
        ) {
            opcaoInicial.textContent =
                "Nenhuma origem vinculada";

            selectOrigem.appendChild(
                opcaoInicial
            );

            selectOrigem.disabled = true;
            botaoSalvar.disabled = true;
            return;
        }

        opcaoInicial.textContent =
            "Selecione a origem";

        selectOrigem.appendChild(
            opcaoInicial
        );

        selectOrigem.append(
            ...opcoesSelect(
                configuracaoOrigem.itens,
                configuracaoOrigem
                    .obterRotulo
            )
        );

    } catch (falhaOrigens) {
        console.error(
            "Erro ao carregar origens:",
            falhaOrigens
        );

        selectOrigem.innerHTML = `
            <option value="">
                Erro ao carregar origens
            </option>
        `;

        selectOrigem.disabled = true;
        botaoSalvar.disabled = true;
        return;
    }

    const atualizarDestinos = async () => {
        const origemId =
            selectOrigem.value;

        if (!origemId) {
            selectDestino.innerHTML = `
                <option value="">
                    Selecione primeiro a origem
                </option>
            `;

            selectDestino.disabled = true;
            return;
        }

        await atualizarDestinosCadastroRapido({
            perfil,
            tipoDestino:
                selectTipoDestino.value,
            origemId,
            selectDestino
        });
    };

    selectOrigem.addEventListener(
        "change",
        atualizarDestinos
    );

    selectTipoDestino.addEventListener(
        "change",
        atualizarDestinos
    );

    formulario.addEventListener(
        "submit",
        async evento => {
            evento.preventDefault();

            const origemId =
                Number(selectOrigem.value);

            const destinoTipo =
                perfil === "SETOR"
                    ? "ESCOLA"
                    : selectTipoDestino.value;

            const destinoId =
                Number(selectDestino.value);

            const descricao =
                textarea.value.trim();

            if (!Number.isInteger(origemId)) {
                alert(
                    "Selecione a origem."
                );

                selectOrigem.focus();
                return;
            }

            if (
                !["ESCOLA", "SETOR"]
                    .includes(destinoTipo)
            ) {
                alert(
                    "Selecione o tipo de destino."
                );
                return;
            }

            if (!Number.isInteger(destinoId)) {
                alert(
                    "Selecione o destino."
                );

                selectDestino.focus();
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
                await apiPost(
                    "/api/requisicoes",
                    {
                        origem_tipo:
                            configuracaoOrigem.tipo,
                        origem_id:
                            origemId,
                        destino_tipo:
                            destinoTipo,
                        destino_id:
                            destinoId,
                        descricao
                    }
                );

                await tocarBip("nova");

                formulario.reset();
                formulario.hidden = true;
                botaoAbrir.hidden = false;

                selectDestino.innerHTML = `
                    <option value="">
                        Selecione primeiro a origem
                    </option>
                `;

                selectDestino.disabled = true;

                notificarAlteracaoRequisicoes(
                    origemId
                );

                alert(
                    "Requisição cadastrada com sucesso."
                );

            } catch (falhaCadastro) {
                console.error(
                    "Erro no cadastro rápido:",
                    falhaCadastro
                );

                alert(
                    falhaCadastro.message
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

