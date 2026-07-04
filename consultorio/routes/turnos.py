from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, session

from consultorio.auth.decorators import login_requerido, rol_permitido, rol_requerido
from consultorio.paths import (
    AGENDA_FILE,
    DATA_FILE,
    PACIENTES_FILE,
    PAGOS_FILE,
    TURNOS_FILE,
    timezone_ar,
)
from consultorio.storage import cargar_json, guardar_json
from consultorio.utils.helpers import (
    adjuntar_observacion_pago_desde_pagos,
    enriquecer_turnos,
    listar_pacientes_dedup,
    normalizar_texto_obs,
    validar_historia,
    _texto_plano_desde_html,
)

bp = Blueprint("turnos", __name__)


@bp.route("/api/turnos", methods=["GET"], endpoint="obtener_turnos")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_turnos():
    pacientes = listar_pacientes_dedup()
    turnos_raw = cargar_json(TURNOS_FILE)
    pagos = cargar_json(PAGOS_FILE)
    return jsonify(enriquecer_turnos(turnos_raw, pacientes, pagos))



@bp.route("/api/turnos", methods=["POST"], endpoint="asignar_turno")
@login_requerido
@rol_requerido("secretaria")
def asignar_turno():
    data = request.json
    campos = ["medico", "hora", "fecha", "dni_paciente"]
    for campo in campos:
        if not data.get(campo):
            return jsonify({"error": f"El campo '{campo}' es obligatorio"}), 400


    try:
        fecha_dt = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido (usar YYYY-MM-DD)"}), 400


    dia_semana = fecha_dt.strftime("%A").upper()
    if dia_semana not in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]:
        return jsonify({"error": "Solo se pueden asignar turnos de lunes a sábado"}), 400


    dia_es = {
        "MONDAY": "LUNES", "TUESDAY": "MARTES", "WEDNESDAY": "MIERCOLES",
        "THURSDAY": "JUEVES", "FRIDAY": "VIERNES", "SATURDAY": "SABADO"
    }[dia_semana]


    agenda = cargar_json(AGENDA_FILE)
    medico = data["medico"]
    if medico not in agenda:
        return jsonify({"error": "Médico no encontrado"}), 404


    horarios_disponibles = agenda[medico].get(dia_es, [])
    if data["hora"] not in horarios_disponibles:
        return jsonify({"error": f"La hora '{data['hora']}' no está disponible para el médico {medico} el día {dia_es}"}), 400


    turnos = cargar_json(TURNOS_FILE)
    if any(t["medico"] == medico and t.get("fecha") == data["fecha"] and t["hora"] == data["hora"] for t in turnos):
        return jsonify({"error": "Ya existe un turno asignado para ese horario y fecha"}), 400


    pacientes = cargar_json(PACIENTES_FILE)
    if not any(p["dni"] == data["dni_paciente"] for p in pacientes):
        return jsonify({"error": "Paciente no encontrado"}), 404

    obs_raw = data.get("observacion")
    observacion = (obs_raw.strip()[:500] if isinstance(obs_raw, str) else "") or ""

    turno_nuevo = {
        "medico": medico,
        "hora": data["hora"],
        "fecha": data["fecha"],
        "dni_paciente": data["dni_paciente"],
        "estado": "sin atender",
        "observacion": observacion,
    }


    turnos.append(turno_nuevo)
    guardar_json(TURNOS_FILE, turnos)
    return jsonify({"mensaje": "Turno asignado correctamente"})



@bp.route("/api/turnos/estado", methods=["PUT"], endpoint="actualizar_estado_turno")
@login_requerido
@rol_permitido(["medico"])
def actualizar_estado_turno():
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    hora = data.get("hora")
    nuevo_estado = data.get("estado")


    if nuevo_estado not in ["sin atender", "llamado", "atendido", "ausente", "atendiendo"]:
        return jsonify({"error": "Estado inválido"}), 400


    turnos = cargar_json(TURNOS_FILE)
    encontrado = False


    for turno in turnos:
        if turno["dni_paciente"] == dni_paciente and turno["fecha"] == fecha and turno["hora"] == hora:
            turno["estado"] = nuevo_estado
            encontrado = True
            break


    if not encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404


    guardar_json(TURNOS_FILE, turnos)
    return jsonify({"mensaje": "Estado actualizado correctamente"})



@bp.route("/turnos", endpoint="ver_turnos")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def ver_turnos():
    # Redirigir según el rol
    if session.get("rol") == "medico":
        return render_template("turnos_medico.html")
    else:
        return render_template("pacientes_turnos.html")


