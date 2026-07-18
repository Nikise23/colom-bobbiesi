"""Capa de agenda pública (sitio web): visibilidad, horarios y bloqueos."""

from __future__ import annotations

import re
from datetime import date, datetime

from consultorio.config import DIAS_AGENDA, use_database
from consultorio.paths import (
    AGENDA_FILE,
    AGENDA_WEB_FILE,
    BLOQUEOS_WEB_FILE,
    MEDICOS_WEB_SEED,
)
from consultorio.storage import cargar_json, guardar_json

_HORA_RE = re.compile(r"^(\d{1,2}):([0-5]\d)$")

TIPOS_BLOQUEO = frozenset({"dia", "rango_horas", "semanal"})

DIA_EN_ES = {
    "MONDAY": "LUNES",
    "TUESDAY": "MARTES",
    "WEDNESDAY": "MIERCOLES",
    "THURSDAY": "JUEVES",
    "FRIDAY": "VIERNES",
    "SATURDAY": "SABADO",
}


def normalizar_hora(hora) -> str | None:
    if hora is None:
        return None
    texto = str(hora).strip()
    if not texto:
        return None
    match = _HORA_RE.match(texto)
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _dias_vacios() -> dict:
    return {dia: [] for dia in DIAS_AGENDA}


def _normalizar_dias(dias) -> dict:
    out = _dias_vacios()
    if not isinstance(dias, dict):
        return out
    for dia in DIAS_AGENDA:
        horas = dias.get(dia) or []
        if not isinstance(horas, list):
            continue
        seen = set()
        limpios = []
        for h in horas:
            hn = normalizar_hora(h)
            if hn and hn not in seen:
                seen.add(hn)
                limpios.append(hn)
        out[dia] = sorted(limpios)
    return out


def load_agenda_web() -> dict:
    data = cargar_json(AGENDA_WEB_FILE)
    if not isinstance(data, dict):
        return {}
    result = {}
    for medico, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        result[medico] = {
            "visible": bool(cfg.get("visible", False)),
            "dias": _normalizar_dias(cfg.get("dias")),
        }
    return result


def load_bloqueos_web() -> list:
    data = cargar_json(BLOQUEOS_WEB_FILE)
    if not isinstance(data, list):
        return []
    return [b for b in data if isinstance(b, dict)]


def ensure_seed_from_internal() -> None:
    """Si no hay config web, copia agenda interna de Marianela/Francisco (JSON o DB)."""
    web = load_agenda_web()
    if web:
        return
    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict):
        return
    seeded = {}
    for medico in MEDICOS_WEB_SEED:
        dias = agenda.get(medico)
        if not isinstance(dias, dict):
            continue
        seeded[medico] = {"visible": True, "dias": _normalizar_dias(dias)}
    if seeded:
        guardar_json(AGENDA_WEB_FILE, seeded)


def listar_config_completa() -> dict:
    """Mapa por médico de la agenda interna + su config web (defaults si falta)."""
    ensure_seed_from_internal()
    agenda = cargar_json(AGENDA_FILE)
    web = load_agenda_web()
    result = {}
    if not isinstance(agenda, dict):
        return result
    for medico in sorted(agenda.keys()):
        cfg = web.get(medico) or {"visible": False, "dias": _dias_vacios()}
        result[medico] = {
            "visible": bool(cfg.get("visible", False)),
            "dias": _normalizar_dias(cfg.get("dias")),
        }
    return result


def get_medico_web(medico: str) -> dict | None:
    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict) or medico not in agenda:
        return None
    web = load_agenda_web()
    cfg = web.get(medico) or {"visible": False, "dias": _dias_vacios()}
    return {
        "medico": medico,
        "visible": bool(cfg.get("visible", False)),
        "dias": _normalizar_dias(cfg.get("dias")),
    }


def validar_dias_subset(medico: str, dias: dict) -> str | None:
    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict) or medico not in agenda:
        return "Médico no encontrado en la agenda interna"
    interna = agenda[medico] or {}
    for dia, horas in dias.items():
        if dia not in DIAS_AGENDA:
            return f"Día inválido: {dia}"
        permitidas = set(interna.get(dia) or [])
        for h in horas:
            if h not in permitidas:
                return (
                    f"El horario {h} de {dia} no está en la agenda interna de {medico}. "
                    "Agregalo primero en Agenda interna o usá Copiar."
                )
    return None


