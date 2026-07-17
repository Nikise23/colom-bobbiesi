from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from consultorio.auth.decorators import login_requerido
from consultorio.auth.login_limiter import (
    clear_login_attempts,
    client_ip,
    is_login_blocked,
    record_failed_login,
)
from consultorio.auth.security import cerrar_sesion, iniciar_sesion
from consultorio.paths import USUARIOS_FILE
from consultorio.storage import cargar_json

bp = Blueprint("auth", __name__)


def _redirigir_por_rol(rol: str):
    if rol == "secretaria":
        return redirect(url_for("secretaria.vista_secretaria"))
    if rol == "administrador":
        return redirect(url_for("administrador.vista_administrador"))
    return redirect(url_for("auth.inicio"))


@bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    ip = client_ip(request)

    if request.method == "POST":
        bloqueado, segundos = is_login_blocked(ip)
        if bloqueado:
            minutos = max(1, segundos // 60)
            return render_template(
                "login.html",
                error=(
                    f"Demasiados intentos fallidos. "
                    f"Esperá {minutos} minuto(s) antes de volver a intentar."
                ),
            ), 429

        usuario = (request.form.get("usuario") or "").strip()
        contrasena = request.form.get("contrasena") or ""
        usuarios = cargar_json(USUARIOS_FILE)

        for u in usuarios:
            if u["usuario"] == usuario and check_password_hash(u["contrasena"], contrasena):
                clear_login_attempts(ip)
                iniciar_sesion(usuario, u.get("rol", ""))
                return _redirigir_por_rol(u.get("rol", ""))

        bloqueado_ahora, segundos = record_failed_login(ip)
        if bloqueado_ahora:
            minutos = max(1, segundos // 60)
            return render_template(
                "login.html",
                error=(
                    f"Demasiados intentos fallidos. "
                    f"Esperá {minutos} minuto(s) antes de volver a intentar."
                ),
            ), 429

        return render_template("login.html", error="Usuario o contraseña incorrectos")

    bloqueado, segundos = is_login_blocked(ip)
    if bloqueado:
        minutos = max(1, segundos // 60)
        return render_template(
            "login.html",
            error=(
                f"Demasiados intentos fallidos. "
                f"Esperá {minutos} minuto(s) antes de volver a intentar."
            ),
        )

    return render_template("login.html")


@bp.route("/logout", endpoint="logout")
def logout():
    cerrar_sesion()
    return redirect(url_for("auth.login"))


@bp.route("/", endpoint="inicio")
@login_requerido
def inicio():
    return render_template("index.html")


@bp.route("/api/session-info", endpoint="session_info")
@login_requerido
def session_info():
    return jsonify(
        {
            "usuario": session.get("usuario"),
            "rol": session.get("rol"),
        }
    )
