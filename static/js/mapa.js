// ==========================================
// MAPA.JS
// Ponto de entrada da aplicação no navegador
// ==========================================

import {
    CONFIG,
    coresRegioes,
    nomesRegioes
} from "./config.js";

import { AppState } from "./state.js";

import {
    apiGet,
    apiPost
} from "./api.js";

import { tocarBip } from "./audio.js";

import {
    obterId,
    obterIdRegiao,
    abrirNovaAba
} from "./utils.js";

import {
    nomeRota,
    regiao,
    trecho,
    totalPontos
} from "./props.js";

import {
    carregarEscolas,
    atualizarAlertasEscolas
} from "./escolas.js";

import {
    inicializarCadastroRapido
} from "./requisicoes.js";

import {
    carregarVisaoGeral
} from "./dashboard.js";

import {
    inicializarPainelContextual
} from "./painel_contextual.js";

import {
    inicializarBuscaMapa
} from "./busca_mapa.js";

import {
    popupRota
} from "./templates/popup.js";

import {
    erro
} from "./templates/ui.js";


// ==========================================
// CLASSIFICAÇÃO DAS ROTAS
// ==========================================

const codigosRotasPcd = new Set();


function normalizarCodigoRota(valor) {
    return String(valor ?? "")
        .trim()
        .replace(/\s+/g, " ")
        .toUpperCase();
}


function valorBooleano(valor) {
    if (typeof valor === "boolean") {
        return valor;
    }

    return [
        "1",
        "TRUE",
        "T",
        "SIM",
        "S",
        "YES",
        "ON"
    ].includes(
        String(valor ?? "")
            .trim()
            .toUpperCase()
    );
}


function rotaEhPcd(feature) {
    const props =
        feature?.properties ?? feature ?? {};

    const pcdNaPropriedade =
        props.onibus_pcd
        ?? props.ONIBUS_PCD
        ?? props.pcd
        ?? props.PCD
        ?? props.rota_pcd;

    if (valorBooleano(pcdNaPropriedade)) {
        return true;
    }

    const codigo = normalizarCodigoRota(
        nomeRota(props)
    );

    return codigosRotasPcd.has(codigo);
}


function estiloRota(feature) {
    const props =
        feature?.properties ?? {};

    const idRegiao =
        obterIdRegiao(props);

    const pcd =
        rotaEhPcd(feature);

    return {
        pane:
            CONFIG
                .paineis
                .rotas
                .nome,

        color:
            coresRegioes[idRegiao]
            ?? "#800000",

        weight: 4,
        opacity: 0.8,
        lineJoin: "round",
        lineCap: pcd ? "butt" : "round",

        // A cor continua sendo a da região.
        // Somente a forma da linha muda.
        dashArray: pcd
            ? "14 10"
            : null,

        dashOffset: pcd
            ? "0"
            : null
    };
}


// ==========================================
// CONFIGURAÇÃO DOS PAINÉIS DO LEAFLET
// ==========================================

function configurarPaineisMapa(map) {
    const paineis =
        Object.values(CONFIG.paineis);

    paineis.forEach(
        ({ nome, zIndex }) => {
            if (!map.getPane(nome)) {
                map.createPane(nome);
            }

            const painel =
                map.getPane(nome);

            painel.style.zIndex =
                String(zIndex);
        }
    );
}


// ==========================================
// INICIALIZAÇÃO DO MAPA
// ==========================================

export function inicializarMapaLeaflet() {
    if (AppState.map) {
        return AppState.map;
    }

    const elementoMapa =
        document.getElementById("map");

    if (!elementoMapa) {
        throw new Error(
            "Elemento #map não encontrado."
        );
    }

    if (typeof L === "undefined") {
        throw new Error(
            "Leaflet não foi carregado."
        );
    }

    AppState.map = L
        .map("map")
        .setView(
            CONFIG.centro,
            CONFIG.zoom
        );

    configurarPaineisMapa(
        AppState.map
    );

    L.tileLayer(
        CONFIG.tileLayer,
        {
            maxZoom: CONFIG.maxZoom,
            attribution: CONFIG.attribution
        }
    ).addTo(AppState.map);

    return AppState.map;
}


// ==========================================
// CARREGAMENTO DOS DADOS DO MAPA
// ==========================================