@bp.route("/turnos/gestion", endpoint="gestion_turnos")
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def gestion_turnos():
    return render_template("pacientes_turnos.html")


@bp.route("/api/turnos/medico", methods=["GET"], endpoint="obtener_turnos_medico")
@login_requerido
@rol_requerido("medico")
def obtener_turnos_medico():
    usuario_medico = session.get("usuario")
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    pagos = cargar_json(PAGOS_FILE)

    turnos_medico = [t for t in turnos if t.get("medico") == usuario_medico]


    # Enriquecer con datos del paciente
    for t in turnos_medico:
        paciente = next((p for p in pacientes if p["dni"] == t["dni_paciente"]), {})
        t["paciente"] = paciente
        t["estado"] = t.get("estado", "sin atender")
        adjuntar_observacion_pago_desde_pagos(t, pagos)

    return jsonify(turnos_medico)


@bp.route("/api/turnos/<dni>/<fecha>/<hora>", methods=["PUT"], endpoint="editar_turno")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def editar_turno(dni, fecha, hora):
    data = request.json
    turnos = cargar_json(TURNOS_FILE)
    
    # Encontrar el turno específico
    turno_encontrado = None
    for turno in turnos:
        if turno["dni_paciente"] == dni and turno["fecha"] == fecha and turno["hora"] == hora:
            turno_encontrado = turno
            break
    
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
    
    # Actualizar los campos permitidos
    if "nueva_hora" in data:
        nueva_hora = data["nueva_hora"]
        nueva_fecha = data.get("nueva_fecha", fecha)
        # Verificar que la nueva hora no esté ocupada en la fecha correspondiente
        if any(t["medico"] == turno_encontrado["medico"] and t["fecha"] == nueva_fecha and t["hora"] == nueva_hora and 
               not (t["dni_paciente"] == dni and t["fecha"] == fecha and t["hora"] == hora) for t in turnos):
            return jsonify({"error": "La nueva hora ya está ocupada"}), 400
        turno_encontrado["hora"] = nueva_hora
    
    if "nueva_fecha" in data:
        nueva_fecha = data["nueva_fecha"]
        nueva_hora = data.get("nueva_hora", turno_encontrado["hora"])
        # Verificar que la nueva fecha/hora no esté ocupada
        if any(t["medico"] == turno_encontrado["medico"] and t["fecha"] == nueva_fecha and t["hora"] == nueva_hora and 
               not (t["dni_paciente"] == dni and t["fecha"] == fecha and t["hora"] == hora) for t in turnos):
            return jsonify({"error": "La nueva fecha/hora ya está ocupada"}), 400
        turno_encontrado["fecha"] = nueva_fecha
    
    if "nuevo_medico" in data:
        turno_encontrado["medico"] = data["nuevo_medico"]
    
    if "nuevo_estado" in data:
        estados_validos = ["sin atender", "recepcionado", "sala de espera", "llamado", "atendiendo", "atendido", "ausente"]
        if data["nuevo_estado"] in estados_validos:
            turno_encontrado["estado"] = data["nuevo_estado"]

    if "observacion" in data:
        obs_raw = data.get("observacion")
        turno_encontrado["observacion"] = (
            obs_raw.strip()[:500] if isinstance(obs_raw, str) else ""
        )

    guardar_json(TURNOS_FILE, turnos)
    return jsonify({"mensaje": "Turno actualizado correctamente"})


@bp.route("/api/turnos/<dni>/<fecha>/<hora>", methods=["DELETE"], endpoint="eliminar_turno")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def eliminar_turno(dni, fecha, hora):
    turnos = cargar_json(TURNOS_FILE)
    
    # Filtrar el turno a eliminar
    turnos_filtrados = [
        t for t in turnos 
        if not (t["dni_paciente"] == dni and t["fecha"] == fecha and t["hora"] == hora)
    ]
    
    if len(turnos_filtrados) == len(turnos):
        return jsonify({"error": "Turno no encontrado"}), 404
    
    guardar_json(TURNOS_FILE, turnos_filtrados)
    return jsonify({"mensaje": "Turno eliminado correctamente"})



