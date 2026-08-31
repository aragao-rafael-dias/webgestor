(() => {
    "use strict";

    const CENTRO_LAGARTO = {
        latitude: -10.9160,
        longitude: -37.6680,
        zoom: 13,
    };

    const CHAVE_FUNDO = "semdu:websig:fundo";
    const CHAVE_OPACIDADE = "semdu:websig:opacidade-ortofoto";

    const estado = {
        mapa: null,
        fundos: new Map(),
        fundoAtualId: null,
        opacidadeOrtofoto: 1,
        barraSuperior: null,
        barraInferior: null,
        menuAberto: null,
        dialogoEstilos: null,
        dialogoCoordenadas: null,
        toast: null,
        preferenciasLocais: {},
        camadaMedicoes: null,
        camadaLocalizacao: null,
        marcadorLocalizacao: null,
        circuloPrecisao: null,
        medicao: {
            modo: null,
            pontos: [],
            geometria: null,
            preview: null,
            marcadores: [],
            concluida: false,
        },
        painelMedicao: null,
    };

    function csrfToken() {
        return document.querySelector(
            'meta[name="csrf-token"]'
        )?.content ?? "";
    }

    async function respostaJson(resposta) {
        if (window.SemduMapa?.lerRespostaJson) {
            return window.SemduMapa.lerRespostaJson(
                resposta
            );
        }

        const texto = await resposta.text();

        try {
            return JSON.parse(texto);
        } catch {
            throw new Error(
                `Resposta inválida do servidor (HTTP ${resposta.status}).`
            );
        }
    }

    async function api(
        url,
        opcoes = {}
    ) {
        const metodo = String(
            opcoes.method ?? "GET"
        ).toUpperCase();

        const resposta = await fetch(
            url,
            {
                credentials: "same-origin",
                ...opcoes,
                headers: {
                    Accept: "application/json",
                    ...(
                        opcoes.body
                            ? {
                                "Content-Type":
                                    "application/json",
                            }
                            : {}
                    ),
                    ...(
                        metodo !== "GET"
                            ? {
                                "X-CSRFToken":
                                    csrfToken(),
                            }
                            : {}
                    ),
                    ...(opcoes.headers ?? {}),
                },
            }
        );

        const dados = await respostaJson(
            resposta
        );

        if (!resposta.ok) {
            throw new Error(
                dados?.detalhes
                ?? dados?.erro
                ?? `Erro HTTP ${resposta.status}.`
            );
        }

        return dados;
    }

    function escaparHtml(valor) {
        return String(valor ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function numero(
        valor,
        padrao = 0
    ) {
        const convertido = Number(valor);
        return Number.isFinite(convertido)
            ? convertido
            : padrao;
    }

    function limitar(
        valor,
        minimo,
        maximo
    ) {
        return Math.min(
            maximo,
            Math.max(
                minimo,
                valor
            )
        );
    }

    function mostrarToast(
        mensagem,
        tipo = ""
    ) {
        if (!estado.toast) {
            const toast = document.createElement(
                "div"
            );

            toast.className =
                "semdu-ferramentas-toast";
            toast.hidden = true;
            toast.setAttribute(
                "role",
                "status"
            );
            toast.setAttribute(
                "aria-live",
                "polite"
            );

            document.body.appendChild(
                toast
            );

            estado.toast = toast;
        }

        window.clearTimeout(
            mostrarToast.temporizador
        );

        estado.toast.className =
            `semdu-ferramentas-toast ${tipo}`.trim();
        estado.toast.textContent = mensagem;
        estado.toast.hidden = false;

        window.requestAnimationFrame(
            () => {
                estado.toast.classList.add(
                    "visivel"
                );
            }
        );

        mostrarToast.temporizador =
            window.setTimeout(
                () => {
                    estado.toast.classList.remove(
                        "visivel"
                    );

                    window.setTimeout(
                        () => {
                            estado.toast.hidden = true;
                        },
                        180
                    );
                },
                3400
            );
    }

    async function copiarTexto(
        valor,
        mensagem
    ) {
        const texto = String(valor ?? "");

        try {
            if (
                navigator.clipboard
                && window.isSecureContext
            ) {
                await navigator.clipboard.writeText(
                    texto
                );
            } else {
                const area = document.createElement(
                    "textarea"
                );
                area.value = texto;
                area.style.position = "fixed";
                area.style.opacity = "0";
                document.body.appendChild(area);
                area.select();
                document.execCommand("copy");
                area.remove();
            }

            mostrarToast(
                mensagem,
                "sucesso"
            );
        } catch {
            mostrarToast(
                "Não foi possível copiar para a área de transferência.",
                "erro"
            );
        }
    }

    function icone(nome) {
        const icones = {
            fundos: `<svg viewBox="0 0 24 24"><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="m4 12 8 4 8-4M4 17l8 4 8-4"/></svg>`,
            estilo: `<svg viewBox="0 0 24 24"><path d="M4 20h6M14 4l6 6-9 9H5v-6l9-9Z"/><path d="m12 6 6 6"/></svg>`,
            rotulo: `<svg viewBox="0 0 24 24"><path d="M4 5h16M12 5v14M8 19h8"/></svg>`,
            distancia: `<svg viewBox="0 0 24 24"><path d="M4 17 17 4M7 20l-3-3 3-3M14 7l3-3 3 3"/><path d="m9 12 3 3"/></svg>`,
            azimute: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m15 6-2 7-7 2 2-7 7-2Z"/></svg>`,
            area: `<svg viewBox="0 0 24 24"><path d="m4 18 3-12 10-2 3 12-8 4-8-2Z"/><circle cx="7" cy="6" r="1"/><circle cx="17" cy="4" r="1"/><circle cx="20" cy="16" r="1"/><circle cx="12" cy="20" r="1"/><circle cx="4" cy="18" r="1"/></svg>`,
            poligonal: `<svg viewBox="0 0 24 24"><path d="m3 17 5-8 5 5 8-10"/><circle cx="3" cy="17" r="1.5"/><circle cx="8" cy="9" r="1.5"/><circle cx="13" cy="14" r="1.5"/><circle cx="21" cy="4" r="1.5"/></svg>`,
            limpar: `<svg viewBox="0 0 24 24"><path d="m4 16 8-11 8 6-7 9H7l-3-4Z"/><path d="M13 20h8"/></svg>`,
            localizar: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg>`,
            coordenada: `<svg viewBox="0 0 24 24"><path d="M4 7V4h3M17 4h3v3M20 17v3h-3M7 20H4v-3"/><circle cx="12" cy="12" r="2"/><path d="M12 6v4M12 14v4M6 12h4M14 12h4"/></svg>`,
            municipio: `<svg viewBox="0 0 24 24"><path d="m3 6 5-3 8 3 5-3v15l-5 3-8-3-5 3V6Z"/><path d="M8 3v15M16 6v15"/></svg>`,
            extensao: `<svg viewBox="0 0 24 24"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/></svg>`,
            copiar: `<svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>`,
            street: `<svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="2"/><path d="M8 21 10 13 7 11l2-4h6l2 4-3 2 2 8M10 13h4"/></svg>`,
        };

        return icones[nome] ?? "";
    }

    function criarBotaoBarra({
        acao,
        titulo,
        iconeNome,
        classe = "",
    }) {
        return `
            <button
                type="button"
                data-ferramenta-acao="${escaparHtml(acao)}"
                class="${escaparHtml(classe)}"
                title="${escaparHtml(titulo)}"
                aria-label="${escaparHtml(titulo)}"
            >
                ${icone(iconeNome)}
                <span>${escaparHtml(titulo)}</span>
            </button>
        `;
    }

    function criarBarras() {
        const area = document.querySelector(
            ".semdu-mapa-area"
        );

        if (!area) {
            return;
        }

        const superior = document.createElement(
            "nav"
        );
        superior.className =
            "semdu-barra-superior";
        superior.setAttribute(
            "aria-label",
            "Ferramentas cartográficas da SEMDU"
        );

        superior.innerHTML = `
            ${criarBotaoBarra({
                acao: "fundos",
                titulo: "Fundos",
                iconeNome: "fundos",
            })}
            ${criarBotaoBarra({
                acao: "simbologia",
                titulo: "Simbologia",
                iconeNome: "estilo",
            })}
            ${criarBotaoBarra({
                acao: "rotulos",
                titulo: "Rótulos",
                iconeNome: "rotulo",
            })}
            <span class="semdu-barra-divisor"></span>
            ${criarBotaoBarra({
                acao: "distancia",
                titulo: "Distância",
                iconeNome: "distancia",
            })}
            ${criarBotaoBarra({
                acao: "azimute",
                titulo: "Azimute",
                iconeNome: "azimute",
            })}
            ${criarBotaoBarra({
                acao: "area",
                titulo: "Área",
                iconeNome: "area",
            })}
            ${criarBotaoBarra({
                acao: "poligonal",
                titulo: "Poligonal",
                iconeNome: "poligonal",
            })}
            ${criarBotaoBarra({
                acao: "limpar-medicoes",
                titulo: "Limpar",
                iconeNome: "limpar",
            })}
        `;

        const inferior = document.createElement(
            "nav"
        );
        inferior.className =
            "semdu-barra-inferior";
        inferior.setAttribute(
            "aria-label",
            "Ferramentas de localização"
        );

        inferior.innerHTML = `
            ${criarBotaoBarra({
                acao: "minha-localizacao",
                titulo: "Minha localização",
                iconeNome: "localizar",
            })}
            ${criarBotaoBarra({
                acao: "ir-coordenada",
                titulo: "Ir para coordenada",
                iconeNome: "coordenada",
            })}
            ${criarBotaoBarra({
                acao: "centro-lagarto",
                titulo: "Centro de Lagarto",
                iconeNome: "municipio",
            })}
            ${criarBotaoBarra({
                acao: "extensao-camadas",
                titulo: "Extensão das camadas",
                iconeNome: "extensao",
            })}
            ${criarBotaoBarra({
                acao: "copiar-centro",
                titulo: "Copiar centro",
                iconeNome: "copiar",
            })}
            ${criarBotaoBarra({
                acao: "street-view-centro",
                titulo: "Street View no centro",
                iconeNome: "street",
            })}
        `;

        area.append(
            superior,
            inferior
        );

        estado.barraSuperior = superior;
        estado.barraInferior = inferior;

        superior.addEventListener(
            "click",
            tratarAcaoBarra
        );
        inferior.addEventListener(
            "click",
            tratarAcaoBarra
        );
    }

    function criarMenuFundos() {
        const menu = document.createElement(
            "section"
        );
        menu.className =
            "semdu-menu-fundos";
        menu.hidden = true;
        menu.setAttribute(
            "aria-label",
            "Escolha do fundo cartográfico"
        );

        menu.innerHTML = `
            <header>
                <div>
                    <span>PLANO DE FUNDO</span>
                    <strong>Fonte cartográfica</strong>
                </div>
                <button
                    type="button"
                    data-fechar-menu
                    aria-label="Fechar"
                >×</button>
            </header>
            <div data-lista-fundos class="semdu-lista-fundos"></div>
            <label class="semdu-opacidade-fundo">
                <span>
                    Opacidade da ortofoto
                    <strong data-valor-opacidade>100%</strong>
                </span>
                <input
                    type="range"
                    min="20"
                    max="100"
                    step="5"
                    value="100"
                    data-opacidade-fundo
                >
            </label>
            <p class="semdu-menu-fundos-nota">
                A resolução escolhida altera somente o fundo. As camadas vetoriais permanecem independentes.
            </p>
        `;

        document.querySelector(
            ".semdu-mapa-area"
        )?.appendChild(menu);

        menu.querySelector(
            "[data-fechar-menu]"
        )?.addEventListener(
            "click",
            fecharMenus
        );

        menu.querySelector(
            "[data-opacidade-fundo]"
        )?.addEventListener(
            "input",
            evento => {
                const opacidade = limitar(
                    numero(evento.target.value, 100) / 100,
                    0.2,
                    1
                );

                estado.opacidadeOrtofoto =
                    opacidade;

                localStorage.setItem(
                    CHAVE_OPACIDADE,
                    String(opacidade)
                );

                atualizarOpacidadeFundo();
            }
        );

        estado.menuFundos = menu;
        return menu;
    }

    function fecharMenus() {
        if (estado.menuFundos) {
            estado.menuFundos.hidden = true;
        }

        estado.menuAberto = null;

        estado.barraSuperior
            ?.querySelectorAll(
                "button.ativo"
            )
            .forEach(
                botao =>
                    botao.classList.remove(
                        "ativo"
                    )
            );
    }

    function abrirMenuFundos(
        botao
    ) {
        const menu =
            estado.menuFundos
            ?? criarMenuFundos();

        const abrindo = menu.hidden;
        fecharMenus();

        if (!abrindo) {
            return;
        }

        renderizarFundos();
        menu.hidden = false;
        estado.menuAberto = "fundos";
        botao?.classList.add("ativo");
    }

    function criarFundoBranco() {
        const GradeBranca = L.GridLayer.extend({
            createTile() {
                const tile = document.createElement(
                    "div"
                );
                tile.className =
                    "semdu-tile-branco";
                return tile;
            },
        });

        return new GradeBranca({
            minZoom: 0,
            maxZoom: 24,
            attribution: "",
            pane: "tilePane",
        });
    }

    function registrarFundo(
        id,
        titulo,
        layer,
        opcoes = {}
    ) {
        estado.fundos.set(
            id,
            {
                id,
                titulo,
                layer,
                tipo: opcoes.tipo ?? "mapa",
                disponivel:
                    opcoes.disponivel
                    !== false,
                descricao:
                    opcoes.descricao
                    ?? "",
                resolucao:
                    opcoes.resolucao
                    ?? "",
                motivo:
                    opcoes.motivo
                    ?? "",
            }
        );
    }

    async function prepararFundos() {
        registrarFundo(
            "mapa_claro",
            "Mapa claro",
            L.tileLayer(
                "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                {
                    maxZoom: 20,
                    attribution:
                        "&copy; OpenStreetMap &copy; CARTO",
                }
            ),
            {
                descricao:
                    "Base clara para leitura das camadas vetoriais.",
            }
        );

        registrarFundo(
            "osm",
            "OpenStreetMap",
            L.tileLayer(
                "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                {
                    maxZoom: 19,
                    attribution:
                        "&copy; OpenStreetMap contributors",
                }
            ),
            {
                descricao:
                    "Mapa colaborativo com ruas e pontos de interesse.",
            }
        );

        registrarFundo(
            "branco",
            "Mapa em branco",
            criarFundoBranco(),
            {
                descricao:
                    "Fundo neutro, sem informação cartográfica externa.",
            }
        );

        try {
            const dados = await api(
                "/api/semdu/ortofotos"
            );

            for (
                const item
                of dados?.ortofotos ?? []
            ) {
                const layer = item.disponivel
                    ? L.tileLayer(
                        item.url_tiles,
                        {
                            minZoom:
                                item.min_zoom
                                ?? 10,
                            maxZoom:
                                item.max_zoom
                                ?? 24,
                            maxNativeZoom:
                                item.max_zoom_nativo
                                ?? 22,
                            tileSize: 256,
                            opacity:
                                estado.opacidadeOrtofoto,
                            updateWhenIdle: true,
                            keepBuffer: 4,
                            attribution:
                                item.atribuicao
                                ?? "Prefeitura de Lagarto",
                        }
                    )
                    : null;

                registrarFundo(
                    item.id,
                    item.titulo,
                    layer,
                    {
                        tipo: "ortofoto",
                        disponivel:
                            item.disponivel,
                        descricao:
                            item.descricao,
                        resolucao:
                            item.resolucao,
                        motivo:
                            item.motivo,
                    }
                );
            }
        } catch (erro) {
            console.error(
                "Não foi possível consultar as ortofotos:",
                erro
            );

            [
                [
                    "satelite_15cm",
                    "Imagem de satélite 2025 — 15 cm",
                    "15 cm",
                ],
                [
                    "ortofoto_8cm",
                    "Ortofoto 2025 — 8 cm",
                    "8 cm",
                ],
            ].forEach(
                ([id, titulo, resolucao]) =>
                    registrarFundo(
                        id,
                        titulo,
                        null,
                        {
                            tipo: "ortofoto",
                            disponivel: false,
                            resolucao,
                            motivo:
                                "O servidor não respondeu ao catálogo de ortofotos.",
                        }
                    )
            );
        }

        const salvo = localStorage.getItem(
            CHAVE_FUNDO
        );

        const escolhido =
            estado.fundos.get(salvo)
                ?.disponivel
                ? salvo
                : "mapa_claro";

        aplicarFundo(
            escolhido,
            {
                silencioso: true,
            }
        );
    }

    function aplicarFundo(
        id,
        {
            silencioso = false,
        } = {}
    ) {
        const fundo = estado.fundos.get(id);

        if (!fundo?.disponivel || !fundo.layer) {
            mostrarToast(
                fundo?.motivo
                || "Esse fundo ainda não está disponível no servidor.",
                "erro"
            );
            return;
        }

        const atual = estado.fundos.get(
            estado.fundoAtualId
        );

        if (
            atual?.layer
            && estado.mapa.hasLayer(
                atual.layer
            )
        ) {
            estado.mapa.removeLayer(
                atual.layer
            );
        }

        fundo.layer.addTo(
            estado.mapa
        );
        fundo.layer.setZIndex?.(0);

        if (fundo.tipo === "ortofoto") {
            fundo.layer.setOpacity?.(
                estado.opacidadeOrtofoto
            );
        }

        estado.fundoAtualId = id;
        localStorage.setItem(
            CHAVE_FUNDO,
            id
        );

        document.getElementById("map")
            ?.classList.toggle(
                "semdu-mapa-sem-fundo",
                id === "branco"
            );

        renderizarFundos();

        if (!silencioso) {
            mostrarToast(
                `${fundo.titulo} aplicado.`,
                "sucesso"
            );
        }
    }

    function atualizarOpacidadeFundo() {
        const atual = estado.fundos.get(
            estado.fundoAtualId
        );

        if (atual?.tipo === "ortofoto") {
            atual.layer?.setOpacity?.(
                estado.opacidadeOrtofoto
            );
        }

        const menu = estado.menuFundos;
        const valor = menu?.querySelector(
            "[data-valor-opacidade]"
        );
        const entrada = menu?.querySelector(
            "[data-opacidade-fundo]"
        );

        if (valor) {
            valor.textContent =
                `${Math.round(estado.opacidadeOrtofoto * 100)}%`;
        }

        if (entrada) {
            entrada.value = String(
                Math.round(
                    estado.opacidadeOrtofoto * 100
                )
            );
        }
    }

    function renderizarFundos() {
        const menu = estado.menuFundos;
        const lista = menu?.querySelector(
            "[data-lista-fundos]"
        );

        if (!lista) {
            return;
        }

        lista.innerHTML = "";

        const fragmento =
            document.createDocumentFragment();

        for (
            const fundo
            of estado.fundos.values()
        ) {
            const label = document.createElement(
                "label"
            );
            label.className =
                "semdu-fundo-opcao";
            label.classList.toggle(
                "indisponivel",
                !fundo.disponivel
            );

            label.innerHTML = `
                <input
                    type="radio"
                    name="semdu-fundo"
                    value="${escaparHtml(fundo.id)}"
                    ${
                        fundo.id === estado.fundoAtualId
                            ? "checked"
                            : ""
                    }
                    ${
                        fundo.disponivel
                            ? ""
                            : "disabled"
                    }
                >
                <span class="semdu-fundo-miniatura ${escaparHtml(fundo.tipo)}"></span>
                <span class="semdu-fundo-texto">
                    <strong>${escaparHtml(fundo.titulo)}</strong>
                    <small>
                        ${escaparHtml(
                            fundo.disponivel
                                ? (
                                    fundo.descricao
                                    || fundo.resolucao
                                    || "Disponível"
                                )
                                : (
                                    fundo.motivo
                                    || "Ainda não preparado."
                                )
                        )}
                    </small>
                </span>
            `;

            label.querySelector("input")
                ?.addEventListener(
                    "change",
                    () => {
                        aplicarFundo(
                            fundo.id
                        );
                    }
                );

            fragmento.appendChild(label);
        }

        lista.appendChild(fragmento);
        atualizarOpacidadeFundo();
    }

    function chavePreferencias() {
        const usuario =
            document.body.dataset.usuarioId
            || "usuario";

        return `semdu:websig:preferencias:${usuario}`;
    }

    function carregarPreferenciasLocais() {
        try {
            const dados = JSON.parse(
                localStorage.getItem(
                    chavePreferencias()
                )
                || "{}"
            );

            estado.preferenciasLocais =
                dados
                && typeof dados === "object"
                    ? dados
                    : {};
        } catch {
            estado.preferenciasLocais = {};
        }

        window.SemduMapa
            ?.definirPreferenciasCamadas(
                estado.preferenciasLocais
            );
    }

    function salvarPreferenciasLocais() {
        localStorage.setItem(
            chavePreferencias(),
            JSON.stringify(
                estado.preferenciasLocais
            )
        );
    }

    async function carregarPreferenciasServidor() {
        carregarPreferenciasLocais();

        try {
            const dados = await api(
                "/api/semdu/preferencias-camadas"
            );

            const recebidas = {};

            for (
                const item
                of dados?.preferencias ?? []
            ) {
                recebidas[item.camada_id] = {
                    estilo: item.estilo ?? {},
                    rotulo: item.rotulo ?? {},
                };
            }

            estado.preferenciasLocais = {
                ...estado.preferenciasLocais,
                ...recebidas,
            };

            salvarPreferenciasLocais();

            window.SemduMapa
                ?.definirPreferenciasCamadas(
                    estado.preferenciasLocais
                );
        } catch (erro) {
            console.warn(
                "Preferências do servidor indisponíveis; usando o navegador:",
                erro
            );
        }
    }

    function camadasAtivas() {
        return window.SemduMapa
            ?.obterCamadasAtivas?.()
            ?? [];
    }

    function criarDialogoEstilos() {
        if (estado.dialogoEstilos) {
            return estado.dialogoEstilos;
        }

        const dialogo = document.createElement(
            "dialog"
        );
        dialogo.className =
            "semdu-dialogo semdu-dialogo-estilos";

        dialogo.innerHTML = `
            <form method="dialog" class="semdu-dialogo-estrutura">
                <header>
                    <div>
                        <span>CAMADA VETORIAL</span>
                        <h2>Configuração cartográfica</h2>
                    </div>
                    <button
                        type="button"
                        data-fechar-dialogo
                        aria-label="Fechar"
                    >×</button>
                </header>

                <div class="semdu-dialogo-corpo">
                    <label class="semdu-campo">
                        <span>Camada ativa</span>
                        <select data-estilo-camada></select>
                    </label>

                    <nav class="semdu-estilo-abas">
                        <button
                            type="button"
                            data-estilo-aba="simbologia"
                            class="ativa"
                        >Simbologia</button>
                        <button
                            type="button"
                            data-estilo-aba="rotulos"
                        >Rótulos</button>
                    </nav>

                    <section
                        data-estilo-secao="simbologia"
                        class="semdu-estilo-secao ativa"
                    >
                        <div class="semdu-grade-campos duas-colunas">
                            <label class="semdu-campo">
                                <span>Cor do contorno</span>
                                <input type="color" data-estilo="strokeColor">
                            </label>
                            <label class="semdu-campo">
                                <span>Cor do preenchimento</span>
                                <input type="color" data-estilo="fillColor">
                            </label>
                            <label class="semdu-campo">
                                <span>Espessura</span>
                                <input type="number" min="1" max="12" step="1" data-estilo="weight">
                            </label>
                            <label class="semdu-campo">
                                <span>Raio dos pontos</span>
                                <input type="number" min="2" max="22" step="1" data-estilo="radius">
                            </label>
                            <label class="semdu-campo">
                                <span>Opacidade do contorno</span>
                                <input type="range" min="0" max="1" step="0.05" data-estilo="opacity">
                            </label>
                            <label class="semdu-campo">
                                <span>Opacidade do preenchimento</span>
                                <input type="range" min="0" max="1" step="0.05" data-estilo="fillOpacity">
                            </label>
                            <label class="semdu-campo ocupar-duas">
                                <span>Tracejado</span>
                                <select data-estilo="dashArray">
                                    <option value="">Linha contínua</option>
                                    <option value="8 6">Tracejado</option>
                                    <option value="2 6">Pontilhado</option>
                                    <option value="12 5 2 5">Traço e ponto</option>
                                </select>
                            </label>
                        </div>
                    </section>

                    <section
                        data-estilo-secao="rotulos"
                        class="semdu-estilo-secao"
                    >
                        <label class="semdu-opcao-checkbox">
                            <input type="checkbox" data-rotulo="enabled">
                            <span>Exibir rótulos permanentes</span>
                        </label>

                        <div class="semdu-grade-campos duas-colunas">
                            <label class="semdu-campo ocupar-duas">
                                <span>Campo do rótulo</span>
                                <select data-rotulo="field"></select>
                            </label>
                            <label class="semdu-campo">
                                <span>Cor do texto</span>
                                <input type="color" data-rotulo="color">
                            </label>
                            <label class="semdu-campo">
                                <span>Tamanho</span>
                                <input type="number" min="8" max="30" step="1" data-rotulo="fontSize">
                            </label>
                            <label class="semdu-campo">
                                <span>Cor do halo</span>
                                <input type="color" data-rotulo="haloColor">
                            </label>
                            <label class="semdu-campo">
                                <span>Largura do halo</span>
                                <input type="number" min="0" max="8" step="1" data-rotulo="haloWidth">
                            </label>
                            <label class="semdu-campo ocupar-duas">
                                <span>Zoom mínimo</span>
                                <input type="number" min="0" max="24" step="1" data-rotulo="minZoom">
                            </label>
                        </div>
                    </section>
                </div>

                <footer>
                    <button
                        type="button"
                        class="secundario"
                        data-restaurar-estilo
                    >Restaurar padrão</button>
                    <button
                        type="button"
                        class="primario"
                        data-salvar-estilo
                    >Salvar e aplicar</button>
                </footer>
            </form>
        `;

        document.body.appendChild(dialogo);

        dialogo.querySelector(
            "[data-fechar-dialogo]"
        )?.addEventListener(
            "click",
            () => dialogo.close()
        );

        dialogo.querySelector(
            "[data-estilo-camada]"
        )?.addEventListener(
            "change",
            carregarFormularioEstilo
        );

        dialogo.querySelectorAll(
            "[data-estilo-aba]"
        ).forEach(
            botao => {
                botao.addEventListener(
                    "click",
                    () => selecionarAbaEstilo(
                        botao.dataset.estiloAba
                    )
                );
            }
        );

        dialogo.querySelector(
            "[data-salvar-estilo]"
        )?.addEventListener(
            "click",
            salvarEstiloAtual
        );

        dialogo.querySelector(
            "[data-restaurar-estilo]"
        )?.addEventListener(
            "click",
            restaurarEstiloAtual
        );

        estado.dialogoEstilos = dialogo;
        return dialogo;
    }

    function selecionarAbaEstilo(
        nome
    ) {
        const dialogo =
            estado.dialogoEstilos;

        dialogo?.querySelectorAll(
            "[data-estilo-aba]"
        ).forEach(
            botao =>
                botao.classList.toggle(
                    "ativa",
                    botao.dataset.estiloAba
                        === nome
                )
        );

        dialogo?.querySelectorAll(
            "[data-estilo-secao]"
        ).forEach(
            secao =>
                secao.classList.toggle(
                    "ativa",
                    secao.dataset.estiloSecao
                        === nome
                )
        );
    }

    function abrirEditorCamada(
        aba
    ) {
        fecharMenus();

        const ativas = camadasAtivas();

        if (!ativas.length) {
            mostrarToast(
                "Ative pelo menos uma camada antes de configurar a simbologia ou os rótulos.",
                "erro"
            );
            return;
        }

        const dialogo =
            criarDialogoEstilos();

        const select = dialogo.querySelector(
            "[data-estilo-camada]"
        );

        const anterior = select.value;
        select.innerHTML = ativas
            .map(
                registro => `
                    <option value="${escaparHtml(registro.camada.id)}">
                        ${escaparHtml(registro.camada.titulo)}
                    </option>
                `
            )
            .join("");

        if (
            anterior
            && ativas.some(
                item =>
                    item.camada.id === anterior
            )
        ) {
            select.value = anterior;
        }

        selecionarAbaEstilo(aba);
        carregarFormularioEstilo();
        dialogo.showModal();
    }

    function registroSelecionadoEstilo() {
        const id = estado.dialogoEstilos
            ?.querySelector(
                "[data-estilo-camada]"
            )
            ?.value;

        return camadasAtivas().find(
            item =>
                item.camada.id === id
        );
    }

    function definirValor(
        seletor,
        valor
    ) {
        const elemento =
            estado.dialogoEstilos
                ?.querySelector(seletor);

        if (!elemento) {
            return;
        }

        if (elemento.type === "checkbox") {
            elemento.checked = Boolean(valor);
        } else {
            elemento.value = valor ?? "";
        }
    }

    function carregarFormularioEstilo() {
        const registro =
            registroSelecionadoEstilo();

        if (!registro) {
            return;
        }

        const preferencia =
            window.SemduMapa
                ?.obterPreferenciaCamada(
                    registro.camada
                );

        for (
            const [campo, valor]
            of Object.entries(
                preferencia?.estilo
                ?? {}
            )
        ) {
            definirValor(
                `[data-estilo="${campo}"]`,
                valor
            );
        }

        const campoRotulo =
            estado.dialogoEstilos
                .querySelector(
                    '[data-rotulo="field"]'
                );

        campoRotulo.innerHTML = `
            <option value="">Selecione um atributo</option>
            ${registro.campos.map(
                campo => `
                    <option value="${escaparHtml(campo)}">
                        ${escaparHtml(campo)}
                    </option>
                `
            ).join("")}
        `;

        for (
            const [campo, valor]
            of Object.entries(
                preferencia?.rotulo
                ?? {}
            )
        ) {
            definirValor(
                `[data-rotulo="${campo}"]`,
                valor
            );
        }
    }

    function lerValorFormulario(
        seletor,
        tipo = "texto"
    ) {
        const elemento =
            estado.dialogoEstilos
                ?.querySelector(seletor);

        if (!elemento) {
            return null;
        }

        if (tipo === "booleano") {
            return elemento.checked;
        }

        if (tipo === "numero") {
            return numero(elemento.value);
        }

        return elemento.value;
    }

    function preferenciaDoFormulario() {
        return {
            estilo: {
                strokeColor:
                    lerValorFormulario(
                        '[data-estilo="strokeColor"]'
                    ),
                fillColor:
                    lerValorFormulario(
                        '[data-estilo="fillColor"]'
                    ),
                weight:
                    lerValorFormulario(
                        '[data-estilo="weight"]',
                        "numero"
                    ),
                radius:
                    lerValorFormulario(
                        '[data-estilo="radius"]',
                        "numero"
                    ),
                opacity:
                    lerValorFormulario(
                        '[data-estilo="opacity"]',
                        "numero"
                    ),
                fillOpacity:
                    lerValorFormulario(
                        '[data-estilo="fillOpacity"]',
                        "numero"
                    ),
                dashArray:
                    lerValorFormulario(
                        '[data-estilo="dashArray"]'
                    ),
            },
            rotulo: {
                enabled:
                    lerValorFormulario(
                        '[data-rotulo="enabled"]',
                        "booleano"
                    ),
                field:
                    lerValorFormulario(
                        '[data-rotulo="field"]'
                    ),
                color:
                    lerValorFormulario(
                        '[data-rotulo="color"]'
                    ),
                fontSize:
                    lerValorFormulario(
                        '[data-rotulo="fontSize"]',
                        "numero"
                    ),
                haloColor:
                    lerValorFormulario(
                        '[data-rotulo="haloColor"]'
                    ),
                haloWidth:
                    lerValorFormulario(
                        '[data-rotulo="haloWidth"]',
                        "numero"
                    ),
                minZoom:
                    lerValorFormulario(
                        '[data-rotulo="minZoom"]',
                        "numero"
                    ),
            },
        };
    }

    async function salvarEstiloAtual() {
        const registro =
            registroSelecionadoEstilo();

        if (!registro) {
            return;
        }

        const preferencia =
            preferenciaDoFormulario();

        const normalizada =
            window.SemduMapa
                ?.definirPreferenciaCamada(
                    registro.camada.id,
                    preferencia
                )
            ?? preferencia;

        estado.preferenciasLocais[
            registro.camada.id
        ] = normalizada;
        salvarPreferenciasLocais();

        try {
            await api(
                "/api/semdu/preferencias-camadas",
                {
                    method: "PUT",
                    body: JSON.stringify({
                        camada_id:
                            registro.camada.id,
                        estilo:
                            normalizada.estilo,
                        rotulo:
                            normalizada.rotulo,
                    }),
                }
            );

            mostrarToast(
                "Simbologia e rótulos salvos.",
                "sucesso"
            );
        } catch (erro) {
            mostrarToast(
                "A configuração foi aplicada neste navegador, mas não pôde ser gravada no servidor.",
                "erro"
            );
            console.error(erro);
        }
    }

    async function restaurarEstiloAtual() {
        const registro =
            registroSelecionadoEstilo();

        if (!registro) {
            return;
        }

        window.SemduMapa
            ?.limparPreferenciaCamada(
                registro.camada.id
            );

        delete estado.preferenciasLocais[
            registro.camada.id
        ];
        salvarPreferenciasLocais();
        carregarFormularioEstilo();

        try {
            const parametros = new URLSearchParams({
                camada_id:
                    registro.camada.id,
            });

            await api(
                "/api/semdu/preferencias-camadas?"
                + parametros.toString(),
                {
                    method: "DELETE",
                }
            );
        } catch (erro) {
            console.warn(
                "Não foi possível remover a preferência do servidor:",
                erro
            );
        }

        mostrarToast(
            "Simbologia padrão restaurada.",
            "sucesso"
        );
    }

    function radianos(graus) {
        return graus * Math.PI / 180;
    }

    function graus(radianosValor) {
        return radianosValor * 180 / Math.PI;
    }

    function distanciaGeodesica(
        pontoA,
        pontoB
    ) {
        const raio = 6371008.8;
        const lat1 = radianos(pontoA.lat);
        const lat2 = radianos(pontoB.lat);
        const deltaLat = radianos(
            pontoB.lat - pontoA.lat
        );
        const deltaLon = radianos(
            pontoB.lng - pontoA.lng
        );

        const a =
            Math.sin(deltaLat / 2) ** 2
            + Math.cos(lat1)
            * Math.cos(lat2)
            * Math.sin(deltaLon / 2) ** 2;

        return raio * 2 * Math.atan2(
            Math.sqrt(a),
            Math.sqrt(1 - a)
        );
    }

    function azimuteInicial(
        pontoA,
        pontoB
    ) {
        const lat1 = radianos(pontoA.lat);
        const lat2 = radianos(pontoB.lat);
        const deltaLon = radianos(
            pontoB.lng - pontoA.lng
        );

        const y = Math.sin(deltaLon)
            * Math.cos(lat2);
        const x = Math.cos(lat1)
            * Math.sin(lat2)
            - Math.sin(lat1)
            * Math.cos(lat2)
            * Math.cos(deltaLon);

        return (
            graus(
                Math.atan2(y, x)
            )
            + 360
        ) % 360;
    }

    function areaGeodesica(
        pontos
    ) {
        if (pontos.length < 3) {
            return 0;
        }

        const raio = 6378137;
        let soma = 0;

        for (
            let indice = 0;
            indice < pontos.length;
            indice += 1
        ) {
            const atual = pontos[indice];
            const seguinte = pontos[
                (indice + 1) % pontos.length
            ];

            soma += radianos(
                seguinte.lng - atual.lng
            ) * (
                2
                + Math.sin(
                    radianos(atual.lat)
                )
                + Math.sin(
                    radianos(seguinte.lat)
                )
            );
        }

        return Math.abs(
            soma * raio * raio / 2
        );
    }

    function latLonParaUtm(
        latitude,
        longitude
    ) {
        const a = 6378137;
        const f = 1 / 298.257222101;
        const k0 = 0.9996;
        const e2 = f * (2 - f);
        const ep2 = e2 / (1 - e2);
        const zona = Math.floor(
            (longitude + 180) / 6
        ) + 1;
        const lon0 = radianos(
            (zona - 1) * 6 - 180 + 3
        );
        const lat = radianos(latitude);
        const lon = radianos(longitude);
        const n = a / Math.sqrt(
            1 - e2 * Math.sin(lat) ** 2
        );
        const t = Math.tan(lat) ** 2;
        const c = ep2 * Math.cos(lat) ** 2;
        const A = Math.cos(lat)
            * (lon - lon0);

        const m = a * (
            (
                1
                - e2 / 4
                - 3 * e2 ** 2 / 64
                - 5 * e2 ** 3 / 256
            ) * lat
            - (
                3 * e2 / 8
                + 3 * e2 ** 2 / 32
                + 45 * e2 ** 3 / 1024
            ) * Math.sin(2 * lat)
            + (
                15 * e2 ** 2 / 256
                + 45 * e2 ** 3 / 1024
            ) * Math.sin(4 * lat)
            - (
                35 * e2 ** 3 / 3072
            ) * Math.sin(6 * lat)
        );

        let leste = k0 * n * (
            A
            + (1 - t + c) * A ** 3 / 6
            + (
                5
                - 18 * t
                + t ** 2
                + 72 * c
                - 58 * ep2
            ) * A ** 5 / 120
        ) + 500000;

        let norte = k0 * (
            m
            + n * Math.tan(lat) * (
                A ** 2 / 2
                + (
                    5
                    - t
                    + 9 * c
                    + 4 * c ** 2
                ) * A ** 4 / 24
                + (
                    61
                    - 58 * t
                    + t ** 2
                    + 600 * c
                    - 330 * ep2
                ) * A ** 6 / 720
            )
        );

        const hemisferio =
            latitude < 0
                ? "S"
                : "N";

        if (latitude < 0) {
            norte += 10000000;
        }

        return {
            zona,
            hemisferio,
            leste,
            norte,
        };
    }

    function utmParaLatLon(
        leste,
        norte,
        zona = 24,
        hemisferio = "S"
    ) {
        const a = 6378137;
        const f = 1 / 298.257222101;
        const k0 = 0.9996;
        const e2 = f * (2 - f);
        const e1 = (
            1 - Math.sqrt(1 - e2)
        ) / (
            1 + Math.sqrt(1 - e2)
        );
        const ep2 = e2 / (1 - e2);

        const x = leste - 500000;
        let y = norte;

        if (
            String(hemisferio)
                .toUpperCase()
            === "S"
        ) {
            y -= 10000000;
        }

        const m = y / k0;
        const mu = m / (
            a * (
                1
                - e2 / 4
                - 3 * e2 ** 2 / 64
                - 5 * e2 ** 3 / 256
            )
        );

        const phi1 =
            mu
            + (
                3 * e1 / 2
                - 27 * e1 ** 3 / 32
            ) * Math.sin(2 * mu)
            + (
                21 * e1 ** 2 / 16
                - 55 * e1 ** 4 / 32
            ) * Math.sin(4 * mu)
            + (
                151 * e1 ** 3 / 96
            ) * Math.sin(6 * mu)
            + (
                1097 * e1 ** 4 / 512
            ) * Math.sin(8 * mu);

        const n1 = a / Math.sqrt(
            1 - e2 * Math.sin(phi1) ** 2
        );
        const t1 = Math.tan(phi1) ** 2;
        const c1 = ep2 * Math.cos(phi1) ** 2;
        const r1 = a * (1 - e2) / (
            1 - e2 * Math.sin(phi1) ** 2
        ) ** 1.5;
        const d = x / (n1 * k0);

        const latitude = phi1 - (
            n1 * Math.tan(phi1) / r1
        ) * (
            d ** 2 / 2
            - (
                5
                + 3 * t1
                + 10 * c1
                - 4 * c1 ** 2
                - 9 * ep2
            ) * d ** 4 / 24
            + (
                61
                + 90 * t1
                + 298 * c1
                + 45 * t1 ** 2
                - 252 * ep2
                - 3 * c1 ** 2
            ) * d ** 6 / 720
        );

        const longitude = (
            d
            - (1 + 2 * t1 + c1)
                * d ** 3 / 6
            + (
                5
                - 2 * c1
                + 28 * t1
                - 3 * c1 ** 2
                + 8 * ep2
                + 24 * t1 ** 2
            ) * d ** 5 / 120
        ) / Math.cos(phi1);

        const lon0 = (
            (zona - 1) * 6
            - 180
            + 3
        );

        return {
            latitude: graus(latitude),
            longitude:
                lon0 + graus(longitude),
        };
    }

    function formatarDistancia(valor) {
        if (valor >= 1000) {
            return `${(valor / 1000).toLocaleString(
                "pt-BR",
                {
                    minimumFractionDigits: 3,
                    maximumFractionDigits: 3,
                }
            )} km`;
        }

        return `${valor.toLocaleString(
            "pt-BR",
            {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }
        )} m`;
    }

    function formatarArea(valor) {
        if (valor >= 10000) {
            return `${(valor / 10000).toLocaleString(
                "pt-BR",
                {
                    minimumFractionDigits: 4,
                    maximumFractionDigits: 4,
                }
            )} ha`;
        }

        return `${valor.toLocaleString(
            "pt-BR",
            {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }
        )} m²`;
    }

    function formatarAzimute(valor) {
        const normalizado = (
            valor + 360
        ) % 360;
        const grausInteiros = Math.floor(
            normalizado
        );
        const minutosDecimais = (
            normalizado - grausInteiros
        ) * 60;
        const minutos = Math.floor(
            minutosDecimais
        );
        const segundos = (
            minutosDecimais - minutos
        ) * 60;

        return `${normalizado.toFixed(4)}° · ${grausInteiros}° ${minutos}' ${segundos.toFixed(1)}"`;
    }

    function criarPainelMedicao() {
        if (estado.painelMedicao) {
            return estado.painelMedicao;
        }

        const painel = document.createElement(
            "section"
        );
        painel.className =
            "semdu-painel-medicao";
        painel.hidden = true;
        painel.innerHTML = `
            <header>
                <div>
                    <span>TOPOGRAFIA PLANIMÉTRICA</span>
                    <strong data-medicao-titulo>Ferramenta</strong>
                </div>
                <button
                    type="button"
                    data-medicao-fechar
                    aria-label="Fechar painel"
                >×</button>
            </header>
            <div class="semdu-medicao-instrucao" data-medicao-instrucao></div>
            <div class="semdu-medicao-resultados" data-medicao-resultados></div>
            <footer>
                <button type="button" class="secundario" data-medicao-exportar>Exportar</button>
                <button type="button" class="secundario" data-medicao-desfazer>Desfazer</button>
                <button type="button" class="primario" data-medicao-finalizar>Finalizar</button>
            </footer>
        `;

        document.querySelector(
            ".semdu-mapa-area"
        )?.appendChild(painel);

        painel.querySelector(
            "[data-medicao-fechar]"
        )?.addEventListener(
            "click",
            () => encerrarMedicao({
                ocultarPainel: true,
            })
        );

        painel.querySelector(
            "[data-medicao-finalizar]"
        )?.addEventListener(
            "click",
            finalizarMedicao
        );

        painel.querySelector(
            "[data-medicao-desfazer]"
        )?.addEventListener(
            "click",
            desfazerPontoMedicao
        );

        painel.querySelector(
            "[data-medicao-exportar]"
        )?.addEventListener(
            "click",
            exportarMedicao
        );

        estado.painelMedicao = painel;
        return painel;
    }

    function nomeFerramentaMedicao(
        modo
    ) {
        return {
            distancia: "Cálculo de distância",
            azimute: "Distância e azimute",
            area: "Área e perímetro",
            poligonal: "Poligonal topográfica",
        }[modo] ?? "Medição";
    }

    function instrucaoMedicao(
        modo
    ) {
        return {
            distancia:
                "Clique nos vértices do percurso. Dê duplo clique ou use Finalizar.",
            azimute:
                "Clique no ponto inicial e depois no ponto final.",
            area:
                "Clique nos vértices do polígono. Use pelo menos três pontos.",
            poligonal:
                "Clique nos vértices. A tabela apresenta coordenadas UTM, distâncias e azimutes.",
        }[modo] ?? "Clique no mapa.";
    }

    function marcarBotaoMedicao() {
        estado.barraSuperior
            ?.querySelectorAll(
                "[data-ferramenta-acao]"
            )
            .forEach(
                botao => {
                    botao.classList.toggle(
                        "ativo",
                        botao.dataset.ferramentaAcao
                            === estado.medicao.modo
                    );
                }
            );
    }

    function iniciarMedicao(
        modo
    ) {
        fecharMenus();

        if (estado.medicao.modo === modo) {
            encerrarMedicao();
            return;
        }

        limparMedicoes();

        estado.medicao.modo = modo;
        estado.medicao.concluida = false;

        estado.mapa.doubleClickZoom.disable();
        estado.mapa.getContainer()
            .classList.add(
                "semdu-modo-medicao"
            );

        const painel = criarPainelMedicao();
        painel.hidden = false;
        painel.querySelector(
            "[data-medicao-titulo]"
        ).textContent =
            nomeFerramentaMedicao(modo);
        painel.querySelector(
            "[data-medicao-instrucao]"
        ).textContent =
            instrucaoMedicao(modo);

        marcarBotaoMedicao();
        renderizarMedicao();
    }

    function encerrarMedicao({
        ocultarPainel = false,
    } = {}) {
        estado.medicao.modo = null;
        estado.mapa?.doubleClickZoom.enable();
        estado.mapa?.getContainer()
            .classList.remove(
                "semdu-modo-medicao"
            );

        if (estado.medicao.preview) {
            estado.camadaMedicoes.removeLayer(
                estado.medicao.preview
            );
            estado.medicao.preview = null;
        }

        marcarBotaoMedicao();

        if (
            ocultarPainel
            && estado.painelMedicao
        ) {
            estado.painelMedicao.hidden = true;
        }
    }

    function limparMedicoes() {
        encerrarMedicao();
        estado.camadaMedicoes?.clearLayers();
        estado.medicao = {
            modo: null,
            pontos: [],
            geometria: null,
            preview: null,
            marcadores: [],
            concluida: false,
        };

        if (estado.painelMedicao) {
            estado.painelMedicao.hidden = true;
        }
    }

    function adicionarPontoMedicao(
        latlng
    ) {
        const modo = estado.medicao.modo;

        if (!modo) {
            return;
        }

        const ponto = L.latLng(
            latlng.lat,
            latlng.lng
        );
        estado.medicao.pontos.push(ponto);

        const marcador = L.circleMarker(
            ponto,
            {
                radius: 5,
                color: "#ffffff",
                weight: 2,
                fillColor: "#d06b12",
                fillOpacity: 1,
                pane: "markerPane",
            }
        ).addTo(
            estado.camadaMedicoes
        );

        marcador.bindTooltip(
            `P${estado.medicao.pontos.length}`,
            {
                permanent: true,
                direction: "top",
                offset: [0, -4],
                className:
                    "semdu-medicao-rotulo-ponto",
            }
        );

        estado.medicao.marcadores.push(
            marcador
        );

        atualizarGeometriaMedicao();
        renderizarMedicao();

        if (
            modo === "azimute"
            && estado.medicao.pontos.length >= 2
        ) {
            finalizarMedicao();
        }
    }

    function atualizarGeometriaMedicao() {
        if (estado.medicao.geometria) {
            estado.camadaMedicoes.removeLayer(
                estado.medicao.geometria
            );
            estado.medicao.geometria = null;
        }

        const pontos = estado.medicao.pontos;
        const modo = estado.medicao.modo
            ?? estado.medicao.modoAnterior;

        if (pontos.length < 2) {
            return;
        }

        if (modo === "area") {
            estado.medicao.geometria =
                L.polygon(
                    pontos,
                    {
                        color: "#d06b12",
                        weight: 3,
                        opacity: 0.95,
                        fillColor: "#f3a44c",
                        fillOpacity: 0.22,
                        dashArray: "8 5",
                    }
                ).addTo(
                    estado.camadaMedicoes
                );
        } else {
            estado.medicao.geometria =
                L.polyline(
                    pontos,
                    {
                        color: "#d06b12",
                        weight: 4,
                        opacity: 0.95,
                        dashArray:
                            modo === "poligonal"
                                ? "10 5"
                                : null,
                    }
                ).addTo(
                    estado.camadaMedicoes
                );
        }
    }

    function atualizarPreviewMedicao(
        latlng
    ) {
        if (
            !estado.medicao.modo
            || !estado.medicao.pontos.length
        ) {
            return;
        }

        if (estado.medicao.preview) {
            estado.camadaMedicoes.removeLayer(
                estado.medicao.preview
            );
        }

        const ultimo = estado.medicao.pontos[
            estado.medicao.pontos.length - 1
        ];

        estado.medicao.preview = L.polyline(
            [ultimo, latlng],
            {
                color: "#d06b12",
                weight: 2,
                opacity: 0.72,
                dashArray: "5 6",
                interactive: false,
            }
        ).addTo(
            estado.camadaMedicoes
        );
    }

    function desfazerPontoMedicao() {
        if (!estado.medicao.pontos.length) {
            return;
        }

        estado.medicao.pontos.pop();
        const marcador =
            estado.medicao.marcadores.pop();

        if (marcador) {
            estado.camadaMedicoes.removeLayer(
                marcador
            );
        }

        atualizarGeometriaMedicao();
        renderizarMedicao();
    }

    function finalizarMedicao() {
        const modo = estado.medicao.modo;
        const quantidade =
            estado.medicao.pontos.length;

        const minimo =
            modo === "area"
                ? 3
                : 2;

        if (
            modo
            && quantidade < minimo
        ) {
            mostrarToast(
                `Adicione pelo menos ${minimo} pontos.`,
                "erro"
            );
            return;
        }

        if (!modo) {
            return;
        }

        estado.medicao.modoAnterior = modo;
        estado.medicao.concluida = true;
        encerrarMedicao();
        atualizarGeometriaMedicao();
        renderizarMedicao();

        mostrarToast(
            "Medição finalizada.",
            "sucesso"
        );
    }

    function segmentosMedicao() {
        const segmentos = [];
        let acumulada = 0;

        for (
            let indice = 1;
            indice < estado.medicao.pontos.length;
            indice += 1
        ) {
            const origem =
                estado.medicao.pontos[indice - 1];
            const destino =
                estado.medicao.pontos[indice];
            const distancia =
                distanciaGeodesica(
                    origem,
                    destino
                );
            const azimute =
                azimuteInicial(
                    origem,
                    destino
                );

            acumulada += distancia;

            segmentos.push({
                indice,
                origem,
                destino,
                distancia,
                azimute,
                acumulada,
            });
        }

        return segmentos;
    }

    function perimetroArea() {
        const pontos = estado.medicao.pontos;
        let perimetro = segmentosMedicao()
            .reduce(
                (soma, item) =>
                    soma + item.distancia,
                0
            );

        if (pontos.length >= 3) {
            perimetro += distanciaGeodesica(
                pontos[pontos.length - 1],
                pontos[0]
            );
        }

        return perimetro;
    }

    function tabelaSegmentos(
        segmentos
    ) {
        if (!segmentos.length) {
            return "";
        }

        return `
            <div class="semdu-tabela-medicao-wrap">
                <table class="semdu-tabela-medicao">
                    <thead>
                        <tr>
                            <th>Trecho</th>
                            <th>Distância</th>
                            <th>Azimute</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${segmentos.map(
                            item => `
                                <tr>
                                    <td>P${item.indice}–P${item.indice + 1}</td>
                                    <td>${formatarDistancia(item.distancia)}</td>
                                    <td>${item.azimute.toFixed(4)}°</td>
                                </tr>
                            `
                        ).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function tabelaPoligonal() {
        const segmentos = segmentosMedicao();

        if (!estado.medicao.pontos.length) {
            return "";
        }

        return `
            <div class="semdu-tabela-medicao-wrap grande">
                <table class="semdu-tabela-medicao">
                    <thead>
                        <tr>
                            <th>Pt.</th>
                            <th>Latitude</th>
                            <th>Longitude</th>
                            <th>E (m)</th>
                            <th>N (m)</th>
                            <th>Dist.</th>
                            <th>Az.</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${estado.medicao.pontos.map(
                            (ponto, indice) => {
                                const utm = latLonParaUtm(
                                    ponto.lat,
                                    ponto.lng
                                );
                                const segmento =
                                    indice > 0
                                        ? segmentos[indice - 1]
                                        : null;

                                return `
                                    <tr>
                                        <td>P${indice + 1}</td>
                                        <td>${ponto.lat.toFixed(7)}</td>
                                        <td>${ponto.lng.toFixed(7)}</td>
                                        <td>${utm.leste.toFixed(3)}</td>
                                        <td>${utm.norte.toFixed(3)}</td>
                                        <td>${segmento ? segmento.distancia.toFixed(3) : "—"}</td>
                                        <td>${segmento ? segmento.azimute.toFixed(4) + "°" : "—"}</td>
                                    </tr>
                                `;
                            }
                        ).join("")}
                    </tbody>
                </table>
            </div>
            <small class="semdu-medicao-sistema">
                Coordenadas UTM calculadas em SIRGAS 2000, zona 24S, para apoio planimétrico.
            </small>
        `;
    }

    function renderizarMedicao() {
        const painel = criarPainelMedicao();
        const resultados = painel.querySelector(
            "[data-medicao-resultados]"
        );
        const modo =
            estado.medicao.modo
            ?? estado.medicao.modoAnterior;
        const pontos = estado.medicao.pontos;
        const segmentos = segmentosMedicao();
        const total = segmentos.reduce(
            (soma, item) =>
                soma + item.distancia,
            0
        );

        if (!pontos.length) {
            resultados.innerHTML = `
                <div class="semdu-medicao-vazia">
                    Nenhum vértice registrado.
                </div>
            `;
            return;
        }

        if (modo === "azimute") {
            const segmento = segmentos[0];
            resultados.innerHTML = segmento
                ? `
                    <div class="semdu-medicao-destaques">
                        <article><span>Distância</span><strong>${formatarDistancia(segmento.distancia)}</strong></article>
                        <article><span>Azimute</span><strong>${formatarAzimute(segmento.azimute)}</strong></article>
                        <article><span>Contra-azimute</span><strong>${formatarAzimute((segmento.azimute + 180) % 360)}</strong></article>
                    </div>
                `
                : `<div class="semdu-medicao-vazia">Selecione o segundo ponto.</div>`;
            return;
        }

        if (modo === "area") {
            resultados.innerHTML = `
                <div class="semdu-medicao-destaques">
                    <article><span>Área</span><strong>${formatarArea(areaGeodesica(pontos))}</strong></article>
                    <article><span>Perímetro</span><strong>${formatarDistancia(perimetroArea())}</strong></article>
                    <article><span>Vértices</span><strong>${pontos.length}</strong></article>
                </div>
                ${tabelaSegmentos(segmentos)}
            `;
            return;
        }

        if (modo === "poligonal") {
            resultados.innerHTML = `
                <div class="semdu-medicao-destaques">
                    <article><span>Extensão</span><strong>${formatarDistancia(total)}</strong></article>
                    <article><span>Vértices</span><strong>${pontos.length}</strong></article>
                    <article><span>Fuso UTM</span><strong>24S</strong></article>
                </div>
                ${tabelaPoligonal()}
            `;
            return;
        }

        resultados.innerHTML = `
            <div class="semdu-medicao-destaques">
                <article><span>Distância total</span><strong>${formatarDistancia(total)}</strong></article>
                <article><span>Trechos</span><strong>${segmentos.length}</strong></article>
                <article><span>Vértices</span><strong>${pontos.length}</strong></article>
            </div>
            ${tabelaSegmentos(segmentos)}
        `;
    }

    function baixarArquivo(
        nome,
        conteudo,
        tipo
    ) {
        const blob = new Blob(
            [conteudo],
            {
                type: tipo,
            }
        );
        const url = URL.createObjectURL(
            blob
        );
        const link = document.createElement(
            "a"
        );
        link.href = url;
        link.download = nome;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function exportarMedicao() {
        const pontos = estado.medicao.pontos;

        if (!pontos.length) {
            mostrarToast(
                "Não há medição para exportar.",
                "erro"
            );
            return;
        }

        const segmentos = segmentosMedicao();
        const linhas = [
            [
                "ponto",
                "latitude",
                "longitude",
                "utm_zona",
                "utm_hemisferio",
                "utm_leste_m",
                "utm_norte_m",
                "distancia_segmento_m",
                "azimute_graus",
                "distancia_acumulada_m",
            ].join(";"),
        ];

        pontos.forEach(
            (ponto, indice) => {
                const utm = latLonParaUtm(
                    ponto.lat,
                    ponto.lng
                );
                const segmento =
                    indice > 0
                        ? segmentos[indice - 1]
                        : null;

                linhas.push(
                    [
                        `P${indice + 1}`,
                        ponto.lat.toFixed(8),
                        ponto.lng.toFixed(8),
                        utm.zona,
                        utm.hemisferio,
                        utm.leste.toFixed(3),
                        utm.norte.toFixed(3),
                        segmento
                            ? segmento.distancia.toFixed(3)
                            : "",
                        segmento
                            ? segmento.azimute.toFixed(6)
                            : "",
                        segmento
                            ? segmento.acumulada.toFixed(3)
                            : "0.000",
                    ].join(";")
                );
            }
        );

        const data = new Date()
            .toISOString()
            .slice(0, 19)
            .replaceAll(":", "-");

        baixarArquivo(
            `semdu_medicao_${data}.csv`,
            "\uFEFF" + linhas.join("\n"),
            "text/csv;charset=utf-8"
        );

        const modo =
            estado.medicao.modo
            ?? estado.medicao.modoAnterior;
        let geometry;

        if (modo === "area") {
            const coordenadas = pontos.map(
                ponto => [ponto.lng, ponto.lat]
            );
            coordenadas.push([
                pontos[0].lng,
                pontos[0].lat,
            ]);
            geometry = {
                type: "Polygon",
                coordinates: [coordenadas],
            };
        } else if (pontos.length === 1) {
            geometry = {
                type: "Point",
                coordinates: [
                    pontos[0].lng,
                    pontos[0].lat,
                ],
            };
        } else {
            geometry = {
                type: "LineString",
                coordinates: pontos.map(
                    ponto => [
                        ponto.lng,
                        ponto.lat,
                    ]
                ),
            };
        }

        baixarArquivo(
            `semdu_medicao_${data}.geojson`,
            JSON.stringify(
                {
                    type: "Feature",
                    properties: {
                        ferramenta: modo,
                        distancia_m: segmentos.reduce(
                            (soma, item) =>
                                soma + item.distancia,
                            0
                        ),
                        area_m2:
                            modo === "area"
                                ? areaGeodesica(pontos)
                                : null,
                    },
                    geometry,
                },
                null,
                2
            ),
            "application/geo+json;charset=utf-8"
        );

        mostrarToast(
            "CSV e GeoJSON gerados.",
            "sucesso"
        );
    }

    function criarDialogoCoordenadas() {
        if (estado.dialogoCoordenadas) {
            return estado.dialogoCoordenadas;
        }

        const dialogo = document.createElement(
            "dialog"
        );
        dialogo.className =
            "semdu-dialogo semdu-dialogo-coordenadas";
        dialogo.innerHTML = `
            <form method="dialog" class="semdu-dialogo-estrutura">
                <header>
                    <div>
                        <span>LOCALIZAÇÃO</span>
                        <h2>Ir para coordenada</h2>
                    </div>
                    <button type="button" data-fechar-dialogo aria-label="Fechar">×</button>
                </header>
                <div class="semdu-dialogo-corpo">
                    <label class="semdu-campo">
                        <span>Sistema de entrada</span>
                        <select data-coordenada-sistema>
                            <option value="decimal">Latitude e longitude decimais</option>
                            <option value="utm">UTM — zona 24S</option>
                        </select>
                    </label>
                    <div data-coordenada-decimal class="semdu-grade-campos duas-colunas">
                        <label class="semdu-campo">
                            <span>Latitude</span>
                            <input type="number" step="any" value="-10.9160" data-coordenada-latitude>
                        </label>
                        <label class="semdu-campo">
                            <span>Longitude</span>
                            <input type="number" step="any" value="-37.6680" data-coordenada-longitude>
                        </label>
                    </div>
                    <div data-coordenada-utm class="semdu-grade-campos duas-colunas" hidden>
                        <label class="semdu-campo">
                            <span>Leste — E</span>
                            <input type="number" step="any" data-coordenada-leste>
                        </label>
                        <label class="semdu-campo">
                            <span>Norte — N</span>
                            <input type="number" step="any" data-coordenada-norte>
                        </label>
                        <label class="semdu-campo">
                            <span>Zona</span>
                            <input type="number" min="1" max="60" value="24" data-coordenada-zona>
                        </label>
                        <label class="semdu-campo">
                            <span>Hemisfério</span>
                            <select data-coordenada-hemisferio>
                                <option value="S">Sul</option>
                                <option value="N">Norte</option>
                            </select>
                        </label>
                    </div>
                </div>
                <footer>
                    <button type="button" class="secundario" data-fechar-dialogo>Cancelar</button>
                    <button type="button" class="primario" data-ir-coordenada>Localizar</button>
                </footer>
            </form>
        `;

        document.body.appendChild(dialogo);

        dialogo.querySelectorAll(
            "[data-fechar-dialogo]"
        ).forEach(
            botao =>
                botao.addEventListener(
                    "click",
                    () => dialogo.close()
                )
        );

        dialogo.querySelector(
            "[data-coordenada-sistema]"
        )?.addEventListener(
            "change",
            evento => {
                const utm =
                    evento.target.value
                    === "utm";
                dialogo.querySelector(
                    "[data-coordenada-decimal]"
                ).hidden = utm;
                dialogo.querySelector(
                    "[data-coordenada-utm]"
                ).hidden = !utm;
            }
        );

        dialogo.querySelector(
            "[data-ir-coordenada]"
        )?.addEventListener(
            "click",
            localizarCoordenadaInformada
        );

        estado.dialogoCoordenadas = dialogo;
        return dialogo;
    }

    function marcarLocalizacao(
        latitude,
        longitude,
        titulo = "Localização"
    ) {
        estado.camadaLocalizacao.clearLayers();

        const marcador = L.circleMarker(
            [latitude, longitude],
            {
                radius: 8,
                color: "#ffffff",
                weight: 3,
                fillColor: "#176d99",
                fillOpacity: 1,
            }
        ).addTo(
            estado.camadaLocalizacao
        );

        marcador.bindTooltip(
            `${escaparHtml(titulo)}<br>${latitude.toFixed(7)}, ${longitude.toFixed(7)}`,
            {
                permanent: true,
                direction: "top",
                offset: [0, -8],
                className:
                    "semdu-localizacao-rotulo",
            }
        );

        estado.mapa.setView(
            [latitude, longitude],
            Math.max(
                estado.mapa.getZoom(),
                18
            ),
            {
                animate: true,
            }
        );
    }

    function localizarCoordenadaInformada() {
        const dialogo =
            estado.dialogoCoordenadas;
        const sistema = dialogo.querySelector(
            "[data-coordenada-sistema]"
        ).value;
        let latitude;
        let longitude;

        if (sistema === "utm") {
            const leste = numero(
                dialogo.querySelector(
                    "[data-coordenada-leste]"
                ).value,
                NaN
            );
            const norte = numero(
                dialogo.querySelector(
                    "[data-coordenada-norte]"
                ).value,
                NaN
            );
            const zona = numero(
                dialogo.querySelector(
                    "[data-coordenada-zona]"
                ).value,
                24
            );
            const hemisferio =
                dialogo.querySelector(
                    "[data-coordenada-hemisferio]"
                ).value;

            if (
                !Number.isFinite(leste)
                || !Number.isFinite(norte)
            ) {
                mostrarToast(
                    "Informe coordenadas UTM válidas.",
                    "erro"
                );
                return;
            }

            const convertida = utmParaLatLon(
                leste,
                norte,
                zona,
                hemisferio
            );
            latitude = convertida.latitude;
            longitude = convertida.longitude;
        } else {
            latitude = numero(
                dialogo.querySelector(
                    "[data-coordenada-latitude]"
                ).value,
                NaN
            );
            longitude = numero(
                dialogo.querySelector(
                    "[data-coordenada-longitude]"
                ).value,
                NaN
            );
        }

        if (
            !Number.isFinite(latitude)
            || !Number.isFinite(longitude)
            || latitude < -90
            || latitude > 90
            || longitude < -180
            || longitude > 180
        ) {
            mostrarToast(
                "Informe uma latitude e longitude válidas.",
                "erro"
            );
            return;
        }

        dialogo.close();
        marcarLocalizacao(
            latitude,
            longitude,
            "Coordenada informada"
        );
    }

    function minhaLocalizacao() {
        if (!navigator.geolocation) {
            mostrarToast(
                "O navegador não oferece geolocalização.",
                "erro"
            );
            return;
        }

        mostrarToast(
            "Obtendo sua localização..."
        );

        navigator.geolocation.getCurrentPosition(
            posicao => {
                const latitude =
                    posicao.coords.latitude;
                const longitude =
                    posicao.coords.longitude;
                const precisao =
                    posicao.coords.accuracy;

                estado.camadaLocalizacao.clearLayers();

                estado.circuloPrecisao = L.circle(
                    [latitude, longitude],
                    {
                        radius: precisao,
                        color: "#176d99",
                        weight: 1,
                        opacity: 0.7,
                        fillColor: "#4ea7cc",
                        fillOpacity: 0.13,
                    }
                ).addTo(
                    estado.camadaLocalizacao
                );

                estado.marcadorLocalizacao =
                    L.circleMarker(
                        [latitude, longitude],
                        {
                            radius: 8,
                            color: "#ffffff",
                            weight: 3,
                            fillColor: "#176d99",
                            fillOpacity: 1,
                        }
                    ).addTo(
                        estado.camadaLocalizacao
                    );

                estado.marcadorLocalizacao.bindTooltip(
                    `Sua localização · precisão aproximada de ${precisao.toFixed(0)} m`,
                    {
                        permanent: true,
                        direction: "top",
                        className:
                            "semdu-localizacao-rotulo",
                    }
                );

                estado.mapa.fitBounds(
                    estado.circuloPrecisao.getBounds(),
                    {
                        padding: [40, 40],
                        maxZoom: 19,
                    }
                );

                mostrarToast(
                    "Localização encontrada.",
                    "sucesso"
                );
            },
            erro => {
                const mensagens = {
                    1: "A permissão de localização foi negada.",
                    2: "A localização não está disponível.",
                    3: "A busca da localização excedeu o tempo limite.",
                };

                mostrarToast(
                    mensagens[erro.code]
                    || "Não foi possível obter a localização.",
                    "erro"
                );
            },
            {
                enableHighAccuracy: true,
                timeout: 15000,
                maximumAge: 30000,
            }
        );
    }

    function extensaoCamadasAtivas() {
        const limite = L.latLngBounds([]);
        let encontrou = false;

        for (
            const registro
            of camadasAtivas()
        ) {
            const bounds =
                registro.grupo?.getBounds?.();

            if (bounds?.isValid?.()) {
                limite.extend(bounds);
                encontrou = true;
            }
        }

        if (!encontrou) {
            mostrarToast(
                "Nenhuma camada ativa possui feições no mapa.",
                "erro"
            );
            return;
        }

        estado.mapa.fitBounds(
            limite,
            {
                padding: [45, 45],
                maxZoom: 18,
            }
        );
    }

    function copiarCentroMapa() {
        const centro = estado.mapa.getCenter();
        const utm = latLonParaUtm(
            centro.lat,
            centro.lng
        );

        copiarTexto(
            [
                `Latitude: ${centro.lat.toFixed(8)}`,
                `Longitude: ${centro.lng.toFixed(8)}`,
                `UTM ${utm.zona}${utm.hemisferio}: E ${utm.leste.toFixed(3)} · N ${utm.norte.toFixed(3)}`,
            ].join("\n"),
            "Coordenadas do centro copiadas."
        );
    }

    function abrirStreetViewCentro() {
        const centro = estado.mapa.getCenter();
        const url = new URL(
            "https://www.google.com/maps/@"
        );
        url.searchParams.set("api", "1");
        url.searchParams.set(
            "map_action",
            "pano"
        );
        url.searchParams.set(
            "viewpoint",
            `${centro.lat},${centro.lng}`
        );

        window.open(
            url.toString(),
            "_blank",
            "noopener,noreferrer"
        );
    }

    function tratarAcaoBarra(evento) {
        const botao = evento.target.closest(
            "[data-ferramenta-acao]"
        );

        if (!botao) {
            return;
        }

        const acao =
            botao.dataset.ferramentaAcao;

        const acoes = {
            fundos: () =>
                abrirMenuFundos(botao),
            simbologia: () =>
                abrirEditorCamada("simbologia"),
            rotulos: () =>
                abrirEditorCamada("rotulos"),
            distancia: () =>
                iniciarMedicao("distancia"),
            azimute: () =>
                iniciarMedicao("azimute"),
            area: () =>
                iniciarMedicao("area"),
            poligonal: () =>
                iniciarMedicao("poligonal"),
            "limpar-medicoes": limparMedicoes,
            "minha-localizacao":
                minhaLocalizacao,
            "ir-coordenada": () =>
                criarDialogoCoordenadas()
                    .showModal(),
            "centro-lagarto": () => {
                estado.mapa.setView(
                    [
                        CENTRO_LAGARTO.latitude,
                        CENTRO_LAGARTO.longitude,
                    ],
                    CENTRO_LAGARTO.zoom,
                    {
                        animate: true,
                    }
                );
            },
            "extensao-camadas":
                extensaoCamadasAtivas,
            "copiar-centro":
                copiarCentroMapa,
            "street-view-centro":
                abrirStreetViewCentro,
        };

        acoes[acao]?.();
    }

    function registrarEventosMapa() {
        estado.mapa.on(
            "click",
            evento => {
                if (estado.medicao.modo) {
                    adicionarPontoMedicao(
                        evento.latlng
                    );
                }
            }
        );

        estado.mapa.on(
            "mousemove",
            evento => {
                atualizarPreviewMedicao(
                    evento.latlng
                );
            }
        );

        estado.mapa.on(
            "dblclick",
            evento => {
                if (!estado.medicao.modo) {
                    return;
                }

                L.DomEvent.stop(
                    evento.originalEvent
                );
                finalizarMedicao();
            }
        );

        document.addEventListener(
            "keydown",
            evento => {
                if (
                    evento.key === "Escape"
                    && estado.medicao.modo
                ) {
                    encerrarMedicao();
                }

                if (
                    (
                        evento.key === "Backspace"
                        || evento.key === "Delete"
                    )
                    && estado.medicao.modo
                    && ![
                        "INPUT",
                        "TEXTAREA",
                        "SELECT",
                    ].includes(
                        document.activeElement
                            ?.tagName
                    )
                ) {
                    evento.preventDefault();
                    desfazerPontoMedicao();
                }
            }
        );

        document.addEventListener(
            "pointerdown",
            evento => {
                if (
                    estado.menuAberto
                    && !estado.menuFundos
                        ?.contains(evento.target)
                    && !evento.target.closest(
                        '[data-ferramenta-acao="fundos"]'
                    )
                ) {
                    fecharMenus();
                }
            }
        );
    }

    function interceptarCliqueFeicao({
        evento,
    }) {
        if (!estado.medicao.modo) {
            return false;
        }

        adicionarPontoMedicao(
            evento.latlng
        );
        return true;
    }

    async function iniciar(
        mapa
    ) {
        if (
            estado.mapa
            || !mapa
        ) {
            return;
        }

        estado.mapa = mapa;
        estado.opacidadeOrtofoto = limitar(
            numero(
                localStorage.getItem(
                    CHAVE_OPACIDADE
                ),
                1
            ),
            0.2,
            1
        );

        estado.camadaMedicoes =
            L.featureGroup().addTo(mapa);
        estado.camadaLocalizacao =
            L.featureGroup().addTo(mapa);

        criarBarras();
        criarMenuFundos();
        registrarEventosMapa();

        await Promise.allSettled([
            prepararFundos(),
            carregarPreferenciasServidor(),
        ]);

        window.setTimeout(
            () => mapa.invalidateSize(),
            120
        );
    }

    window.SemduFerramentas = {
        interceptarCliqueFeicao,
        iniciarMedicao,
        limparMedicoes,
        abrirEditorCamada,
        aplicarFundo,
    };

    document.addEventListener(
        "semdu:mapa-pronto",
        evento => iniciar(
            evento.detail?.mapa
        )
    );

    document.addEventListener(
        "semdu:camada-carregada",
        () => {
            window.SemduMapa
                ?.atualizarVisibilidadeRotulos?.();
        }
    );
})();
