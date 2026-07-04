import copy
import re
from datetime import date, datetime

from consultorio.paths import PACIENTES_FILE, timezone_ar
from consultorio.storage import cargar_json
from consultorio.utils.fechas import calcular_edad, enriquecer_paciente


def enriquecer_turnos(turnos, pacientes, pagos):
    pacientes_por_dni = {p["dni"]: p for p in pacientes if p.get("dni")}
    resultado = []
    for t in turnos:
        turno = copy.deepcopy(t)
        turno["paciente"] = pacientes_por_dni.get(turno.get("dni_paciente"))
        turno["estado"] = turno.get("estado", "sin atender")
        adjuntar_observacion_pago_desde_pagos(turno, pagos)
        if turno.get("fecha"):
            parts = turno["fecha"].split("-")
            if len(parts) >= 3:
                turno["fecha_fmt"] = f"{int(parts[2])}/{int(parts[1])}/{parts[0]}"
            else:
                turno["fecha_fmt"] = turno["fecha"]
        else:
            turno["fecha_fmt"] = ""
        resultado.append(turno)
    return resultado


def calcular_estadisticas_pagos(pagos, fecha_dia, mes_param=None):
    if mes_param is None:
        mes_param = fecha_dia.strftime("%Y-%m")
    pagos_hoy = [p for p in pagos if p["fecha"] == fecha_dia.isoformat()]
    total_dia = sum(p["monto"] for p in pagos_hoy)
    pagos_mes = [p for p in pagos if p["fecha"].startswith(mes_param)]
    total_mes = sum(p["monto"] for p in pagos_mes)
    pagos_efectivo_hoy = [p for p in pagos_hoy if p.get("tipo_pago") == "efectivo"]
    pagos_transferencia_hoy = [p for p in pagos_hoy if p.get("tipo_pago") == "transferencia"]
    pagos_obra_social_hoy = [p for p in pagos_hoy if p.get("tipo_pago") == "obra_social"]
    total_efectivo_hoy = sum(p["monto"] for p in pagos_efectivo_hoy)
    total_transferencia_hoy = sum(p["monto"] for p in pagos_transferencia_hoy)
    total_obra_social_hoy = sum(p["monto"] for p in pagos_obra_social_hoy)
    pagos_por_dia = {}
    pagos_obra_social = 0
    pagos_particulares = 0
    for pago in pagos_mes:
        dia = pago["fecha"]
        if dia not in pagos_por_dia:
            pagos_por_dia[dia] = {"cantidad": 0, "monto": 0, "pacientes": []}
        pagos_por_dia[dia]["cantidad"] += 1
        pagos_por_dia[dia]["monto"] += pago["monto"]
        pagos_por_dia[dia]["pacientes"].append({
            "nombre": pago["nombre_paciente"],
            "monto": pago["monto"],
            "obra_social": pago.get("obra_social", ""),
            "tipo_pago": pago.get("tipo_pago", "efectivo"),
        })
        if pago["monto"] == 0:
            pagos_obra_social += 1
        else:
            pagos_particulares += 1
    return {
        "total_dia": total_dia,
        "total_mes": total_mes,
        "cantidad_pagos_dia": len(pagos_hoy),
        "cantidad_pagos_mes": len(pagos_mes),
        "pagos_obra_social": pagos_obra_social,
        "pagos_particulares": pagos_particulares,
        "fecha": fecha_dia.isoformat(),
        "mes_consultado": mes_param,
        "detalle_por_dia": dict(sorted(pagos_por_dia.items())),
        "pagos_efectivo_hoy": len(pagos_efectivo_hoy),
        "pagos_transferencia_hoy": len(pagos_transferencia_hoy),
        "pagos_obra_social_hoy": len(pagos_obra_social_hoy),
        "total_efectivo_hoy": total_efectivo_hoy,
        "total_transferencia_hoy": total_transferencia_hoy,
        "total_obra_social_hoy": total_obra_social_hoy,
    }


