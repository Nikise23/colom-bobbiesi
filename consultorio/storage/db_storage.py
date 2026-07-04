import re

from sqlalchemy import func

from consultorio.config import DIAS_AGENDA
from consultorio.extensions import db
from consultorio.models import (
    AgendaHorario,
    HistoriaClinica,
    Paciente,
    Pago,
    Turno,
    Usuario,
)
from consultorio.utils.fechas import enriquecer_paciente, normalizar_fecha_dia


def _agenda_vacia_medico() -> dict:
    return {dia: [] for dia in DIAS_AGENDA}


def load_usuarios() -> list:
    return [u.to_dict() for u in Usuario.query.order_by(Usuario.usuario).all()]


def save_usuarios(data: list) -> None:
    if not isinstance(data, list):
        return
    incoming = {item["usuario"]: item for item in data if item.get("usuario")}
    existing = {u.usuario: u for u in Usuario.query.all()}

    for usuario, item in incoming.items():
        row = existing.get(usuario)
        if row is None:
            db.session.add(Usuario(
                usuario=usuario,
                contrasena=item["contrasena"],
                rol=item.get("rol", "medico"),
            ))
        else:
            row.contrasena = item["contrasena"]
            row.rol = item.get("rol", row.rol)

    for usuario, row in existing.items():
        if usuario not in incoming:
            db.session.delete(row)

    db.session.commit()


def _fecha_nacimiento_db(value) -> str | None:
    from consultorio.utils.fechas import normalizar_fecha_nacimiento

    normalizada = normalizar_fecha_nacimiento(value)
    if normalizada:
        return normalizada
    if value is None:
        return None
    texto = str(value).strip()
    return texto[:30] if texto else None


_HORA_RE = re.compile(r"(\d{1,2}:\d{2})")


def _normalizar_hora(hora) -> str:
    if hora is None:
        return ""
    texto = str(hora).strip()
    if not texto:
        return ""
    match = _HORA_RE.search(texto)
    if match:
        horas, minutos = match.group(1).split(":", 1)
        return f"{int(horas):02d}:{minutos}"
    return texto[:10]


def load_pacientes() -> list:
    return [p.to_dict() for p in Paciente.query.order_by(Paciente.fecha_registro).all()]


def save_pacientes(data: list) -> None:
    if not isinstance(data, list):
        return
    incoming = {item["dni"]: item for item in data if item.get("dni")}
    existing = {p.dni: p for p in Paciente.query.all()}

    for dni, item in incoming.items():
        row = existing.get(dni)
        if row is None:
            db.session.add(Paciente(
                dni=dni,
                nombre=item.get("nombre", ""),
                apellido=item.get("apellido", ""),
                fecha_nacimiento=_fecha_nacimiento_db(item.get("fecha_nacimiento")),
                obra_social=item.get("obra_social"),
                numero_obra_social=item.get("numero_obra_social"),
                celular=item.get("celular"),
                fecha_registro=item.get("fecha_registro"),
            ))
        else:
            row.nombre = item.get("nombre", row.nombre)
            row.apellido = item.get("apellido", row.apellido)
            row.fecha_nacimiento = _fecha_nacimiento_db(
                item.get("fecha_nacimiento", row.fecha_nacimiento)
            )
            row.obra_social = item.get("obra_social", row.obra_social)
            row.numero_obra_social = item.get("numero_obra_social", row.numero_obra_social)
            row.celular = item.get("celular", row.celular)
            row.fecha_registro = item.get("fecha_registro", row.fecha_registro)

    for dni, row in existing.items():
        if dni not in incoming:
            db.session.delete(row)

    db.session.commit()


def load_turnos() -> list:
    return [t.to_dict() for t in Turno.query.order_by(Turno.fecha, Turno.hora).all()]


def save_turnos(data: list) -> None:
    if not isinstance(data, list):
        return

    incoming_keys = set()
    existing = {
        (t.dni_paciente, t.fecha, t.hora): t
        for t in Turno.query.all()
    }
    pending: dict[tuple, Turno] = {}

    for item in data:
        hora = _normalizar_hora(item.get("hora"))
        key = (item.get("dni_paciente"), item.get("fecha"), hora)
        if not all(key):
            continue
        incoming_keys.add(key)
        row = existing.get(key) or pending.get(key)
        if row is None:
            row = Turno(
                medico=item.get("medico", ""),
                fecha=item["fecha"],
                hora=hora,
                dni_paciente=item["dni_paciente"],
            )
            db.session.add(row)
            pending[key] = row
        row.medico = item.get("medico", row.medico if row.medico else "")
        row.estado = item.get("estado", "sin atender")
        row.observacion = item.get("observacion")
        row.hora_recepcion = _normalizar_hora(item.get("hora_recepcion")) or None
        row.hora_sala_espera = _normalizar_hora(item.get("hora_sala_espera")) or None
        row.pago_registrado = item.get("pago_registrado")
        row.monto_pagado = item.get("monto_pagado")
        row.observacion_pago = item.get("observacion_pago")
        row.borrador_consulta = item.get("borrador_consulta")
        row.borrador_fecha_consulta = item.get("borrador_fecha_consulta")
        row.borrador_actualizado = item.get("borrador_actualizado")

    for key, row in existing.items():
        if key not in incoming_keys:
            db.session.delete(row)

    db.session.commit()


