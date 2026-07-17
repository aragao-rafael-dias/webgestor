// ==========================================
// API
// ==========================================

const TIMEOUT_PADRAO = 15000;

async function request(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(
        () => controller.abort(),
        options.timeout ?? TIMEOUT_PADRAO
    );

    const method = (options.method ?? "GET").toUpperCase();
    const headers = new Headers(options.headers ?? {});
    let body = options.body;

    if (body !== undefined && body !== null && !(body instanceof FormData)) {
        if (typeof body !== "string") {
            body = JSON.stringify(body);
        }

        if (!headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json");
        }
    }

    try {
        const resposta = await fetch(url, {
            ...options,
            method,
            headers,
            body,
            signal: controller.signal
        });

        const contentType = resposta.headers.get("content-type") ?? "";
        const temJson = contentType.includes("application/json");

        if (!resposta.ok) {
            let mensagem = `Erro ${resposta.status}`;

            try {
                const detalhe = temJson
                    ? await resposta.json()
                    : await resposta.text();

                if (typeof detalhe === "string" && detalhe.trim()) {
                    mensagem = detalhe;
                } else if (detalhe && typeof detalhe === "object") {
                    mensagem =
                        detalhe.erro ??
                        detalhe.message ??
                        detalhe.detail ??
                        mensagem;
                }
            } catch (_) {
            }

            throw new Error(mensagem);
        }

        if (resposta.status === 204) {
            return null;
        }

        return temJson
            ? resposta.json()
            : resposta.text();
    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error("A requisição excedeu o tempo limite.");
        }

        throw error;
    } finally {
        clearTimeout(timeoutId);
    }
}

export function apiGet(url, options = {}) {
    return request(url, {
        ...options,
        method: "GET"
    });
}

export function apiPost(url, dados = null, options = {}) {
    return request(url, {
        ...options,
        method: "POST",
        body: dados
    });
}

export function apiPut(url, dados, options = {}) {
    return request(url, {
        ...options,
        method: "PUT",
        body: dados
    });
}

export function apiDelete(url, options = {}) {
    return request(url, {
        ...options,
        method: "DELETE"
    });
}
