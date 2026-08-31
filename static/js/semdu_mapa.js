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
        menuContexto: null,
        coordenadaContexto: null,
        toastContexto: null,
        painelFeicao: null,
        fundoFeicao: null,
        feicaoSelecionada: null,
        temporizadorPainelFeicao: null,
        preferenciasCamadas: new Map(),
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

    async function lerRespostaJson(
        resposta
    ) {
        const corpo = await resposta.text();
        const tipo = String(
            resposta.headers.get(
                "content-type"
            )
            || ""
        ).toLowerCase();

        if (!corpo.trim()) {
            if (resposta.ok) {
                return {};
            }

            throw new Error(
                `O servidor respondeu HTTP ${resposta.status} sem conteúdo.`
            );
        }

        try {
            return JSON.parse(
                corpo
            );
        } catch (erro) {
            const resumo = corpo
                .replace(
                    /<[^>]*>/g,
                    " "
                )
                .replace(
                    /\s+/g,
                    " "
                )
                .trim()
                .slice(
                    0,
                    240
                );

            console.error(
                "Resposta não JSON recebida:",
                {
                    status:
                        resposta.status,
                    contentType:
                        tipo,
                    corpo,
                }
            );

            throw new Error(
                (
                    "O servidor não devolveu JSON "
                    + `(HTTP ${resposta.status}). `
                    + (
                        resumo
                        || "Consulte o terminal do Flask."
                    )
                )
            );
        }
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

        const dados =
            await lerRespostaJson(
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
                    tabela:
                        camada.tabela,
                    coluna:
                        camada.coluna_geometria,
                    bbox:
                        bboxAtual(),
                    limite:
                        String(
                            LIMITE_FEICOES
                        ),
                }
            );

        return (
            "/api/semdu/camada?"
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

    function valorDetalhe(valor) {
        if (
            valor === null
            || valor === undefined
        ) {
            return "";
        }

        if (typeof valor === "boolean") {
            return valor ? "Sim" : "Não";
        }

        if (
            typeof valor === "number"
            && Number.isFinite(valor)
        ) {
            return new Intl.NumberFormat(
                "pt-BR",
                {
                    maximumFractionDigits: 10,
                    useGrouping: false,
                }
            ).format(valor);
        }

        if (typeof valor === "object") {
            try {
                return JSON.stringify(
                    valor,
                    null,
                    2
                );
            } catch {
                return String(valor);
            }
        }

        return String(valor);
    }

    function campoPossuiValor(valor) {
        return !(
            valor === null
            || valor === undefined
            || (
                typeof valor === "string"
                && valor.trim() === ""
            )
        );
    }

    function rotuloCampo(chave) {
        const limpo = String(
            chave ?? ""
        )
            .replace(
                /([a-z0-9])([A-Z])/g,
                "$1 $2"
            )
            .replace(
                /[_\-]+/g,
                " "
            )
            .replace(
                /\s+/g,
                " "
            )
            .trim();

        if (!limpo) {
            return "Campo";
        }

        return (
            limpo.charAt(0).toUpperCase()
            + limpo.slice(1)
        );
    }

    function obterTituloFeicao(
        feature,
        camada
    ) {
        const propriedades =
            feature?.properties
            ?? {};

        const prioridades = [
            "nome",
            "name",
            "denominacao",
            "descricao",
            "descrição",
            "logradouro",
            "endereco",
            "endereço",
            "inscricao",
            "inscrição",
            "codigo",
            "código",
            "id",
            "gid",
            "fid",
        ];

        const entradas =
            Object.entries(
                propriedades
            );

        for (
            const prioridade
            of prioridades
        ) {
            const encontrada =
                entradas.find(
                    ([chave, valor]) =>
                        String(chave)
                            .trim()
                            .toLocaleLowerCase(
                                "pt-BR"
                            )
                        === prioridade
                        && campoPossuiValor(
                            valor
                        )
                );

            if (encontrada) {
                return valorDetalhe(
                    encontrada[1]
                );
            }
        }

        const primeira =
            entradas.find(
                ([, valor]) =>
                    campoPossuiValor(
                        valor
                    )
            );

        if (primeira) {
            return valorDetalhe(
                primeira[1]
            );
        }

        return camada.titulo;
    }

    function obterCentroDaLayer(
        layer
    ) {
        try {
            if (
                typeof layer?.getLatLng
                === "function"
            ) {
                const ponto =
                    layer.getLatLng();

                return {
                    latitude: ponto.lat,
                    longitude: ponto.lng,
                };
            }

            if (
                typeof layer?.getBounds
                === "function"
            ) {
                const limites =
                    layer.getBounds();

                if (
                    limites
                    && limites.isValid()
                ) {
                    const centro =
                        limites.getCenter();

                    return {
                        latitude: centro.lat,
                        longitude: centro.lng,
                    };
                }
            }
        } catch (erro) {
            console.warn(
                "Não foi possível obter o centro da feição:",
                erro
            );
        }

        return null;
    }

    function obterEnquadramentoDaLayer(
        layer
    ) {
        try {
            if (
                typeof layer?.getBounds
                === "function"
            ) {
                const limites =
                    layer.getBounds();

                if (
                    limites
                    && limites.isValid()
                ) {
                    return {
                        tipo: "limites",
                        sul: limites.getSouth(),
                        oeste: limites.getWest(),
                        norte: limites.getNorth(),
                        leste: limites.getEast(),
                    };
                }
            }

            const centro =
                obterCentroDaLayer(
                    layer
                );

            if (centro) {
                return {
                    tipo: "ponto",
                    ...centro,
                };
            }
        } catch (erro) {
            console.warn(
                "Não foi possível obter o enquadramento da feição:",
                erro
            );
        }

        return null;
    }

    function restaurarEstiloFeicao(
        selecao = estado.feicaoSelecionada
    ) {
        if (
            !selecao?.layer
            || !selecao?.camada
        ) {
            return;
        }

        try {
            const grupo =
                estado.camadasAtivas
                    .get(
                        selecao.camada.id
                    )
                    ?.grupo;

            if (
                grupo
                && typeof grupo.resetStyle
                    === "function"
            ) {
                grupo.resetStyle(
                    selecao.layer
                );
            }
        } catch (erro) {
            console.warn(
                "Não foi possível restaurar o estilo da feição:",
                erro
            );
        }
    }

    function destacarFeicao(
        layer,
        feature
    ) {
        if (
            typeof layer?.setStyle
            !== "function"
        ) {
            return;
        }

        const tipo =
            String(
                feature?.geometry?.type
                ?? ""
            ).toLocaleLowerCase(
                "pt-BR"
            );

        const estilo = {
            color: "#d17b11",
            weight:
                tipo.includes("line")
                    ? 7
                    : 4,
            opacity: 1,
            fillColor: "#f0a13b",
            fillOpacity:
                tipo.includes("polygon")
                    ? 0.46
                    : 0.86,
        };

        if (tipo.includes("point")) {
            estilo.radius = 9;
        }

        layer.setStyle(
            estilo
        );

        if (
            typeof layer.bringToFront
            === "function"
        ) {
            layer.bringToFront();
        }
    }

    function criarElementoTexto(
        tag,
        classe,
        conteudo
    ) {
        const elemento =
            document.createElement(
                tag
            );

        if (classe) {
            elemento.className =
                classe;
        }

        elemento.textContent =
            conteudo;

        return elemento;
    }

    function criarPainelFeicao() {
        if (estado.painelFeicao) {
            return estado.painelFeicao;
        }

        const painel =
            document.createElement(
                "aside"
            );

        painel.id =
            "semdu-painel-feicao";
        painel.className =
            "semdu-painel-feicao";
        painel.hidden = true;
        painel.setAttribute(
            "aria-label",
            "Informações da feição selecionada"
        );
        painel.setAttribute(
            "aria-hidden",
            "true"
        );

        painel.innerHTML = `
            <header class="semdu-feicao-cabecalho">
                <div>
                    <span>INFORMAÇÕES DA CAMADA</span>
                    <h1 data-feicao-camada>Feição selecionada</h1>
                </div>

                <button
                    type="button"
                    data-feicao-fechar
                    aria-label="Fechar informações da feição"
                    title="Fechar"
                >×</button>
            </header>

            <div class="semdu-feicao-conteudo">
                <section class="semdu-feicao-resumo">
                    <span>FEIÇÃO SELECIONADA</span>
                    <strong data-feicao-titulo>—</strong>

                    <div class="semdu-feicao-meta">
                        <span data-feicao-tabela>—</span>
                        <span data-feicao-geometria>—</span>
                    </div>

                    <small data-feicao-coordenada></small>
                </section>

                <label class="semdu-feicao-busca">
                    <span>Localizar atributo</span>
                    <input
                        type="search"
                        data-feicao-busca
                        placeholder="Ex.: bairro, inscrição, área..."
                        autocomplete="off"
                    >
                </label>

                <div
                    class="semdu-feicao-contagem"
                    data-feicao-contagem
                ></div>

                <dl
                    class="semdu-feicao-campos"
                    data-feicao-campos
                ></dl>
            </div>

            <footer class="semdu-feicao-acoes">
                <button
                    type="button"
                    class="secundario"
                    data-feicao-copiar
                >
                    Copiar dados
                </button>

                <button
                    type="button"
                    class="primario"
                    data-feicao-enquadrar
                >
                    Enquadrar no mapa
                </button>
            </footer>
        `;

        const fundo =
            document.createElement(
                "div"
            );

        fundo.className =
            "semdu-feicao-fundo";
        fundo.hidden = true;
        fundo.setAttribute(
            "aria-hidden",
            "true"
        );

        painel.querySelector(
            "[data-feicao-fechar]"
        )?.addEventListener(
            "click",
            () => fecharPainelFeicao()
        );

        painel.querySelector(
            "[data-feicao-busca]"
        )?.addEventListener(
            "input",
            evento => {
                renderizarCamposFeicao(
                    evento.target.value
                );
            }
        );

        painel.querySelector(
            "[data-feicao-copiar]"
        )?.addEventListener(
            "click",
            copiarDadosFeicao
        );

        painel.querySelector(
            "[data-feicao-enquadrar]"
        )?.addEventListener(
            "click",
            enquadrarFeicaoSelecionada
        );

        fundo.addEventListener(
            "click",
            () => fecharPainelFeicao()
        );

        document.body.append(
            fundo,
            painel
        );

        estado.painelFeicao =
            painel;
        estado.fundoFeicao =
            fundo;

        return painel;
    }

    function renderizarCamposFeicao(
        filtro = ""
    ) {
        const painel =
            estado.painelFeicao;
        const selecao =
            estado.feicaoSelecionada;

        if (
            !painel
            || !selecao
        ) {
            return;
        }

        const termo =
            String(
                filtro ?? ""
            )
                .trim()
                .toLocaleLowerCase(
                    "pt-BR"
                );

        const propriedades =
            Object.entries(
                selecao.feature
                    ?.properties
                ?? {}
            )
                .filter(
                    ([, valor]) =>
                        campoPossuiValor(
                            valor
                        )
                );

        const filtradas =
            propriedades.filter(
                ([chave, valor]) => {
                    if (!termo) {
                        return true;
                    }

                    const base =
                        (
                            `${chave} `
                            + `${valorDetalhe(valor)}`
                        )
                            .toLocaleLowerCase(
                                "pt-BR"
                            );

                    return base.includes(
                        termo
                    );
                }
            );

        const lista =
            painel.querySelector(
                "[data-feicao-campos]"
            );

        const contagem =
            painel.querySelector(
                "[data-feicao-contagem]"
            );

        lista.replaceChildren();

        contagem.textContent =
            termo
                ? (
                    `${filtradas.length} de `
                    + `${propriedades.length} atributo(s)`
                )
                : (
                    `${propriedades.length} atributo(s) `
                    + "com valor"
                );

        if (!filtradas.length) {
            const vazio =
                document.createElement(
                    "div"
                );

            vazio.className =
                "semdu-feicao-vazio";
            vazio.textContent =
                termo
                    ? "Nenhum atributo corresponde à busca."
                    : "A feição não possui atributos públicos preenchidos.";

            lista.appendChild(
                vazio
            );

            return;
        }

        const fragmento =
            document.createDocumentFragment();

        for (
            const [chave, valor]
            of filtradas
        ) {
            const linha =
                document.createElement(
                    "div"
                );

            linha.className =
                "semdu-feicao-campo";

            const dt =
                criarElementoTexto(
                    "dt",
                    "",
                    rotuloCampo(chave)
                );

            dt.title =
                String(chave);

            const dd =
                criarElementoTexto(
                    "dd",
                    "",
                    valorDetalhe(valor)
                );

            linha.append(
                dt,
                dd
            );

            fragmento.appendChild(
                linha
            );
        }

        lista.appendChild(
            fragmento
        );
    }

    function abrirPainelFeicao(
        feature,
        camada,
        layer
    ) {
        const painel =
            criarPainelFeicao();

        restaurarEstiloFeicao();

        const centro =
            obterCentroDaLayer(
                layer
            );

        estado.feicaoSelecionada = {
            feature,
            camada,
            layer,
            centro,
            enquadramento:
                obterEnquadramentoDaLayer(
                    layer
                ),
        };

        destacarFeicao(
            layer,
            feature
        );

        painel.querySelector(
            "[data-feicao-camada]"
        ).textContent =
            camada.titulo;

        painel.querySelector(
            "[data-feicao-titulo]"
        ).textContent =
            obterTituloFeicao(
                feature,
                camada
            );

        painel.querySelector(
            "[data-feicao-tabela]"
        ).textContent =
            camada.tabela;

        painel.querySelector(
            "[data-feicao-geometria]"
        ).textContent =
            (
                feature?.geometry?.type
                || camada.tipo_geometria
                || "Geometria"
            );

        painel.querySelector(
            "[data-feicao-coordenada]"
        ).textContent =
            centro
                ? (
                    "Centro aproximado: "
                    + `${centro.latitude.toFixed(6)}, `
                    + `${centro.longitude.toFixed(6)}`
                )
                : "";

        const busca =
            painel.querySelector(
                "[data-feicao-busca]"
            );

        busca.value = "";

        renderizarCamposFeicao();

        window.clearTimeout(
            estado.temporizadorPainelFeicao
        );

        painel.hidden = false;
        painel.setAttribute(
            "aria-hidden",
            "false"
        );

        if (estado.fundoFeicao) {
            estado.fundoFeicao.hidden =
                false;
        }

        document.body.classList.add(
            "semdu-feicao-aberta"
        );

        document.body.classList.remove(
            "arborizacao-aberta"
        );

        const fundoArborizacao =
            document.getElementById(
                "fundo-arborizacao"
            );

        if (fundoArborizacao) {
            fundoArborizacao.hidden =
                true;
        }

        fecharPainel();
        fecharMenuContexto();

        window.requestAnimationFrame(
            () => {
                painel.classList.add(
                    "visivel"
                );
            }
        );
    }

    function fecharPainelFeicao({
        restaurar = true,
    } = {}) {
        const painel =
            estado.painelFeicao;

        if (!painel) {
            return;
        }

        if (restaurar) {
            restaurarEstiloFeicao();
        }

        document.body.classList.remove(
            "semdu-feicao-aberta"
        );

        painel.classList.remove(
            "visivel"
        );
        painel.setAttribute(
            "aria-hidden",
            "true"
        );

        if (estado.fundoFeicao) {
            estado.fundoFeicao.hidden =
                true;
        }

        window.clearTimeout(
            estado.temporizadorPainelFeicao
        );

        estado.temporizadorPainelFeicao =
            window.setTimeout(
                () => {
                    if (
                        !document.body
                            .classList
                            .contains(
                                "semdu-feicao-aberta"
                            )
                    ) {
                        painel.hidden =
                            true;
                    }
                },
                230
            );

        estado.feicaoSelecionada =
            null;
    }

    async function copiarDadosFeicao() {
        const selecao =
            estado.feicaoSelecionada;

        if (!selecao) {
            return;
        }

        const dados = {
            camada:
                selecao.camada.titulo,
            tabela:
                selecao.camada.tabela,
            coluna_geometria:
                selecao.camada
                    .coluna_geometria,
            tipo_geometria:
                selecao.feature
                    ?.geometry
                    ?.type
                || selecao.camada
                    .tipo_geometria,
            centro_aproximado:
                selecao.centro,
            atributos:
                selecao.feature
                    ?.properties
                ?? {},
        };

        await copiarTextoContexto(
            JSON.stringify(
                dados,
                null,
                2
            ),
            "Dados da feição copiados."
        );
    }

    function enquadrarFeicaoSelecionada() {
        const enquadramento =
            estado.feicaoSelecionada
                ?.enquadramento;

        if (!enquadramento) {
            mostrarToastContexto(
                "Não foi possível calcular o enquadramento.",
                "erro"
            );
            return;
        }

        if (
            enquadramento.tipo
            === "limites"
        ) {
            estado.mapa.fitBounds(
                [
                    [
                        enquadramento.sul,
                        enquadramento.oeste,
                    ],
                    [
                        enquadramento.norte,
                        enquadramento.leste,
                    ],
                ],
                {
                    padding: [42, 42],
                    maxZoom: 19,
                }
            );
        } else {
            estado.mapa.setView(
                [
                    enquadramento.latitude,
                    enquadramento.longitude,
                ],
                Math.max(
                    estado.mapa.getZoom(),
                    18
                ),
                {
                    animate: true,
                }
            );
        }

        mostrarToastContexto(
            "Feição enquadrada no mapa.",
            "sucesso"
        );
    }

    function preferenciaPadraoCamada(
        camada
    ) {
        const cor = corDaCamada(
            camada
        );

        return {
            estilo: {
                strokeColor: cor,
                fillColor: cor,
                weight: 3,
                opacity: 0.9,
                fillOpacity: 0.22,
                radius: 6,
                dashArray: "",
                pointShape: "circle",
            },
            rotulo: {
                enabled: false,
                field: "",
                color: "#1d2438",
                fontSize: 12,
                haloColor: "#ffffff",
                haloWidth: 3,
                minZoom: 15,
            },
        };
    }

    function numeroLimitado(
        valor,
        minimo,
        maximo,
        padrao
    ) {
        const numero = Number(
            valor
        );

        if (!Number.isFinite(numero)) {
            return padrao;
        }

        return Math.min(
            maximo,
            Math.max(
                minimo,
                numero
            )
        );
    }

    function normalizarCor(
        valor,
        padrao
    ) {
        const cor = String(
            valor ?? ""
        ).trim();

        return /^#[0-9a-f]{6}$/i.test(cor)
            ? cor
            : padrao;
    }

    function normalizarPreferenciaCamada(
        camada,
        preferencia = {}
    ) {
        const padrao =
            preferenciaPadraoCamada(
                camada
            );

        const estiloEntrada =
            preferencia?.estilo
            ?? {};

        const rotuloEntrada =
            preferencia?.rotulo
            ?? {};

        return {
            estilo: {
                strokeColor: normalizarCor(
                    estiloEntrada.strokeColor,
                    padrao.estilo.strokeColor
                ),
                fillColor: normalizarCor(
                    estiloEntrada.fillColor,
                    padrao.estilo.fillColor
                ),
                weight: numeroLimitado(
                    estiloEntrada.weight,
                    1,
                    12,
                    padrao.estilo.weight
                ),
                opacity: numeroLimitado(
                    estiloEntrada.opacity,
                    0,
                    1,
                    padrao.estilo.opacity
                ),
                fillOpacity: numeroLimitado(
                    estiloEntrada.fillOpacity,
                    0,
                    1,
                    padrao.estilo.fillOpacity
                ),
                radius: numeroLimitado(
                    estiloEntrada.radius,
                    2,
                    22,
                    padrao.estilo.radius
                ),
                dashArray: String(
                    estiloEntrada.dashArray
                    ?? ""
                )
                    .replace(
                        /[^0-9 ,.]/g,
                        ""
                    )
                    .slice(
                        0,
                        40
                    ),
                pointShape: [
                    "circle",
                    "square",
                ].includes(
                    estiloEntrada.pointShape
                )
                    ? estiloEntrada.pointShape
                    : padrao.estilo.pointShape,
            },
            rotulo: {
                enabled: Boolean(
                    rotuloEntrada.enabled
                ),
                field: String(
                    rotuloEntrada.field
                    ?? ""
                ).slice(
                    0,
                    120
                ),
                color: normalizarCor(
                    rotuloEntrada.color,
                    padrao.rotulo.color
                ),
                fontSize: numeroLimitado(
                    rotuloEntrada.fontSize,
                    8,
                    30,
                    padrao.rotulo.fontSize
                ),
                haloColor: normalizarCor(
                    rotuloEntrada.haloColor,
                    padrao.rotulo.haloColor
                ),
                haloWidth: numeroLimitado(
                    rotuloEntrada.haloWidth,
                    0,
                    8,
                    padrao.rotulo.haloWidth
                ),
                minZoom: numeroLimitado(
                    rotuloEntrada.minZoom,
                    0,
                    24,
                    padrao.rotulo.minZoom
                ),
            },
        };
    }

    function obterPreferenciaCamada(
        camadaOuId
    ) {
        const camada =
            typeof camadaOuId === "string"
                ? estado.catalogo.find(
                    item =>
                        item.id === camadaOuId
                )
                : camadaOuId;

        if (!camada) {
            return null;
        }

        return normalizarPreferenciaCamada(
            camada,
            estado.preferenciasCamadas.get(
                camada.id
            )
        );
    }

    function estiloLeafletCamada(
        camada
    ) {
        const preferencia =
            obterPreferenciaCamada(
                camada
            );

        return {
            color:
                preferencia.estilo
                    .strokeColor,
            weight:
                preferencia.estilo
                    .weight,
            opacity:
                preferencia.estilo
                    .opacity,
            fillColor:
                preferencia.estilo
                    .fillColor,
            fillOpacity:
                preferencia.estilo
                    .fillOpacity,
            dashArray:
                preferencia.estilo
                    .dashArray
                || null,
        };
    }

    function aplicarEstiloRotulo(
        tooltip,
        rotulo
    ) {
        const elemento =
            tooltip?.getElement?.();

        if (!elemento) {
            return;
        }

        elemento.style.setProperty(
            "--semdu-rotulo-cor",
            rotulo.color
        );
        elemento.style.setProperty(
            "--semdu-rotulo-tamanho",
            `${rotulo.fontSize}px`
        );
        elemento.style.setProperty(
            "--semdu-rotulo-halo",
            rotulo.haloColor
        );
        elemento.style.setProperty(
            "--semdu-rotulo-halo-largura",
            `${rotulo.haloWidth}px`
        );
        elemento.style.setProperty(
            "--semdu-rotulo-halo-negativo",
            `${-rotulo.haloWidth}px`
        );
    }

    function configurarRotuloLayer(
        layer,
        feature,
        camada
    ) {
        if (
            typeof layer?.unbindTooltip
            === "function"
        ) {
            layer.unbindTooltip();
        }

        const preferencia =
            obterPreferenciaCamada(
                camada
            );

        const rotulo =
            preferencia?.rotulo;

        if (
            !rotulo?.enabled
            || !rotulo.field
        ) {
            return;
        }

        const valor =
            feature?.properties
                ?.[rotulo.field];

        if (!campoPossuiValor(valor)) {
            return;
        }

        layer.bindTooltip(
            escaparHtml(
                valorDetalhe(valor)
            ),
            {
                permanent: true,
                direction: "center",
                opacity: 1,
                className:
                    "semdu-rotulo-camada",
                interactive: false,
            }
        );

        layer.on(
            "tooltipopen",
            evento => {
                aplicarEstiloRotulo(
                    evento.tooltip,
                    rotulo
                );
            }
        );

        if (
            estado.mapa?.hasLayer?.(layer)
        ) {
            if (
                estado.mapa.getZoom()
                >= rotulo.minZoom
            ) {
                layer.openTooltip();
            } else {
                layer.closeTooltip();
            }
        }
    }

    function atualizarVisibilidadeRotulos() {
        if (!estado.mapa) {
            return;
        }

        const zoom =
            estado.mapa.getZoom();

        estado.camadasAtivas.forEach(
            registro => {
                const rotulo =
                    obterPreferenciaCamada(
                        registro.camada
                    )?.rotulo;

                registro.grupo?.eachLayer(
                    layer => {
                        const tooltip =
                            layer.getTooltip?.();

                        if (!tooltip) {
                            return;
                        }

                        if (
                            rotulo?.enabled
                            && zoom >= rotulo.minZoom
                        ) {
                            layer.openTooltip();
                            aplicarEstiloRotulo(
                                tooltip,
                                rotulo
                            );
                        } else {
                            layer.closeTooltip();
                        }
                    }
                );
            }
        );
    }

    function aplicarPreferenciaCamada(
        idCamada
    ) {
        const registro =
            estado.camadasAtivas.get(
                idCamada
            );

        if (!registro?.grupo) {
            return;
        }

        const preferencia =
            obterPreferenciaCamada(
                registro.camada
            );

        registro.grupo.eachLayer(
            layer => {
                const feature =
                    layer.feature
                    ?? {};

                if (
                    typeof layer.setStyle
                    === "function"
                ) {
                    layer.setStyle(
                        estiloLeafletCamada(
                            registro.camada
                        )
                    );
                }

                if (
                    typeof layer.setRadius
                    === "function"
                ) {
                    layer.setRadius(
                        preferencia.estilo
                            .radius
                    );
                }

                configurarRotuloLayer(
                    layer,
                    feature,
                    registro.camada
                );
            }
        );

        atualizarVisibilidadeRotulos();
    }

    function definirPreferenciaCamada(
        idCamada,
        preferencia
    ) {
        const camada =
            estado.catalogo.find(
                item =>
                    item.id === idCamada
            )
            ?? estado.camadasAtivas
                .get(idCamada)
                ?.camada;

        if (!camada) {
            return null;
        }

        const normalizada =
            normalizarPreferenciaCamada(
                camada,
                preferencia
            );

        estado.preferenciasCamadas.set(
            idCamada,
            normalizada
        );

        aplicarPreferenciaCamada(
            idCamada
        );

        return normalizada;
    }

    function definirPreferenciasCamadas(
        preferencias
    ) {
        if (!preferencias) {
            return;
        }

        const entradas =
            preferencias instanceof Map
                ? preferencias.entries()
                : Object.entries(
                    preferencias
                );

        for (
            const [idCamada, preferencia]
            of entradas
        ) {
            definirPreferenciaCamada(
                idCamada,
                preferencia
            );
        }
    }

    function limparPreferenciaCamada(
        idCamada
    ) {
        estado.preferenciasCamadas.delete(
            idCamada
        );

        aplicarPreferenciaCamada(
            idCamada
        );
    }

    function camposDoGeoJson(
        dados
    ) {
        const campos =
            new Set();

        for (
            const feature
            of dados?.features?.slice(
                0,
                250
            )
            ?? []
        ) {
            Object.keys(
                feature?.properties
                ?? {}
            ).forEach(
                campo =>
                    campos.add(campo)
            );
        }

        return Array.from(
            campos
        ).sort(
            (a, b) =>
                a.localeCompare(
                    b,
                    "pt-BR"
                )
        );
    }

    function opcoesGeoJson(
        camada
    ) {
        return {
            style() {
                return estiloLeafletCamada(
                    camada
                );
            },

            pointToLayer(
                feature,
                latlng
            ) {
                const preferencia =
                    obterPreferenciaCamada(
                        camada
                    );

                const opcoes = {
                    radius:
                        preferencia.estilo
                            .radius,
                    color:
                        preferencia.estilo
                            .strokeColor,
                    weight:
                        preferencia.estilo
                            .weight,
                    opacity:
                        preferencia.estilo
                            .opacity,
                    fillColor:
                        preferencia.estilo
                            .fillColor,
                    fillOpacity:
                        preferencia.estilo
                            .fillOpacity,
                };

                if (
                    preferencia.estilo
                        .pointShape
                    === "square"
                ) {
                    const raio =
                        preferencia.estilo
                            .radius;

                    return L.rectangle(
                        [
                            [
                                latlng.lat
                                    - raio * 0.000003,
                                latlng.lng
                                    - raio * 0.000003,
                            ],
                            [
                                latlng.lat
                                    + raio * 0.000003,
                                latlng.lng
                                    + raio * 0.000003,
                            ],
                        ],
                        opcoes
                    );
                }

                return L.circleMarker(
                    latlng,
                    opcoes
                );
            },

            onEachFeature(
                feature,
                layer
            ) {
                configurarRotuloLayer(
                    layer,
                    feature,
                    camada
                );

                layer.on(
                    "click",
                    evento => {
                        if (
                            evento?.originalEvent
                            && typeof L
                                ?.DomEvent
                                ?.stopPropagation
                                === "function"
                        ) {
                            L.DomEvent.stopPropagation(
                                evento.originalEvent
                            );
                        }

                        if (
                            window.SemduFerramentas
                                ?.interceptarCliqueFeicao
                                ?.({
                                    evento,
                                    feature,
                                    camada,
                                    layer,
                                })
                        ) {
                            return;
                        }

                        abrirPainelFeicao(
                            feature,
                            camada,
                            layer
                        );
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
                            const estilo =
                                obterPreferenciaCamada(
                                    camada
                                )?.estilo;

                            evento.target.setStyle(
                                {
                                    weight: Math.min(
                                        14,
                                        Number(
                                            estilo?.weight
                                            ?? 3
                                        ) + 2
                                    ),
                                    fillOpacity: Math.min(
                                        1,
                                        Number(
                                            estilo?.fillOpacity
                                            ?? 0.22
                                        ) + 0.14
                                    ),
                                }
                            );
                        }
                    }
                );

                layer.on(
                    "mouseout",
                    evento => {
                        if (
                            estado.feicaoSelecionada
                                ?.layer
                            === evento.target
                        ) {
                            destacarFeicao(
                                evento.target,
                                feature
                            );
                            return;
                        }

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

                            if (
                                typeof evento.target
                                    .setRadius
                                === "function"
                            ) {
                                evento.target.setRadius(
                                    obterPreferenciaCamada(
                                        camada
                                    )?.estilo
                                        ?.radius
                                    ?? 6
                                );
                            }
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
                await lerRespostaJson(
                    resposta
                );

            if (!resposta.ok) {
                throw new Error(
                    dados?.detalhes
                    ?? dados?.erro
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
            registro.campos =
                camposDoGeoJson(
                    dados
                );

            aplicarPreferenciaCamada(
                camada.id
            );

            document.dispatchEvent(
                new CustomEvent(
                    "semdu:camada-carregada",
                    {
                        detail: {
                            camada,
                            registro,
                        },
                    }
                )
            );

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
                campos: [],
            }
        );

        document.dispatchEvent(
            new CustomEvent(
                "semdu:camada-ativada",
                {
                    detail: {
                        camada,
                    },
                }
            )
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

        if (
            estado.feicaoSelecionada
                ?.camada
                ?.id
            === camada.id
        ) {
            fecharPainelFeicao({
                restaurar: false,
            });
        }

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

        document.dispatchEvent(
            new CustomEvent(
                "semdu:camada-desativada",
                {
                    detail: {
                        camada,
                    },
                }
            )
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

    const ICONES_CONTEXTO = {
        copiar: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="8" y="8" width="11" height="11" rx="2"/>
                <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>
            </svg>
        `,
        wkt: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M5 4h14v16H5z"/>
                <path d="M8 8h8M8 12h8M8 16h5"/>
            </svg>
        `,
        mapa: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m3 6 5-3 8 3 5-3v15l-5 3-8-3-5 3V6Z"/>
                <path d="M8 3v15M16 6v15"/>
            </svg>
        `,
        streetview: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="5" r="2.4"/>
                <path d="M8.5 21 10 14l-3-2 1.5-4h7L17 12l-3 2 1.5 7"/>
                <path d="M10 14h4"/>
            </svg>
        `,
        centralizar: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
            </svg>
        `,
        arvore: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 22v-6"/>
                <path d="M8 22h8"/>
                <path d="M12 3c-4 0-7 3-7 7 0 3.5 2.5 6 7 6s7-2.5 7-6c0-4-3-7-7-7Z"/>
                <path d="M12 7v9M8.5 10.5 12 13l3.5-2.5"/>
            </svg>
        `,
        bloqueio: `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="5" y="10" width="14" height="10" rx="2"/>
                <path d="M8 10V7a4 4 0 0 1 8 0v3"/>
            </svg>
        `,
    };

    function formatarCoordenada(
        valor,
        casas = 7
    ) {
        const numero = Number(valor);

        if (!Number.isFinite(numero)) {
            return "";
        }

        return numero.toFixed(casas);
    }

    function obterCoordenadaContexto() {
        const coordenada =
            estado.coordenadaContexto;

        if (
            !coordenada
            || !Number.isFinite(
                coordenada.latitude
            )
            || !Number.isFinite(
                coordenada.longitude
            )
        ) {
            return null;
        }

        return coordenada;
    }

    function criarBotaoContexto({
        acao,
        icone,
        titulo,
        descricao = "",
        desabilitado = false,
    }) {
        const botao =
            document.createElement("button");

        botao.type = "button";
        botao.className =
            "semdu-contexto-item";
        botao.dataset.acao = acao;
        botao.disabled = desabilitado;

        const caixaIcone =
            document.createElement("span");

        caixaIcone.className =
            "semdu-contexto-icone";
        caixaIcone.innerHTML =
            ICONES_CONTEXTO[icone]
            ?? ICONES_CONTEXTO.mapa;

        const caixaTexto =
            document.createElement("span");

        caixaTexto.className =
            "semdu-contexto-texto";

        const forte =
            document.createElement("strong");
        forte.textContent = titulo;

        const pequeno =
            document.createElement("small");
        pequeno.textContent = descricao;

        caixaTexto.append(
            forte,
            pequeno
        );

        botao.append(
            caixaIcone,
            caixaTexto
        );

        return botao;
    }

    function criarMenuContexto() {
        if (estado.menuContexto) {
            return estado.menuContexto;
        }

        const menu =
            document.createElement("div");

        menu.id =
            "semdu-menu-contexto";
        menu.className =
            "semdu-menu-contexto";
        menu.hidden = true;
        menu.setAttribute(
            "role",
            "menu"
        );
        menu.setAttribute(
            "aria-label",
            "Ações do ponto selecionado"
        );

        const cabecalho =
            document.createElement("div");

        cabecalho.className =
            "semdu-contexto-cabecalho";

        const etiqueta =
            document.createElement("span");
        etiqueta.textContent =
            "PONTO SELECIONADO";

        const coordenadas =
            document.createElement("strong");
        coordenadas.dataset.contextoCoordenadas =
            "true";

        cabecalho.append(
            etiqueta,
            coordenadas
        );

        const grupoPrincipal =
            document.createElement("div");
        grupoPrincipal.className =
            "semdu-contexto-grupo";

        grupoPrincipal.append(
            criarBotaoContexto({
                acao:
                    "copiar-coordenadas",
                icone:
                    "copiar",
                titulo:
                    "Copiar coordenadas",
                descricao:
                    "Latitude, longitude",
            }),
            criarBotaoContexto({
                acao:
                    "copiar-wkt",
                icone:
                    "wkt",
                titulo:
                    "Copiar como WKT",
                descricao:
                    "POINT (longitude latitude)",
            }),
            criarBotaoContexto({
                acao:
                    "abrir-google-maps",
                icone:
                    "mapa",
                titulo:
                    "Abrir no Google Maps",
                descricao:
                    "Abrir o ponto em nova guia",
            }),
            criarBotaoContexto({
                acao:
                    "abrir-street-view",
                icone:
                    "streetview",
                titulo:
                    "Abrir no Street View",
                descricao:
                    "Panorama mais próximo disponível",
            }),
            criarBotaoContexto({
                acao:
                    "centralizar",
                icone:
                    "centralizar",
                titulo:
                    "Centralizar e aproximar",
                descricao:
                    "Aplicar zoom no ponto",
            })
        );

        const separador =
            document.createElement("div");
        separador.className =
            "semdu-contexto-separador";
        separador.setAttribute(
            "role",
            "separator"
        );

        const podeEditarArborizacao =
            document.body.dataset
                .podeEditarArborizacao
            === "true";

        const botaoArvore =
            criarBotaoContexto({
                acao:
                    "planejar-arvore",
                icone:
                    podeEditarArborizacao
                        ? "arvore"
                        : "bloqueio",
                titulo:
                    podeEditarArborizacao
                        ? "Planejar árvore neste ponto"
                        : "Planejamento arbóreo restrito",
                descricao:
                    podeEditarArborizacao
                        ? "Usar o ponto no módulo ambiental"
                        : "Somente Eng. Ambiental pode editar",
                desabilitado:
                    !podeEditarArborizacao,
            });

        const grupoAmbiental =
            document.createElement("div");
        grupoAmbiental.className =
            "semdu-contexto-grupo";
        grupoAmbiental.appendChild(
            botaoArvore
        );

        menu.append(
            cabecalho,
            grupoPrincipal,
            separador,
            grupoAmbiental
        );

        menu.addEventListener(
            "click",
            evento => {
                const botao =
                    evento.target.closest(
                        "[data-acao]"
                    );

                if (
                    !botao
                    || botao.disabled
                ) {
                    return;
                }

                executarAcaoContexto(
                    botao.dataset.acao
                );
            }
        );

        document.body.appendChild(
            menu
        );

        estado.menuContexto = menu;

        return menu;
    }

    function criarToastContexto() {
        if (estado.toastContexto) {
            return estado.toastContexto;
        }

        const toast =
            document.createElement("div");

        toast.className =
            "semdu-contexto-toast";
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

        estado.toastContexto = toast;

        return toast;
    }

    function mostrarToastContexto(
        mensagem,
        tipo = "sucesso"
    ) {
        const toast =
            criarToastContexto();

        toast.className =
            (
                "semdu-contexto-toast "
                + tipo
            );

        toast.textContent =
            mensagem;
        toast.hidden = false;

        window.clearTimeout(
            mostrarToastContexto
                .temporizador
        );

        mostrarToastContexto
            .temporizador =
            window.setTimeout(
                () => {
                    toast.hidden = true;
                },
                2600
            );
    }

    function fecharMenuContexto() {
        if (!estado.menuContexto) {
            return;
        }

        estado.menuContexto.hidden =
            true;
        estado.menuContexto.classList
            .remove("visivel");
    }

    async function copiarTextoContexto(
        conteudo,
        mensagem
    ) {
        try {
            if (
                navigator.clipboard
                && window.isSecureContext
            ) {
                await navigator.clipboard
                    .writeText(conteudo);
            } else {
                const campo =
                    document.createElement(
                        "textarea"
                    );

                campo.value = conteudo;
                campo.setAttribute(
                    "readonly",
                    ""
                );
                campo.style.position =
                    "fixed";
                campo.style.opacity =
                    "0";

                document.body.appendChild(
                    campo
                );

                campo.select();

                const copiado =
                    document.execCommand(
                        "copy"
                    );

                campo.remove();

                if (!copiado) {
                    throw new Error(
                        "O navegador recusou a cópia."
                    );
                }
            }

            mostrarToastContexto(
                mensagem,
                "sucesso"
            );
        } catch (erro) {
            console.error(
                "Erro ao copiar:",
                erro
            );

            mostrarToastContexto(
                (
                    "Não foi possível copiar. "
                    + "Selecione o texto manualmente."
                ),
                "erro"
            );
        }
    }

    function abrirNovaGuiaContexto(
        url
    ) {
        const janela =
            window.open(
                url,
                "_blank",
                "noopener,noreferrer"
            );

        if (!janela) {
            mostrarToastContexto(
                (
                    "O navegador bloqueou a nova guia. "
                    + "Libere pop-ups para este endereço."
                ),
                "erro"
            );
        }
    }

    function executarAcaoContexto(
        acao
    ) {
        const coordenada =
            obterCoordenadaContexto();

        if (!coordenada) {
            fecharMenuContexto();
            return;
        }

        const latitude =
            formatarCoordenada(
                coordenada.latitude,
                7
            );

        const longitude =
            formatarCoordenada(
                coordenada.longitude,
                7
            );

        if (
            acao === "copiar-coordenadas"
        ) {
            copiarTextoContexto(
                `${latitude}, ${longitude}`,
                "Coordenadas copiadas."
            );
        } else if (
            acao === "copiar-wkt"
        ) {
            copiarTextoContexto(
                (
                    `POINT(${longitude} `
                    + `${latitude})`
                ),
                "WKT copiado."
            );
        } else if (
            acao === "abrir-google-maps"
        ) {
            const url =
                new URL(
                    "https://www.google.com/maps/search/"
                );

            url.searchParams.set(
                "api",
                "1"
            );
            url.searchParams.set(
                "query",
                `${latitude},${longitude}`
            );

            abrirNovaGuiaContexto(
                url.toString()
            );
        } else if (
            acao === "abrir-street-view"
        ) {
            const url =
                new URL(
                    "https://www.google.com/maps/@"
                );

            url.searchParams.set(
                "api",
                "1"
            );
            url.searchParams.set(
                "map_action",
                "pano"
            );
            url.searchParams.set(
                "viewpoint",
                `${latitude},${longitude}`
            );

            abrirNovaGuiaContexto(
                url.toString()
            );
        } else if (
            acao === "centralizar"
        ) {
            estado.mapa.setView(
                [
                    coordenada.latitude,
                    coordenada.longitude,
                ],
                Math.max(
                    estado.mapa.getZoom(),
                    18
                ),
                {
                    animate: true,
                }
            );

            mostrarToastContexto(
                "Mapa centralizado no ponto.",
                "sucesso"
            );
        } else if (
            acao === "planejar-arvore"
        ) {
            document.dispatchEvent(
                new CustomEvent(
                    "semdu:planejar-arvore-ponto",
                    {
                        detail: {
                            latitude:
                                coordenada.latitude,
                            longitude:
                                coordenada.longitude,
                        },
                    }
                )
            );
        }

        fecharMenuContexto();
    }

    function posicionarMenuContexto(
        eventoOriginal,
        menu
    ) {
        const margem = 10;
        const larguraJanela =
            window.innerWidth;
        const alturaJanela =
            window.innerHeight;

        menu.style.left =
            `${eventoOriginal.clientX}px`;
        menu.style.top =
            `${eventoOriginal.clientY}px`;
        menu.hidden = false;
        menu.classList.add(
            "visivel"
        );

        const caixa =
            menu.getBoundingClientRect();

        const esquerda = Math.max(
            margem,
            Math.min(
                eventoOriginal.clientX,
                larguraJanela
                    - caixa.width
                    - margem
            )
        );

        const topo = Math.max(
            margem,
            Math.min(
                eventoOriginal.clientY,
                alturaJanela
                    - caixa.height
                    - margem
            )
        );

        menu.style.left =
            `${esquerda}px`;
        menu.style.top =
            `${topo}px`;
    }

    function abrirMenuContexto(
        evento
    ) {
        evento.originalEvent
            ?.preventDefault();

        const latitude =
            Number(
                evento.latlng?.lat
            );

        const longitude =
            Number(
                evento.latlng?.lng
            );

        if (
            !Number.isFinite(latitude)
            || !Number.isFinite(longitude)
        ) {
            return;
        }

        estado.coordenadaContexto = {
            latitude,
            longitude,
        };

        const menu =
            criarMenuContexto();

        const coordenadas =
            menu.querySelector(
                "[data-contexto-coordenadas]"
            );

        if (coordenadas) {
            coordenadas.textContent =
                (
                    `${formatarCoordenada(latitude, 6)}, `
                    + `${formatarCoordenada(longitude, 6)}`
                );
        }

        posicionarMenuContexto(
            evento.originalEvent,
            menu
        );

        const primeiroBotao =
            menu.querySelector(
                "button:not(:disabled)"
            );

        window.setTimeout(
            () => {
                primeiroBotao?.focus(
                    {
                        preventScroll: true,
                    }
                );
            },
            0
        );
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

        document.getElementById(
            "map"
        )?.classList.add(
            "semdu-mapa-sem-fundo"
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
            "contextmenu",
            abrirMenuContexto
        );

        estado.mapa.on(
            "movestart",
            fecharMenuContexto
        );

        estado.mapa.on(
            "zoomstart",
            fecharMenuContexto
        );

        estado.mapa.on(
            "moveend",
            recarregarCamadasAtivas
        );

        estado.mapa.on(
            "zoomend",
            atualizarVisibilidadeRotulos
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

        document.getElementById(
            "abrir-arborizacao-mobile"
        )?.addEventListener(
            "click",
            () => fecharPainelFeicao()
        );

        document.addEventListener(
            "pointerdown",
            evento => {
                if (
                    estado.menuContexto
                    && !estado.menuContexto
                        .contains(evento.target)
                ) {
                    fecharMenuContexto();
                }
            }
        );

        document.addEventListener(
            "keydown",
            evento => {
                if (evento.key === "Escape") {
                    fecharPainel();
                    fecharMenuContexto();
                    fecharPainelFeicao();
                }
            }
        );

        window.addEventListener(
            "blur",
            fecharMenuContexto
        );

        window.addEventListener(
            "resize",
            () => {
                estado.mapa?.invalidateSize();
                fecharMenuContexto();

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

            window.SemduMapa = {
                obterMapa() {
                    return estado.mapa;
                },
                lerRespostaJson,
                mostrarAviso,
                iniciarCarregamento,
                terminarCarregamento,
                abrirPainelFeicao,
                fecharPainelFeicao,
                obterCatalogo() {
                    return estado.catalogo.map(
                        camada => ({
                            ...camada,
                        })
                    );
                },
                obterCamadasAtivas() {
                    return Array.from(
                        estado.camadasAtivas.values()
                    ).map(
                        registro => ({
                            camada: {
                                ...registro.camada,
                            },
                            grupo:
                                registro.grupo,
                            quantidade:
                                registro.quantidade,
                            campos: [
                                ...(registro.campos ?? []),
                            ],
                        })
                    );
                },
                obterPreferenciaCamada,
                definirPreferenciaCamada,
                definirPreferenciasCamadas,
                limparPreferenciaCamada,
                aplicarPreferenciaCamada,
                atualizarVisibilidadeRotulos,
            };

            document.dispatchEvent(
                new CustomEvent(
                    "semdu:mapa-pronto",
                    {
                        detail: {
                            mapa: estado.mapa,
                        },
                    }
                )
            );

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
