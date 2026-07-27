import os
import time
from datetime import date, datetime, timedelta

from consultorio.paths import PACIENTES_FILE, TURNOS_FILE, timezone_ar
from consultorio.storage import cargar_json, guardar_json
from consultorio.utils import agenda_web as aw
from consultorio.utils.email import avisar_turno_online, validar_email
from consultorio.utils.fechas import normalizar_fecha_nacimiento

DIA_EN_ES = {
    "MONDAY": "LUNES",
    "TUESDAY": "MARTES",
    "WEDNESDAY": "MIERCOLES",
    "THURSDAY": "JUEVES",
    "FRIDAY": "VIERNES",
    "SATURDAY": "SABADO",
}

ESTADOS_CANCELABLES = {"sin atender", "recepcionado", "sala de espera", "llamado"}

_RANGO_CACHE: dict[tuple[str, str, str], tuple[float, dict]] = {}


def max_dias_reserva() -> int:
    try:
        return max(1, int(os.environ.get("PUBLIC_API_MAX_DIAS", "60")))
    except ValueError:
        return 60


def max_dias_por_request() -> int:
    try:
        return min(31, max(1, int(os.environ.get("PUBLIC_API_MAX_DIAS_RANGO", "31"))))
    except ValueError:
        return 31


def cache_segundos_rango() -> int:
    try:
        return max(0, int(os.environ.get("PUBLIC_API_CACHE_SECONDS", "45")))
    except ValueError:
        return 45


