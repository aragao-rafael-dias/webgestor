// ==========================================
// ESCOLAS.JS
// ==========================================

import { AppState } from "./state.js";
import { obterId, escapeHtml } from "./utils.js";
import {
    nomeEscola,
    diretor,
    telefone
} from "./props.js";
import { fichaEscola } from "./templates/escolas.js";
import {
    carregarRequisicoes,
    novaRequisicao
} from "./requisicoes.js";
import { carregarVisaoGeral } from "./dashboard.js";

export function carregarEscolas(map, geojson) {
    if (AppState.layers.escolas) {
        map.removeLayer(AppState.layers.escolas);
    }

    AppState.escolas = {};

    AppState.layers.escolas = L.geoJSON(geojson, {
        pointToLayer(_feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 8,
                fillColor: "#ffff00",
                color: "#800000",
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            });
        },

        onEachFeature(feature, layer) {
            const props = feature.properties ?? {};
            const id = obterId(feature);
            const nome = nomeEscola(props);

            if (id !== "") {
                AppState.escolas[id] = nome;
            }

            layer.bindTooltip(
                `<strong>${escapeHtml(nome)}</strong>`,
                { direction: "top" }
            );

            layer.on("click", () => {
                if (id === "") {
                    alert("Esta escola não possui um identificador válido.");
                    return;
                }

                abrirFichaEscola(id, nome, props);
            });
        }
    }).addTo(map);

    return AppState.layers.escolas;
}

export function abrirFichaEscola(id, nome, props = {}) {
    const painel = document.getElementById("info-escola");

    if (!painel) {
        return;
    }

    painel.innerHTML = fichaEscola({
        id,
        nome,
        diretor: diretor(props),
        telefone: telefone(props)
    });

    document
        .getElementById("btn-voltar-dashboard")
        ?.addEventListener("click", carregarVisaoGeral);

    document
        .getElementById(`btn-nova-req-${id}`)
        ?.addEventListener("click", () => novaRequisicao(id));

    carregarRequisicoes(id);
}
