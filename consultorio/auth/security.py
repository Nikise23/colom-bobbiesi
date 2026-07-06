"""Configuración de sesión, cabeceras HTTP y utilidades de autenticación."""

from __future__ import annotations

import os
from datetime import timedelta

from flask import Flask, session


def is_production_deploy() -> bool:
    return bool(os.environ.get("RENDER")) or os.environ.get("FLASK_ENV") == "production"


def configure_app_security(app: Flask) -> None:
    secret = app.secret_key
    if is_production_deploy() and (not secret or secret == "clave_insegura_dev"):
        raise RuntimeError(
            "SECRET_KEY no configurada en producción. Definila en las variables de entorno."
        )

    secure_cookies = is_production_deploy() or os.environ.get("SESSION_COOKIE_SECURE") == "1"

    app.config.update(
        SESSION_COOKIE_SECURE=secure_cookies,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(
            hours=int(os.environ.get("SESSION_LIFETIME_HOURS", "12"))
        ),
    )

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if secure_cookies:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def iniciar_sesion(usuario: str, rol: str) -> None:
    """Nueva sesión tras login exitoso (mitiga session fixation)."""
    session.clear()
    session.permanent = True
    session["usuario"] = usuario
    session["rol"] = rol


def cerrar_sesion() -> None:
    session.clear()
