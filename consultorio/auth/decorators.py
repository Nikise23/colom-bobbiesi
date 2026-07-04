from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def _es_ruta_api():
    return request.path.startswith("/api/")


def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            if _es_ruta_api():
                return jsonify({"error": "Sesión no iniciada. Volvé a iniciar sesión."}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def rol_requerido(rol_esperado):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("rol") != rol_esperado:
                if _es_ruta_api():
                    return jsonify({"error": "No tenés permiso para esta acción."}), 403
                return redirect(url_for("auth.inicio"))
            return f(*args, **kwargs)
        return decorated
    return wrapper


def rol_permitido(varios_roles):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("rol") not in varios_roles:
                if _es_ruta_api():
                    return jsonify({"error": "No tenés permiso para esta acción."}), 403
                return redirect(url_for("auth.inicio"))
            return f(*args, **kwargs)
        return decorated
    return wrapper
