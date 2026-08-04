// ==========================================
// UTILS.JS
// ==========================================

export function valor(...campos) {
    for (const campo of campos) {
        if (
            campo === undefined
            || campo === null
        ) {
            continue;
        }

        if (
            typeof campo === "string"
            && campo.trim() === ""
        ) {
            continue;
        }

        return campo;
    }

    return "";
}


export function obterId(feature = {}) {
    const props =
        feature.properties ?? {};

    return valor(
        feature.id,
        props.id,
        props.ID,
        props.gid,
        props.GID
    );
}


function normalizarTextoRegiao(valorOriginal) {
    return String(valorOriginal ?? "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim()
        .toUpperCase();
}


export function obterIdRegiao(props = {}) {
    const textoOriginal = valor(
        props.regiao,
        props.REGIAO,
        props.Regiao,
        props.região,
        props.Região
    );

    const textoNormalizado =
        normalizarTextoRegiao(
            textoOriginal
        );

    /*
     * O GeoJSON usa:
     *
     *     REGIÃO UNIVERSIDADE
     *
     * Também aceitamos variações como:
     *
     *     REGIÃO UNIVERSITÁRIA
     *     UNIVERSIDADE
     *     UNIVERSITARIA
     */
    if (
        textoNormalizado.includes(
            "UNIVERSIT"
        )
        || textoNormalizado.includes(
            "UNIVERSIDADE"
        )
    ) {
        return "universidade";
    }

    const correspondenciaNumero =
        textoNormalizado.match(/\d+/);

    if (correspondenciaNumero) {
        return String(
            Number(
                correspondenciaNumero[0]
            )
        );
    }

    return textoNormalizado
        .toLowerCase()
        .replace(/\s+/g, "_");
}


export function abrirNovaAba(url) {
    const novaAba = window.open(
        url,
        "_blank",
        "noopener,noreferrer"
    );

    if (novaAba) {
        novaAba.opener = null;
    }
}


export function escapeHtml(valorOriginal) {
    return String(valorOriginal ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
