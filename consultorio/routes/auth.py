import os

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash

from consultorio.auth.decorators import login_requerido, rol_requerido
from consultorio.paths import USUARIOS_FILE
from consultorio.storage import cargar_json

bp = Blueprint("auth", __name__)


@bp.route('/descargar/<archivo>', endpoint="descargar_archivo")
@login_requerido
@rol_requerido("administrador")
def descargar_archivo(archivo):
    # En producción usa /data/, en desarrollo local usa la raíz
    if os.path.exists("/data"):
        ruta = f"/data/{archivo}"
    else:
        ruta = archivo
    
    if os.path.exists(ruta):
        return send_file(ruta, as_attachment=True)
    else:
        return f"Archivo '{archivo}' no encontrado", 404



@bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        contrasena = request.form.get("contrasena")
        usuarios = cargar_json(USUARIOS_FILE)


        for u in usuarios:
            if u["usuario"] == usuario and check_password_hash(u["contrasena"], contrasena):
                session["usuario"] = usuario
                session["rol"] = u.get("rol", "")
                # Redirigir según el rol
                if u.get("rol") == "secretaria":
                    return redirect(url_for("secretaria.vista_secretaria"))
                elif u.get("rol") == "administrador":
                    return redirect(url_for("administrador.vista_administrador"))
                else:
                    return redirect(url_for("auth.inicio"))
        return render_template("login.html", error="Usuario o contraseña incorrectos")


    return render_template("login.html")



@bp.route("/logout", endpoint="logout")
def logout():
    session.pop("usuario", None)
    session.pop("rol", None)
    return redirect(url_for("auth.login"))



@bp.route("/", endpoint="inicio")
@login_requerido
def inicio():
    return render_template("index.html")



@bp.route("/api/session-info", endpoint="session_info")
@login_requerido
def session_info():
    return jsonify({
        "usuario": session.get("usuario"),
        "rol": session.get("rol")
    })


# ========================== MÉDICO ============================