def load_agenda() -> dict:
    agenda: dict = {}
    for row in AgendaHorario.query.order_by(
        AgendaHorario.medico, AgendaHorario.dia, AgendaHorario.hora
    ).all():
        medico_data = agenda.setdefault(row.medico, _agenda_vacia_medico())
        if row.dia not in medico_data:
            medico_data[row.dia] = []
        medico_data[row.dia].append(row.hora)
    return agenda


def save_agenda(data: dict) -> None:
    if not isinstance(data, dict):
        return

    incoming_keys = set()
    existing = {
        (row.medico, row.dia, row.hora): row
        for row in AgendaHorario.query.all()
    }

    for medico, dias in data.items():
        if not isinstance(dias, dict):
            continue
        for dia, horas in dias.items():
            if not isinstance(horas, list):
                continue
            for hora in horas:
                hora_norm = _normalizar_hora(hora)
                if not hora_norm:
                    continue
                key = (medico, dia, hora_norm)
                incoming_keys.add(key)
                if key not in existing:
                    db.session.add(AgendaHorario(medico=medico, dia=dia, hora=hora_norm))

    for key, row in existing.items():
        if key not in incoming_keys:
            db.session.delete(row)

    db.session.commit()


def load_historias() -> list:
    return [h.to_dict() for h in HistoriaClinica.query.order_by(HistoriaClinica.id).all()]


def save_historias(data: list) -> None:
    if not isinstance(data, list):
        return

    incoming_ids = set()
    existing = {h.id: h for h in HistoriaClinica.query.all()}
    pending: dict[int, HistoriaClinica] = {}

    for item in data:
        historia_id = item.get("id")
        if historia_id is None:
            max_id = db.session.query(db.func.max(HistoriaClinica.id)).scalar() or 0
            historia_id = max_id + 1
        incoming_ids.add(historia_id)
        row = existing.get(historia_id) or pending.get(historia_id)
        if row is None:
            row = HistoriaClinica(id=historia_id)
            db.session.add(row)
            pending[historia_id] = row
        row.dni = item.get("dni", row.dni or "")
        row.fecha_consulta = item.get("fecha_consulta")
        row.medico = item.get("medico")
        row.consulta_medica = item.get("consulta_medica")
        row.fecha_creacion = item.get("fecha_creacion")

    for historia_id, row in existing.items():
        if historia_id not in incoming_ids:
            db.session.delete(row)

    db.session.commit()


def load_pagos() -> list:
    return [p.to_dict() for p in Pago.query.order_by(Pago.id).all()]


def save_pagos(data: list) -> None:
    if not isinstance(data, list):
        return

    incoming_ids = set()
    existing = {p.id: p for p in Pago.query.all()}
    pending: dict[int, Pago] = {}

    for item in data:
        pago_id = item.get("id")
        if pago_id is None:
            max_id = db.session.query(db.func.max(Pago.id)).scalar() or 0
            pago_id = max_id + 1
        incoming_ids.add(pago_id)
        row = existing.get(pago_id) or pending.get(pago_id)
        if row is None:
            row = Pago(id=pago_id)
            db.session.add(row)
            pending[pago_id] = row
        row.dni_paciente = item.get("dni_paciente", row.dni_paciente or "")
        row.nombre_paciente = item.get("nombre_paciente")
        row.monto = item.get("monto", 0)
        row.fecha = item.get("fecha", row.fecha or "")
        row.hora = _normalizar_hora(item.get("hora")) or None
        row.tipo_pago = item.get("tipo_pago")
        row.obra_social = item.get("obra_social")
        row.observaciones = item.get("observaciones")
        row.fecha_registro = item.get("fecha_registro")

    for pago_id, row in existing.items():
        if pago_id not in incoming_ids:
            db.session.delete(row)

    db.session.commit()


def load_turnos_fecha(fecha: str) -> list:
    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    rows = (
        Turno.query.filter(func.substr(Turno.fecha, 1, 10) == f)
        .order_by(Turno.hora)
        .all()
    )
    return [t.to_dict() for t in rows]


def load_pagos_fecha(fecha: str) -> list:
    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    rows = (
        Pago.query.filter(func.substr(Pago.fecha, 1, 10) == f)
        .order_by(Pago.id)
        .all()
    )
    return [p.to_dict() for p in rows]


