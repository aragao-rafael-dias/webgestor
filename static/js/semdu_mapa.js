(() => {
    "use strict";

    const COR_SEMDU = "#232c61";
    const LIMITE_FEICOES = 5000;

    const estado = {
        mapa: null,
        catalogo: [],
        camadasAtivas: new Map(),
        carregamentos: 0,
        recarregamentoAgendado: null,
    };

    const elementos = {};

    function escaparHtml(valor) {
        return String(valor ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function texto(valor, padrao = "") {
        const resultado = String(valor ?? "").trim();
        return resultado || padrao;
    }

    async function apiGet(url) {
        const resposta = await fetch(
            url,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                },
            }
        );

        let dados = null;

        try {
            dados = await resposta.json();
        } catch {
            dados = null;
        }

        if (!resposta.ok) {
            throw new Error(
                dados?.erro
                ?? dados?.description
                ?? `Erro HTTP ${resposta.status}.`
            );
        }

        return dados;
    }

    function definirStatus(
        mensagem,
        tipo = ""
    ) {
        if (!elementos.statusCatalogo) {
            return;
        }

        elementos.statusCatalogo.className =
            `semdu-status ${tipo}`.trim();

        elementos.statusCatalogo.textContent =
            mensagem;
    }

    function mostrarAviso(mensagem) {
        if (!elementos.mapaAviso) {
            return;
        }

        elementos.mapaAviso.textContent =
            mensagem;

        elementos.mapaAviso.hidden = false;

        window.clearTimeout(
            mostrarAviso.temporizador
        );

        mostrarAviso.temporizador =
            window.setTimeout(
                () => {
                    elementos.mapaAviso.hidden = true;
                },
                7000
            );
    }

    function iniciarCarregamento() {
        estado.carregamentos += 1;

        if (elementos.mapaCarregamento) {
            elementos.mapaCarregamento.hidden =
                false;
        }
    }

    function terminarCarregamento() {
        estado.carregamentos = Math.max(
            0,
            estado.carregamentos - 1
        );

        if (
            elementos.mapaCarregamento
            && estado.carregamentos === 0
        ) {
            elementos.mapaCarregamento.hidden =
                true;
        }
    }

    function bboxAtual() {
        const limites =
            estado.mapa.getBounds();

        return [
            limites.getWest(),
            limites.getSouth(),
            limites.getEast(),
            limites.getNorth(),
        ]
            .map(
                valor => valor.toFixed(7)
            )
            .join(",");
    }

    function urlCamada(camada) {
        const parametros =
            new URLSearchParams(
                {
                    bbox: bboxAtual(),
                    limite: String(
                        LIMITE_FEICOES
                    ),
                }
            );

        return (
            "/api/semdu/camadas/"
            + encodeURIComponent(
                camada.tabela
            )
            + "/"
            + encodeURIComponent(
                camada.coluna_geometria
            )
            + "?"
            + parametros.toString()
        );
    }

    function corDaCamada(camada) {
        const indice = Math.max(
            0,
            estado.catalogo.findIndex(
                item => item.id === camada.id
            )
        );

        const cores = [
            COR_SEMDU,
            "#4052a3",
            "#136f8a",
            "#436a3f",
            "#9a5a25",
            "#7e3f79",
            "#8a3446",
        ];

        return cores[
            indice % cores.length
        ];
    }

    function valorPopup(valor) {
        if (
            valor === null
            || valor === undefined
            || valor === ""
        ) {
            return "";
        }

        if (
            typeof valor === "object"
        ) {
            try {
                return JSON.stringify(
                    valor
                );
            } catch {
                return String(
                    valor
                );
            }
        }

        return String(
            valor
        );
    }

    function popupFeature(
        feature,
        camada
    ) {
        const propriedades =
            Object.entries(
                feature?.properties
                ?? {}
            )
                .filter(
                    ([, valor]) =>
                        valor !== null
                        && valor !== ""
                )
                .slice(
                    0,
                    16
                );

        const linhas = propriedades
            .map(
                ([chave, valor]) => `
                    <div>
                        <dt>${escaparHtml(chave)}</dt>
                        <dd>${escaparHtml(
                            valorPopup(valor)
                        )}</dd>
                    </div>
                `
            )
            .join("");

        return `
            <div class="semdu-popup">
                <h3>${escaparHtml(camada.titulo)}</h3>
                <dl>
                    ${
                        linhas
                        || (
                            "<div>"
                            + "<dt>Dados</dt>"
                            + "<dd>Sem atributos públicos.</dd>"
                            + "</div>"
                        )
                    }
                </dl>
            </div>
        `;
    }

    function opcoesGeoJson(
        camada
    ) {
        const cor =
            corDaCamada(camada);

        return {
            style() {
                return {
                    color: cor,
                    weight: 3,
                    opacity: 0.9,
                    fillColor: cor,
                    fillOpacity: 0.22,
                };
            },

            pointToLayer(
                feature,
                latlng
            ) {
                return L.circleMarker(
                    latlng,
                    {
                        radius: 6,
                        color: "#ffffff",
                        weight: 2,
                        fillColor: cor,
                        fillOpacity: 0.96,
                    }
                );
            },

            onEachFeature(
                feature,
                layer
            ) {
                layer.bindPopup(
                    popupFeature(
                        feature,
                        camada
                    ),
                    {
                        maxWidth: 380,
                    }
                );

                layer.on(
                    "mouseover",
                    evento => {
                        if (
                            typeof evento.target
                                .setStyle
                            === "function"
                        ) {
                            evento.target.setStyle(
                                {
                                    weight: 5,
                                    fillOpacity: 0.34,
                                }
                            );
                        }
                    }
                );

                layer.on(
                    "mouseout",
                    evento => {
                        const grupo =
                            estado.camadasAtivas
                                .get(camada.id)
                                ?.grupo;

                        if (
                            grupo
                            && typeof grupo.resetStyle
                                === "function"
                        ) {
                            grupo.resetStyle(
                                evento.target
                            );
                        }
                    }
                );
            },
        };
    }

    async function carregarCamada(
        camada,
        {
            enquadrar = false,
            silencioso = false,
        } = {}
    ) {
        const registro =
            estado.camadasAtivas.get(
                camada.id
            );

        if (!registro) {
            return;
        }

        if (registro.controlador) {
            registro.controlador.abort();
        }

        const controlador =
            new AbortController();

        registro.controlador =
            controlador;

        if (!silencioso) {
            definirStatus(
                `Carregando ${camada.titulo}...`,
                "carregando"
            );
        }

        iniciarCarregamento();

        try {
            const resposta = await fetch(
                urlCamada(camada),
                {
                    credentials: "same-origin",
                    headers: {
                        Accept: "application/json",
                    },
                    signal: controlador.signal,
                }
            );

            const dados =
                await resposta.json();

            if (!resposta.ok) {
                throw new Error(
                    dados?.erro
                    ?? `Erro HTTP ${resposta.status}.`
                );
            }

            if (!estado.camadasAtivas.has(camada.id)) {
                return;
            }

            if (registro.grupo) {
                estado.mapa.removeLayer(
                    registro.grupo
                );
            }

            const grupo = L.geoJSON(
                dados,
                opcoesGeoJson(camada)
            ).addTo(
                estado.mapa
            );

            registro.grupo = grupo;
            registro.controlador = null;
            registro.quantidade =
                dados?.metadata
                    ?.quantidade_retornada
                ?? dados?.features?.length
                ?? 0;

            atualizarLinhaCamada(
                camada.id
            );

            if (
                enquadrar
                && registro.quantidade > 0
            ) {
                const limites =
                    grupo.getBounds();

                if (
                    limites
                    && limites.isValid()
                ) {
                    estado.mapa.fitBounds(
                        limites,
                        {
                            padding: [28, 28],
                            maxZoom: 17,
                        }
                    );
                }
            }

            if (!silencioso) {
                definirStatus(
                    (
                        `${camada.titulo}: `
                        + `${registro.quantidade} `
                        + "feição(ões) carregada(s)."
                    ),
                    "sucesso"
                );
            }
        } catch (erro) {
            if (
                erro?.name === "AbortError"
            ) {
                return;
            }

            console.error(
                `Erro ao carregar ${camada.id}:`,
                erro
            );

            definirStatus(
                erro.message
                || "Erro ao carregar a camada.",
                "erro"
            );

            mostrarAviso(
                (
                    `${camada.titulo}: `
                    + (
                        erro.message
                        || "não foi possível carregar."
                    )
                )
            );
        } finally {
            terminarCarregamento();
        }
    }

    function ativarCamada(
        camada,
        checkbox
    ) {
        if (
            estado.camadasAtivas.has(
                camada.id
            )
        ) {
            return;
        }

        estado.camadasAtivas.set(
            camada.id,
            {
                camada,
                grupo: null,
                controlador: null,
                quantidade: 0,
            }
        );

        checkbox
            ?.closest(".semdu-camada")
            ?.classList.add("ativa");

        carregarCamada(
            camada,
            {
                enquadrar:
                    estado.camadasAtivas.size
                    === 1,
            }
        );
    }

    function desativarCamada(
        camada,
        checkbox
    ) {
        const registro =
            estado.camadasAtivas.get(
                camada.id
            );

        if (!registro) {
            return;
        }

        registro.controlador?.abort();

        if (registro.grupo) {
            estado.mapa.removeLayer(
                registro.grupo
            );
        }

        estado.camadasAtivas.delete(
            camada.id
        );

        checkbox
            ?.closest(".semdu-camada")
            ?.classList.remove("ativa");

        atualizarLinhaCamada(
            camada.id
        );

        definirStatus(
            (
                `${camada.titulo} removida. `
                + `${estado.camadasAtivas.size} `
                + "camada(s) ativa(s)."
            ),
            "sucesso"
        );
    }

    function atualizarLinhaCamada(
        idCamada
    ) {
        const linha =
            elementos.listaCamadas
                ?.querySelector(
                    `[data-camada-id="${
                        CSS.escape(idCamada)
                    }"]`
                );

        if (!linha) {
            return;
        }

        const registro =
            estado.camadasAtivas.get(
                idCamada
            );

        linha.classList.toggle(
            "ativa",
            Boolean(registro)
        );

        const quantidade =
            linha.querySelector(
                "[data-quantidade]"
            );

        if (quantidade) {
            quantidade.textContent =
                registro
                    ? `${registro.quantidade} no mapa`
                    : "desativada";
        }
    }

    function criarLinhaCamada(
        camada
    ) {
        const label =
            document.createElement(
                "label"
            );

        label.className =
            "semdu-camada";

        label.dataset.camadaId =
            camada.id;

        const checkbox =
            document.createElement(
                "input"
            );

        checkbox.type = "checkbox";
        checkbox.checked =
            estado.camadasAtivas.has(
                camada.id
            );

        const bloco =
            document.createElement(
                "span"
            );

        bloco.className =
            "semdu-camada-texto";

        bloco.innerHTML = `
            <strong>${escaparHtml(camada.titulo)}</strong>
            <small>
                ${escaparHtml(camada.tabela)}
                · ${escaparHtml(camada.coluna_geometria)}
            </small>
            <span class="semdu-camada-meta">
                <span>${escaparHtml(camada.tipo_geometria)}</span>
                <span>SRID ${escaparHtml(camada.srid)}</span>
                <span data-quantidade>
                    ${
                        estado.camadasAtivas.has(camada.id)
                            ? (
                                estado.camadasAtivas
                                    .get(camada.id)
                                    ?.quantidade
                                ?? 0
                            ) + " no mapa"
                            : "desativada"
                    }
                </span>
            </span>
        `;

        checkbox.addEventListener(
            "change",
            () => {
                if (checkbox.checked) {
                    ativarCamada(
                        camada,
                        checkbox
                    );
                } else {
                    desativarCamada(
                        camada,
                        checkbox
                    );
                }
            }
        );

        label.append(
            checkbox,
            bloco
        );

        return label;
    }

    function renderizarCatalogo() {
        const termo = texto(
            elementos.buscarCamada?.value
        ).toLocaleLowerCase("pt-BR");

        const filtradas =
            estado.catalogo.filter(
                camada => {
                    if (!termo) {
                        return true;
                    }

                    return [
                        camada.titulo,
                        camada.tabela,
                        camada.coluna_geometria,
                        camada.tipo_geometria,
                    ]
                        .join(" ")
                        .toLocaleLowerCase("pt-BR")
                        .includes(termo);
                }
            );

        elementos.listaCamadas.innerHTML =
            "";

        if (!filtradas.length) {
            elementos.listaCamadas.innerHTML = `
                <div class="semdu-lista-vazia">
                    Nenhuma camada corresponde à busca.
                </div>
            `;
            return;
        }

        const fragmento =
            document.createDocumentFragment();

        filtradas.forEach(
            camada => {
                fragmento.appendChild(
                    criarLinhaCamada(
                        camada
                    )
                );
            }
        );

        elementos.listaCamadas.appendChild(
            fragmento
        );
    }

    async function carregarCatalogo() {
        definirStatus(
            "Consultando o catálogo do PostGIS...",
            "carregando"
        );

        try {
            const dados = await apiGet(
                "/api/semdu/camadas"
            );

            estado.catalogo =
                Array.isArray(dados?.camadas)
                    ? dados.camadas
                    : [];

            renderizarCatalogo();

            if (!estado.catalogo.length) {
                definirStatus(
                    (
                        "Nenhuma tabela espacial foi "
                        + "encontrada no schema semdu."
                    )
                );
                return;
            }

            definirStatus(
                (
                    `${estado.catalogo.length} `
                    + "camada(s) disponível(is)."
                ),
                "sucesso"
            );
        } catch (erro) {
            console.error(
                "Erro ao carregar catálogo:",
                erro
            );

            estado.catalogo = [];
            renderizarCatalogo();

            definirStatus(
                erro.message
                || "Erro ao consultar o catálogo.",
                "erro"
            );
        }
    }

    function recarregarCamadasAtivas() {
        window.clearTimeout(
            estado.recarregamentoAgendado
        );

        estado.recarregamentoAgendado =
            window.setTimeout(
                () => {
                    estado.camadasAtivas
                        .forEach(
                            registro => {
                                carregarCamada(
                                    registro.camada,
                                    {
                                        enquadrar: false,
                                        silencioso: true,
                                    }
                                );
                            }
                        );
                },
                350
            );
    }

    function abrirPainel() {
        document.body.classList.add(
            "painel-aberto"
        );

        elementos.abrirPainel?.setAttribute(
            "aria-expanded",
            "true"
        );

        if (elementos.fundoPainel) {
            elementos.fundoPainel.hidden =
                false;
        }
    }

    function fecharPainel() {
        document.body.classList.remove(
            "painel-aberto"
        );

        elementos.abrirPainel?.setAttribute(
            "aria-expanded",
            "false"
        );

        if (elementos.fundoPainel) {
            elementos.fundoPainel.hidden =
                true;
        }
    }

    function inicializarMapa() {
        if (typeof L === "undefined") {
            throw new Error(
                (
                    "A biblioteca Leaflet não foi carregada. "
                    + "Confira a conexão e o arquivo mapa.html."
                )
            );
        }

        estado.mapa = L.map(
            "map",
            {
                preferCanvas: true,
                zoomControl: true,
            }
        ).setView(
            [-10.9160, -37.6680],
            12
        );

        const mapaClaro =
            L.tileLayer(
                (
                    "https://{s}.basemaps.cartocdn.com/"
                    + "light_all/{z}/{x}/{y}{r}.png"
                ),
                {
                    maxZoom: 20,
                    attribution:
                        "&copy; OpenStreetMap &copy; CARTO",
                }
            ).addTo(
                estado.mapa
            );

        const osm =
            L.tileLayer(
                (
                    "https://{s}.tile.openstreetmap.org/"
                    + "{z}/{x}/{y}.png"
                ),
                {
                    maxZoom: 19,
                    attribution:
                        "&copy; OpenStreetMap contributors",
                }
            );

        L.control.layers(
            {
                "Mapa claro": mapaClaro,
                "OpenStreetMap": osm,
            },
            {},
            {
                position: "topright",
            }
        ).addTo(
            estado.mapa
        );

        L.control.scale(
            {
                imperial: false,
                position: "bottomright",
            }
        ).addTo(
            estado.mapa
        );

        estado.mapa.on(
            "mousemove",
            evento => {
                elementos.coordenadas.textContent =
                    (
                        `Lat ${evento.latlng.lat.toFixed(6)}`
                        + ` · Lon ${evento.latlng.lng.toFixed(6)}`
                    );
            }
        );

        estado.mapa.on(
            "moveend",
            recarregarCamadasAtivas
        );

        window.setTimeout(
            () => {
                estado.mapa.invalidateSize();
            },
            120
        );
    }

    function obterElementos() {
        elementos.listaCamadas =
            document.getElementById(
                "lista-camadas"
            );

        elementos.statusCatalogo =
            document.getElementById(
                "status-catalogo"
            );

        elementos.buscarCamada =
            document.getElementById(
                "buscar-camada"
            );

        elementos.coordenadas =
            document.getElementById(
                "coordenadas"
            );

        elementos.mapaCarregamento =
            document.getElementById(
                "mapa-carregamento"
            );

        elementos.mapaAviso =
            document.getElementById(
                "mapa-aviso"
            );

        elementos.abrirPainel =
            document.getElementById(
                "abrir-painel"
            );

        elementos.fecharPainel =
            document.getElementById(
                "fechar-painel"
            );

        elementos.fundoPainel =
            document.getElementById(
                "fundo-painel"
            );
    }

    function registrarEventos() {
        elementos.buscarCamada
            ?.addEventListener(
                "input",
                renderizarCatalogo
            );

        elementos.abrirPainel
            ?.addEventListener(
                "click",
                abrirPainel
            );

        elementos.fecharPainel
            ?.addEventListener(
                "click",
                fecharPainel
            );

        elementos.fundoPainel
            ?.addEventListener(
                "click",
                fecharPainel
            );

        document.addEventListener(
            "keydown",
            evento => {
                if (evento.key === "Escape") {
                    fecharPainel();
                }
            }
        );

        window.addEventListener(
            "resize",
            () => {
                estado.mapa?.invalidateSize();

                if (
                    window.innerWidth > 820
                ) {
                    fecharPainel();
                }
            }
        );
    }

    async function iniciar() {
        obterElementos();
        registrarEventos();

        try {
            inicializarMapa();
            await carregarCatalogo();
        } catch (erro) {
            console.error(
                "Erro na inicialização da SEMDU:",
                erro
            );

            definirStatus(
                erro.message
                || "Não foi possível iniciar o mapa.",
                "erro"
            );

            mostrarAviso(
                erro.message
                || "Não foi possível iniciar o mapa."
            );
        }
    }

    document.addEventListener(
        "DOMContentLoaded",
        iniciar
    );
})();