export async function carregarMapa() {
    try {
        const [
            escolas,
            rotas,
            respostaRotasPcd
        ] = await Promise.all([
            apiGet("/api/escolas"),
            apiGet("/api/rotas"),
            apiGet("/api/rotas-pcd")
        ]);

        AppState.rotas = rotas;

        codigosRotasPcd.clear();

        (
            respostaRotasPcd?.rotas_pcd
            ?? []
        ).forEach(
            codigo => {
                codigosRotasPcd.add(
                    normalizarCodigoRota(
                        codigo
                    )
                );
            }
        );

        criarFiltroRegioes();
        renderizarRotas();

        await carregarEscolas(
            AppState.map,
            escolas
        );

        await atualizarAlertasEscolas();
        await carregarVisaoGeral();

    } catch (errorCarregamento) {
        console.error(
            "Erro ao carregar o mapa:",
            errorCarregamento
        );

        const painel =
            document.getElementById(
                "info-escola"
            );

        if (painel) {
            painel.innerHTML = erro(
                "Erro ao carregar os dados do mapa."
            );
        }
    }
}


// ==========================================
// RENDERIZAÇÃO DAS ROTAS
// ==========================================

export function renderizarRotas() {
    if (
        !AppState.map
        || !AppState.rotas
    ) {
        return;
    }

    if (AppState.layers.rotas) {
        AppState.map.removeLayer(
            AppState.layers.rotas
        );
    }

    const checkboxes = [
        ...document.querySelectorAll(
            ".filtro-regiao:checked"
        )
    ];

    const regioesPermitidas =
        checkboxes.map(
            checkbox => checkbox.value
        );

    const mostrarRotasRegulares =
        document.getElementById(
            "filtro-rotas-regulares"
        )?.checked ?? true;

    const mostrarRotasPcd =
        document.getElementById(
            "filtro-rotas-pcd"
        )?.checked ?? true;

    AppState.layers.rotas = L.geoJSON(
        AppState.rotas,
        {
            pane: CONFIG.paineis.rotas.nome,

            filter(feature) {
                const idRegiao =
                    obterIdRegiao(
                        feature.properties ?? {}
                    );

                if (
                    regioesPermitidas.length === 0
                    || !regioesPermitidas.includes(
                        idRegiao
                    )
                ) {
                    return false;
                }

                const pcd =
                    rotaEhPcd(feature);

                if (
                    pcd
                    && !mostrarRotasPcd
                ) {
                    return false;
                }

                if (
                    !pcd
                    && !mostrarRotasRegulares
                ) {
                    return false;
                }

                return true;
            },

            style(feature) {
                return estiloRota(feature);
            },

            onEachFeature(feature, layer) {
                configurarRota(
                    feature,
                    layer
                );
            }
        }
    ).addTo(AppState.map);
}


// ==========================================
// CONFIGURAÇÃO DE CADA ROTA
// ==========================================

function configurarRota(
    feature,
    layer
) {
    const props =
        feature.properties ?? {};

    const idRota =
        obterId(feature);

    const idRegiao =
        obterIdRegiao(props);

    layer.bindPopup(
        popupRota({
            id: idRota,

            nome:
                nomeRota(props),

            regiao:
                regiao(props)
                || idRegiao
                || "Não informada",

            trecho:
                trecho(props),

            totalPontos:
                totalPontos(props)
        })
    );

    layer.on(
        "popupopen",
        evento => {
            const botao = evento.popup
                .getElement()
                ?.querySelector(
                    ".btn-memorial"
                );

            if (!botao) {
                return;
            }

            if (idRota === "") {
                botao.disabled = true;

                botao.title =
                    "Rota sem identificador válido";

                return;
            }

            botao.addEventListener(
                "click",
                () => gerarMemorial(
                    idRota,
                    {
                        nome: nomeRota(props),
                        regiao: regiao(props)
                            || idRegiao
                            || ""
                    }
                ),
                {
                    once: true
                }
            );
        }
    );

    layer.on(
        "mouseover",
        evento => {
            evento.target.setStyle({
                weight: 7,
                color: "#ffff00",
                opacity: 1
            });
        }
    );

    layer.on(
        "mouseout",
        evento => {
            if (
                AppState.layers.rotas
                && typeof AppState
                    .layers
                    .rotas
                    .resetStyle === "function"
            ) {
                AppState.layers.rotas.resetStyle(
                    evento.target
                );
                return;
            }

            evento.target.setStyle(
                estiloRota(feature)
            );
        }
    );
}


