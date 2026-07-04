import csv
import io
from datetime import datetime

from flask import Blueprint, jsonify, make_response, request

from consultorio.auth.decorators import login_requerido, rol_permitido, rol_requerido
from consultorio.paths import PAGOS_FILE, timezone_ar
from consultorio.storage import cargar_json, guardar_json
from consultorio.storage.queries import (
    insert_pago,
    load_pagos_fecha,
    load_pagos_mes,
    load_turnos_fecha,
    obtener_paciente,
    pago_existe,
    update_turno,
)
from consultorio.utils.fechas import hoy_ar, normalizar_fecha_dia
from consultorio.utils.helpers import calcular_estadisticas_pagos, normalizar_texto_obs

bp = Blueprint("pagos", __name__)


def _registrar_pago_interno(data: dict, requiere_hora_unica: bool = False):
    campos_requeridos = ["dni_paciente", "fecha"]
    for campo in campos_requeridos:
        if not data.get(campo):
            return {"error": f"El campo '{campo}' es requerido"}, 400

    fecha = normalizar_fecha_dia(data.get("fecha"))
    if not fecha:
        return {"error": "Fecha inválida (use YYYY-MM-DD)"}, 400

    try:
        monto = float(data.get("monto", 0))
        if monto < 0:
            return {"error": "El monto no puede ser negativo"}, 400
    except (ValueError, TypeError):
        return {"error": "Monto inválido"}, 400

    tipo_pago = data.get("tipo_pago", "efectivo")
    if monto > 0 and tipo_pago not in ["efectivo", "transferencia"]:
        return {"error": "Tipo de pago inválido. Debe ser 'efectivo' o 'transferencia'"}, 400
    if monto == 0:
        tipo_pago = "obra_social"

    paciente = obtener_paciente(data["dni_paciente"])
    if not paciente:
        return {"error": "Paciente no encontrado"}, 404

    hora = data.get("hora", "")
    if requiere_hora_unica and hora and pago_existe(data["dni_paciente"], fecha, hora):
        return {"error": "Ya existe un pago registrado para este paciente en esta fecha y hora"}, 400
    if not requiere_hora_unica and pago_existe(data["dni_paciente"], fecha):
        return {"error": "Ya existe un pago registrado para este paciente en esta fecha"}, 400

    nuevo_pago = insert_pago(
        {
            "dni_paciente": data["dni_paciente"],
            "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
            "monto": monto,
            "fecha": fecha,
            "hora": hora,
            "fecha_registro": datetime.now(timezone_ar).isoformat(),
            "observaciones": data.get("observaciones", ""),
            "obra_social": paciente.get("obra_social", ""),
            "tipo_pago": tipo_pago,
        }
    )
    return {"mensaje": "Pago registrado correctamente", "pago": nuevo_pago}, 201


@bp.route("/api/pagos", methods=["GET"], endpoint="obtener_pagos")
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def obtener_pagos():
    fecha = request.args.get("fecha")
    if fecha:
        return jsonify(load_pagos_fecha(fecha))
    mes = request.args.get("mes", hoy_ar().strftime("%Y-%m"))
    return jsonify(load_pagos_mes(mes))


@bp.route("/api/pagos", methods=["POST"], endpoint="registrar_pago")
@login_requerido
@rol_requerido("secretaria")
def registrar_pago():
    payload, status = _registrar_pago_interno(request.json or {}, requiere_hora_unica=True)
    return jsonify(payload), status


@bp.route("/api/pagos/<int:pago_id>", methods=["DELETE"], endpoint="eliminar_pago")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def eliminar_pago(pago_id):
    pagos = cargar_json(PAGOS_FILE)
    pagos_filtrados = [p for p in pagos if p.get("id") != pago_id]
    if len(pagos_filtrados) == len(pagos):
        return jsonify({"error": "Pago no encontrado"}), 404

    guardar_json(PAGOS_FILE, pagos_filtrados)
    return jsonify({"mensaje": "Pago eliminado correctamente"})


