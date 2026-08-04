// ==========================================
// BUSCA UNIFICADA DO MAPA
// Escolas, localidades e rotas escolares
// ==========================================

import {
    AppState
} from "./state.js";

import {
    escapeHtml,
    obterId
} from "./utils.js";


const CSS_BUSCA_URL =
    "/static/css/busca_mapa.css";

const ATRASO_BUSCA_MS = 280;

let controladorBusca = null;
let temporizadorBusca = null;
let indiceAtivo = -1;
let resultadosAtuais = [];
let marcadorTemporario = null;
let renderizarRotasCallback = null;


// ==========================================
// HELPERS
// ==========================================

function carregarCssBusca() {
    if (
        document.querySelector(
            'link[data-websig-busca-mapa="1"]'
        )
    ) {
        return;
    }

    const link =
        document.createElement("link");

    link.rel = "stylesheet";
    link.href = CSS_BUSCA_URL;

    link.dataset.websigBuscaMapa =
        "1";

    document.head.appendChild(
        link
    );
}


function textoSeguro(
    valor,
    padrao = ""
) {
    const texto = String(
        valor ?? ""
    ).trim();

    return texto || padrao;
}


function numeroSeguro(
    valor
) {
    const numero = Number(valor);

    return Number.isFinite(numero)
        ? numero
        : null;
}


function esconderResultados() {
    const painel =
        document.getElementById(
            "busca-mapa-resultados"
        );

    if (!painel) {
        return;
    }

    painel.hidden = true;
    painel.innerHTML = "";

    resultadosAtuais = [];
    indiceAtivo = -1;
}


function mostrarMensagem(
    mensagem,
    classe = ""
) {
    const painel =
        document.getElementById(
            "busca-mapa-resultados"
        );

    if (!painel) {
        return;
    }

    painel.hidden = false;

    painel.innerHTML = `
        <div class="
            busca-mapa-mensagem
            ${classe}
        ">
            ${escapeHtml(mensagem)}
        </div>
    `;
}


function removerMarcadorTemporario() {
    if (
        marcadorTemporario
        && AppState.map
    ) {
        AppState.map.removeLayer(
            marcadorTemporario
        );
    }

    marcadorTemporario = null;
}


function iconeTipo(
    tipo
) {
    const icones = {
        escola: "🏫",
        rota: "🚌",
        localidade: "📍"
    };

    return icones[tipo] ?? "🔎";
}


function rotuloTipo(
    tipo
) {
    const rotulos = {
        escola: "Escola",
        rota: "Rota escolar",
        localidade: "Localidade"
    };

    return rotulos[tipo]
        ?? "Resultado";
}


function encontrarCheckboxRegiao(
    valor
) {
    return [
        ...document.querySelectorAll(
            ".filtro-regiao"
        )
    ].find(
        checkbox =>
            checkbox.value
            === String(valor)
    );
}


function encontrarCamadaRota(
    rotaId
) {
    const camadaRotas =
        AppState.layers?.rotas;

    if (
        !camadaRotas
        || typeof camadaRotas
            .eachLayer !== "function"
    ) {
        return null;
    }

    let camadaEncontrada = null;

    camadaRotas.eachLayer(
        camada => {
            if (camadaEncontrada) {
                return;
            }

            const feature =
                camada.feature;

            if (!feature) {
                return;
            }

            const idFeature =
                String(
                    obterId(feature)
                );

            if (
                idFeature
                === String(rotaId)
            ) {
                camadaEncontrada =
                    camada;
            }
        }
    );

    return camadaEncontrada;
}


function criarMarcadorTemporario(
    resultado
) {
    removerMarcadorTemporario();

    const lat =
        numeroSeguro(resultado.lat);

    const lon =
        numeroSeguro(resultado.lon);

    if (
        lat === null
        || lon === null
        || !AppState.map
    ) {
        return null;
    }

    marcadorTemporario =
        L.circleMarker(
            [lat, lon],
            {
                radius: 9,
                color: "#ffffff",
                weight: 3,
                fillColor: "#800000",
                fillOpacity: 1
            }
        )
        .addTo(AppState.map)
        .bindPopup(
            `
                <strong>
                    ${escapeHtml(
                        textoSeguro(
                            resultado.titulo,
                            "Resultado"
                        )
                    )}
                </strong>

                <br>

                <span>
                    ${escapeHtml(
                        textoSeguro(
                            resultado.subtitulo
                        )
                    )}
                </span>
            `
        );

    marcadorTemporario.openPopup();

    return marcadorTemporario;
}


