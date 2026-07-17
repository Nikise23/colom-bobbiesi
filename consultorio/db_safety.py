"""Protecciones para no destruir datos de producción por error."""

from __future__ import annotations

import os
from urllib.parse import urlparse


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def normalize_database_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def database_hostname(url: str) -> str:
    return (urlparse(normalize_database_url(url)).hostname or "").lower()


def is_local_database_url(url: str | None = None) -> bool:
    url = normalize_database_url(url or os.environ.get("DATABASE_URL", ""))
    if not url:
        return False
    return database_hostname(url) in LOCAL_HOSTS


def require_local_database(action: str = "esta operación") -> str:
    """Exige DATABASE_URL en localhost. Devuelve la URL normalizada o termina el proceso."""
    url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    if not url:
        raise SystemExit(
            f"Error: DATABASE_URL no está definida. No se puede ejecutar {action}."
        )
    if not is_local_database_url(url):
        host = database_hostname(url) or "(sin host)"
        raise SystemExit(
            f"Error: DATABASE_URL apunta a un servidor remoto ({host}).\n"
            f"Por seguridad, {action} solo se permite contra localhost.\n"
            "Usá una Postgres local, o restaurá producción solo con scripts/restore_*.py "
            "y backups ZIP (nunca con migrate/setup)."
        )
    os.environ["DATABASE_URL"] = url
    return url


def allow_remote_data_migrate() -> bool:
    """Migración remota solo con confirmación explícita por variable de entorno."""
    return os.environ.get("ALLOW_REMOTE_DATA_MIGRATE", "").strip() == "I_UNDERSTAND"


def refuse_empty_replace(entity: str, incoming_count: int, existing_count: int) -> None:
    if incoming_count == 0 and existing_count > 0:
        raise ValueError(
            f"Refusing to overwrite {entity} with an empty list "
            f"({existing_count} existing rows). "
            "This protects against accidental wipe from empty JSON."
        )


def refuse_mass_delete(
    entity: str,
    incoming_count: int,
    existing_count: int,
    *,
    min_existing: int = 100,
    max_delete_ratio: float = 0.95,
) -> None:
    """Bloquea reemplazos que borrarían casi toda la tabla de un golpe."""
    if existing_count < min_existing or incoming_count >= existing_count:
        return
    if os.environ.get("ALLOW_DESTRUCTIVE_REPLACE", "").strip() == "1":
        return
    delete_ratio = 1.0 - (incoming_count / existing_count)
    if delete_ratio >= max_delete_ratio:
        raise ValueError(
            f"Refusing mass delete on {entity}: "
            f"incoming={incoming_count}, existing={existing_count} "
            f"({delete_ratio:.0%} would be removed). "
            "Set ALLOW_DESTRUCTIVE_REPLACE=1 only if this is intentional."
        )
