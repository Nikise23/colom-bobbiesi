import csv
import io
from datetime import date, datetime

from flask import Blueprint, jsonify, make_response, request

from consultorio.auth.decorators import login_requerido, rol_permitido, rol_requerido
from consultorio.paths import PACIENTES_FILE, PAGOS_FILE, TURNOS_FILE, timezone_ar
from consultorio.storage import cargar_json, guardar_json
from consultorio.utils.helpers import calcular_estadisticas_pagos, normalizar_texto_obs

bp = Blueprint("pagos", __name__)


@bp.route("/api/pagos", methods=["GET"], endpoint="obtener_pagos")
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def obtener_pagos():
    pagos = cargar_json(PAGOS_FILE)
    return jsonify(pagos)


@bp.route("/api/pagos", methods=["POST"], endpoint="registrar_pago")
@login_requerido
@rol_requerido("secretaria")
def registrar_pago():
    data = request.json
    campos_requeridos = ["dni_paciente", "fecha"]
    
    for campo in campos_requeridos:
        if not data.get(campo):
            return jsonify({"error": f"El campo '{campo}' es requerido"}), 400
        
    # Validar monto (puede ser 0 para obra social)
    try:
        monto = float(data.get("monto", 0))
        if monto < 0:
             return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    
    # Validar tipo de pago (solo para pagos particulares)
    tipo_pago = data.get("tipo_pago", "efectivo")
    if monto > 0 and tipo_pago not in ["efectivo", "transferencia"]:
        return jsonify({"error": "Tipo de pago inválido. Debe ser 'efectivo' o 'transferencia'"}), 400
    
    # Para obra social, el tipo de pago siempre es "obra_social"
    if monto == 0:
        tipo_pago = "obra_social"
    
    # Verificar que el paciente existe
    pacientes = cargar_json(PACIENTES_FILE)
    paciente = next((p for p in pacientes if p["dni"] == data["dni_paciente"]), None)
    
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    
    # Verificar si ya existe un pago para este paciente en esta fecha y hora
    pagos = cargar_json(PAGOS_FILE)
    hora = data.get("hora", "")
    pago_existente = next((p for p in pagos if 
                          p["dni_paciente"] == data["dni_paciente"] and 
                          p["fecha"] == data["fecha"] and 
                          p.get("hora", "") == hora), None)
     
    if pago_existente and hora:
        return jsonify({"error": "Ya existe un pago registrado para este paciente en esta fecha y hora"}), 400
     
    nuevo_pago = {
        "id": len(pagos) + 1,
        "dni_paciente": data["dni_paciente"],
        "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
        "monto": monto,
        "fecha": data["fecha"],
        "hora": data.get("hora", ""),
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
        "observaciones": data.get("observaciones", ""),
        "obra_social": paciente.get("obra_social", ""),
        "tipo_pago": tipo_pago
    }
    
    pagos.append(nuevo_pago)
    guardar_json(PAGOS_FILE, pagos)
    
    return jsonify({"mensaje": "Pago registrado correctamente", "pago": nuevo_pago}), 201


@bp.route("/api/pagos/<int:pago_id>", methods=["DELETE"], endpoint="eliminar_pago")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def eliminar_pago(pago_id):
    pagos = cargar_json(PAGOS_FILE)
     
    # Filtrar el pago a eliminar
    pagos_filtrados = [p for p in pagos if p.get("id") != pago_id]
     
    if len(pagos_filtrados) == len(pagos):
        return jsonify({"error": "Pago no encontrado"}), 404
     
    guardar_json(PAGOS_FILE, pagos_filtrados)
    return jsonify({"mensaje": "Pago eliminado correctamente"})
 


@bp.route("/api/pagos/estadisticas", methods=["GET"], endpoint="obtener_estadisticas_pagos")
@login_requerido
@rol_requerido("secretaria")
def obtener_estadisticas_pagos():
    pagos = cargar_json(PAGOS_FILE)
    hoy = date.today()
    fecha_param = request.args.get("fecha")
    if fecha_param:
        try:
            fecha_dia = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            fecha_dia = hoy
    else:
        fecha_dia = hoy
    mes_param = request.args.get("mes", fecha_dia.strftime("%Y-%m"))
    return jsonify(calcular_estadisticas_pagos(pagos, fecha_dia, mes_param))

