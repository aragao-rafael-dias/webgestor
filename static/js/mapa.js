// ==========================================
// MAPA.JS
// Ponto de entrada da aplicação no navegador
// ==========================================

import { CONFIG, coresRegioes } from "./config.js";
import { AppState } from "./state.js";
import { apiGet, apiPost } from "./api.js";
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
import { carregarEscolas } from "./escolas.js";
import { carregarVisaoGeral } from "./dashboard.js";
import { popupRota } from "./templates/popup.js";
import { erro } from "./templates/ui.js";

export function inicializarMapaLeaflet() {
    if (AppState.map) {
        return AppState.map;
    }

    const elementoMapa = document.getElementById("map");

    if (!elementoMapa) {
        throw new Error("Elemento #map não encontrado.");
    }

    if (typeof L === "undefined") {
        throw new Error("Leaflet não foi carregado.");
    }

    AppState.map = L.map("map").setView(
        CONFIG.centro,
        CONFIG.zoom
    );

    L.tileLayer(CONFIG.tileLayer, {
        maxZoom: CONFIG.maxZoom,
        attribution: CONFIG.attribution
    }).addTo(AppState.map);

    return AppState.map;
}

export async function carregarMapa() {
    try {
        const [escolas, rotas] = await Promise.all([
            apiGet("/api/escolas"),
            apiGet("/api/rotas")
        ]);

        carregarEscolas(AppState.map, escolas);
        AppState.rotas = rotas;

        criarFiltroRegioes();
        renderizarRotas();
        await carregarVisaoGeral();
    } catch (errorCarregamento) {
        console.error("Erro ao carregar o mapa:", errorCarregamento);

        const painel = document.getElementById("info-escola");

        if (painel) {
            painel.innerHTML = erro(
                "Erro ao carregar os dados do mapa."
            );
        }
    }
}

export function renderizarRotas() {
    if (!AppState.map || !AppState.rotas) {
        return;
    }

    if (AppState.layers.rotas) {
        AppState.map.removeLayer(AppState.layers.rotas);
    }

    const checkboxes = [
        ...document.querySelectorAll(".filtro-regiao:checked")
    ];
    const regioesPermitidas = checkboxes.map(
        (checkbox) => checkbox.value
    );

    AppState.layers.rotas = L.geoJSON(AppState.rotas, {
        filter(feature) {
            const idRegiao = obterIdRegiao(
                feature.properties ?? {}
            );

            return regioesPermitidas.length === 0
                ? false
                : regioesPermitidas.includes(idRegiao);
        },

        style(feature) {
            const idRegiao = obterIdRegiao(
                feature.properties ?? {}
            );

            return {
                color: coresRegioes[idRegiao] ?? "#800000",
                weight: 4,
                opacity: 0.8,
                lineJoin: "round"
            };
        },

        onEachFeature(feature, layer) {
            configurarRota(feature, layer);
        }
    }).addTo(AppState.map);
}

function configurarRota(feature, layer) {
    const props = feature.properties ?? {};
    const idRota = obterId(feature);
    const idRegiao = obterIdRegiao(props);
    const corBase = coresRegioes[idRegiao] ?? "#800000";

    layer.bindPopup(
        popupRota({
            id: idRota,
            nome: nomeRota(props),
            regiao: regiao(props) || idRegiao || "Não informada",
            trecho: trecho(props),
            totalPontos: totalPontos(props)
        })
    );

    layer.on("popupopen", (evento) => {
        const botao = evento.popup
            .getElement()
            ?.querySelector(".btn-memorial");

        if (!botao) {
            return;
        }

        if (idRota === "") {
            botao.disabled = true;
            botao.title = "Rota sem identificador válido";
            return;
        }

        botao.addEventListener(
            "click",
            () => gerarMemorial(idRota),
            { once: true }
        );
    });

    layer.on("mouseover", (evento) => {
        evento.target.setStyle({
            weight: 7,
            color: "#ffff00",
            opacity: 1
        });
    });

    layer.on("mouseout", (evento) => {
        evento.target.setStyle({
            weight: 4,
            color: corBase,
            opacity: 0.8
        });
    });
}

