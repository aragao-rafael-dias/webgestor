// ==========================================
// UTILS.JS
// ==========================================

export function valor(...campos) {
    for (const campo of campos) {
        if (campo === undefined || campo === null) {
            continue;
        }

        if (typeof campo === "string" && campo.trim() === "") {
            continue;
        }

        return campo;
    }

    return "";
}

export function obterId(feature = {}) {
    const props = feature.properties ?? {};

    return valor(
        feature.id,
        props.id,
        props.ID,
        props.gid,
        props.GID
    );
}

export function obterIdRegiao(props = {}) {
    const texto = valor(
        props.regiao,
        props.REGIAO,
        props.Regiao,
        props.região,
        props.Região
    );

    const match = String(texto).match(/\d+/);

    return match
        ? String(Number(match[0]))
        : String(texto).trim();
}

export function abrirNovaAba(url) {
    const novaAba = window.open(url, "_blank", "noopener,noreferrer");

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
