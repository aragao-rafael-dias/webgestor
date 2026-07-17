# ==========================================
# SERVIÇOS DE SETORES
# ==========================================

from datetime import date

from sqlalchemy import or_

from models import (
    Setor,
    Usuario,
    UsuarioSetor,
    db,
)


class ErroVinculoSetor(ValueError):
    """
    Erro de validação durante a atribuição
    de setores a um usuário.
    """


def normalizar_ids_setores(valores):
    """
    Converte uma lista de valores em uma
    lista de IDs inteiros, positivos e únicos.
    """

    if valores is None:
        return []

    if not isinstance(
        valores,
        (list, tuple, set),
    ):
        raise ErroVinculoSetor(
            "A lista de setores é inválida."
        )

    ids_normalizados = []

    for valor in valores:
        try:
            setor_id = int(valor)

        except (
            TypeError,
            ValueError,
        ) as erro:
            raise ErroVinculoSetor(
                "Um dos setores informados "
                "possui identificador inválido."
            ) from erro

        if setor_id <= 0:
            raise ErroVinculoSetor(
                "Os identificadores dos setores "
                "devem ser números positivos."
            )

        if setor_id not in ids_normalizados:
            ids_normalizados.append(
                setor_id
            )

    return ids_normalizados


def obter_setores_ativos_por_ids(
    setor_ids,
):
    """
    Retorna os setores ativos correspondentes
    aos IDs informados.
    """

    ids_normalizados = normalizar_ids_setores(
        setor_ids
    )

    if not ids_normalizados:
        return []

    setores = (
        db.session.execute(
            db.select(Setor)
            .where(
                Setor.id.in_(
                    ids_normalizados
                ),
                Setor.ativo.is_(True),
            )
            .order_by(
                Setor.ordem.asc(),
                Setor.nome.asc(),
            )
        )
        .scalars()
        .all()
    )

    ids_encontrados = {
        setor.id
        for setor in setores
    }

    ids_inexistentes = [
        setor_id
        for setor_id in ids_normalizados
        if setor_id not in ids_encontrados
    ]

    if ids_inexistentes:
        texto_ids = ", ".join(
            str(setor_id)
            for setor_id in ids_inexistentes
        )

        raise ErroVinculoSetor(
            "Os seguintes setores não existem "
            f"ou estão inativos: {texto_ids}."
        )

    return setores


def obter_vinculos_ativos_usuario(
    usuario_id,
):
    """
    Retorna os vínculos atuais de um usuário,
    já acompanhados dos dados dos setores.
    """

    hoje = date.today()

    return (
        db.session.execute(
            db.select(UsuarioSetor)
            .join(
                Setor,
                Setor.id
                == UsuarioSetor.setor_id,
            )
            .where(
                UsuarioSetor.usuario_id
                == usuario_id,

                UsuarioSetor.ativo.is_(
                    True
                ),

                UsuarioSetor.inicio_vinculo
                <= hoje,

                or_(
                    UsuarioSetor.fim_vinculo
                    .is_(None),

                    UsuarioSetor.fim_vinculo
                    >= hoje,
                ),

                Setor.ativo.is_(True),
            )
            .order_by(
                UsuarioSetor.principal.desc(),
                Setor.ordem.asc(),
                Setor.nome.asc(),
            )
        )
        .scalars()
        .all()
    )


def usuario_pertence_ao_setor(
    usuario_id,
    setor_id,
):
    """
    Verifica se o usuário possui vínculo ativo
    com o setor informado.
    """

    hoje = date.today()

    vinculo = (
        db.session.execute(
            db.select(UsuarioSetor.id)
            .where(
                UsuarioSetor.usuario_id
                == usuario_id,

                UsuarioSetor.setor_id
                == setor_id,

                UsuarioSetor.ativo.is_(
                    True
                ),

                UsuarioSetor.inicio_vinculo
                <= hoje,

                or_(
                    UsuarioSetor.fim_vinculo
                    .is_(None),

                    UsuarioSetor.fim_vinculo
                    >= hoje,
                ),
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )

    return vinculo is not None


def sincronizar_setores_usuario(
    usuario,
    setor_ids,
    setor_principal_id=None,
):
    """
    Substitui os vínculos atuais do usuário
    pelos setores informados.

    O commit deve ser realizado pelo chamador.
    """

    if usuario is None:
        raise ErroVinculoSetor(
            "Usuário não informado."
        )

    if usuario.id is None:
        raise ErroVinculoSetor(
            "O usuário precisa ser salvo antes "
            "da atribuição dos setores."
        )

    ids_normalizados = normalizar_ids_setores(
        setor_ids
    )

    if (
        usuario.perfil
        != Usuario.PERFIL_SETOR
    ):
        if ids_normalizados:
            raise ErroVinculoSetor(
                "Somente usuários com perfil "
                "SETOR podem receber setores."
            )

        setor_principal_id = None

    setores = obter_setores_ativos_por_ids(
        ids_normalizados
    )

    ids_selecionados = {
        setor.id
        for setor in setores
    }

    if setor_principal_id in (
        None,
        "",
    ):
        principal_id = (
            ids_normalizados[0]
            if ids_normalizados
            else None
        )

    else:
        try:
            principal_id = int(
                setor_principal_id
            )

        except (
            TypeError,
            ValueError,
        ) as erro:
            raise ErroVinculoSetor(
                "O setor principal é inválido."
            ) from erro

        if (
            principal_id
            not in ids_selecionados
        ):
            raise ErroVinculoSetor(
                "O setor principal deve estar "
                "entre os setores selecionados."
            )

    vinculos_existentes = (
        db.session.execute(
            db.select(UsuarioSetor)
            .where(
                UsuarioSetor.usuario_id
                == usuario.id
            )
        )
        .scalars()
        .all()
    )

    vinculos_por_setor = {
        vinculo.setor_id: vinculo
        for vinculo in vinculos_existentes
    }

    hoje = date.today()

    for vinculo in vinculos_existentes:
        if (
            vinculo.setor_id
            not in ids_selecionados
        ):
            vinculo.ativo = False
            vinculo.principal = False

            if vinculo.fim_vinculo is None:
                vinculo.fim_vinculo = hoje

    for setor in setores:
        vinculo = vinculos_por_setor.get(
            setor.id
        )

        if vinculo is None:
            vinculo = UsuarioSetor(
                usuario_id=usuario.id,
                setor_id=setor.id,
                ativo=True,
                principal=(
                    setor.id
                    == principal_id
                ),
                inicio_vinculo=hoje,
                fim_vinculo=None,
            )

            db.session.add(
                vinculo
            )

        else:
            estava_inativo = (
                not vinculo.ativo
                or vinculo.fim_vinculo
                is not None
            )

            vinculo.ativo = True
            vinculo.fim_vinculo = None
            vinculo.principal = (
                setor.id
                == principal_id
            )

            if estava_inativo:
                vinculo.inicio_vinculo = hoje

    return setores