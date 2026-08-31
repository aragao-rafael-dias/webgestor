(() => {
    "use strict";

    const COR_COPA_MIN = "#1c7a45";
    const COR_COPA_MAX = "#4baa6e";
    const COR_RAIZ_MIN = "#9a5a2e";
    const COR_RAIZ_MAX = "#c4875a";
    const COR_TRONCO = "#4a3123";

    const estado = {
        mapa: null,
        podeEditar: document.body.dataset.podeEditarArborizacao === "true",
        especies: [],
        especieSelecionada: null,
        planejamentos: [],
        grupos: new Map(),
        preview: null,
        coordenadaPreview: null,
        validacaoPreview: null,
        modo: null,
        planejamentoEditandoId: null,
        carregamentoAgendado: null,
        coordenadaContextoPendente: null,
    };

    const elementos = {};

    function escapar(valor) {
        return String(valor ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function numero(valor) {
        if (valor === null || valor === undefined || valor === "") {
            return null;
        }
        const n = Number(valor);
        return Number.isFinite(n) ? n : null;
    }

    function formatarMetro(valor) {
        const n = numero(valor);
        return n === null ? "Não definido" : `${n.toFixed(2)} m`;
    }

    function csrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content ?? "";
    }

    async function respostaJson(resposta) {
        if (window.SemduMapa?.lerRespostaJson) {
            return window.SemduMapa.lerRespostaJson(resposta);
        }

        const texto = await resposta.text();
        try {
            return JSON.parse(texto);
        } catch {
            throw new Error(`Resposta inválida do servidor (HTTP ${resposta.status}).`);
        }
    }

    async function api(url, opcoes = {}) {
        const headers = {
            Accept: "application/json",
            ...(opcoes.body ? { "Content-Type": "application/json" } : {}),
            ...(opcoes.method && opcoes.method !== "GET"
                ? { "X-CSRFToken": csrfToken() }
                : {}),
            ...(opcoes.headers ?? {}),
        };

        const resposta = await fetch(url, {
            credentials: "same-origin",
            ...opcoes,
            headers,
        });

        const dados = await respostaJson(resposta);

        if (!resposta.ok) {
            const erro = new Error(
                dados?.detalhes
                ?? dados?.erro
                ?? `Erro HTTP ${resposta.status}.`
            );
            erro.dados = dados;
            erro.status = resposta.status;
            throw erro;
        }

        return dados;
    }

    function status(mensagem, tipo = "") {
        elementos.status.className = `arborizacao-status ${tipo}`.trim();
        elementos.status.textContent = mensagem;
    }

    function usoNome(codigo) {
        const nomes = {
            PARQUE: "Parque",
            PRACA: "Praça",
            JARDIM: "Jardim",
            CANTEIRO_CENTRAL: "Canteiro central",
            AVENIDA: "Avenida",
            ESTACIONAMENTO: "Estacionamento",
            CALCADA: "Calçada",
            QUINTAL: "Quintal",
            AREA_VERDE: "Área verde",
            AREA_LAZER: "Área de lazer",
            SOB_REDE_ELETRICA: "Rede elétrica",
        };
        return nomes[codigo] ?? codigo;
    }

    function iconeFolha() {
        return `
            <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M20 4C12 4 6 7.5 4 14c4.5 1.5 9 .5 12-2.5C19 8.5 20 4 20 4Z"/>
                <path d="M4 20c2-5 6-8.5 12-11"/>
            </svg>
        `;
    }

    function fotoEspecie(especie) {
        if (especie.foto_principal_url) {
            return `<img src="${escapar(especie.foto_principal_url)}" alt="${escapar(especie.nome_popular)}">`;
        }
        return iconeFolha();
    }

    function porteCombina(especie, filtro) {
        if (!filtro) return true;
        return String(especie.porte ?? "").includes(filtro);
    }

    function especiesFiltradas() {
        const busca = elementos.buscar.value.trim().toLocaleLowerCase("pt-BR");
        const porte = elementos.porte.value;
        const uso = elementos.uso.value;

        return estado.especies.filter(especie => {
            const texto = [
                especie.nome_popular,
                especie.nome_cientifico,
                especie.familia,
                especie.biomas,
            ].join(" ").toLocaleLowerCase("pt-BR");

            return (!busca || texto.includes(busca))
                && porteCombina(especie, porte)
                && (!uso || (especie.usos ?? []).includes(uso));
        });
    }

    function renderizarEspecies() {
        const filtradas = especiesFiltradas();
        elementos.listaEspecies.innerHTML = "";

        if (!filtradas.length) {
            elementos.listaEspecies.innerHTML = '<div class="semdu-lista-vazia">Nenhuma espécie encontrada.</div>';
            return;
        }

        const fragmento = document.createDocumentFragment();

        filtradas.forEach(especie => {
            const card = document.createElement("article");
            card.className = "especie-card";
            if (estado.especieSelecionada?.id === especie.id) {
                card.classList.add("selecionada");
            }
            card.innerHTML = `
                <div class="especie-foto">${fotoEspecie(especie)}</div>
                <div class="especie-card-conteudo">
                    <h3>${escapar(especie.nome_popular)}</h3>
                    <em>${escapar(especie.nome_cientifico)}</em>
                    <div class="especie-card-meta">
                        <span>${escapar(especie.porte)}</span>
                        <span>${formatarMetro(especie.raio_copa_max_m)} de raio máximo</span>
                        ${especie.nativa_regional ? '<span class="nativa">Nativa</span>' : ''}
                        ${!especie.permitida_planejamento ? '<span class="bloqueada">Plantio restrito</span>' : ''}
                    </div>
                </div>
            `;
            card.addEventListener("click", () => selecionarEspecie(especie));
            fragmento.appendChild(card);
        });

        elementos.listaEspecies.appendChild(fragmento);
    }

    function detalheEspecie(especie) {
        const usos = (especie.usos ?? [])
            .map(item => `<span>${escapar(usoNome(item))}</span>`)
            .join("");

        const podePlanejar = estado.podeEditar && especie.permitida_planejamento;

        return `
            <h2>${escapar(especie.nome_popular)}</h2>
            <em>${escapar(especie.nome_cientifico)}</em>
            <dl>
                <div><dt>Família</dt><dd>${escapar(especie.familia || "—")}</dd></div>
                <div><dt>Porte</dt><dd>${escapar(especie.porte)}</dd></div>
                <div><dt>Altura</dt><dd>${formatarMetro(especie.altura_min_m)} a ${formatarMetro(especie.altura_max_m)}</dd></div>
                <div><dt>Copa mínima</dt><dd>${formatarMetro(especie.raio_copa_min_m)} de raio</dd></div>
                <div><dt>Copa máxima</dt><dd>${formatarMetro(especie.raio_copa_max_m)} de raio</dd></div>
                <div><dt>Raiz</dt><dd>${escapar(especie.tipo_raiz || "Não informada")}</dd></div>
                <div><dt>Espaçamento</dt><dd>${formatarMetro(especie.espacamento_recomendado_m)}</dd></div>
                <div><dt>Grupo ecológico</dt><dd>${escapar(especie.grupo_ecologico || "—")}</dd></div>
            </dl>
            <div class="especie-usos">${usos || '<span>Sem uso classificado</span>'}</div>
            <p>${escapar(especie.uso_recomendado_texto || "")}</p>
            ${especie.observacoes ? `<p><strong>Observação:</strong> ${escapar(especie.observacoes)}</p>` : ""}
            <p><strong>Fonte:</strong> ${escapar(especie.fonte_tecnica || "")}, página ${escapar(especie.pagina_fonte || "—")}.</p>
            <button
                type="button"
                id="planejar-especie"
                class="especie-planejar"
                ${podePlanejar ? "" : "disabled"}
            >
                ${
                    !estado.podeEditar
                        ? "Edição restrita à Eng. Ambiental"
                        : !especie.permitida_planejamento
                            ? "Espécie com plantio restrito"
                            : "Planejar plantio desta espécie"
                }
            </button>
        `;
    }

    function selecionarEspecie(especie) {
        estado.especieSelecionada = especie;
        elementos.detalhe.hidden = false;
        elementos.detalhe.innerHTML = detalheEspecie(especie);
        renderizarEspecies();
        document.getElementById("planejar-especie")?.addEventListener("click", () => abrirEditor(especie));
    }

    async function carregarEspecies() {
        status("Carregando catálogo técnico...");
        try {
            const dados = await api("/api/semdu/arborizacao/especies");
            estado.especies = dados.especies ?? [];
            renderizarEspecies();
            status(`${estado.especies.length} espécies disponíveis.`, "sucesso");
        } catch (erro) {
            console.error(erro);
            estado.especies = [];
            renderizarEspecies();
            status(erro.message, "erro");
        }
    }

    function abrirEditor(especie, planejamento = null) {
        if (!estado.podeEditar) return;

        estado.especieSelecionada = especie;
        estado.planejamentoEditandoId = planejamento?.properties?.id ?? null;
        estado.modo = planejamento ? "EDITAR" : "CRIAR";
        estado.coordenadaPreview = planejamento
            ? {
                latitude: planejamento.geometry.coordinates[1],
                longitude: planejamento.geometry.coordinates[0],
            }
            : estado.coordenadaContextoPendente
                ? {
                    latitude:
                        estado.coordenadaContextoPendente.latitude,
                    longitude:
                        estado.coordenadaContextoPendente.longitude,
                }
                : null;

        estado.coordenadaContextoPendente = null;
        estado.validacaoPreview = null;

        elementos.editor.hidden = false;
        elementos.editorTitulo.textContent = planejamento ? "Editar plantio" : "Novo plantio";
        elementos.editorResumo.innerHTML = `
            <div class="editor-especie">
                <strong>${escapar(especie.nome_popular)}</strong>
                <em>${escapar(especie.nome_cientifico)}</em>
            </div>
        `;
        elementos.raizMin.value = planejamento?.properties?.raio_raiz_min_m ?? especie.raio_raiz_min_m ?? "";
        elementos.raizMax.value = planejamento?.properties?.raio_raiz_max_m ?? especie.raio_raiz_max_m ?? "";
        elementos.statusPlanejamento.value = planejamento?.properties?.status ?? "RASCUNHO";
        elementos.justificativa.value = planejamento?.properties?.justificativa_tecnica ?? "";
        elementos.observacoes.value = planejamento?.properties?.observacoes ?? "";
        elementos.salvar.disabled = true;
        elementos.resultado.hidden = true;
        elementos.resultado.innerHTML = "";
        document.body.classList.add("modo-plantio");

        if (estado.coordenadaPreview) {
            atualizarCoordenadaTexto();
            desenharPreview();
            validarPreview();
        } else {
            elementos.coordenada.textContent = "Clique no mapa para definir o centro do tronco.";
            removerPreview();
        }
    }

    function fecharEditor() {
        elementos.editor.hidden = true;
        document.body.classList.remove("modo-plantio");
        estado.modo = null;
        estado.planejamentoEditandoId = null;
        estado.coordenadaPreview = null;
        estado.validacaoPreview = null;
        removerPreview();
    }

    function removerPreview() {
        if (estado.preview) {
            estado.mapa.removeLayer(estado.preview);
            estado.preview = null;
        }
    }

    function desenharPreview() {
        removerPreview();
        if (!estado.coordenadaPreview || !estado.especieSelecionada) return;

        const centro = [
            estado.coordenadaPreview.latitude,
            estado.coordenadaPreview.longitude,
        ];
        const especie = estado.especieSelecionada;
        const raizMin = numero(elementos.raizMin.value);
        const raizMax = numero(elementos.raizMax.value);
        const layers = [];

        const copaMax = numero(especie.raio_copa_max_m);
        const copaMin = numero(especie.raio_copa_min_m);
        const espacamento = numero(especie.espacamento_recomendado_m);

        if (espacamento !== null) {
            layers.push(L.circle(centro, {
                radius: espacamento,
                color: "#6d5ba7",
                weight: 1.5,
                dashArray: "7 6",
                fillOpacity: 0.02,
            }));
        }
        if (copaMax !== null) {
            layers.push(L.circle(centro, {
                radius: copaMax,
                color: COR_COPA_MAX,
                weight: 2,
                dashArray: "7 5",
                fillColor: COR_COPA_MAX,
                fillOpacity: 0.11,
            }));
        }
        if (copaMin !== null) {
            layers.push(L.circle(centro, {
                radius: copaMin,
                color: COR_COPA_MIN,
                weight: 2,
                fillColor: COR_COPA_MIN,
                fillOpacity: 0.19,
            }));
        }
        if (raizMax !== null) {
            layers.push(L.circle(centro, {
                radius: raizMax,
                color: COR_RAIZ_MAX,
                weight: 2,
                dashArray: "5 5",
                fillColor: COR_RAIZ_MAX,
                fillOpacity: 0.08,
            }));
        }
        if (raizMin !== null) {
            layers.push(L.circle(centro, {
                radius: raizMin,
                color: COR_RAIZ_MIN,
                weight: 2,
                fillColor: COR_RAIZ_MIN,
                fillOpacity: 0.12,
            }));
        }
        layers.push(L.circleMarker(centro, {
            radius: 6,
            color: "#fff",
            weight: 2,
            fillColor: COR_TRONCO,
            fillOpacity: 1,
        }));

        estado.preview = L.layerGroup(layers).addTo(estado.mapa);
    }

    function atualizarCoordenadaTexto() {
        const c = estado.coordenadaPreview;
        elementos.coordenada.textContent = c
            ? `Centro: ${c.latitude.toFixed(6)}, ${c.longitude.toFixed(6)}`
            : "Clique no mapa para definir o centro do tronco.";
    }

    function payloadEditor() {
        return {
            especie_id: estado.especieSelecionada.id,
            latitude: estado.coordenadaPreview.latitude,
            longitude: estado.coordenadaPreview.longitude,
            raio_raiz_min_m: numero(elementos.raizMin.value),
            raio_raiz_max_m: numero(elementos.raizMax.value),
            status: elementos.statusPlanejamento.value,
            justificativa_tecnica: elementos.justificativa.value.trim(),
            observacoes: elementos.observacoes.value.trim(),
            ignorar_id: estado.planejamentoEditandoId,
        };
    }

    function renderizarValidacao(resultado) {
        elementos.resultado.hidden = false;
        const itens = [];

        (resultado.bloqueios ?? []).forEach(item => {
            itens.push(`<div class="validacao-item bloqueio"><strong>Bloqueio:</strong> ${escapar(item.mensagem)}</div>`);
        });
        (resultado.avisos ?? []).forEach(item => {
            itens.push(`<div class="validacao-item aviso"><strong>Aviso:</strong> ${escapar(item.mensagem)}</div>`);
        });
        (resultado.verificacoes ?? [])
            .filter(item => item.resultado === "CONFORME")
            .forEach(item => {
                itens.push(`<div class="validacao-item conforme"><strong>Conforme:</strong> ${escapar(item.titulo)}</div>`);
            });

        if (!itens.length) {
            itens.push('<div class="validacao-item conforme">Nenhum conflito automático foi identificado.</div>');
        }

        elementos.resultado.innerHTML = itens.join("");
        elementos.salvar.disabled = !resultado.valido;
    }

    async function validarPreview() {
        if (!estado.coordenadaPreview || !estado.especieSelecionada) return;
        elementos.salvar.disabled = true;
        elementos.resultado.hidden = false;
        elementos.resultado.innerHTML = '<div class="validacao-item aviso">Executando verificações espaciais...</div>';

        try {
            const dados = await api("/api/semdu/arborizacao/validar-local", {
                method: "POST",
                body: JSON.stringify(payloadEditor()),
            });
            estado.validacaoPreview = dados.resultado;
            renderizarValidacao(dados.resultado);
        } catch (erro) {
            console.error(erro);
            estado.validacaoPreview = erro.dados?.validacao ?? null;
            if (estado.validacaoPreview) {
                renderizarValidacao(estado.validacaoPreview);
            } else {
                elementos.resultado.innerHTML = `<div class="validacao-item bloqueio">${escapar(erro.message)}</div>`;
            }
            elementos.salvar.disabled = true;
        }
    }

    async function salvarPlanejamento() {
        if (!estado.validacaoPreview?.valido) return;
        const url = estado.planejamentoEditandoId
            ? `/api/semdu/arborizacao/planejamentos/${estado.planejamentoEditandoId}`
            : "/api/semdu/arborizacao/planejamentos";
        const method = estado.planejamentoEditandoId ? "PUT" : "POST";

        elementos.salvar.disabled = true;
        elementos.salvar.textContent = "Salvando...";

        try {
            await api(url, {
                method,
                body: JSON.stringify(payloadEditor()),
            });
            fecharEditor();
            await carregarPlanejamentos();
            status("Planejamento salvo com sucesso.", "sucesso");
        } catch (erro) {
            console.error(erro);
            if (erro.dados?.validacao) {
                estado.validacaoPreview = erro.dados.validacao;
                renderizarValidacao(erro.dados.validacao);
            } else {
                alert(erro.message);
            }
        } finally {
            elementos.salvar.textContent = "Salvar planejamento";
            elementos.salvar.disabled = !estado.validacaoPreview?.valido;
        }
    }

    function limparGrupos() {
        estado.grupos.forEach(grupo => estado.mapa.removeLayer(grupo));
        estado.grupos.clear();
    }

    function popupPlanejamento(feature) {
        const p = feature.properties;
        return `
            <div class="arvore-popup">
                <h3>${escapar(p.nome_popular)}</h3>
                <em>${escapar(p.nome_cientifico)}</em>
                <dl>
                    <div><dt>Status</dt><dd>${escapar(p.status)}</dd></div>
                    <div><dt>Copa mínima</dt><dd>${formatarMetro(p.raio_copa_min_m)}</dd></div>
                    <div><dt>Copa máxima</dt><dd>${formatarMetro(p.raio_copa_max_m)}</dd></div>
                    <div><dt>Raiz mínima</dt><dd>${formatarMetro(p.raio_raiz_min_m)}</dd></div>
                    <div><dt>Raiz máxima</dt><dd>${formatarMetro(p.raio_raiz_max_m)}</dd></div>
                    <div><dt>Responsável</dt><dd>${escapar(p.atualizado_por_nome || p.criado_por_nome || "—")}</dd></div>
                </dl>
            </div>
        `;
    }

    function criarGrupoPlanejamento(feature) {
        const p = feature.properties;
        const centro = [feature.geometry.coordinates[1], feature.geometry.coordinates[0]];
        const layers = [];

        const adicionar = (visivel, raio, opcoes) => {
            const r = numero(raio);
            if (visivel && r !== null) layers.push(L.circle(centro, { radius: r, ...opcoes }));
        };

        adicionar(elementos.mostrarCopaMax.checked, p.raio_copa_max_m, {
            color: COR_COPA_MAX, weight: 2, dashArray: "7 5", fillColor: COR_COPA_MAX, fillOpacity: .1,
        });
        adicionar(elementos.mostrarCopaMin.checked, p.raio_copa_min_m, {
            color: COR_COPA_MIN, weight: 2, fillColor: COR_COPA_MIN, fillOpacity: .18,
        });
        adicionar(elementos.mostrarRaizMax.checked, p.raio_raiz_max_m, {
            color: COR_RAIZ_MAX, weight: 2, dashArray: "5 5", fillColor: COR_RAIZ_MAX, fillOpacity: .07,
        });
        adicionar(elementos.mostrarRaizMin.checked, p.raio_raiz_min_m, {
            color: COR_RAIZ_MIN, weight: 2, fillColor: COR_RAIZ_MIN, fillOpacity: .11,
        });

        if (elementos.mostrarCentros.checked) {
            const marcador = L.circleMarker(centro, {
                radius: 6,
                color: "#fff",
                weight: 2,
                fillColor: COR_TRONCO,
                fillOpacity: 1,
            });
            marcador.bindPopup(popupPlanejamento(feature));
            layers.push(marcador);
        }

        return L.layerGroup(layers).addTo(estado.mapa);
    }

    function renderizarPlanejamentosNoMapa() {
        limparGrupos();
        estado.planejamentos.forEach(feature => {
            estado.grupos.set(feature.properties.id, criarGrupoPlanejamento(feature));
        });
    }

    function especiePorId(id) {
        return estado.especies.find(item => Number(item.id) === Number(id));
    }

    function renderizarListaPlanejados() {
        elementos.quantidade.textContent = String(estado.planejamentos.length);
        elementos.listaPlanejados.innerHTML = "";

        if (!estado.planejamentos.length) {
            elementos.listaPlanejados.innerHTML = '<div class="semdu-lista-vazia">Nenhum plantio planejado na extensão atual.</div>';
            return;
        }

        estado.planejamentos.forEach(feature => {
            const p = feature.properties;
            const card = document.createElement("article");
            card.className = "planejado-card";
            card.innerHTML = `
                <h3>${escapar(p.nome_popular)}</h3>
                <em>${escapar(p.nome_cientifico)}</em>
                <p>Status: <strong>${escapar(p.status)}</strong><br>Espaçamento: ${formatarMetro(p.espacamento_recomendado_m)}</p>
                ${estado.podeEditar ? `
                    <div class="planejado-acoes">
                        <button type="button" data-editar="${p.id}">Editar/reposicionar</button>
                        <button type="button" class="perigo" data-cancelar="${p.id}">Cancelar</button>
                    </div>
                ` : ""}
            `;
            card.addEventListener("click", evento => {
                if (evento.target.closest("button")) return;
                estado.mapa.setView([
                    feature.geometry.coordinates[1],
                    feature.geometry.coordinates[0],
                ], Math.max(estado.mapa.getZoom(), 18));
            });
            card.querySelector("[data-editar]")?.addEventListener("click", () => {
                const especie = especiePorId(p.especie_id);
                if (especie) abrirEditor(especie, feature);
            });
            card.querySelector("[data-cancelar]")?.addEventListener("click", () => cancelarPlanejamento(p.id));
            elementos.listaPlanejados.appendChild(card);
        });
    }

    async function cancelarPlanejamento(id) {
        const motivo = window.prompt("Informe o motivo técnico do cancelamento:");
        if (!motivo?.trim()) return;

        try {
            await api(`/api/semdu/arborizacao/planejamentos/${id}`, {
                method: "DELETE",
                body: JSON.stringify({ motivo: motivo.trim() }),
            });
            await carregarPlanejamentos();
            status("Planejamento cancelado.", "sucesso");
        } catch (erro) {
            console.error(
                "Erro ao cancelar planejamento:",
                erro
            );

            status(
                erro.message
                || "Não foi possível cancelar o planejamento.",
                "erro"
            );
        }
    }

    function bboxMapa() {
        const b = estado.mapa.getBounds();
        return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
            .map(item => item.toFixed(7)).join(",");
    }

    async function carregarPlanejamentos() {
        if (!estado.mapa) return;
        try {
            const dados = await api(
                `/api/semdu/arborizacao/planejamentos?bbox=${encodeURIComponent(bboxMapa())}&limite=5000`
            );
            estado.planejamentos = dados.features ?? [];
            renderizarPlanejamentosNoMapa();
            renderizarListaPlanejados();
        } catch (erro) {
            console.error(erro);
            status(erro.message, "erro");
        }
    }

    function agendarRecarregamento() {
        window.clearTimeout(estado.carregamentoAgendado);
        estado.carregamentoAgendado = window.setTimeout(carregarPlanejamentos, 450);
    }

    function trocarAba(nome) {
        document.querySelectorAll("[data-arborizacao-aba]").forEach(botao => {
            botao.classList.toggle("ativa", botao.dataset.arborizacaoAba === nome);
        });
        elementos.abaEspecies.classList.toggle("ativa", nome === "especies");
        elementos.abaPlanejados.classList.toggle("ativa", nome === "planejados");
    }

    function receberPontoContexto(
        evento
    ) {
        const latitude =
            Number(
                evento.detail?.latitude
            );

        const longitude =
            Number(
                evento.detail?.longitude
            );

        if (
            !Number.isFinite(latitude)
            || !Number.isFinite(longitude)
        ) {
            return;
        }

        if (!estado.podeEditar) {
            status(
                (
                    "O planejamento arbóreo é restrito "
                    + "à função Eng. Ambiental."
                ),
                "erro"
            );
            return;
        }

        estado.coordenadaContextoPendente = {
            latitude,
            longitude,
        };

        trocarAba(
            "especies"
        );

        if (
            window.innerWidth <= 1100
        ) {
            abrirPainelMobile();
        }

        if (
            estado.especieSelecionada
            && estado.especieSelecionada
                .permitida_planejamento
        ) {
            abrirEditor(
                estado.especieSelecionada
            );

            status(
                (
                    "Ponto recebido do mapa. "
                    + "Revise os dados e salve "
                    + "o planejamento."
                ),
                "sucesso"
            );

            return;
        }

        elementos.detalhe.hidden = true;

        status(
            (
                "Ponto definido. Selecione uma espécie "
                + "e clique em “Planejar plantio desta espécie”."
            ),
            "sucesso"
        );

        elementos.buscar.focus();
    }

    function abrirPainelMobile() {
        document.body.classList.add("arborizacao-aberta");
        elementos.fundo.hidden = false;
    }

    function fecharPainelMobile() {
        document.body.classList.remove("arborizacao-aberta");
        elementos.fundo.hidden = true;
    }

    function obterElementos() {
        elementos.status = document.getElementById("arborizacao-status");
        elementos.buscar = document.getElementById("buscar-especie");
        elementos.porte = document.getElementById("filtrar-porte");
        elementos.uso = document.getElementById("filtrar-uso");
        elementos.listaEspecies = document.getElementById("lista-especies");
        elementos.detalhe = document.getElementById("especie-detalhe");
        elementos.abaEspecies = document.getElementById("aba-especies");
        elementos.abaPlanejados = document.getElementById("aba-planejados");
        elementos.listaPlanejados = document.getElementById("lista-planejados");
        elementos.quantidade = document.getElementById("quantidade-planejados");
        elementos.editor = document.getElementById("editor-plantio");
        elementos.editorTitulo = document.getElementById("editor-titulo");
        elementos.editorResumo = document.getElementById("editor-especie-resumo");
        elementos.raizMin = document.getElementById("raio-raiz-min");
        elementos.raizMax = document.getElementById("raio-raiz-max");
        elementos.statusPlanejamento = document.getElementById("status-planejamento");
        elementos.justificativa = document.getElementById("justificativa-planejamento");
        elementos.observacoes = document.getElementById("observacoes-planejamento");
        elementos.coordenada = document.getElementById("coordenada-preview");
        elementos.resultado = document.getElementById("resultado-validacao");
        elementos.salvar = document.getElementById("salvar-planejamento");
        elementos.mostrarCentros = document.getElementById("mostrar-centros");
        elementos.mostrarCopaMin = document.getElementById("mostrar-copa-min");
        elementos.mostrarCopaMax = document.getElementById("mostrar-copa-max");
        elementos.mostrarRaizMin = document.getElementById("mostrar-raiz-min");
        elementos.mostrarRaizMax = document.getElementById("mostrar-raiz-max");
        elementos.fundo = document.getElementById("fundo-arborizacao");
    }

    function registrarEventos() {
        [elementos.buscar, elementos.porte, elementos.uso].forEach(elemento => {
            elemento.addEventListener("input", renderizarEspecies);
            elemento.addEventListener("change", renderizarEspecies);
        });

        document.querySelectorAll("[data-arborizacao-aba]").forEach(botao => {
            botao.addEventListener("click", () => trocarAba(botao.dataset.arborizacaoAba));
        });

        document.getElementById("fechar-editor").addEventListener("click", fecharEditor);
        document.getElementById("cancelar-posicionamento").addEventListener("click", fecharEditor);
        elementos.salvar.addEventListener("click", salvarPlanejamento);
        document.getElementById("recarregar-planejamentos").addEventListener("click", carregarPlanejamentos);

        [elementos.mostrarCentros, elementos.mostrarCopaMin, elementos.mostrarCopaMax, elementos.mostrarRaizMin, elementos.mostrarRaizMax]
            .forEach(elemento => elemento.addEventListener("change", renderizarPlanejamentosNoMapa));

        [elementos.raizMin, elementos.raizMax].forEach(elemento => {
            elemento.addEventListener("input", () => {
                if (estado.coordenadaPreview) {
                    desenharPreview();
                    validarPreview();
                }
            });
        });

        document.getElementById("abrir-arborizacao-mobile").addEventListener("click", abrirPainelMobile);
        document.getElementById("fechar-arborizacao-mobile").addEventListener("click", fecharPainelMobile);
        elementos.fundo.addEventListener("click", fecharPainelMobile);

        document.addEventListener(
            "semdu:planejar-arvore-ponto",
            receberPontoContexto
        );
    }

    async function iniciarComMapa(mapa) {
        if (estado.mapa) return;
        estado.mapa = mapa;
        obterElementos();
        registrarEventos();

        estado.mapa.on("click", evento => {
            if (!estado.modo || elementos.editor.hidden) return;
            estado.coordenadaPreview = {
                latitude: evento.latlng.lat,
                longitude: evento.latlng.lng,
            };
            atualizarCoordenadaTexto();
            desenharPreview();
            validarPreview();
        });
        estado.mapa.on("moveend", agendarRecarregamento);

        await Promise.all([carregarEspecies(), carregarPlanejamentos()]);
    }

    document.addEventListener("semdu:mapa-pronto", evento => iniciarComMapa(evento.detail.mapa));

    document.addEventListener("DOMContentLoaded", () => {
        const mapa = window.SemduMapa?.obterMapa?.();
        if (mapa) iniciarComMapa(mapa);
    });
})();