def save_medico_web(medico: str, visible: bool, dias: dict) -> tuple[dict | None, str | None]:
    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict) or medico not in agenda:
        return None, "Médico no encontrado en la agenda interna"

    dias_norm = _normalizar_dias(dias)
    err = validar_dias_subset(medico, dias_norm)
    if err:
        return None, err

    if use_database():
        from consultorio.storage import db_storage

        db_storage.upsert_medico_web(medico, visible, dias_norm)
    else:
        web = load_agenda_web()
        web[medico] = {"visible": bool(visible), "dias": dias_norm}
        guardar_json(AGENDA_WEB_FILE, web)

    _invalidar_cache_publica()
    return {"medico": medico, "visible": bool(visible), "dias": dias_norm}, None


def copiar_desde_interna(medico: str, visible: bool | None = None) -> tuple[dict | None, str | None]:
    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict) or medico not in agenda:
        return None, "Médico no encontrado en la agenda interna"
    actual = get_medico_web(medico) or {"visible": False}
    vis = bool(actual["visible"]) if visible is None else bool(visible)
    return save_medico_web(medico, vis, agenda[medico])


def listar_medicos_visibles() -> list[str]:
    ensure_seed_from_internal()
    web = load_agenda_web()
    return sorted(
        m for m, cfg in web.items() if cfg.get("visible") and any(cfg.get("dias", {}).values())
    )


def _agenda_web_medico(medico: str) -> tuple[dict | None, str | None]:
    ensure_seed_from_internal()
    web = load_agenda_web()
    cfg = web.get(medico)
    if not cfg or not cfg.get("visible"):
        return None, "Médico no encontrado"
    return cfg.get("dias") or _dias_vacios(), None


def fecha_a_dia_semana(fecha_str: str) -> tuple[date | None, str | None, str | None]:
    try:
        fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return None, None, "Formato de fecha inválido (usar YYYY-MM-DD)"
    dia_es = DIA_EN_ES.get(fecha_dt.strftime("%A").upper())
    if not dia_es:
        return None, None, "No hay atención los domingos"
    return fecha_dt, dia_es, None


def _hora_en_rango(hora: str, desde: str | None, hasta: str | None) -> bool:
    """True si la hora está bloqueada por el rango [desde, hasta). Todo el día si ambos None."""
    if not desde and not hasta:
        return True
    if desde and hasta:
        return desde <= hora < hasta
    if desde:
        return hora >= desde
    return hora < hasta


def bloqueo_aplica(bloqueo: dict, fecha_str: str, dia_es: str, hora: str) -> bool:
    if not bloqueo.get("activo", True):
        return False
    tipo = bloqueo.get("tipo")
    hd = normalizar_hora(bloqueo.get("hora_desde")) if bloqueo.get("hora_desde") else None
    hh = normalizar_hora(bloqueo.get("hora_hasta")) if bloqueo.get("hora_hasta") else None

    if tipo == "dia":
        if bloqueo.get("fecha") != fecha_str:
            return False
        return _hora_en_rango(hora, hd, hh)

    if tipo == "rango_horas":
        if bloqueo.get("fecha") != fecha_str:
            return False
        if not hd or not hh:
            return True
        return _hora_en_rango(hora, hd, hh)

    if tipo == "semanal":
        if (bloqueo.get("dia_semana") or "").upper() != dia_es:
            return False
        return _hora_en_rango(hora, hd, hh)

    return False


def filtrar_bloqueos(
    medico: str, fecha_str: str, dia_es: str, horarios: list[str]
) -> list[str]:
    bloqueos = [
        b
        for b in load_bloqueos_web()
        if b.get("medico") == medico and b.get("activo", True)
    ]
    if not bloqueos:
        return horarios
    return [
        h
        for h in horarios
        if not any(bloqueo_aplica(b, fecha_str, dia_es, h) for b in bloqueos)
    ]


def _filtrar_horarios_futuros(fecha_dt: date, horarios: list[str]) -> list[str]:
    from consultorio.paths import timezone_ar

    if fecha_dt != date.today():
        return horarios
    ahora = datetime.now(timezone_ar).strftime("%H:%M")
    return [h for h in horarios if h >= ahora]


