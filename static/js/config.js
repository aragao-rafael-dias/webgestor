// ==========================================
// CONFIG.JS
// ==========================================

export const CONFIG = Object.freeze({
    centro: [-10.915, -37.669],
    zoom: 13,
    maxZoom: 19,

    tileLayer:
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",

    attribution:
        "© OpenStreetMap contributors",

    paineis: Object.freeze({
        rotas: Object.freeze({
            nome: "rotasPane",
            zIndex: 410
        }),

        escolas: Object.freeze({
            nome: "escolasPane",
            zIndex: 620
        })
    })
});


export const coresRegioes = Object.freeze({
    "1": "#4CAF50",
    "2": "#3182BD",
    "3": "#DE2D26",
    "4": "#FFEB3B",
    "5": "#9B4D96",
    "6": "#ED8936",
    "7": "#5E2D79",

    // Região Universitária
    "universidade": "#009688"
});


export const nomesRegioes = Object.freeze({
    "1": "Região 1",
    "2": "Região 2",
    "3": "Região 3",
    "4": "Região 4",
    "5": "Região 5",
    "6": "Região 6",
    "7": "Região 7",
    "universidade": "Região Universitária"
});