def load_pagos_mes(mes: str) -> list:
    rows = (
        Pago.query.filter(Pago.fecha.startswith(mes))
        .order_by(Pago.fecha, Pago.id)
        .all()
    )
    return [p.to_dict() for p in rows]


def load_pacientes_liviano() -> list:
    rows = Paciente.query.order_by(Paciente.apellido).all()
    return [
        {
            "dni": p.dni,
            "nombre": p.nombre,
            "apellido": p.apellido,
            "obra_social": p.obra_social or "",
            "celular": p.celular or "",
            "numero_obra_social": p.numero_obra_social or "",
        }
        for p in rows
    ]


def load_pacientes_por_dnis(dnis: set[str]) -> list:
    if not dnis:
        return []
    rows = Paciente.query.filter(Paciente.dni.in_(dnis)).all()
    resultado = []
    for row in rows:
        data = row.to_dict()
        enriquecer_paciente(data)
        resultado.append(data)
    resultado.sort(key=lambda p: p.get("apellido", "").lower())
    return resultado


def obtener_paciente(dni: str) -> dict | None:
    row = Paciente.query.filter_by(dni=dni).first()
    if not row:
        return None
    data = row.to_dict()
    enriquecer_paciente(data)
    return data


def count_pacientes() -> int:
    return Paciente.query.count()


def count_turnos_estados(estados: set[str]) -> int:
    return Turno.query.filter(Turno.estado.in_(list(estados))).count()


def buscar_pacientes_paginado(busqueda: str, pagina: int, por_pagina: int) -> dict:
    query = Paciente.query
    busqueda = busqueda.strip()
    if busqueda:
        like = f"%{busqueda.lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(Paciente.apellido).like(like),
                db.func.lower(Paciente.nombre).like(like),
                Paciente.dni.like(f"%{busqueda}%"),
            )
        )
    query = query.order_by(Paciente.apellido)
    total = query.count()
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(1, min(pagina, total_paginas))
    rows = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    pacientes = []
    for row in rows:
        data = row.to_dict()
        enriquecer_paciente(data)
        pacientes.append(data)
    return {
        "pacientes": pacientes,
        "total": total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "por_pagina": por_pagina,
    }


def next_pago_id() -> int:
    max_id = db.session.query(db.func.max(Pago.id)).scalar() or 0
    return int(max_id) + 1


def insert_pago(item: dict) -> dict:
    pago_id = item.get("id") or next_pago_id()
    fecha = normalizar_fecha_dia(item.get("fecha")) or str(item.get("fecha", "")).strip()[:10]
    row = Pago(
        id=pago_id,
        dni_paciente=item["dni_paciente"],
        nombre_paciente=item.get("nombre_paciente"),
        monto=item.get("monto", 0),
        fecha=fecha,
        hora=_normalizar_hora(item.get("hora")) or None,
        tipo_pago=item.get("tipo_pago"),
        obra_social=item.get("obra_social"),
        observaciones=item.get("observaciones"),
        fecha_registro=item.get("fecha_registro"),
    )
    db.session.add(row)
    db.session.commit()
    return row.to_dict()


def pago_existe(dni: str, fecha: str, hora: str | None = None) -> bool:
    f = normalizar_fecha_dia(fecha) or str(fecha).strip()[:10]
    query = Pago.query.filter(
        Pago.dni_paciente == dni,
        func.substr(Pago.fecha, 1, 10) == f,
    )
    if hora:
        query = query.filter_by(hora=_normalizar_hora(hora))
    return query.first() is not None


def update_turno(dni_paciente: str, fecha: str, hora: str, campos: dict) -> bool:
    hora_norm = _normalizar_hora(hora)
    row = Turno.query.filter_by(
        dni_paciente=dni_paciente, fecha=fecha, hora=hora_norm
    ).first()
    if not row:
        return False
    for key, value in campos.items():
        if not hasattr(row, key):
            continue
        if key in ("hora_recepcion", "hora_sala_espera", "hora") and value:
            value = _normalizar_hora(value) or value
        setattr(row, key, value)
    db.session.commit()
    return True


LOADERS = {
    "usuarios": load_usuarios,
    "pacientes": load_pacientes,
    "turnos": load_turnos,
    "agenda": load_agenda,
    "historias": load_historias,
    "pagos": load_pagos,
}

SAVERS = {
    "usuarios": save_usuarios,
    "pacientes": save_pacientes,
    "turnos": save_turnos,
    "agenda": save_agenda,
    "historias": save_historias,
    "pagos": save_pagos,
}

DEFAULTS = {
    "usuarios": [],
    "pacientes": [],
    "turnos": [],
    "agenda": {},
    "historias": [],
    "pagos": [],
}


def cargar(entity: str):
    loader = LOADERS.get(entity)
    if loader is None:
        return []
    return loader()


def guardar(entity: str, data) -> None:
    saver = SAVERS.get(entity)
    if saver is None:
        return
    saver(data)