def parse_fecha(fecha_str: str) -> tuple[date | None, str | None]:
    try:
        return datetime.strptime(fecha_str, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Formato de fecha inválido (usar YYYY-MM-DD)"


def fecha_a_dia_agenda(fecha_str: str) -> tuple[date | None, str | None, str | None]:
    fecha_dt, err = parse_fecha(fecha_str)
    if err:
        return None, None, err

    dia_semana = fecha_dt.strftime("%A").upper()
    dia_es = DIA_EN_ES.get(dia_semana)
    if not dia_es:
        return None, None, "No hay atención los domingos"
    return fecha_dt, dia_es, None


def validar_fecha_reservable(fecha_dt: date) -> str | None:
    hoy = date.today()
    if fecha_dt < hoy:
        return "No se pueden reservar turnos en fechas pasadas"
    max_dias = max_dias_reserva()
    if fecha_dt > hoy + timedelta(days=max_dias):
        return f"Solo se pueden reservar turnos hasta {max_dias} días hacia adelante"
    return None


def validar_rango_fechas(desde_dt: date, hasta_dt: date) -> str | None:
    if hasta_dt < desde_dt:
        return "La fecha 'hasta' no puede ser anterior a 'desde'"

    dias_en_rango = (hasta_dt - desde_dt).days + 1
    if dias_en_rango > max_dias_por_request():
        return (
            f"El rango no puede superar {max_dias_por_request()} días por request "
            f"(solicitados: {dias_en_rango})"
        )

    err = validar_fecha_reservable(desde_dt)
    if err:
        return err
    return validar_fecha_reservable(hasta_dt)


def iter_dias_habiles(desde_dt: date, hasta_dt: date):
    actual = desde_dt
    while actual <= hasta_dt:
        if actual.weekday() != 6:
            yield actual
        actual += timedelta(days=1)


def horarios_ocupados(turnos: list, medico: str, fecha: str) -> set[str]:
    return {
        t["hora"]
        for t in turnos
        if t.get("medico") == medico and t.get("fecha") == fecha
    }


def ocupados_por_fecha_en_rango(
    turnos: list, medico: str, desde: str, hasta: str
) -> dict[str, set[str]]:
    resultado: dict[str, set[str]] = {}
    for turno in turnos:
        if turno.get("medico") != medico:
            continue
        fecha = turno.get("fecha", "")
        if fecha < desde or fecha > hasta:
            continue
        hora = turno.get("hora")
        if hora:
            resultado.setdefault(fecha, set()).add(hora)
    return resultado


def filtrar_horarios_futuros(fecha_dt: date, horarios: list[str]) -> list[str]:
    if fecha_dt != date.today():
        return horarios
    ahora = datetime.now(timezone_ar).strftime("%H:%M")
    return [h for h in horarios if h >= ahora]


def slots_disponibles(medico: str, fecha_str: str) -> tuple[list[str], str | None]:
    fecha_dt, _, err = fecha_a_dia_agenda(fecha_str)
    if err:
        return [], err

    err = validar_fecha_reservable(fecha_dt)
    if err:
        return [], err

    turnos = cargar_json(TURNOS_FILE)
    ocupados = horarios_ocupados(turnos, medico, fecha_str)
    return aw.horarios_web_libres(medico, fecha_str, ocupados)


def slots_disponibles_rango(
    medico: str, desde_str: str, hasta_str: str
) -> tuple[dict | None, str | None]:
    desde_dt, err = parse_fecha(desde_str)
    if err:
        return None, err
    hasta_dt, err = parse_fecha(hasta_str)
    if err:
        return None, err

    err = validar_rango_fechas(desde_dt, hasta_dt)
    if err:
        return None, err

    aw.ensure_seed_from_internal()
    web = aw.load_agenda_web()
    cfg = web.get(medico)
    if not cfg or not cfg.get("visible"):
        return None, "Médico no encontrado"

    turnos = cargar_json(TURNOS_FILE)
    ocupados_map = ocupados_por_fecha_en_rango(
        turnos, medico, desde_str, hasta_str
    )

    dias = []
    total_dias_con_turno = 0
    for fecha_dt in iter_dias_habiles(desde_dt, hasta_dt):
        fecha_iso = fecha_dt.isoformat()
        libres, err_dia = aw.horarios_web_libres(
            medico,
            fecha_iso,
            ocupados_map.get(fecha_iso, set()),
        )
        if err_dia:
            libres = []
        if libres:
            total_dias_con_turno += 1
        dias.append(
            {
                "fecha": fecha_iso,
                "horarios_disponibles": libres,
                "total": len(libres),
            }
        )

    return (
        {
            "medico": medico,
            "desde": desde_str,
            "hasta": hasta_str,
            "dias": dias,
            "total_dias_con_turno": total_dias_con_turno,
        },
        None,
    )


def slots_disponibles_rango_cached(
    medico: str, desde_str: str, hasta_str: str
) -> tuple[dict | None, str | None]:
    ttl = cache_segundos_rango()
    clave = (medico, desde_str, hasta_str)
    if ttl > 0 and clave in _RANGO_CACHE:
        ts, payload = _RANGO_CACHE[clave]
        if time.time() - ts < ttl:
            return payload, None

    payload, err = slots_disponibles_rango(medico, desde_str, hasta_str)
    if not err and ttl > 0:
        _RANGO_CACHE[clave] = (time.time(), payload)
    return payload, err


def listar_medicos() -> list[str]:
    return aw.listar_medicos_visibles()


def listar_medicos_detalle() -> list[dict]:
    return aw.listar_medicos_con_agenda()


def turno_publico(turno: dict) -> dict:
    return {
        "medico": turno.get("medico"),
        "fecha": turno.get("fecha"),
        "hora": turno.get("hora"),
        "estado": turno.get("estado", "sin atender"),
    }


def paciente_existe(dni: str) -> tuple[bool | None, str | None]:
    """Devuelve (existe, error). Solo indica existencia; no expone datos del paciente."""
    err = _validar_dni(dni)
    if err:
        return None, err
    pacientes = cargar_json(PACIENTES_FILE)
    existe = any(p.get("dni") == dni for p in pacientes)
    return existe, None


def listar_turnos_paciente(dni: str, solo_futuros: bool = True) -> list[dict]:
    turnos = cargar_json(TURNOS_FILE)
    hoy = date.today().isoformat()
    ahora = datetime.now(timezone_ar).strftime("%H:%M")
    resultado = []
    for t in turnos:
        if t.get("dni_paciente") != dni:
            continue
        if solo_futuros:
            fecha = t.get("fecha", "")
            if fecha < hoy:
                continue
            if fecha == hoy and t.get("hora", "00:00") < ahora:
                continue
        resultado.append(turno_publico(t))
    resultado.sort(key=lambda x: (x.get("fecha", ""), x.get("hora", "")))
    return resultado


def _validar_dni(dni: str) -> str | None:
    if not dni or not dni.isdigit() or len(dni) not in (7, 8):
        return "DNI inválido (7 u 8 dígitos)"
    return None


def _obtener_o_crear_paciente(data: dict) -> tuple[dict | None, str | None, bool]:
    dni = str(data.get("dni", "")).strip()
    err = _validar_dni(dni)
    if err:
        return None, err, False

    pacientes = cargar_json(PACIENTES_FILE)
    existente = next((p for p in pacientes if p.get("dni") == dni), None)
    if existente:
        return existente, None, False

    campos = [
        "nombre",
        "apellido",
        "celular",
        "obra_social",
        "fecha_nacimiento",
    ]
    for campo in campos:
        if not data.get(campo) or not str(data[campo]).strip():
            return None, f"Paciente nuevo: el campo '{campo}' es obligatorio", False

    fecha_nac = normalizar_fecha_nacimiento(data.get("fecha_nacimiento"))
    if not fecha_nac:
        return None, "Fecha de nacimiento inválida. Use dd/mm/aaaa o YYYY-MM-DD.", False

    nuevo = {
        "dni": dni,
        "nombre": str(data["nombre"]).strip(),
        "apellido": str(data["apellido"]).strip(),
        "celular": str(data["celular"]).strip(),
        "obra_social": str(data["obra_social"]).strip(),
        "numero_obra_social": str(data.get("numero_obra_social") or "").strip(),
        "fecha_nacimiento": fecha_nac,
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
    }
    pacientes.append(nuevo)
    guardar_json(PACIENTES_FILE, pacientes)
    return nuevo, None, True


def reservar_turno(data: dict) -> tuple[dict, int]:
    medico = (data.get("medico") or "").strip()
    fecha = (data.get("fecha") or "").strip()
    hora = (data.get("hora") or "").strip()

    if not all([medico, fecha, hora]):
        return {"error": "Los campos 'medico', 'fecha' y 'hora' son obligatorios"}, 400

    email_paciente, err_email = validar_email(data.get("email"))
    if err_email:
        return {"error": err_email}, 400

    libres, err = slots_disponibles(medico, fecha)
    if err:
        return {"error": err}, 400
    if hora not in libres:
        return {"error": "El horario no está disponible"}, 409

    paciente, err, creado = _obtener_o_crear_paciente(data)
    if err:
        return {"error": err}, 400

    obs_raw = data.get("observacion")
    observacion = (obs_raw.strip()[:500] if isinstance(obs_raw, str) else "") or ""

    turnos = cargar_json(TURNOS_FILE)
    turno_nuevo = {
        "medico": medico,
        "hora": hora,
        "fecha": fecha,
        "dni_paciente": paciente["dni"],
        "estado": "sin atender",
        "observacion": observacion,
        "origen": "api_publica",
    }
    turnos.append(turno_nuevo)
    guardar_json(TURNOS_FILE, turnos)
    _RANGO_CACHE.clear()

    try:
        avisar_turno_online(
            medico=medico,
            fecha=fecha,
            hora=hora,
            paciente=paciente,
            paciente_nuevo=creado,
            email_paciente=email_paciente,
        )
    except Exception:
        # Defensa extra: el aviso nunca debe afectar la reserva
        pass

    return {
        "mensaje": "Turno reservado correctamente",
        "paciente_nuevo": creado,
        "turno": turno_publico(turno_nuevo),
    }, 201


def cancelar_turno(dni: str, fecha: str, hora: str) -> tuple[dict, int]:
    err = _validar_dni(dni)
    if err:
        return {"error": err}, 400
    if not fecha or not hora:
        return {"error": "Los campos 'fecha' y 'hora' son obligatorios"}, 400

    turnos = cargar_json(TURNOS_FILE)
    for i, turno in enumerate(turnos):
        if (
            turno.get("dni_paciente") == dni
            and turno.get("fecha") == fecha
            and turno.get("hora") == hora
        ):
            estado = turno.get("estado", "sin atender")
            if estado not in ESTADOS_CANCELABLES:
                return {
                    "error": f"No se puede cancelar un turno en estado '{estado}'"
                }, 400
            turnos.pop(i)
            guardar_json(TURNOS_FILE, turnos)
            _RANGO_CACHE.clear()
            return {"mensaje": "Turno cancelado correctamente"}, 200

    return {"error": "Turno no encontrado"}, 404
