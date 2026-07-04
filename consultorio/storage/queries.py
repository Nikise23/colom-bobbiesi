"""Consultas y escrituras puntuales (evitan cargar tablas completas)."""

from __future__ import annotations

import copy
from datetime import date

from consultorio.config import get_data_paths, use_database
from consultorio.paths import PACIENTES_FILE, PAGOS_FILE, TURNOS_FILE
from consultorio.storage import cargar_json, guardar_json
from consultorio.utils.fechas import enriquecer_paciente, normalizar_fecha_dia

_PATHS = get_data_paths()


def _max_pago_id(pagos: list) -> int:
    return max((int(p.get("id") or 0) for p in pagos), default=0)


def insert_pago(pago: dict) -> dict:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.insert_pago(pago)

    pagos = cargar_json(PAGOS_FILE)
    nuevo = copy.deepcopy(pago)
    nuevo["id"] = _max_pago_id(pagos) + 1
    if nuevo.get("fecha"):
        nuevo["fecha"] = normalizar_fecha_dia(nuevo["fecha"]) or str(nuevo["fecha"]).strip()[:10]
    pagos.append(nuevo)
    guardar_json(PAGOS_FILE, pagos)
    return nuevo


def update_turno(dni_paciente: str, fecha: str, hora: str, campos: dict) -> bool:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.update_turno(dni_paciente, fecha, hora, campos)

    turnos = cargar_json(TURNOS_FILE)
    for turno in turnos:
        if (
            turno.get("dni_paciente") == dni_paciente
            and turno.get("fecha") == fecha
            and turno.get("hora") == hora
        ):
            turno.update(campos)
            guardar_json(TURNOS_FILE, turnos)
            return True
    return False


def load_turnos_fecha(fecha: str) -> list:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_turnos_fecha(fecha)

    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    return [
        t
        for t in cargar_json(TURNOS_FILE)
        if (normalizar_fecha_dia(t.get("fecha")) or str(t.get("fecha", "")).strip()[:10]) == f
    ]


def load_turnos_medico_fecha(medico: str, fecha: str) -> list:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_turnos_medico_fecha(medico, fecha)

    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    return [
        t
        for t in cargar_json(TURNOS_FILE)
        if t.get("medico") == medico
        and (normalizar_fecha_dia(t.get("fecha")) or str(t.get("fecha", "")).strip()[:10]) == f
    ]


def load_turnos_medico_proximos(medico: str, fecha_desde: str, limit: int = 50) -> list:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_turnos_medico_proximos(medico, fecha_desde, limit)

    f = normalizar_fecha_dia(fecha_desde) or str(fecha_desde).strip()[:10]
    estados = {"sin atender", "recepcionado", "sala de espera"}
    turnos = [
        t
        for t in cargar_json(TURNOS_FILE)
        if t.get("medico") == medico
        and (normalizar_fecha_dia(t.get("fecha")) or str(t.get("fecha", "")).strip()[:10]) >= f
        and t.get("estado", "sin atender") in estados
    ]
    turnos.sort(key=lambda t: (t.get("fecha", ""), t.get("hora", "")))
    return turnos[:limit]


def load_pagos_fecha(fecha: str) -> list:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_pagos_fecha(fecha)

    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    return [
        p
        for p in cargar_json(PAGOS_FILE)
        if (normalizar_fecha_dia(p.get("fecha")) or str(p.get("fecha", "")).strip()[:10]) == f
    ]


def load_pagos_mes(mes: str) -> list:
    """mes formato YYYY-MM"""
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_pagos_mes(mes)

    return [p for p in cargar_json(PAGOS_FILE) if str(p.get("fecha", "")).startswith(mes)]


def load_pacientes_liviano() -> list:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_pacientes_liviano()

    vistos = set()
    resultado = []
    for p in cargar_json(PACIENTES_FILE):
        dni = p.get("dni")
        if dni and dni not in vistos:
            vistos.add(dni)
            resultado.append(
                {
                    "dni": dni,
                    "nombre": p.get("nombre", ""),
                    "apellido": p.get("apellido", ""),
                    "obra_social": p.get("obra_social", ""),
                    "celular": p.get("celular", ""),
                    "numero_obra_social": p.get("numero_obra_social", ""),
                }
            )
    resultado.sort(key=lambda x: x.get("apellido", "").lower())
    return resultado