// ==========================================
// PERFIL DO USUÁRIO
// ==========================================

function perfilUsuarioAtual() {
    return String(
        document.body?.dataset
            ?.perfilUsuario
        ?? ""
    )
        .trim()
        .toUpperCase();
}


function podeGerarTodosMemoriais() {
    return [
        "ADMIN",
        "AUDITOR"
    ].includes(
        perfilUsuarioAtual()
    );
}


// ==========================================
// FILTRO DE REGIÕES
// ==========================================

export function criarFiltroRegioes() {
    if (
        document.getElementById(
            "filtro-regioes-container"
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
        document.createElement("div");

    container.id =
        "filtro-regioes-container";

    Object.assign(
        container.style,
        {
            padding: "10px",
            marginBottom: "15px",
            background: "#f9f9f9",
            border: "1px solid #ddd",
            borderRadius: "5px"
        }
    );

    const tituloFiltro =
        document.createElement("h4");

    tituloFiltro.textContent =
        "🗺️ Filtrar por Região";

    Object.assign(
        tituloFiltro.style,
        {
            margin: "0 0 10px 0",
            color: "#800000",
            borderBottom:
                "2px solid #800000",
            paddingBottom: "3px"
        }
    );

    container.appendChild(
        tituloFiltro
    );

    Object
        .entries(coresRegioes)
        .forEach(
            ([idRegiao, cor]) => {
                const label =
                    document.createElement(
                        "label"
                    );

                Object.assign(
                    label.style,
                    {
                        display: "block",
                        marginBottom: "5px",
                        cursor: "pointer",
                        fontSize: "14px"
                    }
                );

                const checkbox =
                    document.createElement(
                        "input"
                    );

                checkbox.type =
                    "checkbox";

                checkbox.className =
                    "filtro-regiao";

                checkbox.value =
                    idRegiao;

                checkbox.checked =
                    true;

                checkbox.addEventListener(
                    "change",
                    renderizarRotas
                );

                const iconeCor =
                    document.createElement(
                        "span"
                    );

                iconeCor.textContent =
                    " ■ ";

                iconeCor.style.color =
                    cor;

                if (idRegiao === "4") {
                    iconeCor.style.textShadow =
                        "1px 1px 1px #888";
                }

                label.append(
                    checkbox,
                    iconeCor,
                    document.createTextNode(
                        ` ${
                            nomesRegioes[idRegiao]
                            ?? `Região ${idRegiao}`
                        }`
                    )
                );

                container.appendChild(
                    label
                );
            }
        );

    criarFiltroTiposRotas(
        container
    );

    criarBotaoTodosMemoriais(
        container
    );

    painelInfo.parentNode.insertBefore(
        container,
        painelInfo
    );
}


// ==========================================
// FILTRO POR TIPO DE ROTA
// ==========================================

function criarAmostraLinha(
    tracejada = false
) {
    const amostra =
        document.createElement("span");

    Object.assign(
        amostra.style,
        {
            display: "inline-block",
            width: "34px",
            height: "0",
            margin: "0 7px 0 4px",
            verticalAlign: "middle",
            borderTop: tracejada
                ? "4px dashed #555555"
                : "4px solid #555555"
        }
    );

    return amostra;
}


function criarFiltroTiposRotas(
    container
) {
    const separador =
        document.createElement("div");

    Object.assign(
        separador.style,
        {
            height: "1px",
            background: "#d8d8d8",
            margin: "12px 0 10px"
        }
    );

    const titulo =
        document.createElement("strong");

    titulo.textContent =
        "Tipo de rota";

    Object.assign(
        titulo.style,
        {
            display: "block",
            marginBottom: "8px",
            color: "#333333",
            fontSize: "12px"
        }
    );

    const opcoes = [
        {
            id: "filtro-rotas-regulares",
            texto: "Rotas regulares",
            tracejada: false
        },
        {
            id: "filtro-rotas-pcd",
            texto: "Rotas PCD",
            tracejada: true
        }
    ];

    container.append(
        separador,
        titulo
    );

    opcoes.forEach(
        opcao => {
            const label =
                document.createElement(
                    "label"
                );

            Object.assign(
                label.style,
                {
                    display: "flex",
                    alignItems: "center",
                    marginBottom: "6px",
                    cursor: "pointer",
                    fontSize: "12px",
                    color: "#444444"
                }
            );

            const checkbox =
                document.createElement(
                    "input"
                );

            checkbox.type = "checkbox";
            checkbox.id = opcao.id;
            checkbox.checked = true;

            checkbox.addEventListener(
                "change",
                renderizarRotas
            );

            label.append(
                checkbox,
                criarAmostraLinha(
                    opcao.tracejada
                ),
                document.createTextNode(
                    opcao.texto
                )
            );

            container.appendChild(
                label
            );
        }
    );

    const explicacao =
        document.createElement("p");

    explicacao.textContent =
        "As rotas PCD mantêm a cor da região e aparecem tracejadas.";

    Object.assign(
        explicacao.style,
        {
            margin: "6px 0 0",
            color: "#666666",
            fontSize: "10.5px",
            lineHeight: "1.35"
        }
    );

    container.appendChild(
        explicacao
    );
}


// ==========================================
// GERAÇÃO FLEXÍVEL DE MEMORIAIS E MAPAS
// ==========================================

let opcoesGeracaoMemoriais = null;
let resolvendoOpcoesMemoriais = null;


function carregarCssGeracaoMemoriais() {
    if (
        document.querySelector(
            'link[data-geracao-memoriais="1"]'
        )
    ) {
        return;
    }

    const link =
        document.createElement("link");

    link.rel = "stylesheet";
    link.href =
        "/static/css/memoriais_geracao.css";
    link.dataset.geracaoMemoriais = "1";

    document.head.appendChild(link);
}


async function carregarOpcoesGeracaoMemoriais() {
    if (opcoesGeracaoMemoriais) {
        return opcoesGeracaoMemoriais;
    }

    if (resolvendoOpcoesMemoriais) {
        return resolvendoOpcoesMemoriais;
    }

    resolvendoOpcoesMemoriais = apiGet(
        "/api/rotas/memoriais/opcoes"
    )
        .then(
            dados => {
                opcoesGeracaoMemoriais = {
                    regioes: Array.isArray(
                        dados?.regioes
                    )
                        ? dados.regioes
                        : [],
                    rotas: Array.isArray(
                        dados?.rotas
                    )
                        ? dados.rotas
                        : [],
                    podeGerarLote: Boolean(
                        dados?.pode_gerar_lote
                    )
                };

                return opcoesGeracaoMemoriais;
            }
        )
        .finally(
            () => {
                resolvendoOpcoesMemoriais = null;
            }
        );

    return resolvendoOpcoesMemoriais;
}


function criarBotaoTodosMemoriais(
    container
) {
    carregarCssGeracaoMemoriais();

    if (
        !podeGerarTodosMemoriais()
        || document.getElementById(
            "btn-gerar-todos-memoriais"
        )
    ) {
        return;
    }

    const separador =
        document.createElement("div");

    separador.className =
        "geracao-memoriais-separador";

    const observacao =
        document.createElement("p");

    observacao.className =
        "geracao-memoriais-observacao";

    observacao.textContent =
        "Gere por rota, região ou por todo o município.";

    const botao =
        document.createElement("button");

    botao.id =
        "btn-gerar-todos-memoriais";

    botao.type = "button";
    botao.className =
        "btn-geracao-memoriais";

    botao.innerHTML =
        "📄 Gerar memoriais e mapas";

    botao.addEventListener(
        "click",
        gerarTodosMemoriais
    );

    container.append(
        separador,
        observacao,
        botao
    );
}


function nomeArquivoResposta(
    resposta,
    nomePadrao
) {
    const disposicao =
        resposta.headers.get(
            "Content-Disposition"
        ) ?? "";

    const utf8 = disposicao.match(
        /filename\*=UTF-8''([^;]+)/i
    );

    if (utf8?.[1]) {
        try {
            return decodeURIComponent(
                utf8[1]
            );
        } catch {
            return utf8[1];
        }
    }

    const simples = disposicao.match(
        /filename="?([^";]+)"?/i
    );

    return simples?.[1]
        ?? nomePadrao;
}