def listar_recepcionados(turnos, pacientes, pagos, fecha):
    pacientes_por_dni = {p["dni"]: p for p in pacientes if p.get("dni")}
    dnis_con_pago = {p["dni_paciente"] for p in pagos if p["fecha"] == fecha}
    resultado = []
    for turno in turnos:
        if turno.get("fecha") != fecha or turno.get("estado") != "recepcionado":
            continue
        if turno["dni_paciente"] in dnis_con_pago:
            continue
        paciente = pacientes_por_dni.get(turno["dni_paciente"])
        if paciente:
            resultado.append({
                "dni": paciente["dni"],
                "nombre": paciente["nombre"],
                "apellido": paciente["apellido"],
                "obra_social": paciente.get("obra_social", ""),
                "celular": paciente.get("celular", ""),
                "hora_turno": turno["hora"],
                "medico": turno["medico"],
                "fecha": turno["fecha"],
                "hora_recepcion": turno.get("hora_recepcion", ""),
            })
    resultado.sort(key=lambda p: p.get("hora_turno", "00:00"))
    return resultado


def listar_sala_espera(turnos, pacientes, pagos, fecha):
    pacientes_por_dni = {p["dni"]: p for p in pacientes if p.get("dni")}
    pagos_por_dni = {p["dni_paciente"]: p for p in pagos if p["fecha"] == fecha}
    resultado = []
    for turno in turnos:
        if turno.get("fecha") != fecha or turno.get("estado") != "sala de espera":
            continue
        paciente = pacientes_por_dni.get(turno["dni_paciente"])
        pago = pagos_por_dni.get(turno["dni_paciente"])
        if paciente:
            resultado.append({
                "dni": paciente["dni"],
                "nombre": paciente["nombre"],
                "apellido": paciente["apellido"],
                "obra_social": paciente.get("obra_social", ""),
                "celular": paciente.get("celular", ""),
                "hora_turno": turno["hora"],
                "medico": turno["medico"],
                "fecha": turno["fecha"],
                "hora_recepcion": turno.get("hora_recepcion", ""),
                "hora_sala_espera": turno.get("hora_sala_espera", ""),
                "monto_pagado": pago.get("monto", 0) if pago else 0,
                "tipo_pago": pago.get("tipo_pago", "obra_social") if pago else "obra_social",
                "observaciones": pago.get("observaciones", "") if pago else "",
            })
    resultado.sort(key=lambda p: p.get("hora_turno", "00:00"))
    return resultado


def normalizar_texto_obs(text, max_len=500):
    if text is None or not isinstance(text, str):
        return ""
    return text.strip()[:max_len]


def adjuntar_observacion_pago_desde_pagos(turno, pagos):
    if turno.get("observacion_pago"):
        return
    if not turno.get("pago_registrado"):
        return
    dni, fecha, hora = turno.get("dni_paciente"), turno.get("fecha"), turno.get("hora")
    if not all([dni, fecha, hora]):
        return
    for p in pagos:
        if p.get("dni_paciente") == dni and p.get("fecha") == fecha and p.get("hora") == hora:
            obs = normalizar_texto_obs(p.get("observaciones", ""))
            if obs:
                turno["observacion_pago"] = obs
            break


def listar_pacientes_dedup():
    pacientes_raw = cargar_json(PACIENTES_FILE)
    vistos = set()
    pacientes = []
    for p in pacientes_raw:
        if p.get("dni") and p["dni"] not in vistos:
            vistos.add(p["dni"])
            pacientes.append(copy.deepcopy(p))
    for paciente in pacientes:
        enriquecer_paciente(paciente)
    pacientes.sort(key=lambda p: p.get("apellido", "").lower())
    return pacientes


def _texto_plano_desde_html(texto):
    if not texto:
        return ""
    return re.sub(r"<[^>]+>", "", str(texto)).replace("\xa0", " ").strip()


def validar_historia(data):
    campos_obligatorios = ["dni", "consulta_medica", "medico"]
    for campo in campos_obligatorios:
        valor = data.get(campo)
        if campo == "consulta_medica":
            if not valor or not _texto_plano_desde_html(valor):
                return False, f"El campo '{campo}' es obligatorio."
            continue
        if not valor or not str(valor).strip():
            return False, f"El campo '{campo}' es obligatorio."

    if not data["dni"].isdigit() or len(data["dni"]) not in [7, 8]:
        return False, "DNI inválido."

    for campo in ["fecha_consulta"]:
        fecha = data.get(campo)
        if fecha:
            try:
                f = datetime.strptime(fecha, "%Y-%m-%d")
                f = f.replace(tzinfo=timezone_ar)
                ahora = datetime.now(timezone_ar)
                if f > ahora:
                    return False, f"La fecha '{campo}' no puede ser futura."
            except ValueError:
                return False, f"Formato de fecha inválido en '{campo}'."

    return True, ""


def agenda_vacia_medico():
    from consultorio.config import DIAS_AGENDA
    return {dia: [] for dia in DIAS_AGENDA}
