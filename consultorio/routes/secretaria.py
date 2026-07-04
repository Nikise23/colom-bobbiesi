from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from consultorio.auth.decorators import login_requerido, rol_permitido
from consultorio.storage.queries import (
    count_pacientes,
    count_turnos_pendientes,
    count_turnos_total,
    listar_atendidos_sin_pago,
    load_pacientes_liviano,
    load_pagos_fecha,
    load_pagos_mes,
    load_turnos_fecha,
)
from consultorio.utils.fechas import hoy_ar, hoy_ar_iso, normalizar_fecha_dia
from consultorio.utils.helpers import (
    calcular_estadisticas_pagos,
    enriquecer_turnos,
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
    """Carga inicial optimizada: solo datos del día y del mes en curso."""
    fecha_param = request.args.get("fecha", hoy_ar_iso())
    try:
        iso = normalizar_fecha_dia(fecha_param) or fecha_param
        fecha_dia = datetime.strptime(iso, "%Y-%m-%d").date()
        fecha_param = iso
    except ValueError:
        fecha_dia = hoy_ar()
        fecha_param = hoy_ar_iso()

    mes_param = fecha_dia.strftime("%Y-%m")
    turnos_raw = load_turnos_fecha(fecha_param)
    pagos_dia = load_pagos_fecha(fecha_param)
    pagos_mes = load_pagos_mes(mes_param)
    pacientes = load_pacientes_liviano()
    turnos_hoy = enriquecer_turnos(turnos_raw, pacientes, pagos_dia)
    turnos_hoy.sort(key=lambda t: t.get("hora", "00:00"))

    return jsonify(
        {
            "pacientes": pacientes,
            "total_pacientes": count_pacientes(),
            "total_turnos_sistema": count_turnos_total(),
            "turnos_del_dia": len(turnos_raw),
            "turnos_pendientes_total": count_turnos_pendientes(),
            "turnos": turnos_raw,
            "pagos": pagos_dia,
            "estadisticas_pagos": calcular_estadisticas_pagos(pagos_mes, fecha_dia, mes_param),
            "turnos_hoy": turnos_hoy,
            "recepcionados": listar_recepcionados(turnos_raw, pacientes, pagos_dia, fecha_param),
            "sala_espera": listar_sala_espera(turnos_raw, pacientes, pagos_dia, fecha_param),
            "atendidos_sin_pago": listar_atendidos_sin_pago(fecha_param),
            "fecha": fecha_param,
        }
    )
