(() => {
    "use strict";

    function prepararCartoes() {
        document
            .querySelectorAll(
                "[data-modulo-card]"
            )
            .forEach(
                cartao => {
                    if (
                        cartao.dataset.disponivel
                        !== "true"
                    ) {
                        return;
                    }

                    const botao =
                        cartao.querySelector(
                            ".modulo-entrar"
                        );

                    if (!botao) {
                        return;
                    }

                    cartao.addEventListener(
                        "keydown",
                        evento => {
                            if (
                                evento.key === "Enter"
                                && evento.target === cartao
                            ) {
                                botao.click();
                            }
                        }
                    );
                }
            );
    }

    document.addEventListener(
        "DOMContentLoaded",
        prepararCartoes
    );
})();
