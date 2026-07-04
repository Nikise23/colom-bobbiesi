from datetime import date, datetime

from flask import Blueprint, jsonify, render_template, request

from consultorio.auth.decorators import login_requerido, rol_permitido
from consultorio.paths import PAGOS_FILE, TURNOS_FILE
from consultorio.storage import cargar_json
from consultorio.utils.helpers import (
    calcular_estadisticas_pagos,
    enriquecer_turnos,
    listar_pacientes_dedup,
    listar_recepcionados,
    listar_sala_espera,
)

bp = Blueprint("secretaria", __name__)


@bp.route("/secretaria", endpoint="vista_secretaria")
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def vista_secretaria():
    return render_template("secretaria.html")



@bp.route("/api/secretaria/inicio", methods=["GET"], endpoint="secretaria_inicio")
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def secretaria_inicio():
    """Carga inicial unificada: una lectura de cada JSON en lugar de 6+ requests."""
    fecha_param = request.args.get("fecha", date.today().isoformat())
    try:
        fecha_dia = datetime.strptime(fecha_param, "%Y-%m-%d").date()
    except ValueError:
        fecha_dia = date.today()
        fecha_param = fecha_dia.isoformat()

    pacientes = listar_pacientes_dedup()
    turnos_raw = cargar_json(TURNOS_FILE)
    pagos = cargar_json(PAGOS_FILE)
    turnos = enriquecer_turnos(turnos_raw, pacientes, pagos)
    turnos_hoy = [t for t in turnos if t.get("fecha") == fecha_param]
    turnos_hoy.sort(key=lambda t: t.get("hora", "00:00"))

    return jsonify({
        "pacientes": pacientes,
        "turnos": turnos,
        "pagos": pagos,
        "estadisticas_pagos": calcular_estadisticas_pagos(pagos, fecha_dia),
        "turnos_hoy": turnos_hoy,
        "recepcionados": listar_recepcionados(turnos_raw, pacientes, pagos, fecha_param),
        "sala_espera": listar_sala_espera(turnos_raw, pacientes, pagos, fecha_param),
        "fecha": fecha_param,
    })