async function mensagemErroResposta(
    resposta
) {
    const texto = (
        await resposta.text()
    ).trim();

    if (!texto) {
        return `O servidor retornou o erro ${
            resposta.status
        }.`;
    }

    const semHtml = texto
        .replace(/<[^>]*>/g, " ")
        .replace(/\s+/g, " ")
        .trim();

    return semHtml || texto;
}


function baixarBlob(
    blob,
    nomeArquivo
) {
    const urlTemporaria =
        URL.createObjectURL(blob);

    const link =
        document.createElement("a");

    link.href = urlTemporaria;
    link.download = nomeArquivo;

    document.body.appendChild(link);
    link.click();
    link.remove();

    window.setTimeout(
        () => URL.revokeObjectURL(
            urlTemporaria
        ),
        1000
    );
}


function preencherSelect(
    select,
    itens,
    obterValor,
    obterRotulo,
    textoInicial
) {
    select.innerHTML = "";

    const inicial =
        document.createElement("option");

    inicial.value = "";
    inicial.textContent = textoInicial;
    select.appendChild(inicial);

    itens.forEach(
        item => {
            const opcao =
                document.createElement("option");

            opcao.value = String(
                obterValor(item)
            );

            opcao.textContent =
                obterRotulo(item);

            select.appendChild(opcao);
        }
    );
}


