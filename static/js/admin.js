// ==========================================
// FORMULÁRIO ADMINISTRATIVO DE USUÁRIOS
// ==========================================

function obterElementosFormulario() {
    return {
        formulario:
            document.getElementById(
                "form-novo-usuario"
            ),

        perfil:
            document.getElementById(
                "perfil"
            ),

        blocoEscolas:
            document.getElementById(
                "bloco-escolas"
            ),

        escolas:
            document.getElementById(
                "escolas_ids"
            ),

        blocoSetores:
            document.getElementById(
                "bloco-setores"
            ),

        setores:
            document.getElementById(
                "setores_ids"
            ),

        blocoSetorPrincipal:
            document.getElementById(
                "bloco-setor-principal"
            ),

        setorPrincipal:
            document.getElementById(
                "setor_principal_id"
            )
    };
}


// ==========================================
// EXIBIR OU ESCONDER BLOCO
// ==========================================

function configurarBloco(
    bloco,
    controles,
    visivel
) {
    if (bloco) {
        bloco.hidden = !visivel;

        bloco.setAttribute(
            "aria-hidden",
            visivel
                ? "false"
                : "true"
        );
    }

    controles
        .filter(Boolean)
        .forEach(
            controle => {
                controle.disabled =
                    !visivel;
            }
        );
}


// ==========================================
// SETOR PRINCIPAL
// ==========================================

function atualizarSetoresPrincipais(
    setores,
    setorPrincipal
) {
    if (
        !setores
        || !setorPrincipal
    ) {
        return;
    }

    const valorAtual = String(
        setorPrincipal.value
        || setorPrincipal.dataset.valorInicial
        || ""
    );

    const opcoesSelecionadas = [
        ...setores.options
    ].filter(
        option => option.selected
    );

    setorPrincipal.innerHTML = "";

    const opcaoInicial =
        document.createElement(
            "option"
        );

    opcaoInicial.value = "";

    opcaoInicial.textContent =
        opcoesSelecionadas.length > 0
            ? "Selecione o setor principal"
            : "Selecione primeiro os setores";

    setorPrincipal.appendChild(
        opcaoInicial
    );

    opcoesSelecionadas.forEach(
        option => {
            const novaOpcao =
                document.createElement(
                    "option"
                );

            novaOpcao.value =
                option.value;

            novaOpcao.textContent =
                option.textContent;

            if (
                String(option.value)
                === valorAtual
            ) {
                novaOpcao.selected = true;
            }

            setorPrincipal.appendChild(
                novaOpcao
            );
        }
    );

    const valorAindaExiste = (
        opcoesSelecionadas.some(
            option =>
                String(option.value)
                === valorAtual
        )
    );

    if (
        !valorAindaExiste
        && opcoesSelecionadas.length === 1
    ) {
        setorPrincipal.value =
            opcoesSelecionadas[0].value;
    }

    setorPrincipal.disabled =
        opcoesSelecionadas.length === 0;

    setorPrincipal.dataset.valorInicial =
        "";
}


// ==========================================
// PERFIL SELECIONADO
// ==========================================

function atualizarFormulario(
    elementos
) {
    const perfil = String(
        elementos.perfil?.value
        || ""
    )
        .trim()
        .toUpperCase();

    const diretor =
        perfil === "DIRETOR";

    const usuarioSetor =
        perfil === "SETOR";

    configurarBloco(
        elementos.blocoEscolas,
        [
            elementos.escolas
        ],
        diretor
    );

    configurarBloco(
        elementos.blocoSetores,
        [
            elementos.setores
        ],
        usuarioSetor
    );

    configurarBloco(
        elementos.blocoSetorPrincipal,
        [
            elementos.setorPrincipal
        ],
        usuarioSetor
    );

    if (usuarioSetor) {
        atualizarSetoresPrincipais(
            elementos.setores,
            elementos.setorPrincipal
        );
    }
}


// ==========================================
// INICIALIZAÇÃO
// ==========================================

function inicializarFormularioUsuario() {
    const elementos =
        obterElementosFormulario();

    if (
        !elementos.formulario
        || !elementos.perfil
    ) {
        return;
    }

    elementos.perfil.addEventListener(
        "change",
        () => {
            atualizarFormulario(
                elementos
            );
        }
    );

    elementos.setores?.addEventListener(
        "change",
        () => {
            atualizarSetoresPrincipais(
                elementos.setores,
                elementos.setorPrincipal
            );
        }
    );

    atualizarFormulario(
        elementos
    );
}


document.addEventListener(
    "DOMContentLoaded",
    inicializarFormularioUsuario
);