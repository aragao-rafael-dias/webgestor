// ==========================================
// PROPS.JS
// ==========================================

import { valor } from "./utils.js";

export function nomeEscola(props = {}) {
    return valor(
        props.nome,
        props.NOME,
        props.Nome,
        props.nome_escola,
        props.NOME_ESCOLA
    ) || "Sem Nome Definido";
}

export function diretor(props = {}) {
    return valor(
        props.diretor,
        props.DIRETOR,
        props.nome_diretor,
        props.NOME_DIRETOR
    ) || "Sem Nome Definido";
}

export function telefone(props = {}) {
    return valor(
        props.telefone,
        props.TELEFONE,
        props.fone,
        props.FONE
    ) || "Sem Número Definido";
}

export function nomeRota(props = {}) {
    return valor(
        props.nome_rota,
        props.NOME_ROTA,
        props.nome,
        props.NOME
    ) || "Sem Identificação";
}

export function regiao(props = {}) {
    return valor(
        props.regiao,
        props.REGIAO,
        props.Regiao,
        props.região,
        props.Região
    );
}

export function trecho(props = {}) {
    return valor(
        props.trecho,
        props.TRECHO
    ) || "Não Informado";
}

export function totalPontos(props = {}) {
    const total = valor(
        props.total_pontos,
        props.TOTAL_PONTOS
    );

    return total === "" ? 0 : Number(total);
}