@bp.route("/api/pagos/exportar", methods=["GET"], endpoint="exportar_pagos_csv")
@login_requerido
@rol_requerido("secretaria")
def exportar_pagos_csv():
    pagos = cargar_json(PAGOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)

    # Obtener la fecha seleccionada (o hoy por defecto)
    
    fecha_param = request.args.get("fecha")
    if fecha_param:
        try:
            fecha_dia = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            fecha_dia = date.today()
    else:
        fecha_dia = date.today()
    
    # Filtrar pagos de la fecha seleccionada
    pagos_dia = [p for p in pagos if p["fecha"] == fecha_dia.isoformat()]
    
    # Calcular subtotales
    subtotal_efectivo = sum(p["monto"] for p in pagos_dia if p.get("tipo_pago") == "efectivo")
    subtotal_transferencia = sum(p["monto"] for p in pagos_dia if p.get("tipo_pago") == "transferencia")
    total = subtotal_efectivo + subtotal_transferencia
    
    # Crear archivo CSV en memoria
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados
    writer.writerow(['Fecha', 'Apellido', 'Nombre', 'DNI', 'Monto', 'Tipo de Pago', 'Observaciones'])
    
    # Datos
    for pago in pagos_dia:
        paciente = next((p for p in pacientes if p["dni"] == pago["dni_paciente"]), {})
        writer.writerow([
            pago["fecha"],
            paciente.get("apellido", ""),
            paciente.get("nombre", ""),
            pago["dni_paciente"],
            pago.get("tipo_pago", "efectivo"),
            pago.get("observaciones", "")
        ])
    # Fila vacía
    
    writer.writerow([])
    # Subtotales
    writer.writerow(["", "", "", "", "Subtotal Efectivo", subtotal_efectivo, ""])
    writer.writerow(["", "", "", "", "Subtotal Transferencia", subtotal_transferencia, ""])
    writer.writerow(["", "", "", "", "TOTAL", total, ""])

    # Preparar respuesta
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=pagos_{fecha_dia.isoformat()}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response


@bp.route("/api/pagos/cobrar-y-sala", methods=["PUT"], endpoint="cobrar_y_mover_a_sala")
@login_requerido
@rol_permitido(["secretaria"])
def cobrar_y_mover_a_sala():
    """Cobrar a un paciente recepcionado y moverlo a sala de espera desde gestión de pagos"""
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    monto = data.get("monto", 0)
    observaciones = normalizar_texto_obs(data.get("observaciones", ""))

    if not all([dni_paciente, fecha]):
        return jsonify({"error": "DNI y fecha son requeridos"}), 400
    
    # Validar monto
    try:
        monto = float(monto)
        if monto < 0:
            return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Buscar el turno recepcionado
    turno_encontrado = None
    for turno in turnos:
        if (turno["dni_paciente"] == dni_paciente and 
            turno["fecha"] == fecha and 
            turno.get("estado") == "recepcionado"):
            turno_encontrado = turno
            break

    if not turno_encontrado:
        return jsonify({"error": "No se encontró un turno recepcionado para este paciente en esta fecha"}), 404
    
    # Verificar que el paciente existe
    paciente = next((p for p in pacientes if p["dni"] == dni_paciente), None)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    
    # Verificar si ya existe un pago para este paciente en esta fecha
    pagos = cargar_json(PAGOS_FILE)
    pago_existente = next((p for p in pagos if p["dni_paciente"] == dni_paciente and p["fecha"] == fecha), None)
    
    if pago_existente:
        return jsonify({"error": "Ya existe un pago registrado para este paciente en esta fecha"}), 400
    # Determinar tipo de pago
    tipo_pago = data.get("tipo_pago", "efectivo")
    if monto == 0:
        tipo_pago = "obra_social"
    elif tipo_pago not in ["efectivo", "transferencia"]:
        return jsonify({"error": "Tipo de pago inválido"}), 400
    
    # Registrar el pago
    nuevo_pago = {
        "id": len(pagos) + 1,
        "dni_paciente": dni_paciente,
        "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
        "monto": monto,
        "fecha": fecha,
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
        "observaciones": observaciones,
        "obra_social": paciente.get("obra_social", ""),
        "tipo_pago": tipo_pago
    }
    
    pagos.append(nuevo_pago)
    guardar_json(PAGOS_FILE, pagos)
    
    # Mover a sala de espera
    turno_encontrado["estado"] = "sala de espera"
    turno_encontrado["hora_sala_espera"] = datetime.now(timezone_ar).strftime("%H:%M")
    turno_encontrado["pago_registrado"] = True
    turno_encontrado["monto_pagado"] = monto
    turno_encontrado["observacion_pago"] = observaciones

    guardar_json(TURNOS_FILE, turnos)
    return jsonify({
        "mensaje": "Pago registrado y paciente movido a sala de espera",
        "pago": nuevo_pago
    })
