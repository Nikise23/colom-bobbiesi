import os
from functools import wraps

from flask import Blueprint, jsonify, make_response, request

from consultorio.config import public_api_configured, public_api_key, public_api_origins
from consultorio.utils.turnos_publicos import (
    cancelar_turno,
    listar_medicos,
    listar_turnos_paciente,
    max_dias_por_request,
    max_dias_reserva,
    reservar_turno,
    slots_disponibles,
    slots_disponibles_rango_cached,
)

bp = Blueprint("public_api", __name__)


def _origen_permitido(origin: str | None) -> bool:
    if not origin:
        return True
    normalizado = origin.rstrip("/")
    return normalizado in public_api_origins()


def _cors_headers(response):
    origins = public_api_origins()
    request_origin = request.headers.get("Origin")
    if request_origin and request_origin.rstrip("/") in origins:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    return response


@bp.after_request
def add_cors(response):
    return _cors_headers(response)


@bp.before_request
def validar_acceso_publico():
    if not public_api_configured():
        return (
            jsonify(
                {
                    "error": "API pública no configurada. Definí PUBLIC_API_KEY y PUBLIC_API_CORS_ORIGIN en .env"
                }
            ),
            503,
        )

    if request.method == "OPTIONS":
        origin = request.headers.get("Origin")
        if origin and not _origen_permitido(origin):
            return jsonify({"error": "Origen no autorizado"}), 403
        return _cors_headers(make_response("", 204))

    origin = request.headers.get("Origin")
    if origin and not _origen_permitido(origin):
        return jsonify({"error": "Origen no autorizado"}), 403


def public_api_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-API-Key")
        if not provided or provided != public_api_key():
            return jsonify({"error": "API key inválida o ausente (header X-API-Key)"}), 401
        return f(*args, **kwargs)

    return decorated


@bp.route("/api/public/v1", methods=["GET"], endpoint="public_api_info")
@public_api_auth
def public_api_info():
    return jsonify(
        {
            "nombre": "Colom Bobbiesi - API pública de turnos",
            "version": "1",
            "autenticacion": "Header X-API-Key obligatorio",
            "cors": "Solo orígenes listados en PUBLIC_API_CORS_ORIGIN",
            "registro_pacientes": "Pacientes nuevos pueden reservar y registrarse en la misma operación",
            "max_dias_reserva": max_dias_reserva(),
            "max_dias_por_request": max_dias_por_request(),
            "endpoints": {
                "medicos": "GET /api/public/v1/medicos",
                "disponibilidad": "GET /api/public/v1/disponibilidad?medico=...&fecha=YYYY-MM-DD",
                "disponibilidad_rango": (
                    "GET /api/public/v1/disponibilidad-rango?"
                    "medico=...&desde=YYYY-MM-DD&hasta=YYYY-MM-DD"
                ),
                "reservar": "POST /api/public/v1/turnos",
                "consultar": "GET /api/public/v1/turnos?dni=...",
                "cancelar": "DELETE /api/public/v1/turnos",
            },
        }
    )


@bp.route("/api/public/v1/medicos", methods=["GET"], endpoint="public_medicos")
@public_api_auth
def public_medicos():
    return jsonify({"medicos": listar_medicos()})


@bp.route("/api/public/v1/disponibilidad", methods=["GET"], endpoint="public_disponibilidad")
@public_api_auth
def public_disponibilidad():
    medico = (request.args.get("medico") or "").strip()
    fecha = (request.args.get("fecha") or "").strip()
    if not medico or not fecha:
        return jsonify({"error": "Parámetros 'medico' y 'fecha' son obligatorios"}), 400

    horarios, err = slots_disponibles(medico, fecha)
    if err:
        status = 404 if err == "Médico no encontrado" else 400
        return jsonify({"error": err}), status

    return jsonify(
        {
            "medico": medico,
            "fecha": fecha,
            "horarios_disponibles": horarios,
            "total": len(horarios),
        }
    )


@bp.route(
    "/api/public/v1/disponibilidad-rango",
    methods=["GET"],
    endpoint="public_disponibilidad_rango",
)
@public_api_auth
def public_disponibilidad_rango():
    medico = (request.args.get("medico") or "").strip()
    desde = (request.args.get("desde") or "").strip()
    hasta = (request.args.get("hasta") or "").strip()
    if not medico or not desde or not hasta:
        return jsonify(
            {"error": "Parámetros 'medico', 'desde' y 'hasta' son obligatorios"}
        ), 400

    payload, err = slots_disponibles_rango_cached(medico, desde, hasta)
    if err:
        status = 404 if err == "Médico no encontrado" else 400
        return jsonify({"error": err}), status

    return jsonify(payload)


@bp.route("/api/public/v1/turnos", methods=["GET"], endpoint="public_listar_turnos")
@public_api_auth
def public_listar_turnos():
    dni = (request.args.get("dni") or "").strip()
    if not dni:
        return jsonify({"error": "Parámetro 'dni' es obligatorio"}), 400

    solo_futuros = request.args.get("futuros", "1").strip().lower() not in ("0", "false", "no")
    turnos = listar_turnos_paciente(dni, solo_futuros=solo_futuros)
    return jsonify({"dni": dni, "turnos": turnos, "total": len(turnos)})


@bp.route("/api/public/v1/turnos", methods=["POST"], endpoint="public_reservar_turno")
@public_api_auth
def public_reservar_turno():
    data = request.get_json(silent=True) or {}
    body, status = reservar_turno(data)
    return jsonify(body), status


@bp.route("/api/public/v1/turnos", methods=["DELETE"], endpoint="public_cancelar_turno")
@public_api_auth
def public_cancelar_turno():
    data = request.get_json(silent=True) or {}
    dni = str(data.get("dni", "")).strip()
    fecha = str(data.get("fecha", "")).strip()
    hora = str(data.get("hora", "")).strip()
    body, status = cancelar_turno(dni, fecha, hora)
    return jsonify(body), status