// ==========================================
// FOCO NOS RESULTADOS
// ==========================================

function focarEscola(
    resultado
) {
    const lat =
        numeroSeguro(resultado.lat);

    const lon =
        numeroSeguro(resultado.lon);

    if (
        lat !== null
        && lon !== null
        && AppState.map
    ) {
        AppState.map.setView(
            [lat, lon],
            17,
            {
                animate: true
            }
        );
    }

    const marcador =
        AppState
            .marcadoresEscolas
            ?.[
                String(resultado.id)
            ];

    if (marcador) {
        marcador.fire("click");

        if (
            typeof marcador
                .openTooltip
                === "function"
        ) {
            marcador.openTooltip();
        }

        return;
    }

    criarMarcadorTemporario(
        resultado
    );
}


function focarLocalidade(
    resultado
) {
    const lat =
        numeroSeguro(resultado.lat);

    const lon =
        numeroSeguro(resultado.lon);

    if (
        lat === null
        || lon === null
        || !AppState.map
    ) {
        return;
    }

    AppState.map.setView(
        [lat, lon],
        16,
        {
            animate: true
        }
    );

    criarMarcadorTemporario(
        resultado
    );
}


function focarRota(
    resultado
) {
    const checkbox =
        encontrarCheckboxRegiao(
            resultado.regiao_chave
        );

    if (
        checkbox
        && !checkbox.checked
    ) {
        checkbox.checked = true;
    }

    if (
        typeof renderizarRotasCallback
            === "function"
    ) {
        renderizarRotasCallback();
    }

    const bbox =
        resultado.bbox;

    if (
        Array.isArray(bbox)
        && bbox.length === 2
        && AppState.map
    ) {
        AppState.map.fitBounds(
            bbox,
            {
                padding: [35, 35],
                maxZoom: 16,
                animate: true
            }
        );

    } else {
        const lat =
            numeroSeguro(resultado.lat);

        const lon =
            numeroSeguro(resultado.lon);

        if (
            lat !== null
            && lon !== null
            && AppState.map
        ) {
            AppState.map.setView(
                [lat, lon],
                14,
                {
                    animate: true
                }
            );
        }
    }

    window.requestAnimationFrame(
        () => {
            const camada =
                encontrarCamadaRota(
                    resultado.id
                );

            if (!camada) {
                return;
            }

            if (
                typeof camada
                    .bringToFront
                    === "function"
            ) {
                camada.bringToFront();
            }

            camada.setStyle({
                weight: 8,
                color: "#00BCD4",
                opacity: 1
            });

            if (
                typeof camada
                    .openPopup
                    === "function"
            ) {
                camada.openPopup();
            }

            window.setTimeout(
                () => {
                    const grupo =
                        AppState
                            .layers
                            ?.rotas;

                    if (
                        grupo
                        && typeof grupo
                            .resetStyle
                            === "function"
                    ) {
                        grupo.resetStyle(
                            camada
                        );
                    }
                },
                4500
            );
        }
    );
}


function selecionarResultado(
    resultado
) {
    if (!resultado) {
        return;
    }

    esconderResultados();

    const input =
        document.getElementById(
            "busca-mapa-input"
        );

    if (input) {
        input.value =
            textoSeguro(
                resultado.titulo
            );
    }

    switch (resultado.tipo) {
        case "escola":
            focarEscola(resultado);
            break;

        case "rota":
            focarRota(resultado);
            break;

        case "localidade":
            focarLocalidade(resultado);
            break;

        default:
            break;
    }
}


// ==========================================
// RENDERIZAÇÃO
// ==========================================