function criarModalGeracaoMemoriais() {
    const existente =
        document.getElementById(
            "modal-geracao-memoriais"
        );

    if (existente) {
        return existente;
    }

    carregarCssGeracaoMemoriais();

    const modal =
        document.createElement("div");

    modal.id =
        "modal-geracao-memoriais";

    modal.className =
        "modal-geracao-memoriais";

    modal.hidden = true;

    modal.innerHTML = `
        <div
            class="modal-geracao-memoriais-fundo"
            data-fechar-modal="1"
        ></div>

        <section
            class="modal-geracao-memoriais-caixa"
            role="dialog"
            aria-modal="true"
            aria-labelledby="titulo-modal-geracao-memoriais"
        >
            <header>
                <div>
                    <h3 id="titulo-modal-geracao-memoriais">
                        Gerar memoriais e mapas
                    </h3>

                    <p>
                        Escolha o conteúdo, a abrangência
                        e a organização dos arquivos.
                    </p>
                </div>

                <button
                    type="button"
                    class="modal-geracao-fechar"
                    data-fechar-modal="1"
                    aria-label="Fechar"
                >
                    ×
                </button>
            </header>

            <form id="form-geracao-memoriais">
                <fieldset>
                    <legend>1. Conteúdo</legend>

                    <label class="opcao-geracao">
                        <input
                            type="radio"
                            name="conteudo-geracao"
                            value="memorial_mapa"
                            checked
                        >
                        <span>
                            <strong>Memorial + mapa</strong>
                            <small>Um PDF completo por conjunto.</small>
                        </span>
                    </label>

                    <label class="opcao-geracao">
                        <input
                            type="radio"
                            name="conteudo-geracao"
                            value="mapa"
                        >
                        <span>
                            <strong>Somente mapa</strong>
                            <small>Mapa geral e mapas detalhados.</small>
                        </span>
                    </label>

                    <label class="opcao-geracao">
                        <input
                            type="radio"
                            name="conteudo-geracao"
                            value="memorial"
                        >
                        <span>
                            <strong>Somente memorial</strong>
                            <small>Ficha, unidades assistidas e itinerário.</small>
                        </span>
                    </label>

                    <label class="opcao-geracao">
                        <input
                            type="radio"
                            name="conteudo-geracao"
                            value="separados"
                        >
                        <span>
                            <strong>Memorial e mapa separados</strong>
                            <small>Gera dois PDFs dentro de um ZIP.</small>
                        </span>
                    </label>
                </fieldset>

                <fieldset>
                    <legend>2. Abrangência</legend>

                    <label for="escopo-geracao-memoriais">
                        Gerar para
                    </label>

                    <select id="escopo-geracao-memoriais">
                        <option value="rota">
                            Uma rota específica
                        </option>

                        <option value="regiao">
                            Todas as rotas de uma região
                        </option>

                        <option value="municipio">
                            Todas as rotas do município
                        </option>
                    </select>

                    <div id="campo-rota-geracao">
                        <label for="rota-geracao-memoriais">
                            Rota
                        </label>

                        <select id="rota-geracao-memoriais">
                            <option value="">
                                Carregando rotas...
                            </option>
                        </select>
                    </div>

                    <div id="campo-regiao-geracao" hidden>
                        <label for="regiao-geracao-memoriais">
                            Região
                        </label>

                        <select id="regiao-geracao-memoriais">
                            <option value="">
                                Carregando regiões...
                            </option>
                        </select>
                    </div>
                </fieldset>

                <fieldset id="campo-organizacao-geracao">
                    <legend>3. Organização</legend>

                    <label for="organizacao-geracao-memoriais">
                        Organização das rotas
                    </label>

                    <select id="organizacao-geracao-memoriais">
                        <option value="unico">
                            Todas as rotas em um único PDF
                        </option>

                        <option value="separados">
                            Um arquivo por rota, dentro de um ZIP
                        </option>
                    </select>
                </fieldset>

                <p class="aviso-unidades-assistidas">
                    Nos memoriais serão exibidas somente as unidades
                    registradas em “escolas_atendidas” como assistidas
                    pelo transporte escolar.
                </p>

                <div class="acoes-modal-geracao">
                    <button
                        type="button"
                        class="btn-cancelar-geracao"
                        data-fechar-modal="1"
                    >
                        Cancelar
                    </button>

                    <button
                        type="submit"
                        id="btn-confirmar-geracao-memoriais"
                        class="btn-confirmar-geracao"
                    >
                        Gerar arquivo
                    </button>
                </div>
            </form>
        </section>
    `;

    document.body.appendChild(modal);

    modal
        .querySelectorAll(
            "[data-fechar-modal='1']"
        )
        .forEach(
            elemento => {
                elemento.addEventListener(
                    "click",
                    () => {
                        modal.hidden = true;
                        document.body.classList.remove(
                            "modal-geracao-aberto"
                        );
                    }
                );
            }
        );

    return modal;
}


