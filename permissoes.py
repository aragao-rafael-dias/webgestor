from functools import wraps

from flask import abort, current_app
from flask_login import current_user

from models import (
    Usuario,
    UsuarioEscola,
    db,
)


def admin_required(funcao):
    """
    Permite acesso somente a usuários
    autenticados com perfil ADMIN.
    """

    @wraps(funcao)
    def funcao_protegida(*args, **kwargs):

        if not current_user.is_authenticated:
            return (
                current_app
                .login_manager
                .unauthorized()
            )

        if not current_user.ativo:
            abort(403)

        if (
            current_user.perfil
            != Usuario.PERFIL_ADMIN
        ):
            abort(403)

        return funcao(*args, **kwargs)

    return funcao_protegida
def diretor_pode_acessar_escola(escola_id):
    """
    Retorna True somente quando o usuário atual
    é um diretor e possui vínculo ativo com a escola.
    """

    if not current_user.is_authenticated:
        return False

    if not current_user.ativo:
        return False

    if (
        current_user.perfil
        != Usuario.PERFIL_DIRETOR
    ):
        return False

    vinculo_id = (
        db.session
        .execute(
            db.select(
                UsuarioEscola.id
            )
            .where(
                UsuarioEscola.usuario_id
                == current_user.id,

                UsuarioEscola.escola_id
                == escola_id,

                UsuarioEscola.ativo.is_(True),

                UsuarioEscola.fim_vinculo.is_(
                    None
                ),

                UsuarioEscola.inicio_vinculo
                <= db.func.current_date(),
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )

    return vinculo_id is not None