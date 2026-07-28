from datetime import date, datetime

from consultorio.paths import timezone_ar


def hoy_ar() -> date:
    """Fecha calendario en Argentina (turnos/pagos del día)."""
    return datetime.now(timezone_ar).date()


def hoy_ar_iso() -> str:
    return hoy_ar().isoformat()


def normalizar_fecha_dia(value: str | None) -> str | None:
    """Normaliza turnos/pagos a YYYY-MM-DD."""
    return normalizar_fecha_nacimiento(value)


def _anio_nacimiento_valido(anio: int) -> bool:
    hoy = hoy_ar()
    return 1900 <= anio <= hoy.year


def normalizar_fecha_nacimiento(value: str | None) -> str | None:
    """Convierte dd/mm/yyyy, yyyy-mm-dd u ISO con hora a yyyy-mm-dd."""
    if not value or not str(value).strip():
        return None
    texto = str(value).strip()
    if "T" in texto:
        texto = texto.split("T", 1)[0]
    elif " " in texto:
        texto = texto.split(" ", 1)[0]
    digits = "".join(ch for ch in texto if ch.isdigit())
    if len(digits) == 8:
        try:
            fecha = datetime.strptime(digits, "%d%m%Y").date()
            return fecha.isoformat() if _anio_nacimiento_valido(fecha.year) else None
        except ValueError:
            pass
    formatos = (
        ("%d/%m/%Y", r"^\d{2}/\d{2}/\d{4}$"),
        ("%Y-%m-%d", r"^\d{4}-\d{2}-\d{2}$"),
        ("%d-%m-%Y", r"^\d{2}-\d{2}-\d{4}$"),
    )
    for fmt, patron in formatos:
        import re

        if not re.fullmatch(patron, texto):
            continue
        try:
            fecha = datetime.strptime(texto, fmt).date()
            return fecha.isoformat() if _anio_nacimiento_valido(fecha.year) else None
        except ValueError:
            continue
    return None


def formatear_fecha_nacimiento(value: str | None) -> str:
    """Convierte yyyy-mm-dd (u otras) a dd/mm/yyyy para mostrar."""
    if not value:
        return ""
    iso = normalizar_fecha_nacimiento(value)
    if not iso:
        return str(value)
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def enriquecer_paciente(paciente: dict) -> dict:
    if paciente.get("fecha_nacimiento"):
        paciente["edad"] = calcular_edad(paciente["fecha_nacimiento"])
        paciente["fecha_nacimiento"] = formatear_fecha_nacimiento(paciente["fecha_nacimiento"])
    return paciente


def calcular_edad(fecha_nacimiento: str | None):
    iso = normalizar_fecha_nacimiento(fecha_nacimiento)
    if not iso:
        return None
    try:
        fecha_nac = datetime.strptime(iso, "%Y-%m-%d").date()
        hoy = hoy_ar()
        return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))
    except ValueError:
        return None
