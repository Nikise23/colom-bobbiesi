from datetime import date

from flask import Blueprint, jsonify, render_template, request

from consultorio.auth.decorators import login_requerido, rol_permitido, rol_requerido
from consultorio.paths import AGENDA_FILE
from consultorio.storage import cargar_json, guardar_json
from consultorio.storage.queries import load_pacientes_por_dnis, load_pagos_fecha, load_turnos_fecha
from consultorio.utils.helpers import enriquecer_turnos

bp = Blueprint("agenda", __name__)


@bp.route("/agenda", endpoint="ver_agenda")
@login_requerido
@rol_requerido("secretaria")
def ver_agenda():
    return render_template("agenda.html")


@bp.route("/api/agenda", methods=["GET"], endpoint="obtener_agenda")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_agenda():
    try:
        agenda_data = cargar_json(AGENDA_FILE)
        return jsonify(agenda_data)
    except Exception as e:
        print(f"Error al cargar agenda: {e}")
        return jsonify({"error": "Error al cargar la agenda"}), 500


@bp.route("/api/agenda/inicio", methods=["GET"], endpoint="agenda_inicio")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def agenda_inicio():
    """Carga inicial de agenda: turnos del día con pacientes embebidos (sin listar todos)."""
    fecha = request.args.get("fecha", date.today().isoformat())
    turnos_raw = load_turnos_fecha(fecha)
    pagos = load_pagos_fecha(fecha)
    dnis = {t["dni_paciente"] for t in turnos_raw if t.get("dni_paciente")}
    pacientes = load_pacientes_por_dnis(dnis)
    agenda_data = cargar_json(AGENDA_FILE)
    return jsonify(
        {
            "agenda": agenda_data,
            "medicos": sorted(agenda_data.keys()),
            "turnos": enriquecer_turnos(turnos_raw, pacientes, pagos),
            "fecha": fecha,
        }
    )


@bp.route("/api/agenda/<medico>/<dia>", methods=["PUT"], endpoint="actualizar_agenda_dia")
@login_requerido
@rol_requerido("secretaria")
def actualizar_agenda_dia(medico, dia):
    nuevos_horarios = request.json
    if dia.upper() not in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]:
        return jsonify({"error": "Día inválido"}), 400
    if (
        not isinstance(nuevos_horarios, dict)
        or "horarios" not in nuevos_horarios
        or not isinstance(nuevos_horarios["horarios"], list)
    ):
        return jsonify({"error": "Formato inválido, se espera un objeto con clave 'horarios' que sea una lista"}), 400
    nuevos_horarios = nuevos_horarios["horarios"]

    agenda = cargar_json(AGENDA_FILE)
    if medico not in agenda:
        agenda[medico] = {}

    agenda[medico][dia.upper()] = nuevos_horarios
    guardar_json(AGENDA_FILE, agenda)
    return jsonify({"mensaje": "Agenda actualizada correctamente"})


@bp.route("/api/agenda/<medico>", methods=["PUT"], endpoint="actualizar_agenda_medico")
@login_requerido
@rol_requerido("secretaria")
def actualizar_agenda_medico(medico):
    datos = request.json
    if not isinstance(datos, dict) or "dias" not in datos or not isinstance(datos["dias"], dict):
        return jsonify({"error": 'Formato inválido, se espera { "dias": { "LUNES": [...], ... } }'}), 400

    dias_validos = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    agenda = cargar_json(AGENDA_FILE)
    if medico not in agenda:
        agenda[medico] = {}

    for dia, horarios in datos["dias"].items():
        dia_upper = dia.upper()
        if dia_upper not in dias_validos:
            return jsonify({"error": f"Día inválido: {dia}"}), 400
        if not isinstance(horarios, list):
            return jsonify({"error": f"Los horarios de {dia_upper} deben ser una lista"}), 400
        agenda[medico][dia_upper] = horarios

    guardar_json(AGENDA_FILE, agenda)
    return jsonify({"mensaje": f"Agenda de {medico} actualizada correctamente"})
