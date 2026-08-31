(() => {
    "use strict";

    const permissoes = {
        fiscalSemdu:
            document.body.dataset.fiscalSemdu
            === "true",
        fiscalSemfaz:
            document.body.dataset.fiscalSemfaz
            === "true",
    };

    const ROTULOS_STATUS = {
        RASCUNHO: "Rascunho",
        PLANEJADA_AUTORIZADA:
            "Planejada - autorizada",
        PLANEJADA_LIBERADA:
            "Planejada - liberada",
        DEVOLVIDA_AJUSTES:
            "Devolvida para ajustes",
        CANCELADA: "Cancelada",
    };

    const CORES_STATUS = {
        RASCUNHO: "#7d8492",
        PLANEJADA_AUTORIZADA: "#d58b20",
        PLANEJADA_LIBERADA: "#2d8a58",
        DEVOLVIDA_AJUSTES: "#bd4236",
        CANCELADA: "#9b9b9b",
    };

    const estado = {
        mapa: null,
        camadaLogradouros: null,
        camadasPorId: new Map(),
        drawnItems: null,
        controleDesenho: null,
        ferramentaDesenho: null,
        ferramentaEdicao: null,
        geometriaRascunho: null,
        logradouros: [],
        detalhe: null,
        selecionadoId: null,
        filtroStatus: "TODOS",
        carregamentos: 0,
        recarregarTimer: null,
        recarregarPendente: false,
        popupAbertoId: null,
        carregandoDetalhe: false,
        detalheToken: 0,
    };

    const el = {};

    function escaparHtml(valor) {
        return String(valor ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function texto(valor, padrao = "-") {
        const resultado = String(valor ?? "").trim();
        return resultado || padrao;
    }

    function numero(valor, casas = 2) {
        const n = Number(valor);

        if (!Number.isFinite(n)) {
            return "-";
        }

        return n.toLocaleString(
            "pt-BR",
            {
                minimumFractionDigits: casas,
                maximumFractionDigits: casas,
            }
        );
    }

    function dataHora(valor) {
        if (!valor) {
            return "-";
        }

        const data = new Date(valor);

        if (Number.isNaN(data.getTime())) {
            return texto(valor);
        }

        return data.toLocaleString(
            "pt-BR",
            {
                dateStyle: "short",
                timeStyle: "short",
            }
        );
    }

    async function lerRespostaJson(resposta) {
        const corpo = await resposta.text();

        if (!corpo.trim()) {
            if (resposta.ok) {
                return {};
            }

            throw new Error(
                `O servidor respondeu HTTP ${resposta.status} sem conteúdo.`
            );
        }

        try {
            return JSON.parse(corpo);
        } catch (erro) {
            console.error(
                "Resposta não JSON:",
                resposta.status,
                corpo
            );

            throw new Error(
                `O servidor não devolveu JSON (HTTP ${resposta.status}).`
            );
        }
    }

    async function api(
        url,
        opcoes = {}
    ) {
        const resposta = await fetch(
            url,
            {
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    ...(opcoes.body instanceof FormData
                        ? {}
                        : {
                            "Content-Type":
                                "application/json",
                        }),
                    ...(opcoes.headers || {}),
                },
                ...opcoes,
            }
        );

        const dados = await lerRespostaJson(
            resposta
        );

        if (!resposta.ok) {
            throw new Error(
                dados?.detalhes
                ?? dados?.erro
                ?? dados?.description
                ?? `Erro HTTP ${resposta.status}.`
            );
        }

        return dados;
    }

    function iniciarCarregamento() {
        estado.carregamentos += 1;
        el.carregando.hidden = false;
    }

    function terminarCarregamento() {
        estado.carregamentos = Math.max(
            0,
            estado.carregamentos - 1
        );
        el.carregando.hidden =
            estado.carregamentos === 0;
    }

    function status(
        mensagem,
        tipo = ""
    ) {
        el.status.className =
            `ct-status ${tipo}`.trim();
        el.status.textContent = mensagem;
    }

    function toast(
        mensagem,
        tipo = ""
    ) {
        el.toast.className =
            `ct-toast ${tipo}`.trim();
        el.toast.textContent = mensagem;
        el.toast.hidden = false;

        clearTimeout(toast.timer);
        toast.timer = setTimeout(
            () => {
                el.toast.hidden = true;
            },
            5000
        );
    }

    function bboxAtual() {
        const b = estado.mapa.getBounds();

        return [
            b.getWest(),
            b.getSouth(),
            b.getEast(),
            b.getNorth(),
        ]
            .map(v => v.toFixed(7))
            .join(",");
    }

    function estiloFeature(feature) {
        const statusFeature =
            feature?.properties?.status
            || "RASCUNHO";
        const selecionada =
            Number(feature?.properties?.id)
            === Number(estado.selecionadoId);

        return {
            color:
                CORES_STATUS[statusFeature]
                || "#7d8492",
            weight: selecionada ? 7 : 5,
            opacity: selecionada ? 1 : 0.9,
            dashArray:
                statusFeature === "RASCUNHO"
                    ? "8 7"
                    : statusFeature === "DEVOLVIDA_AJUSTES"
                        ? "4 7"
                        : null,
            lineCap: "round",
            lineJoin: "round",
        };
    }

    function popupFeature(feature) {
        const p = feature.properties || {};

        return `
            <div class="ct-popup">
                <h3>${escaparHtml(p.nome_completo)}</h3>
                <p><b>Situação:</b> ${escaparHtml(ROTULOS_STATUS[p.status] || p.status)}</p>
                <p><b>Protocolo:</b> ${escaparHtml(p.protocolo)}</p>
                <p><b>Extensão:</b> ${numero(p.extensao_m)} m</p>
                <button type="button" data-abrir-id="${Number(p.id)}">
                    Abrir processo
                </button>
            </div>
        `;
    }

    function camadaGeoJson(geojson) {
        estado.camadasPorId.clear();

        if (estado.camadaLogradouros) {
            estado.mapa.removeLayer(
                estado.camadaLogradouros
            );
        }

        estado.camadaLogradouros = L.geoJSON(
            geojson,
            {
                style: estiloFeature,
                onEachFeature(feature, layer) {
                    const id = Number(
                        feature.properties?.id
                    );

                    estado.camadasPorId.set(
                        id,
                        layer
                    );

                    layer.bindPopup(
                        popupFeature(feature),
                        {
                            maxWidth: 340,
                            minWidth: 250,
                            autoClose: false,
                            closeOnClick: false,
                            closeButton: true,
                            keepInView: true,
                            className: "ct-popup-container",
                        }
                    );

                    layer.on("click", () => {
                        estado.popupAbertoId = id;

                        // O painel é aberto sem reposicionar o mapa.
                        // Isso evita o fechamento imediato do popup.
                        abrirDetalhe(id, false);
                    });

                    layer.on("popupopen", () => {
                        estado.popupAbertoId = id;
                    });

                    layer.on("popupclose", () => {
                        if (
                            Number(estado.popupAbertoId)
                            === id
                        ) {
                            estado.popupAbertoId = null;
                        }

                        if (estado.recarregarPendente) {
                            estado.recarregarPendente = false;

                            clearTimeout(
                                estado.recarregarTimer
                            );

                            estado.recarregarTimer =
                                setTimeout(
                                    () => carregarLogradouros({
                                        silencioso: true,
                                    }),
                                    150
                                );
                        }
                    });
                },
            }
        ).addTo(estado.mapa);
    }

    function atualizarEstilos() {
        estado.camadaLogradouros
            ?.eachLayer(layer => {
                if (
                    layer.feature
                    && typeof layer.setStyle
                        === "function"
                ) {
                    layer.setStyle(
                        estiloFeature(
                            layer.feature
                        )
                    );
                }
            });
    }

    async function carregarLogradouros({ silencioso = false } = {}) {
        clearTimeout(
            estado.recarregarTimer
        );

        if (
            silencioso
            && (
                estado.popupAbertoId !== null
                || estado.carregandoDetalhe
            )
        ) {
            estado.recarregarPendente = true;
            return;
        }

        if (!silencioso) {
            status("Carregando logradouros...");
        }

        try {
            const params = new URLSearchParams({
                bbox: bboxAtual(),
                limite: "5000",
            });

            const dados = await api(
                `/api/cadastro-territorial/logradouros?${params}`
            );

            estado.logradouros =
                dados.features || [];

            camadaGeoJson(dados);
            renderizarLista();

            if (!silencioso) {
                status(
                    `${estado.logradouros.length} logradouro(s) na área visível.`,
                    "sucesso"
                );
            }
        } catch (erro) {
            console.error(erro);
            status(
                erro.message,
                "erro"
            );
        }
    }

    function logradourosFiltrados() {
        const termo = String(
            el.busca.value || ""
        )
            .trim()
            .toLocaleLowerCase("pt-BR");

        return estado.logradouros.filter(
            feature => {
                const p = feature.properties || {};

                if (
                    estado.filtroStatus !== "TODOS"
                    && p.status !== estado.filtroStatus
                ) {
                    return false;
                }

                if (!termo) {
                    return true;
                }

                return [
                    p.nome_completo,
                    p.protocolo,
                    p.bairro,
                    p.localidade,
                ]
                    .join(" ")
                    .toLocaleLowerCase("pt-BR")
                    .includes(termo);
            }
        );
    }

    function renderizarLista() {
        const filtrados =
            logradourosFiltrados();

        el.lista.innerHTML = "";

        if (!filtrados.length) {
            el.lista.innerHTML = `
                <div class="ct-status">
                    Nenhum logradouro corresponde ao filtro.
                </div>
            `;
            return;
        }

        const fragmento =
            document.createDocumentFragment();

        filtrados.forEach(feature => {
            const p = feature.properties || {};
            const botao =
                document.createElement("button");

            botao.type = "button";
            botao.className =
                `ct-item status-${p.status}`;

            if (
                Number(p.id)
                === Number(estado.selecionadoId)
            ) {
                botao.classList.add("ativo");
            }

            botao.innerHTML = `
                <div class="ct-item-topo">
                    <strong>${escaparHtml(p.nome_completo)}</strong>
                    <small>${escaparHtml(p.protocolo)}</small>
                </div>
                <small>
                    ${escaparHtml(
                        [p.bairro, p.localidade]
                            .filter(Boolean)
                            .join(" / ")
                        || "Localidade não informada"
                    )}
                </small>
                <div class="ct-item-meta">
                    <span>${escaparHtml(ROTULOS_STATUS[p.status] || p.status)}</span>
                    <span>${numero(p.extensao_m)} m</span>
                    <span>${Number(p.documentos || 0)} documento(s)</span>
                </div>
            `;

            botao.addEventListener(
                "click",
                () => abrirDetalhe(
                    Number(p.id),
                    true
                )
            );

            fragmento.appendChild(botao);
        });

        el.lista.appendChild(fragmento);
    }

    function abrirPainelLista() {
        document.body.classList.add(
            "ct-lista-aberta"
        );
        document.body.classList.remove(
            "ct-detalhe-aberto"
        );
        el.fundoMobile.hidden = false;
    }

    function abrirPainelDetalhe() {
        document.body.classList.add(
            "ct-detalhe-selecionado"
        );

        if (window.innerWidth <= 980) {
            document.body.classList.add(
                "ct-detalhe-aberto"
            );
            document.body.classList.remove(
                "ct-lista-aberta"
            );
            el.fundoMobile.hidden = false;
        }
    }

    function fecharPaineisMobile() {
        document.body.classList.remove(
            "ct-lista-aberta",
            "ct-detalhe-aberto"
        );
        el.fundoMobile.hidden = true;
    }

    function focarFeature(id) {
        const layer =
            estado.camadasPorId.get(
                Number(id)
            );

        if (!layer) {
            return;
        }

        const bounds = layer.getBounds?.();

        if (bounds?.isValid()) {
            estado.mapa.fitBounds(
                bounds,
                {
                    padding: [40, 40],
                    maxZoom: 18,
                }
            );
        }
    }

    async function abrirDetalhe(
        id,
        focar = false
    ) {
        const token =
            ++estado.detalheToken;

        estado.carregandoDetalhe = true;
        estado.selecionadoId = Number(id);

        renderizarLista();
        atualizarEstilos();
        abrirPainelDetalhe();

        el.vazio.hidden = true;
        el.detalhe.hidden = true;
        el.detalheErro.hidden = true;
        el.detalheCarregando.hidden = false;

        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${id}`
            );

            if (token !== estado.detalheToken) {
                return;
            }

            estado.detalhe =
                dados.logradouro;

            renderizarDetalhe();
            renderizarLista();
            atualizarEstilos();

            el.detalheCarregando.hidden = true;
            el.detalheErro.hidden = true;
            el.detalhe.hidden = false;

            if (focar) {
                focarFeature(id);
            }
        } catch (erro) {
            if (token !== estado.detalheToken) {
                return;
            }

            console.error(
                "Erro ao abrir o processo:",
                erro
            );

            estado.detalhe = null;
            el.detalheCarregando.hidden = true;
            el.detalhe.hidden = true;
            el.detalheErro.hidden = false;
            el.detalheErroMensagem.textContent =
                erro.message
                || "Não foi possível carregar o processo.";

            toast(
                erro.message,
                "erro"
            );
        } finally {
            if (token === estado.detalheToken) {
                estado.carregandoDetalhe = false;
            }

            terminarCarregamento();
        }
    }

    function fecharDetalhe() {
        estado.detalheToken += 1;
        estado.carregandoDetalhe = false;
        estado.detalhe = null;
        estado.selecionadoId = null;

        el.detalhe.hidden = true;
        el.detalheCarregando.hidden = true;
        el.detalheErro.hidden = true;
        el.acoesProcesso.hidden = true;
        el.acoesProcesso.innerHTML = "";
        el.vazio.hidden = false;

        document.body.classList.remove(
            "ct-detalhe-selecionado"
        );

        estado.mapa.closePopup();
        renderizarLista();
        atualizarEstilos();
        fecharPaineisMobile();
    }

    function linhaResumo(rotulo, valor) {
        return `
            <div>
                <dt>${escaparHtml(rotulo)}</dt>
                <dd>${escaparHtml(texto(valor))}</dd>
            </div>
        `;
    }

    function renderizarDocumentos() {
        const detalhe = estado.detalhe;
        const documentos =
            detalhe?.documentos || [];

        if (!documentos.length) {
            el.documentos.innerHTML = `
                <div class="ct-status">
                    Nenhum documento comprobatório anexado.
                </div>
            `;
            return;
        }

        el.documentos.innerHTML =
            documentos.map(item => `
                <div class="ct-documento">
                    <div>
                        <strong>${escaparHtml(item.nome_original)}</strong>
                        <small>
                            ${escaparHtml(item.tipo_documento)} ·
                            ${escaparHtml(item.orgao_origem)} ·
                            ${escaparHtml(item.enviado_por_nome || "-")}
                        </small>
                    </div>
                    <div class="ct-documento-acoes">
                        <a
                            class="ct-link-mini"
                            href="/api/cadastro-territorial/logradouros/${detalhe.id}/documentos/${item.id}"
                        >
                            Baixar
                        </a>
                        ${
                            permissoes.fiscalSemdu
                            && ["RASCUNHO", "DEVOLVIDA_AJUSTES"]
                                .includes(detalhe.status)
                                ? `
                                    <button
                                        type="button"
                                        class="ct-botao-mini perigo"
                                        data-remover-documento="${item.id}"
                                    >
                                        Remover
                                    </button>
                                `
                                : ""
                        }
                    </div>
                </div>
            `).join("");
    }

    function renderizarOficios() {
        const detalhe = estado.detalhe;
        const oficios =
            detalhe?.oficios || [];

        if (!oficios.length) {
            el.oficios.innerHTML = `
                <div class="ct-status">
                    O ofício ainda não foi gerado.
                </div>
            `;
            return;
        }

        el.oficios.innerHTML =
            oficios.map(item => `
                <div class="ct-oficio">
                    <div>
                        <strong>Ofício nº ${item.numero}/${item.ano} - SEMDU</strong>
                        <small>Gerado em ${dataHora(item.criado_em)}</small>
                    </div>
                    <div class="ct-oficio-acoes">
                        <a
                            class="ct-link-mini"
                            href="/api/cadastro-territorial/logradouros/${detalhe.id}/oficios/${item.id}/pdf"
                        >PDF</a>
                        <a
                            class="ct-link-mini"
                            href="/api/cadastro-territorial/logradouros/${detalhe.id}/oficios/${item.id}/docx"
                        >DOCX</a>
                    </div>
                </div>
            `).join("");
    }

    function botaoAcao(
        id,
        titulo,
        classe = "ct-botao-secundario",
        desabilitado = false
    ) {
        return `
            <button
                type="button"
                id="${id}"
                class="${classe}"
                ${desabilitado ? "disabled" : ""}
            >
                ${titulo}
            </button>
        `;
    }

    function renderizarAcoes() {
        const d = estado.detalhe;
        const acoes = [];

        if (
            permissoes.fiscalSemdu
            && ["RASCUNHO", "DEVOLVIDA_AJUSTES"]
                .includes(d.status)
        ) {
            const tiposComprovatorios =
                new Set([
                    "CONSOLIDACAO",
                    "FOTOGRAFIA",
                    "ATO_ADMINISTRATIVO",
                    "PLANTA",
                    "DECLARACAO",
                    "LEVANTAMENTO",
                ]);

            const comprovacoes =
                (d.documentos || []).filter(
                    item => tiposComprovatorios.has(
                        item.tipo_documento
                    )
                );

            const possuiComprovacao =
                comprovacoes.length > 0;

            acoes.push(`
                <div class="ct-fluxo-etapa">
                    <span>PRÓXIMA ETAPA</span>
                    <strong>
                        ${
                            d.status === "RASCUNHO"
                                ? "Autorizar e encaminhar à SEMFAZ"
                                : "Corrigir e reenviar à SEMFAZ"
                        }
                    </strong>
                    <p>
                        ${
                            possuiComprovacao
                                ? (
                                    "Documento comprobatório localizado. "
                                    + "O processo pode gerar o ofício e sair do modo rascunho."
                                )
                                : (
                                    "Para sair do modo rascunho, anexe ao menos "
                                    + "um documento que comprove a consolidação "
                                    + "ou a situação física da rua."
                                )
                        }
                    </p>
                </div>
            `);

            if (!possuiComprovacao) {
                acoes.push(
                    botaoAcao(
                        "ct-ir-documentos",
                        "Anexar documento comprobatório",
                        "ct-botao-secundario"
                    )
                );
            }

            acoes.push(
                `<div class="linha">
                    ${botaoAcao(
                        "ct-editar",
                        "Editar dados e traçado"
                    )}
                    ${botaoAcao(
                        "ct-autorizar",
                        "Autorizar e enviar à SEMFAZ",
                        "ct-botao-primario",
                        !possuiComprovacao
                    )}
                </div>`,
                botaoAcao(
                    "ct-cancelar-processo",
                    "Cancelar planejamento",
                    "ct-botao-perigo"
                )
            );
        }

        if (
            permissoes.fiscalSemfaz
            && d.status === "PLANEJADA_AUTORIZADA"
        ) {
            acoes.push(
                `<div class="ct-fluxo-etapa semfaz">
                    <span>ANÁLISE SEMFAZ</span>
                    <strong>Conferir e deliberar</strong>
                    <p>
                        Consulte o ofício, o memorial e os documentos.
                        Depois libere o logradouro ou devolva para ajustes.
                    </p>
                </div>`,
                `<div class="linha">
                    ${botaoAcao(
                        "ct-devolver",
                        "Devolver para ajustes",
                        "ct-botao-perigo"
                    )}
                    ${botaoAcao(
                        "ct-liberar",
                        "Liberar logradouro",
                        "ct-botao-sucesso"
                    )}
                </div>`
            );
        }

        if (!acoes.length) {
            el.acoesProcesso.innerHTML = "";
            el.acoesProcesso.hidden = true;
            return;
        }

        el.acoesProcesso.hidden = false;
        el.acoesProcesso.innerHTML =
            acoes.join("");
    }

    function renderizarDetalhe() {
        const d = estado.detalhe;

        el.detalheProtocolo.textContent =
            d.protocolo;
        el.detalheNome.textContent =
            d.nome_completo;
        el.detalheStatus.className =
            `ct-status-badge ${d.status}`;
        el.detalheStatus.textContent =
            ROTULOS_STATUS[d.status]
            || d.status;

        el.resumo.innerHTML = [
            linhaResumo(
                "Localização",
                [d.bairro, d.localidade]
                    .filter(Boolean)
                    .join(" / ")
            ),
            linhaResumo(
                "Extensão",
                `${numero(d.extensao_m)} m`
            ),
            linhaResumo(
                "Largura",
                d.largura_m
                    ? `${numero(d.largura_m)} m`
                    : "Não informada"
            ),
            linhaResumo(
                "Início",
                d.coordenada_inicial
            ),
            linhaResumo(
                "Fim",
                d.coordenada_final
            ),
            linhaResumo(
                "Planejado por",
                d.criado_por_nome
            ),
            linhaResumo(
                "Autorizado por",
                d.autorizado_por_nome
            ),
            linhaResumo(
                "Liberado por",
                d.liberado_por_nome
            ),
        ].join("");

        el.memorial.textContent =
            texto(
                d.memorial_descritivo,
                "Memorial não informado."
            );

        if (d.justificativa_devolucao) {
            el.alertaDevolucao.hidden = false;
            el.alertaDevolucao.textContent =
                `Devolução da SEMFAZ: ${d.justificativa_devolucao}`;
        } else {
            el.alertaDevolucao.hidden = true;
            el.alertaDevolucao.textContent = "";
        }

        renderizarDocumentos();
        renderizarOficios();
        renderizarAcoes();
    }

    function limparDesenho() {
        estado.ferramentaDesenho?.disable();
        estado.ferramentaEdicao?.disable();
        estado.ferramentaDesenho = null;
        estado.ferramentaEdicao = null;
        estado.drawnItems.clearLayers();
        estado.geometriaRascunho = null;
    }

    function layerDaGeometria(geometry) {
        const layer = L.geoJSON(
            {
                type: "Feature",
                properties: {},
                geometry,
            },
            {
                style: {
                    color: "#315f72",
                    weight: 6,
                    opacity: 0.95,
                },
            }
        );

        let linha = null;
        layer.eachLayer(item => {
            linha = item;
        });

        return linha;
    }

    function definirGeometria(
        geometry,
        { enquadrar = true } = {}
    ) {
        limparDesenho();

        const linha =
            layerDaGeometria(geometry);

        if (!linha) {
            throw new Error(
                "Não foi possível preparar a geometria."
            );
        }

        estado.drawnItems.addLayer(
            linha
        );
        estado.geometriaRascunho =
            linha.toGeoJSON().geometry;

        if (
            enquadrar
            && linha.getBounds().isValid()
        ) {
            estado.mapa.fitBounds(
                linha.getBounds(),
                {
                    padding: [45, 45],
                    maxZoom: 18,
                }
            );
        }

        atualizarResumoGeometria();
    }

    function geometriaAtual() {
        let geometry = null;

        estado.drawnItems.eachLayer(
            layer => {
                geometry =
                    layer.toGeoJSON().geometry;
            }
        );

        estado.geometriaRascunho =
            geometry;

        return geometry;
    }

    function atualizarResumoGeometria() {
        const geometry = geometriaAtual();

        if (!geometry) {
            el.geometriaResumo.textContent =
                "Nenhuma geometria definida.";
            return;
        }

        const total =
            geometry.coordinates?.length
            || 0;
        const primeiro =
            geometry.coordinates?.[0];
        const ultimo =
            geometry.coordinates?.[
                total - 1
            ];

        el.geometriaResumo.textContent =
            `Linha com ${total} vértice(s). `
            + (
                primeiro && ultimo
                    ? `Início ${Number(primeiro[1]).toFixed(7)}, ${Number(primeiro[0]).toFixed(7)} · `
                        + `fim ${Number(ultimo[1]).toFixed(7)}, ${Number(ultimo[0]).toFixed(7)}.`
                    : ""
            );
    }

    function abrirFormularioNovo() {
        el.formLogradouro.reset();
        el.formLogradouro.elements.id.value = "";
        el.formTitulo.textContent =
            "Novo logradouro";
        atualizarResumoGeometria();
        el.dialogFormulario.showModal();
    }

    function abrirFormularioEdicao() {
        const d = estado.detalhe;

        if (!d) {
            return;
        }

        el.formLogradouro.reset();
        const f = el.formLogradouro.elements;

        f.id.value = d.id;
        f.tipo_logradouro.value =
            d.tipo_logradouro;
        f.nome_proposto.value =
            d.nome_proposto || "";
        f.bairro.value = d.bairro || "";
        f.localidade.value =
            d.localidade || "";
        f.cep.value = d.cep || "";
        f.largura_m.value =
            d.largura_m || "";
        f.codigo_municipal.value =
            d.codigo_municipal || "";
        f.descricao.value =
            d.descricao || "";
        f.memorial_descritivo.value =
            d.memorial_descritivo || "";
        f.observacoes_semdu.value =
            d.observacoes_semdu || "";

        el.formTitulo.textContent =
            `Editar ${d.protocolo}`;

        definirGeometria(
            d.geometry,
            { enquadrar: true }
        );

        estado.ferramentaEdicao =
            new L.EditToolbar.Edit(
                estado.mapa,
                {
                    featureGroup:
                        estado.drawnItems,
                }
            );
        estado.ferramentaEdicao.enable();

        el.dialogFormulario.show();
        toast(
            "O formulário ficou aberto sem bloquear o mapa. Arraste os vértices da linha e salve quando concluir."
        );
        fecharPaineisMobile();
    }

    function iniciarDesenho() {
        limparDesenho();

        estado.ferramentaDesenho =
            new L.Draw.Polyline(
                estado.mapa,
                {
                    shapeOptions: {
                        color: "#315f72",
                        weight: 6,
                        opacity: 0.95,
                    },
                    showLength: true,
                    metric: true,
                    repeatMode: false,
                }
            );

        estado.ferramentaDesenho.enable();
        toast(
            "Clique para adicionar vértices. Dê duplo clique para concluir."
        );
        fecharPaineisMobile();
    }

    async function salvarFormulario(evento) {
        evento.preventDefault();

        const geometry =
            geometriaAtual();

        if (!geometry) {
            toast(
                "Desenhe ou importe o eixo da rua antes de salvar.",
                "erro"
            );
            return;
        }

        const form =
            new FormData(el.formLogradouro);
        const id = form.get("id");

        const corpo = {
            tipo_logradouro:
                form.get("tipo_logradouro"),
            nome_proposto:
                form.get("nome_proposto"),
            bairro: form.get("bairro"),
            localidade:
                form.get("localidade"),
            cep: form.get("cep"),
            largura_m:
                form.get("largura_m") || null,
            codigo_municipal:
                form.get("codigo_municipal"),
            descricao:
                form.get("descricao"),
            memorial_descritivo:
                form.get("memorial_descritivo"),
            observacoes_semdu:
                form.get("observacoes_semdu"),
            geometry,
        };

        iniciarCarregamento();

        try {
            const dados = await api(
                id
                    ? `/api/cadastro-territorial/logradouros/${id}`
                    : "/api/cadastro-territorial/logradouros",
                {
                    method: id ? "PUT" : "POST",
                    body: JSON.stringify(corpo),
                }
            );

            el.dialogFormulario.close();
            limparDesenho();
            await carregarLogradouros();
            await abrirDetalhe(
                Number(id || dados.id),
                true
            );
            toast(
                dados.mensagem,
                ""
            );
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function importarArquivo(evento) {
        evento.preventDefault();
        const formData =
            new FormData(el.formImportar);

        iniciarCarregamento();

        try {
            const dados = await api(
                "/api/cadastro-territorial/importar",
                {
                    method: "POST",
                    body: formData,
                }
            );

            el.dialogImportar.close();
            el.formImportar.reset();
            definirGeometria(
                dados.feature.geometry,
                { enquadrar: true }
            );
            abrirFormularioNovo();
            toast(
                `Arquivo importado: ${dados.metricas.total_vertices} vértice(s), ${numero(dados.metricas.extensao_m)} m.`
            );
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function anexarDocumento(evento) {
        evento.preventDefault();

        if (!estado.detalhe) {
            return;
        }

        const formData =
            new FormData(el.formDocumento);
        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${estado.detalhe.id}/documentos`,
                {
                    method: "POST",
                    body: formData,
                }
            );

            el.formDocumento.reset();
            await abrirDetalhe(
                estado.detalhe.id,
                false
            );
            toast(dados.mensagem);
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function removerDocumento(id) {
        if (!estado.detalhe) {
            return;
        }

        if (!confirm(
            "Remover este documento do processo?"
        )) {
            return;
        }

        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${estado.detalhe.id}/documentos/${id}`,
                { method: "DELETE" }
            );

            await abrirDetalhe(
                estado.detalhe.id,
                false
            );
            toast(dados.mensagem);
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function autorizar(evento) {
        evento.preventDefault();

        const id = estado.detalhe?.id;

        if (!id) {
            return;
        }

        const form =
            new FormData(el.formAutorizar);
        const corpo = Object.fromEntries(
            form.entries()
        );

        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${id}/autorizar`,
                {
                    method: "POST",
                    body: JSON.stringify(corpo),
                }
            );

            el.dialogAutorizar.close();
            await carregarLogradouros();
            await abrirDetalhe(id, true);
            toast(dados.mensagem);
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function liberar() {
        const id = estado.detalhe?.id;
        const observacao = prompt(
            "Informe a análise ou referência cadastral da SEMFAZ:"
        );

        if (!id || !observacao?.trim()) {
            return;
        }

        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${id}/liberar`,
                {
                    method: "POST",
                    body: JSON.stringify({
                        observacao,
                    }),
                }
            );

            await carregarLogradouros();
            await abrirDetalhe(id, true);
            toast(dados.mensagem);
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function devolver() {
        const id = estado.detalhe?.id;
        const motivo = prompt(
            "Informe os ajustes exigidos pela SEMFAZ:"
        );

        if (!id || !motivo?.trim()) {
            return;
        }

        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${id}/devolver`,
                {
                    method: "POST",
                    body: JSON.stringify({ motivo }),
                }
            );

            await carregarLogradouros();
            await abrirDetalhe(id, true);
            toast(dados.mensagem);
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    async function cancelarProcesso() {
        const id = estado.detalhe?.id;
        const motivo = prompt(
            "Informe o motivo do cancelamento:"
        );

        if (!id || !motivo?.trim()) {
            return;
        }

        iniciarCarregamento();

        try {
            const dados = await api(
                `/api/cadastro-territorial/logradouros/${id}/cancelar`,
                {
                    method: "POST",
                    body: JSON.stringify({ motivo }),
                }
            );

            fecharDetalhe();
            await carregarLogradouros();
            toast(dados.mensagem);
        } catch (erro) {
            toast(
                erro.message,
                "erro"
            );
        } finally {
            terminarCarregamento();
        }
    }

    function iniciarMapa() {
        if (typeof L === "undefined") {
            throw new Error(
                "A biblioteca Leaflet não foi carregada."
            );
        }

        estado.mapa = L.map(
            "ct-map",
            {
                preferCanvas: true,
                zoomControl: true,
            }
        ).setView(
            [-10.9160, -37.6680],
            13
        );

        const claro = L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
            {
                maxZoom: 20,
                attribution:
                    "&copy; OpenStreetMap &copy; CARTO",
            }
        ).addTo(estado.mapa);

        const osm = L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                maxZoom: 19,
                attribution:
                    "&copy; OpenStreetMap contributors",
            }
        );

        L.control.layers(
            {
                "Mapa claro": claro,
                "OpenStreetMap": osm,
            },
            {},
            { position: "topright" }
        ).addTo(estado.mapa);

        L.control.scale({
            imperial: false,
            position: "bottomleft",
        }).addTo(estado.mapa);

        estado.drawnItems =
            new L.FeatureGroup();
        estado.drawnItems.addTo(
            estado.mapa
        );

        estado.mapa.on(
            "draw:created",
            evento => {
                estado.drawnItems.clearLayers();
                estado.drawnItems.addLayer(
                    evento.layer
                );
                estado.geometriaRascunho =
                    evento.layer.toGeoJSON().geometry;
                atualizarResumoGeometria();
                abrirFormularioNovo();
            }
        );

        estado.mapa.on(
            "draw:edited",
            atualizarResumoGeometria
        );

        estado.mapa.on(
            "mousemove",
            evento => {
                el.coordenadas.textContent =
                    `Lat ${evento.latlng.lat.toFixed(6)} · Lon ${evento.latlng.lng.toFixed(6)}`;
            }
        );

        estado.mapa.on(
            "moveend",
            () => {
                clearTimeout(
                    estado.recarregarTimer
                );

                if (
                    estado.popupAbertoId !== null
                    || estado.carregandoDetalhe
                ) {
                    estado.recarregarPendente = true;
                    return;
                }

                estado.recarregarTimer =
                    setTimeout(
                        () => carregarLogradouros({
                            silencioso: true,
                        }),
                        350
                    );
            }
        );

        estado.mapa.on(
            "popupopen",
            evento => {
                const botao =
                    evento.popup
                        .getElement()
                        ?.querySelector(
                            "[data-abrir-id]"
                        );

                botao?.addEventListener(
                    "click",
                    () => {
                        abrirDetalhe(
                            Number(
                                botao.dataset.abrirId
                            ),
                            false
                        );
                    }
                );
            }
        );
    }

    function obterElementos() {
        el.status =
            document.getElementById("ct-status");
        el.lista =
            document.getElementById("ct-lista");
        el.busca =
            document.getElementById("ct-busca");
        el.carregando =
            document.getElementById("ct-carregando");
        el.toast =
            document.getElementById("ct-toast");
        el.coordenadas =
            document.getElementById("ct-coordenadas");
        el.vazio =
            document.getElementById("ct-vazio");
        el.detalheCarregando =
            document.getElementById("ct-detalhe-carregando");
        el.detalheErro =
            document.getElementById("ct-detalhe-erro");
        el.detalheErroMensagem =
            document.getElementById("ct-detalhe-erro-mensagem");
        el.detalhe =
            document.getElementById("ct-detalhe");
        el.detalheProtocolo =
            document.getElementById("ct-detalhe-protocolo");
        el.detalheNome =
            document.getElementById("ct-detalhe-nome");
        el.detalheStatus =
            document.getElementById("ct-detalhe-status");
        el.resumo =
            document.getElementById("ct-resumo");
        el.memorial =
            document.getElementById("ct-memorial");
        el.alertaDevolucao =
            document.getElementById("ct-alerta-devolucao");
        el.documentos =
            document.getElementById("ct-documentos");
        el.oficios =
            document.getElementById("ct-oficios");
        el.acoesProcesso =
            document.getElementById("ct-acoes-processo");
        el.formDocumento =
            document.getElementById("ct-form-documento");
        el.dialogFormulario =
            document.getElementById("ct-dialog-formulario");
        el.formLogradouro =
            document.getElementById("ct-form-logradouro");
        el.formTitulo =
            document.getElementById("ct-form-titulo");
        el.geometriaResumo =
            document.getElementById("ct-geometria-resumo");
        el.dialogImportar =
            document.getElementById("ct-dialog-importar");
        el.formImportar =
            document.getElementById("ct-form-importar");
        el.dialogAutorizar =
            document.getElementById("ct-dialog-autorizar");
        el.formAutorizar =
            document.getElementById("ct-form-autorizar");
        el.fundoMobile =
            document.getElementById("ct-fundo-mobile");
    }

    function registrarEventos() {
        el.busca.addEventListener(
            "input",
            renderizarLista
        );

        document
            .querySelectorAll(
                "[data-filtro-status]"
            )
            .forEach(botao => {
                botao.addEventListener(
                    "click",
                    () => {
                        document
                            .querySelectorAll(
                                "[data-filtro-status]"
                            )
                            .forEach(item =>
                                item.classList.remove("ativo")
                            );
                        botao.classList.add("ativo");
                        estado.filtroStatus =
                            botao.dataset.filtroStatus;
                        renderizarLista();
                    }
                );
            });

        document
            .getElementById("ct-desenhar")
            ?.addEventListener(
                "click",
                iniciarDesenho
            );

        document
            .getElementById("ct-importar")
            ?.addEventListener(
                "click",
                () => el.dialogImportar.showModal()
            );

        document
            .getElementById("ct-cancelar-form")
            ?.addEventListener(
                "click",
                () => {
                    el.dialogFormulario.close();
                    limparDesenho();
                }
            );

        document
            .getElementById("ct-cancelar-import")
            ?.addEventListener(
                "click",
                () => el.dialogImportar.close()
            );

        document
            .getElementById("ct-cancelar-autorizar")
            ?.addEventListener(
                "click",
                () => el.dialogAutorizar.close()
            );

        el.dialogFormulario.addEventListener(
            "close",
            limparDesenho
        );

        el.formLogradouro.addEventListener(
            "submit",
            salvarFormulario
        );
        el.formImportar.addEventListener(
            "submit",
            importarArquivo
        );
        el.formDocumento?.addEventListener(
            "submit",
            anexarDocumento
        );
        el.formAutorizar.addEventListener(
            "submit",
            autorizar
        );

        el.documentos.addEventListener(
            "click",
            evento => {
                const botao =
                    evento.target.closest(
                        "[data-remover-documento]"
                    );

                if (botao) {
                    removerDocumento(
                        Number(
                            botao.dataset.removerDocumento
                        )
                    );
                }
            }
        );

        el.acoesProcesso.addEventListener(
            "click",
            evento => {
                const id =
                    evento.target.closest("button")?.id;

                if (id === "ct-editar") {
                    abrirFormularioEdicao();
                } else if (id === "ct-ir-documentos") {
                    const bloco =
                        document.getElementById(
                            "ct-bloco-documentos"
                        );

                    if (bloco) {
                        bloco.open = true;
                        bloco.scrollIntoView({
                            behavior: "smooth",
                            block: "start",
                        });
                    }
                } else if (id === "ct-autorizar") {
                    el.dialogAutorizar.showModal();
                } else if (id === "ct-liberar") {
                    liberar();
                } else if (id === "ct-devolver") {
                    devolver();
                } else if (id === "ct-cancelar-processo") {
                    cancelarProcesso();
                }
            }
        );

        document
            .getElementById("ct-fechar-detalhe")
            .addEventListener(
                "click",
                fecharDetalhe
            );

        document
            .getElementById("ct-abrir-lista")
            .addEventListener(
                "click",
                abrirPainelLista
            );

        document
            .getElementById("ct-fechar-lista")
            .addEventListener(
                "click",
                fecharPaineisMobile
            );

        el.fundoMobile.addEventListener(
            "click",
            fecharPaineisMobile
        );

        document.addEventListener(
            "keydown",
            evento => {
                if (evento.key === "Escape") {
                    fecharPaineisMobile();
                }
            }
        );

        window.addEventListener(
            "resize",
            () => {
                estado.mapa?.invalidateSize();

                if (window.innerWidth > 980) {
                    fecharPaineisMobile();
                }
            }
        );
    }

    async function iniciar() {
        obterElementos();
        registrarEventos();

        try {
            iniciarMapa();
            await carregarLogradouros();
        } catch (erro) {
            console.error(erro);
            status(
                erro.message,
                "erro"
            );
        }
    }

    document.addEventListener(
        "DOMContentLoaded",
        iniciar
    );
})();