@bp.route("/api/turnos/<dni>/<fecha>/<hora>/borrador-consulta", methods=["PUT", "POST", "DELETE"], endpoint="borrador_consulta_turno")
@login_requerido
@rol_requerido("medico")
def borrador_consulta_turno(dni, fecha, hora):
    """Borrador de la consulta en curso (turno en estado atendiendo)."""
    usuario_medico = session.get("usuario")
    turnos = cargar_json(TURNOS_FILE)
    turno_encontrado = None
    for turno in turnos:
        if (
            turno.get("dni_paciente") == dni
            and turno.get("fecha") == fecha
            and turno.get("hora") == hora
        ):
            turno_encontrado = turno
            break
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
    if turno_encontrado.get("medico") != usuario_medico:
        return jsonify({"error": "No autorizado"}), 403
    if turno_encontrado.get("estado") != "atendiendo":
        return jsonify(
            {"error": "El turno no está en atención; el borrador solo aplica con turno en atendiendo."}
        ), 400

    if request.method == "DELETE":
        turno_encontrado.pop("borrador_consulta", None)
        turno_encontrado.pop("borrador_fecha_consulta", None)
        turno_encontrado.pop("borrador_actualizado", None)
        guardar_json(TURNOS_FILE, turnos)
        return jsonify({"mensaje": "Borrador eliminado"})

    data = request.json or {}
    texto = data.get("consulta_medica", "")
    if not isinstance(texto, str):
        texto = ""
    texto = texto[:200000]
    fecha_c = data.get("fecha_consulta", "")
    if not isinstance(fecha_c, str):
        fecha_c = ""
    fecha_c = fecha_c.strip()[:32]

    turno_encontrado["borrador_consulta"] = texto
    turno_encontrado["borrador_fecha_consulta"] = fecha_c
    turno_encontrado["borrador_actualizado"] = datetime.now(timezone_ar).isoformat()
    guardar_json(TURNOS_FILE, turnos)
    return jsonify(
        {
            "mensaje": "Borrador guardado",
            "actualizado": turno_encontrado["borrador_actualizado"],
        }
    )


@bp.route("/api/turnos/<dni>/<fecha>/<hora>/finalizar-atencion", methods=["POST"], endpoint="finalizar_atencion")
@login_requerido
@rol_requerido("medico")
def finalizar_atencion(dni, fecha, hora):
    """Guarda el borrador autoguardado como historia clínica y marca el turno como atendido."""
    usuario_medico = session.get("usuario")
    turnos = cargar_json(TURNOS_FILE)
    turno_encontrado = None
    for turno in turnos:
        if (
            turno.get("dni_paciente") == dni
            and turno.get("fecha") == fecha
            and turno.get("hora") == hora
        ):
            turno_encontrado = turno
            break

    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
    if turno_encontrado.get("medico") != usuario_medico:
        return jsonify({"error": "No autorizado"}), 403
    if turno_encontrado.get("estado") != "atendiendo":
        return jsonify({"error": "El turno no está en atención"}), 400

    consulta = (turno_encontrado.get("borrador_consulta") or "").strip()
    fecha_consulta = (
        turno_encontrado.get("borrador_fecha_consulta")
        or turno_encontrado.get("fecha")
        or date.today().isoformat()
    ).strip()
    historia_guardada = False

    if _texto_plano_desde_html(consulta):
        datos = {
            "dni": dni,
            "consulta_medica": consulta,
            "fecha_consulta": fecha_consulta,
            "medico": usuario_medico,
        }
        valido, mensaje = validar_historia(datos)
        if not valido:
            return jsonify({"error": mensaje}), 400

        historias = cargar_json(DATA_FILE)
        datos["id"] = len(historias) + 1
        datos["fecha_creacion"] = datetime.now(timezone_ar).isoformat()
        historias.append(datos)
        guardar_json(DATA_FILE, historias)
        historia_guardada = True

    turno_encontrado["estado"] = "atendido"
    turno_encontrado.pop("borrador_consulta", None)
    turno_encontrado.pop("borrador_fecha_consulta", None)
    turno_encontrado.pop("borrador_actualizado", None)
    guardar_json(TURNOS_FILE, turnos)

    if historia_guardada:
        mensaje = "Historia clínica guardada y atención finalizada."
    else:
        mensaje = "Atención finalizada (sin texto de historia clínica)."

    return jsonify({"mensaje": mensaje, "historia_guardada": historia_guardada})


# ======================= SISTEMA DE PAGOS =======================


@bp.route("/api/turnos/recepcionar", methods=["PUT"], endpoint="recepcionar_paciente")
@login_requerido
@rol_permitido(["secretaria"])
def recepcionar_paciente():
    """Cambiar el estado de un turno a 'recepcionado' cuando llega el paciente"""
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    hora = data.get("hora")
    
    if not all([dni_paciente, fecha, hora]):
        return jsonify({"error": "DNI, fecha y hora son requeridos"}), 400
    
    turnos = cargar_json(TURNOS_FILE)
    
    for turno in turnos:
        if (turno["dni_paciente"] == dni_paciente and 
            turno["fecha"] == fecha and 
            turno["hora"] == hora):
            
            turno["estado"] = "recepcionado"
            turno["hora_recepcion"] = datetime.now(timezone_ar).strftime("%H:%M")
            
            guardar_json(TURNOS_FILE, turnos)
            return jsonify({"mensaje": "Paciente recepcionado correctamente"})
    
    return jsonify({"error": "Turno no encontrado"}), 404