@bp.route("/api/pagos/estadisticas", methods=["GET"], endpoint="obtener_estadisticas_pagos")
@login_requerido
@rol_requerido("secretaria")
def obtener_estadisticas_pagos():
    fecha_param = request.args.get("fecha")
    if fecha_param:
        iso = normalizar_fecha_dia(fecha_param) or fecha_param
        fecha_dia = datetime.strptime(iso, "%Y-%m-%d").date()
    else:
        fecha_dia = hoy_ar()
    mes_param = request.args.get("mes", fecha_dia.strftime("%Y-%m"))
    pagos = load_pagos_mes(mes_param)
    return jsonify(calcular_estadisticas_pagos(pagos, fecha_dia, mes_param))


@bp.route("/api/pagos/exportar", methods=["GET"], endpoint="exportar_pagos_csv")
@login_requerido
@rol_requerido("secretaria")
def exportar_pagos_csv():
    fecha_param = request.args.get("fecha")
    if fecha_param:
        iso = normalizar_fecha_dia(fecha_param) or fecha_param
        fecha_dia = datetime.strptime(iso, "%Y-%m-%d").date()
    else:
        fecha_dia = hoy_ar()

    pagos_dia = load_pagos_fecha(fecha_dia.isoformat())
    subtotal_efectivo = sum(p["monto"] for p in pagos_dia if p.get("tipo_pago") == "efectivo")
    subtotal_transferencia = sum(
        p["monto"] for p in pagos_dia if p.get("tipo_pago") == "transferencia"
    )
    total = subtotal_efectivo + subtotal_transferencia

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Fecha", "Apellido", "Nombre", "DNI", "Monto", "Tipo de Pago", "Observaciones"])

    for pago in pagos_dia:
        paciente = obtener_paciente(pago["dni_paciente"]) or {}
        writer.writerow(
            [
                pago["fecha"],
                paciente.get("apellido", ""),
                paciente.get("nombre", ""),
                pago["dni_paciente"],
                pago.get("monto", 0),
                pago.get("tipo_pago", "efectivo"),
                pago.get("observaciones", ""),
            ]
        )

    writer.writerow([])
    writer.writerow(["", "", "", "", "Subtotal Efectivo", subtotal_efectivo, ""])
    writer.writerow(["", "", "", "", "Subtotal Transferencia", subtotal_transferencia, ""])
    writer.writerow(["", "", "", "", "TOTAL", total, ""])

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=pagos_{fecha_dia.isoformat()}.csv"
    response.headers["Content-type"] = "text/csv"
    return response


@bp.route("/api/pagos/cobrar-y-sala", methods=["PUT"], endpoint="cobrar_y_mover_a_sala")
@login_requerido
@rol_permitido(["secretaria"])
def cobrar_y_mover_a_sala():
    data = request.json or {}
    dni_paciente = data.get("dni_paciente")
    fecha_raw = data.get("fecha")
    monto = data.get("monto", 0)
    observaciones = normalizar_texto_obs(data.get("observaciones", ""))

    fecha = normalizar_fecha_dia(fecha_raw)
    if not all([dni_paciente, fecha]):
        return jsonify({"error": "DNI y fecha son requeridos"}), 400

    try:
        monto = float(monto)
        if monto < 0:
            return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400

    turno_encontrado = next(
        (
            t
            for t in load_turnos_fecha(fecha)
            if t.get("dni_paciente") == dni_paciente and t.get("estado") == "recepcionado"
        ),
        None,
    )
    if not turno_encontrado:
        return jsonify(
            {"error": "No se encontró un turno recepcionado para este paciente en esta fecha"}
        ), 404

    payload, status = _registrar_pago_interno(
        {
            "dni_paciente": dni_paciente,
            "fecha": fecha,
            "hora": turno_encontrado.get("hora", ""),
            "monto": monto,
            "tipo_pago": data.get("tipo_pago", "efectivo"),
            "observaciones": observaciones,
        },
        requiere_hora_unica=True,
    )
    if status != 201:
        return jsonify(payload), status

    update_turno(
        dni_paciente,
        fecha,
        turno_encontrado["hora"],
        {
            "estado": "sala de espera",
            "hora_sala_espera": datetime.now(timezone_ar).strftime("%H:%M"),
            "pago_registrado": True,
            "monto_pagado": monto,
            "observacion_pago": observaciones,
        },
    )
    return jsonify(
        {
            "mensaje": "Pago registrado y paciente movido a sala de espera",
            "pago": payload["pago"],
        }
    )
