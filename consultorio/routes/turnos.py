from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, session

from consultorio.auth.decorators import login_requerido, rol_permitido, rol_requerido
from consultorio.config import use_database
from consultorio.paths import (
    AGENDA_FILE,
    DATA_FILE,
    TURNOS_FILE,
    timezone_ar,
)
from consultorio.storage import cargar_json, guardar_json
from consultorio.storage.queries import (
    delete_turno,
    get_turno,
    insert_pago,
    insert_turno,
    load_pacientes_por_dnis,
    load_pagos_fecha,
    load_turnos_fecha,
    load_turnos_medico_fecha,
    load_turnos_medico_proximos,
    obtener_paciente,
    pago_existe,
    update_turno,
)
from consultorio.utils.fechas import hoy_ar_iso, normalizar_fecha_dia
from consultorio.utils.helpers import (
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


    ocupados = load_turnos_fecha(data["fecha"])
    if any(
        t.get("medico") == medico and t.get("hora") == data["hora"]
        for t in ocupados
    ):
        return jsonify({"error": "Ya existe un turno asignado para ese horario y fecha"}), 400
    if get_turno(data["dni_paciente"], data["fecha"], data["hora"]):
        return jsonify({"error": "El paciente ya tiene un turno en esa fecha y hora"}), 400

    if not obtener_paciente(data["dni_paciente"]):
        return jsonify({"error": "Paciente no encontrado"}), 404

    obs_raw = data.get("observacion")
    observacion = (obs_raw.strip()[:500] if isinstance(obs_raw, str) else "") or ""

    insert_turno(
        {
            "medico": medico,
            "hora": data["hora"],
            "fecha": data["fecha"],
            "dni_paciente": data["dni_paciente"],
            "estado": "sin atender",
            "observacion": observacion,
        }
    )
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
    usuario_medico = session.get("usuario")

    if nuevo_estado not in ["sin atender", "llamado", "atendido", "ausente", "atendiendo"]:
        return jsonify({"error": "Estado inválido"}), 400

    turno = get_turno(dni_paciente, fecha, hora)
    if not turno:
        return jsonify({"error": "Turno no encontrado"}), 404
    if turno.get("medico") != usuario_medico:
        return jsonify({"error": "No autorizado: el turno pertenece a otro médico"}), 403

    if not update_turno(dni_paciente, fecha, hora, {"estado": nuevo_estado}):
        return jsonify({"error": "Turno no encontrado"}), 404

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
    """Turnos del médico logueado. Por defecto solo hoy; ?proximos=1 para futuros."""
    usuario_medico = session.get("usuario")
    fecha = request.args.get("fecha")
    proximos = request.args.get("proximos", "").lower() in ("1", "true", "yes")

    if proximos:
        turnos_raw = load_turnos_medico_proximos(usuario_medico, hoy_ar_iso())
        fechas = {
            normalizar_fecha_dia(t.get("fecha")) or str(t.get("fecha", "")).strip()[:10]
            for t in turnos_raw
        }
        pagos = []
        for f in fechas:
            if f:
                pagos.extend(load_pagos_fecha(f))
    else:
        fecha = fecha or hoy_ar_iso()
        turnos_raw = load_turnos_medico_fecha(usuario_medico, fecha)
        pagos = load_pagos_fecha(fecha)

    dnis = {t["dni_paciente"] for t in turnos_raw if t.get("dni_paciente")}
    pacientes = load_pacientes_por_dnis(dnis)
    return jsonify(enriquecer_turnos(turnos_raw, pacientes, pagos))


@bp.route("/api/turnos/<dni>/<fecha>/<hora>", methods=["PUT"], endpoint="editar_turno")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def editar_turno(dni, fecha, hora):
    data = request.json or {}
    turno_encontrado = get_turno(dni, fecha, hora)
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404

    campos = {}
    nueva_hora = data.get("nueva_hora", turno_encontrado["hora"])
    nueva_fecha = data.get("nueva_fecha", turno_encontrado["fecha"])
    cambia_horario = ("nueva_hora" in data and data["nueva_hora"] != turno_encontrado["hora"]) or (
        "nueva_fecha" in data and data["nueva_fecha"] != turno_encontrado["fecha"]
    )

    if cambia_horario:
        ocupados = load_turnos_fecha(nueva_fecha)
        if any(
            t.get("medico") == turno_encontrado["medico"]
            and t.get("hora") == nueva_hora
            and not (
                t.get("dni_paciente") == dni
                and t.get("fecha") == turno_encontrado["fecha"]
                and t.get("hora") == turno_encontrado["hora"]
            )
            for t in ocupados
        ):
            return jsonify({"error": "La nueva fecha/hora ya está ocupada"}), 400
        if "nueva_hora" in data:
            campos["hora"] = data["nueva_hora"]
        if "nueva_fecha" in data:
            campos["fecha"] = data["nueva_fecha"]

    if "nuevo_medico" in data:
        campos["medico"] = data["nuevo_medico"]

    if "nuevo_estado" in data:
        estados_validos = [
            "sin atender",
            "recepcionado",
            "sala de espera",
            "llamado",
            "atendiendo",
            "atendido",
            "ausente",
        ]
        if data["nuevo_estado"] in estados_validos:
            campos["estado"] = data["nuevo_estado"]

    if "observacion" in data:
        obs_raw = data.get("observacion")
        campos["observacion"] = obs_raw.strip()[:500] if isinstance(obs_raw, str) else ""

    if not campos:
        return jsonify({"mensaje": "Sin cambios"})

    if not update_turno(dni, fecha, hora, campos):
        return jsonify({"error": "Turno no encontrado"}), 404
    return jsonify({"mensaje": "Turno actualizado correctamente"})


@bp.route("/api/turnos/<dni>/<fecha>/<hora>", methods=["DELETE"], endpoint="eliminar_turno")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def eliminar_turno(dni, fecha, hora):
    if not delete_turno(dni, fecha, hora):
        return jsonify({"error": "Turno no encontrado"}), 404
    return jsonify({"mensaje": "Turno eliminado correctamente"})


@bp.route("/api/turnos/<dni>/<fecha>/<hora>/borrador-consulta", methods=["PUT", "POST", "DELETE"], endpoint="borrador_consulta_turno")
@login_requerido
@rol_requerido("medico")
def borrador_consulta_turno(dni, fecha, hora):
    """Borrador de la consulta en curso (turno en estado atendiendo)."""
    usuario_medico = session.get("usuario")
    turno_encontrado = get_turno(dni, fecha, hora)
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
    if turno_encontrado.get("medico") != usuario_medico:
        return jsonify({"error": "No autorizado"}), 403
    if turno_encontrado.get("estado") != "atendiendo":
        return jsonify(
            {"error": "El turno no está en atención; el borrador solo aplica con turno en atendiendo."}
        ), 400

    if request.method == "DELETE":
        update_turno(
            dni,
            fecha,
            hora,
            {
                "borrador_consulta": None,
                "borrador_fecha_consulta": None,
                "borrador_actualizado": None,
            },
        )
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
    actualizado = datetime.now(timezone_ar).isoformat()

    update_turno(
        dni,
        fecha,
        hora,
        {
            "borrador_consulta": texto,
            "borrador_fecha_consulta": fecha_c,
            "borrador_actualizado": actualizado,
        },
    )
    return jsonify({"mensaje": "Borrador guardado", "actualizado": actualizado})


@bp.route("/api/turnos/<dni>/<fecha>/<hora>/finalizar-atencion", methods=["POST"], endpoint="finalizar_atencion")
@login_requerido
@rol_requerido("medico")
def finalizar_atencion(dni, fecha, hora):
    """Guarda el borrador autoguardado como historia clínica y marca el turno como atendido."""
    usuario_medico = session.get("usuario")
    turno_encontrado = get_turno(dni, fecha, hora)

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

        if use_database():
            from consultorio.storage import db_storage

            datos["fecha_creacion"] = datetime.now(timezone_ar).isoformat()
            db_storage.insert_historia(datos, fecha, hora)
        else:
            historias = cargar_json(DATA_FILE)
            datos["id"] = len(historias) + 1
            datos["fecha_creacion"] = datetime.now(timezone_ar).isoformat()
            historias.append(datos)
            guardar_json(DATA_FILE, historias)
            update_turno(
                dni,
                fecha,
                hora,
                {
                    "estado": "atendido",
                    "borrador_consulta": None,
                    "borrador_fecha_consulta": None,
                    "borrador_actualizado": None,
                },
            )
        historia_guardada = True
    else:
        update_turno(
            dni,
            fecha,
            hora,
            {
                "estado": "atendido",
                "borrador_consulta": None,
                "borrador_fecha_consulta": None,
                "borrador_actualizado": None,
            },
        )

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

    if not get_turno(dni_paciente, fecha, hora):
        return jsonify({"error": "Turno no encontrado"}), 404

    update_turno(
        dni_paciente,
        fecha,
        hora,
        {
            "estado": "recepcionado",
            "hora_recepcion": datetime.now(timezone_ar).strftime("%H:%M"),
        },
    )
    return jsonify({"mensaje": "Paciente recepcionado correctamente"})


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

    turno_encontrado = next(
        (
            t
            for t in load_turnos_fecha(fecha)
            if t.get("dni_paciente") == dni_paciente and t.get("hora") == hora
        ),
        None,
    )
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
    if turno_encontrado.get("estado") != "recepcionado":
        return jsonify({"error": "El paciente debe estar recepcionado primero"}), 400

    paciente = obtener_paciente(dni_paciente)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    if pago_existe(dni_paciente, fecha, hora):
        return jsonify({"error": "Ya existe un pago registrado para este paciente en este turno"}), 400

    nuevo_pago = insert_pago(
        {
            "dni_paciente": dni_paciente,
            "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
            "monto": monto,
            "fecha": fecha,
            "hora": hora,
            "fecha_registro": datetime.now(timezone_ar).isoformat(),
            "observaciones": observaciones,
            "obra_social": paciente.get("obra_social", ""),
            "tipo_pago": tipo_pago,
        }
    )
    update_turno(
        dni_paciente,
        fecha,
        hora,
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
            "mensaje": "Paciente movido a sala de espera y pago registrado",
            "pago": nuevo_pago,
        }
    )
    

@bp.route("/api/turnos/dia", methods=["GET"], endpoint="obtener_turnos_dia")
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_turnos_dia():
    """Obtener todos los turnos de una fecha específica (por defecto hoy)"""
    fecha = request.args.get("fecha", date.today().isoformat())
    turnos_raw = load_turnos_fecha(fecha)
    pagos = load_pagos_fecha(fecha)
    dnis = {t["dni_paciente"] for t in turnos_raw if t.get("dni_paciente")}
    from consultorio.storage.queries import load_pacientes_por_dnis

    pacientes = load_pacientes_por_dnis(dnis)
    turnos_dia = enriquecer_turnos(turnos_raw, pacientes, pagos)
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