function atualizarCamposModalGeracao(
    modal
) {
    const escopo =
        modal.querySelector(
            "#escopo-geracao-memoriais"
        )?.value;

    const campoRota =
        modal.querySelector(
            "#campo-rota-geracao"
        );

    const campoRegiao =
        modal.querySelector(
            "#campo-regiao-geracao"
        );

    const campoOrganizacao =
        modal.querySelector(
            "#campo-organizacao-geracao"
        );

    const organizacao =
        modal.querySelector(
            "#organizacao-geracao-memoriais"
        );

    if (campoRota) {
        campoRota.hidden =
            escopo !== "rota";
    }

    if (campoRegiao) {
        campoRegiao.hidden =
            escopo !== "regiao";
    }

    if (campoOrganizacao) {
        campoOrganizacao.hidden =
            escopo === "rota";
    }

    if (
        organizacao
        && escopo === "regiao"
    ) {
        organizacao.value = "unico";
    }

    if (
        organizacao
        && escopo === "municipio"
        && !organizacao.dataset.usuarioAlterou
    ) {
        organizacao.value = "separados";
    }
}


async function executarGeracaoMemoriais(
    modal
) {
    const formulario =
        modal.querySelector(
            "#form-geracao-memoriais"
        );

    const botao =
        modal.querySelector(
            "#btn-confirmar-geracao-memoriais"
        );

    const escopo =
        modal.querySelector(
            "#escopo-geracao-memoriais"
        )?.value;

    const rotaId =
        modal.querySelector(
            "#rota-geracao-memoriais"
        )?.value;

    const regiaoId =
        modal.querySelector(
            "#regiao-geracao-memoriais"
        )?.value;

    const organizacao =
        modal.querySelector(
            "#organizacao-geracao-memoriais"
        )?.value
        ?? "unico";

    const conteudo =
        formulario?.querySelector(
            "input[name='conteudo-geracao']:checked"
        )?.value;

    if (escopo === "rota" && !rotaId) {
        alert("Selecione a rota.");
        return;
    }

    if (escopo === "regiao" && !regiaoId) {
        alert("Selecione a região.");
        return;
    }

    const parametros =
        new URLSearchParams({
            escopo,
            conteudo,
            organizacao:
                escopo === "rota"
                    ? "unico"
                    : organizacao
        });

    if (escopo === "rota") {
        parametros.set("rota_id", rotaId);
    }

    if (escopo === "regiao") {
        parametros.set("regiao", regiaoId);
    }

    const textoOriginal =
        botao.textContent;

    botao.disabled = true;
    botao.textContent =
        "Gerando...";

    try {
        await tocarBip("resposta");

        const resposta = await fetch(
            `/api/rotas/memoriais/gerar?${
                parametros.toString()
            }`,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    Accept:
                        "application/pdf, application/zip"
                }
            }
        );

        if (!resposta.ok) {
            throw new Error(
                await mensagemErroResposta(
                    resposta
                )
            );
        }

        const blob = await resposta.blob();

        const nomeArquivo =
            nomeArquivoResposta(
                resposta,
                "Memoriais_e_Mapas.zip"
            );

        baixarBlob(blob, nomeArquivo);

        const gerados =
            resposta.headers.get(
                "X-Memoriais-Gerados"
            );

        const erros =
            resposta.headers.get(
                "X-Memoriais-Erros"
            );

        modal.hidden = true;
        document.body.classList.remove(
            "modal-geracao-aberto"
        );

        alert(
            "O arquivo foi gerado e o download foi iniciado."
            + (
                gerados
                    ? `\n\nRotas geradas: ${gerados}`
                    : ""
            )
            + (
                erros && erros !== "0"
                    ? `\nRotas com erro: ${erros}.`
                    : ""
            )
        );

    } catch (falha) {
        console.error(
            "Erro ao gerar memoriais:",
            falha
        );

        alert(
            "Não foi possível gerar o arquivo.\n\n"
            + (
                falha?.message
                ?? "Erro desconhecido."
            )
        );

    } finally {
        botao.disabled = false;
        botao.textContent =
            textoOriginal;
    }
}


