// ==========================================
// ESCOLAS
// ==========================================

import { CONFIG } from "./config.js";
import { apiGet } from "./api.js";
import { AppState } from "./state.js";

import {
    obterId,
    escapeHtml
} from "./utils.js";

import {
    nomeEscola,
    diretor,
    telefone
} from "./props.js";

import {
    fichaEscola
} from "./templates/escolas.js";

import {
    carregarRequisicoes,
    novaRequisicao,
    prepararFormularioRequisicaoEscola
} from "./requisicoes.js";

import {
    carregarVisaoGeral
} from "./dashboard.js";


// ==========================================
// PERFIL DO USUÁRIO
// ==========================================

function obterPerfilUsuario() {
    return String(
        document.body
            .dataset
            .perfilUsuario
        ?? ""
    )
        .trim()
        .toUpperCase();
}


function usuarioEhDiretor() {
    return (
        obterPerfilUsuario()
        === "DIRETOR"
    );
}


// ==========================================
// ESCOLAS VINCULADAS AO DIRETOR
// ==========================================

async function carregarEscolasDoDiretor() {
    AppState.escolasDiretor.clear();

    if (!usuarioEhDiretor()) {
        return;
    }

    try {
        const escolas = await apiGet(
            "/api/minhas-escolas"
        );

        if (!Array.isArray(escolas)) {
            return;
        }

        escolas.forEach(
            escola => {
                AppState.escolasDiretor.add(
                    String(escola.id)
                );
            }
        );

    } catch (errorCarregamento) {
        console.error(
            "Erro ao carregar escolas vinculadas:",
            errorCarregamento
        );

        AppState.escolasDiretor.clear();
    }
}


function diretorPodeCriarNaEscola(
    escolaId
) {
    if (!usuarioEhDiretor()) {
        return false;
    }

    return AppState.escolasDiretor.has(
        String(escolaId)
    );
}


// ==========================================
// ÍCONES DAS ESCOLAS
// ==========================================

function criarIconeEscola(
    possuiAlerta = false
) {
    const conteudo = possuiAlerta
        ? "!"
        : "🏫";

    const classeEstado = possuiAlerta
        ? "marcador-escola--alerta"
        : "marcador-escola--normal";

    return L.divIcon({
        className:
            "icone-escola-leaflet",

        html: `
            <div
                class="
                    marcador-escola
                    ${classeEstado}
                "
            >
                <span>
                    ${conteudo}
                </span>
            </div>
        `,

        iconSize: [38, 44],
        iconAnchor: [19, 42],
        tooltipAnchor: [0, -38]
    });
}


// ==========================================
// ATUALIZAR UM MARCADOR
// ==========================================

function atualizarIconeEscola(
    escolaId,
    possuiAlerta
) {
    const id = String(
        escolaId
    );

    const marcador =
        AppState.marcadoresEscolas[id];

    if (!marcador) {
        return;
    }

    marcador.setIcon(
        criarIconeEscola(
            possuiAlerta
        )
    );

    marcador.setZIndexOffset(
        possuiAlerta
            ? 1000
            : 0
    );
}


// ==========================================
// ALERTAS DE REQUISIÇÕES
// ==========================================

export async function atualizarAlertasEscolas() {
    try {
        const alertas = await apiGet(
            "/api/requisicoes/alertas"
        );

        const idsComAlerta = new Set();

        if (Array.isArray(alertas)) {
            alertas.forEach(
                alerta => {
                    idsComAlerta.add(
                        String(
                            alerta.escola_id
                        )
                    );
                }
            );
        }

        AppState.escolasComAlerta.clear();

        idsComAlerta.forEach(
            escolaId => {
                AppState
                    .escolasComAlerta
                    .add(escolaId);
            }
        );

        Object
            .keys(
                AppState.marcadoresEscolas
            )
            .forEach(
                escolaId => {
                    atualizarIconeEscola(
                        escolaId,
                        idsComAlerta.has(
                            escolaId
                        )
                    );
                }
            );

    } catch (errorCarregamento) {
        console.error(
            "Erro ao atualizar alertas das escolas:",
            errorCarregamento
        );
    }
}


// ==========================================
// CARREGAR ESCOLAS NO MAPA
// ==========================================

export async function carregarEscolas(
    map,
    geojson
) {
    await carregarEscolasDoDiretor();

    if (AppState.layers.escolas) {
        map.removeLayer(
            AppState.layers.escolas
        );
    }

    AppState.escolas = {};
    AppState.marcadoresEscolas = {};

    AppState.layers.escolas = L.geoJSON(
        geojson,
        {
            pointToLayer(feature, latlng) {
                const id = String(
                    obterId(feature)
                );

                const possuiAlerta =
                    AppState
                        .escolasComAlerta
                        .has(id);

                return L.marker(
                    latlng,
                    {
                        pane:
                            CONFIG
                                .paineis
                                .escolas
                                .nome,

                        icon:
                            criarIconeEscola(
                                possuiAlerta
                            ),

                        zIndexOffset:
                            possuiAlerta
                                ? 1000
                                : 0
                    }
                );
            },

            onEachFeature(feature, layer) {
                const props =
                    feature.properties ?? {};

                const id = String(
                    obterId(feature)
                );

                const nome =
                    nomeEscola(props);

                if (id !== "") {
                    AppState.escolas[id] =
                        nome;

                    AppState
                        .marcadoresEscolas[id] =
                        layer;
                }

                layer.bindTooltip(
                    `
                        <strong>
                            ${escapeHtml(nome)}
                        </strong>
                    `,
                    {
                        direction: "top"
                    }
                );

                layer.on(
                    "click",
                    () => {
                        if (id === "") {
                            alert(
                                "Esta escola não possui " +
                                "um identificador válido."
                            );

                            return;
                        }

                        abrirFichaEscola(
                            id,
                            nome,
                            props
                        );
                    }
                );
            }
        }
    ).addTo(map);

    return AppState.layers.escolas;
}


// ==========================================
// ABRIR FICHA DA ESCOLA
// ==========================================

export function abrirFichaEscola(
    id,
    nome,
    props = {}
) {
    const painel =
        document.getElementById(
            "info-escola"
        );

    if (!painel) {
        return;
    }

    const podeCriarRequisicao =
        diretorPodeCriarNaEscola(id);

    painel.innerHTML = fichaEscola({
        id,
        nome,

        diretor:
            diretor(props),

        telefone:
            telefone(props),

        podeCriarRequisicao
    });

    document
        .getElementById(
            "btn-voltar-dashboard"
        )
        ?.addEventListener(
            "click",
            carregarVisaoGeral
        );

    if (podeCriarRequisicao) {
        prepararFormularioRequisicaoEscola(
            id
        );

        document
            .getElementById(
                `btn-nova-req-${id}`
            )
            ?.addEventListener(
                "click",
                () => {
                    novaRequisicao(id);
                }
            );
    }

    carregarRequisicoes(
        id
    );
}


// ==========================================
// ATUALIZAÇÃO AUTOMÁTICA DOS ALERTAS
// ==========================================

window.addEventListener(
    "websig:requisicao-alterada",
    () => {
        atualizarAlertasEscolas();
    }
);