export function criarFiltroRegioes() {
    if (document.getElementById("filtro-regioes-container")) {
        return;
    }

    const painelInfo = document.getElementById("info-escola");

    if (!painelInfo?.parentNode) {
        return;
    }

    const container = document.createElement("div");
    container.id = "filtro-regioes-container";
    Object.assign(container.style, {
        padding: "10px",
        marginBottom: "15px",
        background: "#f9f9f9",
        border: "1px solid #ddd",
        borderRadius: "5px"
    });

    const tituloFiltro = document.createElement("h4");
    tituloFiltro.textContent = "🗺️ Filtrar por Região";
    Object.assign(tituloFiltro.style, {
        margin: "0 0 10px 0",
        color: "#800000",
        borderBottom: "2px solid #800000",
        paddingBottom: "3px"
    });
    container.appendChild(tituloFiltro);

    Object.entries(coresRegioes).forEach(([idRegiao, cor]) => {
        const label = document.createElement("label");
        Object.assign(label.style, {
            display: "block",
            marginBottom: "5px",
            cursor: "pointer",
            fontSize: "14px"
        });

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "filtro-regiao";
        checkbox.value = idRegiao;
        checkbox.checked = true;
        checkbox.addEventListener("change", renderizarRotas);

        const iconeCor = document.createElement("span");
        iconeCor.textContent = " ■ ";
        iconeCor.style.color = cor;

        if (idRegiao === "4") {
            iconeCor.style.textShadow = "1px 1px 1px #888";
        }

        label.append(
            checkbox,
            iconeCor,
            document.createTextNode(` Região ${idRegiao}`)
        );
        container.appendChild(label);
    });

    painelInfo.parentNode.insertBefore(container, painelInfo);
}

export async function gerarMemorial(rotaId) {
    if (rotaId === undefined || rotaId === null || rotaId === "") {
        alert("A rota não possui um identificador válido.");
        return;
    }

    await tocarBip("resposta");
    abrirNovaAba(
        `/api/rotas/${encodeURIComponent(rotaId)}/memorial`
    );
}

export async function sincronizarComSete() {
    const botao = document.getElementById("btn-sync-sete");

    if (!botao) {
        return;
    }

    const textoOriginal = botao.innerHTML;
    const corOriginal = botao.style.background;

    botao.innerHTML = "⏳ Sincronizando com Gov. Federal...";
    botao.disabled = true;
    botao.style.background = "#9e9e9e";

    try {
        const resultado = await apiPost(
            "/api/integracao/sincronizar"
        );

        if (resultado?.sucesso) {
            await tocarBip("resposta");
            alert(resultado.mensagem);
            console.log(
                "DADOS IMPORTADOS DO SETE:",
                resultado.dados
            );
        } else {
            alert(
                `Falha na sincronização: ${
                    resultado?.erro ?? "erro desconhecido"
                }`
            );
        }
    } catch (errorSincronizacao) {
        console.error("Erro crítico:", errorSincronizacao);
        alert("Erro ao tentar conectar com a API.");
    } finally {
        botao.innerHTML = textoOriginal;
        botao.disabled = false;
        botao.style.background = corOriginal;
    }
}

async function iniciarAplicacao() {
    try {
        inicializarMapaLeaflet();

        const botaoSete = document.getElementById("btn-sync-sete");

        if (botaoSete) {
            botaoSete.removeAttribute("onclick");
            botaoSete.addEventListener(
                "click",
                sincronizarComSete
            );
        }

        await carregarMapa();
    } catch (errorInicializacao) {
        console.error(
            "Erro ao inicializar a aplicação:",
            errorInicializacao
        );
    }
}

document.addEventListener("DOMContentLoaded", iniciarAplicacao);