async function abrirModalGeracaoMemorial({
    rotaId = "",
    nome = "",
    regiao = "",
    escopoInicial = "rota"
} = {}) {
    const modal =
        criarModalGeracaoMemoriais();

    const selectEscopo =
        modal.querySelector(
            "#escopo-geracao-memoriais"
        );

    const selectRota =
        modal.querySelector(
            "#rota-geracao-memoriais"
        );

    const selectRegiao =
        modal.querySelector(
            "#regiao-geracao-memoriais"
        );

    const selectOrganizacao =
        modal.querySelector(
            "#organizacao-geracao-memoriais"
        );

    const botaoConfirmar =
        modal.querySelector(
            "#btn-confirmar-geracao-memoriais"
        );

    botaoConfirmar.disabled = true;
    botaoConfirmar.textContent =
        "Carregando opções...";

    try {
        const opcoes =
            await carregarOpcoesGeracaoMemoriais();

        preencherSelect(
            selectRota,
            opcoes.rotas,
            item => item.id,
            item => `${item.nome} — ${item.regiao}`,
            "Selecione a rota"
        );

        preencherSelect(
            selectRegiao,
            opcoes.regioes,
            item => item.id,
            item => item.nome,
            "Selecione a região"
        );

        if (rotaId) {
            selectRota.value =
                String(rotaId);

            if (
                selectRota.value
                !== String(rotaId)
                && nome
            ) {
                const opcao =
                    document.createElement("option");

                opcao.value =
                    String(rotaId);

                opcao.textContent =
                    `${nome}${
                        regiao
                            ? ` — ${regiao}`
                            : ""
                    }`;

                selectRota.appendChild(opcao);
                selectRota.value =
                    String(rotaId);
            }
        }

        if (regiao) {
            const regiaoTexto =
                String(regiao).toLowerCase();

            const encontrada = [
                ...selectRegiao.options
            ].find(
                opcao =>
                    opcao.value.toLowerCase()
                        === regiaoTexto
                    || opcao.textContent
                        .toLowerCase()
                        .includes(regiaoTexto)
            );

            if (encontrada) {
                selectRegiao.value =
                    encontrada.value;
            }
        }

        const podeLote =
            opcoes.podeGerarLote;

        [...selectEscopo.options].forEach(
            opcao => {
                if (opcao.value !== "rota") {
                    opcao.disabled = !podeLote;
                }
            }
        );

        selectEscopo.value = (
            escopoInicial !== "rota"
            && podeLote
        )
            ? escopoInicial
            : "rota";

        if (
            selectEscopo.value === "municipio"
        ) {
            selectOrganizacao.value =
                "separados";
        }

        atualizarCamposModalGeracao(modal);

        botaoConfirmar.disabled = false;
        botaoConfirmar.textContent =
            "Gerar arquivo";

    } catch (falha) {
        console.error(
            "Erro ao carregar opções de geração:",
            falha
        );

        botaoConfirmar.disabled = true;
        botaoConfirmar.textContent =
            "Erro ao carregar opções";

        alert(
            falha?.message
            || "Não foi possível carregar as opções."
        );
    }

    if (!modal.dataset.eventosConfigurados) {
        selectEscopo.addEventListener(
            "change",
            () => atualizarCamposModalGeracao(
                modal
            )
        );

        selectOrganizacao.addEventListener(
            "change",
            () => {
                selectOrganizacao.dataset.usuarioAlterou =
                    "1";
            }
        );

        modal
            .querySelector(
                "#form-geracao-memoriais"
            )
            .addEventListener(
                "submit",
                evento => {
                    evento.preventDefault();
                    executarGeracaoMemoriais(
                        modal
                    );
                }
            );

        modal.dataset.eventosConfigurados =
            "1";
    }

    modal.hidden = false;
    document.body.classList.add(
        "modal-geracao-aberto"
    );

    selectEscopo.focus();
}