function renderizarResultados(
    resultados
) {
    const painel =
        document.getElementById(
            "busca-mapa-resultados"
        );

    if (!painel) {
        return;
    }

    resultadosAtuais = Array.isArray(
        resultados
    )
        ? resultados
        : [];

    indiceAtivo = -1;

    if (
        resultadosAtuais.length === 0
    ) {
        mostrarMensagem(
            "Nenhum resultado encontrado."
        );

        return;
    }

    const grupos = [
        {
            tipo: "escola",
            titulo: "Escolas"
        },
        {
            tipo: "rota",
            titulo: "Rotas escolares"
        },
        {
            tipo: "localidade",
            titulo: "Localidades e pontos"
        }
    ];

    let html = "";

    grupos.forEach(
        grupo => {
            const itens =
                resultadosAtuais.filter(
                    item =>
                        item.tipo
                        === grupo.tipo
                );

            if (itens.length === 0) {
                return;
            }

            html += `
                <section
                    class="busca-mapa-grupo"
                >
                    <h5>
                        ${escapeHtml(
                            grupo.titulo
                        )}
                    </h5>
            `;

            itens.forEach(
                item => {
                    const indiceGlobal =
                        resultadosAtuais
                            .indexOf(item);

                    html += `
                        <button
                            type="button"
                            class="
                                busca-mapa-resultado
                            "
                            data-indice="${
                                indiceGlobal
                            }"
                            role="option"
                        >
                            <span
                                class="
                                    busca-mapa-icone
                                "
                                aria-hidden="true"
                            >
                                ${iconeTipo(
                                    item.tipo
                                )}
                            </span>

                            <span
                                class="
                                    busca-mapa-textos
                                "
                            >
                                <strong>
                                    ${escapeHtml(
                                        textoSeguro(
                                            item.titulo,
                                            rotuloTipo(
                                                item.tipo
                                            )
                                        )
                                    )}
                                </strong>

                                <small>
                                    ${escapeHtml(
                                        textoSeguro(
                                            item.subtitulo,
                                            rotuloTipo(
                                                item.tipo
                                            )
                                        )
                                    )}
                                </small>
                            </span>

                            <span
                                class="
                                    busca-mapa-tipo
                                "
                            >
                                ${escapeHtml(
                                    rotuloTipo(
                                        item.tipo
                                    )
                                )}
                            </span>
                        </button>
                    `;
                }
            );

            html += `
                </section>
            `;
        }
    );

    painel.innerHTML = html;
    painel.hidden = false;

    painel
        .querySelectorAll(
            ".busca-mapa-resultado"
        )
        .forEach(
            botao => {
                botao.addEventListener(
                    "click",
                    () => {
                        const indice =
                            Number(
                                botao
                                    .dataset
                                    .indice
                            );

                        selecionarResultado(
                            resultadosAtuais[
                                indice
                            ]
                        );
                    }
                );
            }
        );
}


function atualizarResultadoAtivo() {
    const botoes = [
        ...document.querySelectorAll(
            ".busca-mapa-resultado"
        )
    ];

    botoes.forEach(
        botao => {
            const indice =
                Number(
                    botao.dataset.indice
                );

            const ativo =
                indice
                === indiceAtivo;

            botao.classList.toggle(
                "busca-mapa-resultado--ativo",
                ativo
            );

            botao.setAttribute(
                "aria-selected",
                ativo
                    ? "true"
                    : "false"
            );

            if (ativo) {
                botao.scrollIntoView({
                    block: "nearest"
                });
            }
        }
    );
}


// ==========================================
// CONSULTA
// ==========================================

async function executarBusca(
    consulta
) {
    const termo =
        textoSeguro(consulta);

    if (termo.length < 2) {
        mostrarMensagem(
            "Digite pelo menos 2 caracteres."
        );

        return;
    }

    if (controladorBusca) {
        controladorBusca.abort();
    }

    controladorBusca =
        new AbortController();

    mostrarMensagem(
        "Buscando...",
        "busca-mapa-mensagem--carregando"
    );

    try {
        const resposta = await fetch(
            `/api/busca-mapa?q=${
                encodeURIComponent(termo)
            }`,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    Accept:
                        "application/json"
                },
                signal:
                    controladorBusca.signal
            }
        );

        const dados =
            await resposta.json();

        if (!resposta.ok) {
            throw new Error(
                dados?.erro
                ?? "Erro ao realizar a busca."
            );
        }

        renderizarResultados(
            dados?.resultados
        );

    } catch (erroBusca) {
        if (
            erroBusca?.name
            === "AbortError"
        ) {
            return;
        }

        console.error(
            "Erro na busca do mapa:",
            erroBusca
        );

        mostrarMensagem(
            erroBusca?.message
            ?? "Não foi possível realizar a busca.",
            "busca-mapa-mensagem--erro"
        );
    }
}


