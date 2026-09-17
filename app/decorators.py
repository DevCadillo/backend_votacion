from functools import wraps

from flask import abort, redirect, url_for
from flask_login import current_user


def admin_required(view_func):
    """
    Restringe una ruta únicamente a usuarios administradores.
    La validación se realiza en el backend.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)

        if not current_user.is_admin:
            abort(403)

        return view_func(*args, **kwargs)

    return wrapped


def voter_session_required(view_func):
    """
    Protege las rutas utilizadas durante el proceso de votación.

    La sesión del votante es independiente de Flask-Login,
    utilizado por los administradores.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):

        # Importación local para evitar importaciones circulares.
        from app.voter.routes import get_voter_from_cookie

        voter = get_voter_from_cookie()

        if not voter or voter.estado != "activo":
            return redirect(url_for("voter.identificarse"))

        kwargs["voter"] = voter

        return view_func(*args, **kwargs)

    return wrapped


def permission_required(permission):
    """
    Exige un permiso administrativo específico.

    Los superadministradores siempre tienen acceso.
    Los administradores normales necesitan el permiso correspondiente.

    Ejemplos:
        @permission_required("elecciones")
        @permission_required("categorias")
        @permission_required("candidatos")
        @permission_required("votantes")
        @permission_required("resultados")
        @permission_required("usuarios")
    """

    def decorator(view_func):

        @wraps(view_func)
        def wrapped(*args, **kwargs):

            # Debe estar autenticado.
            if not current_user.is_authenticated:
                abort(403)

            # Debe ser administrador.
            if not current_user.is_admin:
                abort(403)

            profile = current_user.admin_profile

            # Todo administrador debe tener perfil.
            if profile is None:
                abort(403)

            # El superadministrador tiene acceso completo.
            if profile.nivel == "superadmin":
                return view_func(*args, **kwargs)

            # Buscar dinámicamente el permiso.
            permiso = f"puede_{permission}"

            if not getattr(profile, permiso, False):
                abort(403)

            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def superadmin_required(view_func):
    """
    Permite acceso exclusivamente al superadministrador.

    Se utiliza principalmente para:
    - Crear administradores
    - Modificar administradores
    - Asignar permisos
    - Activar/desactivar administradores
    """

    @wraps(view_func)
    def wrapped(*args, **kwargs):

        if not current_user.is_authenticated:
            abort(403)

        if not current_user.is_admin:
            abort(403)

        profile = current_user.admin_profile

        if profile is None:
            abort(403)

        if profile.nivel != "superadmin":
            abort(403)

        return view_func(*args, **kwargs)

    return wrapped