export async function gerarMemorial(
    rotaId,
    dadosRota = {}
) {
    if (
        rotaId === undefined
        || rotaId === null
        || rotaId === ""
    ) {
        alert(
            "A rota não possui um identificador válido."
        );
        return;
    }

    return abrirModalGeracaoMemorial({
        rotaId,
        nome: dadosRota.nome,
        regiao: dadosRota.regiao,
        escopoInicial: "rota"
    });
}


export async function gerarTodosMemoriais() {
    return abrirModalGeracaoMemorial({
        escopoInicial: "municipio"
    });
}


// ==========================================
// SINCRONIZAÇÃO COM O SETE
// ==========================================

export async function sincronizarComSete() {
    const botao =
        document.getElementById(
            "btn-sync-sete"
        );

    if (!botao) {
        return;
    }

    const textoOriginal =
        botao.innerHTML;

    const corOriginal =
        botao.style.background;

    botao.innerHTML =
        "⏳ Sincronizando com Gov. Federal...";

    botao.disabled = true;

    botao.style.background =
        "#9e9e9e";

    try {
        const resultado =
            await apiPost(
                "/api/integracao/sincronizar"
            );

        if (resultado?.sucesso) {
            await tocarBip(
                "resposta"
            );

            alert(
                resultado.mensagem
            );

            console.log(
                "DADOS IMPORTADOS DO SETE:",
                resultado.dados
            );

        } else {
            alert(
                `Falha na sincronização: ${
                    resultado?.erro
                    ?? "erro desconhecido"
                }`
            );
        }

    } catch (errorSincronizacao) {
        console.error(
            "Erro crítico:",
            errorSincronizacao
        );

        alert(
            "Erro ao tentar conectar com a API."
        );

    } finally {
        botao.innerHTML =
            textoOriginal;

        botao.disabled =
            false;

        botao.style.background =
            corOriginal;
    }
}


// ==========================================
// INICIALIZAÇÃO DA APLICAÇÃO
// ==========================================

async function iniciarAplicacao() {
    try {
        inicializarMapaLeaflet();

        inicializarBuscaMapa({
            renderizarRotas
        });

        await inicializarPainelContextual();

        const botaoSete =
            document.getElementById(
                "btn-sync-sete"
            );

        if (botaoSete) {
            botaoSete.removeAttribute(
                "onclick"
            );

            botaoSete.addEventListener(
                "click",
                sincronizarComSete
            );
        }

        await carregarMapa();
        await inicializarCadastroRapido();

    } catch (errorInicializacao) {
        console.error(
            "Erro ao inicializar a aplicação:",
            errorInicializacao
        );

        const painel =
            document.getElementById(
                "info-escola"
            );

        if (painel) {
            painel.innerHTML = erro(
                "Não foi possível inicializar a aplicação."
            );
        }
    }
}


document.addEventListener(
    "DOMContentLoaded",
    iniciarAplicacao
);