// ==========================================
// EVENTOS
// ==========================================

function agendarBusca(
    valor
) {
    window.clearTimeout(
        temporizadorBusca
    );

    temporizadorBusca =
        window.setTimeout(
            () => executarBusca(
                valor
            ),
            ATRASO_BUSCA_MS
        );
}


function tratarTeclado(
    evento
) {
    if (
        resultadosAtuais.length === 0
    ) {
        if (
            evento.key
            === "Escape"
        ) {
            esconderResultados();
        }

        return;
    }

    if (
        evento.key
        === "ArrowDown"
    ) {
        evento.preventDefault();

        indiceAtivo = Math.min(
            indiceAtivo + 1,
            resultadosAtuais.length - 1
        );

        atualizarResultadoAtivo();
        return;
    }

    if (
        evento.key
        === "ArrowUp"
    ) {
        evento.preventDefault();

        indiceAtivo = Math.max(
            indiceAtivo - 1,
            0
        );

        atualizarResultadoAtivo();
        return;
    }

    if (
        evento.key
        === "Enter"
        && indiceAtivo >= 0
    ) {
        evento.preventDefault();

        selecionarResultado(
            resultadosAtuais[
                indiceAtivo
            ]
        );

        return;
    }

    if (
        evento.key
        === "Escape"
    ) {
        esconderResultados();
    }
}


// ==========================================
// ESTRUTURA VISUAL
// ==========================================

function criarBarraBusca() {
    if (
        document.getElementById(
            "busca-mapa-container"
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
        document.createElement("section");

    container.id =
        "busca-mapa-container";

    container.innerHTML = `
        <h4>
            🔎 Buscar no mapa
        </h4>

        <div
            class="busca-mapa-campo"
        >
            <input
                type="search"
                id="busca-mapa-input"
                placeholder="Escola, localidade ou rota..."
                autocomplete="off"
                spellcheck="false"
                aria-label="Buscar escola, localidade ou rota escolar"
                aria-controls="busca-mapa-resultados"
                aria-autocomplete="list"
            >

            <button
                type="button"
                id="busca-mapa-limpar"
                class="busca-mapa-limpar"
                title="Limpar busca"
                aria-label="Limpar busca"
            >
                ×
            </button>
        </div>

        <p
            class="busca-mapa-ajuda"
        >
            Pesquise por nome de escola,
            código da rota, região,
            povoado, referência ou logradouro.
        </p>

        <div
            id="busca-mapa-resultados"
            class="busca-mapa-resultados"
            role="listbox"
            hidden
        ></div>
    `;

    painelInfo.parentNode.insertBefore(
        container,
        painelInfo
    );

    const input =
        document.getElementById(
            "busca-mapa-input"
        );

    const botaoLimpar =
        document.getElementById(
            "busca-mapa-limpar"
        );

    input?.addEventListener(
        "input",
        evento => {
            const valor =
                evento.target.value;

            if (
                textoSeguro(valor)
                    .length < 2
            ) {
                esconderResultados();
                return;
            }

            agendarBusca(
                valor
            );
        }
    );

    input?.addEventListener(
        "keydown",
        tratarTeclado
    );

    input?.addEventListener(
        "focus",
        () => {
            if (
                resultadosAtuais.length > 0
            ) {
                const painel =
                    document.getElementById(
                        "busca-mapa-resultados"
                    );

                if (painel) {
                    painel.hidden = false;
                }
            }
        }
    );

    botaoLimpar?.addEventListener(
        "click",
        () => {
            if (input) {
                input.value = "";
                input.focus();
            }

            removerMarcadorTemporario();
            esconderResultados();
        }
    );

    document.addEventListener(
        "click",
        evento => {
            if (
                !container.contains(
                    evento.target
                )
            ) {
                esconderResultados();
            }
        }
    );
}


// ==========================================
// INICIALIZAÇÃO
// ==========================================

export function inicializarBuscaMapa({
    renderizarRotas
} = {}) {
    renderizarRotasCallback =
        renderizarRotas
        ?? null;

    carregarCssBusca();
    criarBarraBusca();
}