def horarios_web_libres(
    medico: str,
    fecha_str: str,
    horas_ocupadas: set[str],
    filtrar_pasados: bool = True,
) -> tuple[list[str], str | None]:
    fecha_dt, dia_es, err = fecha_a_dia_semana(fecha_str)
    if err:
        return [], err

    dias, err = _agenda_web_medico(medico)
    if err:
        return [], err

    todos = list(dias.get(dia_es, []))
    libres = [h for h in todos if h not in horas_ocupadas]
    libres = filtrar_bloqueos(medico, fecha_str, dia_es, libres)
    if filtrar_pasados:
        libres = _filtrar_horarios_futuros(fecha_dt, libres)
    return libres, None


def validar_bloqueo_payload(data: dict) -> tuple[dict | None, str | None]:
    medico = (data.get("medico") or "").strip()
    tipo = (data.get("tipo") or "").strip()
    if not medico:
        return None, "El campo 'medico' es obligatorio"
    if tipo not in TIPOS_BLOQUEO:
        return None, "tipo inválido (dia, rango_horas o semanal)"

    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict) or medico not in agenda:
        return None, "Médico no encontrado en la agenda interna"

    motivo = data.get("motivo")
    motivo = str(motivo).strip()[:200] if motivo else None
    hd = normalizar_hora(data.get("hora_desde")) if data.get("hora_desde") else None
    hh = normalizar_hora(data.get("hora_hasta")) if data.get("hora_hasta") else None
    if data.get("hora_desde") and not hd:
        return None, "hora_desde inválida (HH:MM)"
    if data.get("hora_hasta") and not hh:
        return None, "hora_hasta inválida (HH:MM)"
    if hd and hh and hd >= hh:
        return None, "hora_desde debe ser anterior a hora_hasta"

    item = {
        "medico": medico,
        "tipo": tipo,
        "motivo": motivo,
        "activo": bool(data.get("activo", True)),
        "hora_desde": hd,
        "hora_hasta": hh,
    }

    if tipo in ("dia", "rango_horas"):
        fecha = (data.get("fecha") or "").strip()
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            return None, "fecha inválida (YYYY-MM-DD)"
        item["fecha"] = fecha
        if tipo == "rango_horas" and (not hd or not hh):
            return None, "rango_horas requiere hora_desde y hora_hasta"
    else:
        dia = (data.get("dia_semana") or "").strip().upper()
        if dia not in DIAS_AGENDA:
            return None, "dia_semana inválido"
        item["dia_semana"] = dia

    return item, None


def crear_bloqueo(data: dict) -> tuple[dict | None, str | None]:
    item, err = validar_bloqueo_payload(data)
    if err:
        return None, err

    if use_database():
        from consultorio.storage import db_storage

        created = db_storage.insert_bloqueo_web(item)
    else:
        bloqueos = load_bloqueos_web()
        next_id = max((int(b.get("id") or 0) for b in bloqueos), default=0) + 1
        item["id"] = next_id
        bloqueos.append(item)
        guardar_json(BLOQUEOS_WEB_FILE, bloqueos)
        created = item

    _invalidar_cache_publica()
    return created, None


def eliminar_bloqueo(bloqueo_id: int) -> tuple[bool, str | None]:
    if use_database():
        from consultorio.storage import db_storage

        ok = db_storage.delete_bloqueo_web(bloqueo_id)
        if not ok:
            return False, "Bloqueo no encontrado"
    else:
        bloqueos = load_bloqueos_web()
        nuevos = [b for b in bloqueos if int(b.get("id") or 0) != int(bloqueo_id)]
        if len(nuevos) == len(bloqueos):
            return False, "Bloqueo no encontrado"
        guardar_json(BLOQUEOS_WEB_FILE, nuevos)

    _invalidar_cache_publica()
    return True, None


def listar_bloqueos(medico: str | None = None) -> list:
    items = load_bloqueos_web()
    if medico:
        items = [b for b in items if b.get("medico") == medico]
    return sorted(items, key=lambda b: (b.get("medico", ""), b.get("id") or 0))


def _invalidar_cache_publica() -> None:
    try:
        from consultorio.utils import turnos_publicos as tp

        tp._RANGO_CACHE.clear()
    except Exception:
        pass
