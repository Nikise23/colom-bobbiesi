import os

DIAS_AGENDA = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env_file() -> None:
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def use_database() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def get_data_paths() -> dict[str, str]:
    """Rutas de archivos JSON (desarrollo local o disco persistente en Render)."""
    if os.path.exists("/data"):
        base = "/data"
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    names = {
        "historias": "historias_clinicas.json",
        "usuarios": "usuarios.json",
        "pacientes": "pacientes.json",
        "turnos": "turnos.json",
        "agenda": "agenda.json",
        "pagos": "pagos.json",
        "agenda_web": "agenda_web.json",
        "bloqueos_web": "bloqueos_web.json",
    }
    return {key: os.path.join(base, filename) for key, filename in names.items()}


def entity_for_path(path: str, paths: dict[str, str]) -> str | None:
    normalized = os.path.normpath(path)
    for entity, file_path in paths.items():
        if os.path.normpath(file_path) == normalized:
            return entity
    basename = os.path.basename(path)
    for entity, file_path in paths.items():
        if os.path.basename(file_path) == basename:
            return entity
    return None


def public_api_origins() -> list[str]:
    raw = os.environ.get("PUBLIC_API_CORS_ORIGIN", "").strip()
    if not raw:
        return []
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def public_api_key() -> str:
    return os.environ.get("PUBLIC_API_KEY", "").strip()


def public_api_configured() -> bool:
    return bool(public_api_key() and public_api_origins())