def load_pacientes_por_dnis(dnis: set[str]) -> list:
    if not dnis:
        return []
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.load_pacientes_por_dnis(dnis)

    resultado = []
    for p in cargar_json(PACIENTES_FILE):
        if p.get("dni") in dnis:
            copia = copy.deepcopy(p)
            enriquecer_paciente(copia)
            resultado.append(copia)
    return resultado


def count_turnos_total() -> int:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.count_turnos_total()

    return len(cargar_json(TURNOS_FILE))


def count_turnos_fecha(fecha: str) -> int:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.count_turnos_fecha(fecha)

    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    return sum(
        1
        for t in cargar_json(TURNOS_FILE)
        if (normalizar_fecha_dia(t.get("fecha")) or str(t.get("fecha", "")).strip()[:10]) == f
    )


def listar_atendidos_sin_pago(fecha: str) -> list:
    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    turnos = load_turnos_fecha(f)
    pagos = load_pagos_fecha(f)
    dnis_con_pago = {p.get("dni_paciente") for p in pagos}
    pacientes_map = {p["dni"]: p for p in load_pacientes_liviano()}
    resultado = []
    for turno in turnos:
        if turno.get("estado") != "atendido":
            continue
        dni = turno.get("dni_paciente")
        if not dni or dni in dnis_con_pago:
            continue
        paciente = pacientes_map.get(dni)
        if not paciente:
            continue
        resultado.append(
            {
                "dni": dni,
                "nombre": paciente.get("nombre", ""),
                "apellido": paciente.get("apellido", ""),
                "obra_social": paciente.get("obra_social", ""),
                "hora_turno": turno.get("hora", ""),
                "medico": turno.get("medico", ""),
                "fecha": f,
            }
        )
    resultado.sort(key=lambda x: x.get("hora_turno", "00:00"))
    return resultado


def count_pacientes() -> int:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.count_pacientes()

    vistos = set()
    for p in cargar_json(PACIENTES_FILE):
        if p.get("dni"):
            vistos.add(p["dni"])
    return len(vistos)


def count_turnos_pendientes() -> int:
    pendientes = {"sin atender", "llamado"}
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.count_turnos_estados(pendientes)

    return sum(
        1
        for t in cargar_json(TURNOS_FILE)
        if t.get("estado", "sin atender") in pendientes
    )


def buscar_pacientes_paginado(
    busqueda: str, pagina: int, por_pagina: int
) -> dict:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.buscar_pacientes_paginado(busqueda, pagina, por_pagina)

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
    busqueda = busqueda.strip().lower()
    if busqueda:
        pacientes = [
            p
            for p in pacientes
            if busqueda in p.get("dni", "")
            or busqueda in p.get("apellido", "").lower()
            or busqueda in p.get("nombre", "").lower()
        ]

    total = len(pacientes)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(1, min(pagina, total_paginas))
    inicio = (pagina - 1) * por_pagina
    fin = min(inicio + por_pagina, total)
    return {
        "pacientes": pacientes[inicio:fin],
        "total": total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "por_pagina": por_pagina,
    }


def pago_existe(dni: str, fecha: str, hora: str | None = None) -> bool:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.pago_existe(dni, fecha, hora)

    for p in cargar_json(PAGOS_FILE):
        if p.get("dni_paciente") != dni or p.get("fecha") != fecha:
            continue
        if hora and p.get("hora", "") != hora:
            continue
        return True
    return False


def obtener_paciente(dni: str) -> dict | None:
    if use_database():
        from consultorio.storage import db_storage

        return db_storage.obtener_paciente(dni)

    for p in cargar_json(PACIENTES_FILE):
        if p.get("dni") == dni:
            copia = copy.deepcopy(p)
            enriquecer_paciente(copia)
            return copia
    return None