@bp.route("/api/turnos/sala-espera", methods=["PUT"], endpoint="mover_a_sala_espera")
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def mover_a_sala_espera():
    """Mover paciente recepcionado a sala de espera y registrar pago"""
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    hora = data.get("hora")
    monto = data.get("monto", 0)  # Puede ser 0 para obra social
    observaciones = normalizar_texto_obs(data.get("observaciones", ""))
    tipo_pago = data.get("tipo_pago", "efectivo")  # Nuevo campo para tipo de pago

     
    if not all([dni_paciente, fecha, hora]):
        return jsonify({"error": "DNI, fecha y hora son requeridos"}), 400
     
     # Validar monto
    try:
        monto = float(monto)
        if monto < 0:
            return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    # Validar tipo de pago
    if monto == 0:
        tipo_pago = "obra_social"
    elif tipo_pago not in ["efectivo", "transferencia"]:
        return jsonify({"error": "Tipo de pago inválido. Debe ser 'efectivo' o 'transferencia'"}), 400

    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
     
    # Buscar el turno
    turno_encontrado = None

    for turno in turnos:
        if (turno["dni_paciente"] == dni_paciente and 
            turno["fecha"] == fecha and 
            turno["hora"] == hora):
            turno_encontrado = turno
            break
     
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
        
    if turno_encontrado.get("estado") != "recepcionado":
        return jsonify({"error": "El paciente debe estar recepcionado primero"}), 400
        
    # Verificar que el paciente existe

    paciente = next((p for p in pacientes if p["dni"] == dni_paciente), None)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
     
    # Verificar si ya existe un pago para este paciente en esta fecha y hora
    pagos = cargar_json(PAGOS_FILE)
    pago_existente = next((p for p in pagos if p["dni_paciente"] == dni_paciente and p["fecha"] == fecha and p.get("hora") == hora), None)
    
    if pago_existente:
        return jsonify({"error": "Ya existe un pago registrado para este paciente en este turno"}), 400
    
    
    # Registrar el pago
    nuevo_pago = {
        "id": len(pagos) + 1,
        "dni_paciente": dni_paciente,
        "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
        "monto": monto,
        "fecha": fecha,
        "hora": hora,  # Guardar la hora del turno en el pago
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
        "observaciones": observaciones,
        "obra_social": paciente.get("obra_social", ""),
        "tipo_pago": tipo_pago  # Agregar tipo de pago
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
        "mensaje": "Paciente movido a sala de espera y pago registrado",
        "pago": nuevo_pago
    })
    

@bp.route("/api/turnos/dia", methods=["GET"], endpoint="obtener_turnos_dia")
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_turnos_dia():
    """Obtener todos los turnos de una fecha específica (por defecto hoy)"""
    fecha = request.args.get("fecha", date.today().isoformat())
    pacientes = listar_pacientes_dedup()
    turnos_raw = cargar_json(TURNOS_FILE)
    pagos = cargar_json(PAGOS_FILE)
    turnos_dia = enriquecer_turnos([t for t in turnos_raw if t.get("fecha") == fecha], pacientes, pagos)
    turnos_dia.sort(key=lambda t: t.get("hora", "00:00"))
    return jsonify(turnos_dia)


@bp.route('/api/turnos/limpiar-vencidos', methods=['POST'], endpoint="limpiar_turnos_vencidos")
@login_requerido
@rol_requerido('secretaria')
def limpiar_turnos_vencidos():
    
    turnos = cargar_json(TURNOS_FILE)
    ahora = datetime.now()
    nuevos = []
    eliminados = 0
    for t in turnos:
        fecha_hora_str = f"{t.get('fecha', '')} {t.get('hora', '00:00')}"
        try:
            fecha_hora = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
        except Exception:
            nuevos.append(t)
            continue
        if t.get('estado', '').lower() == 'sin atender' and fecha_hora < ahora - timedelta(hours=24):
            eliminados += 1
        else:
            nuevos.append(t)
    guardar_json(TURNOS_FILE, nuevos)
    return jsonify({"eliminados": eliminados, "ok": True})


# ========================== HISTORIAS CLÍNICAS ==================
