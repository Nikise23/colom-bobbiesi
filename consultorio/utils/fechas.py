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
            return datetime.strptime(digits, "%d%m%Y").date().isoformat()
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt).date().isoformat()
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
