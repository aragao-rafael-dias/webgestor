// ==========================================
// STATE
// ==========================================

export const AppState = {
    map: null,

    layers: {
        escolas: null,
        rotas: null
    },

    escolas: {},
    rotas: null,

    marcadoresEscolas: {},

    escolasComAlerta: new Set(),

    escolasDiretor: new Set()
};