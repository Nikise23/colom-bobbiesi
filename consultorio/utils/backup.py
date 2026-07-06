"""Generación de respaldos ZIP (desde PostgreSQL o archivos JSON)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from consultorio.config import get_data_paths, use_database
from consultorio.paths import timezone_ar
from consultorio.storage import cargar_json

# (entidad en get_data_paths, nombre dentro del ZIP)
BACKUP_ENTITIES: list[tuple[str, str]] = [
    ("pagos", "pagos.json"),
    ("historias", "historias_clinicas.json"),
    ("turnos", "turnos.json"),
    ("pacientes", "pacientes.json"),
    ("agenda", "agenda.json"),
    ("usuarios", "usuarios.json"),
]


def _cargar_entidad(entity: str, path: str):
    data = cargar_json(path)
    if entity == "agenda":
        return data if isinstance(data, dict) else {}
    return data if isinstance(data, list) else []


def build_backup_zip() -> tuple[io.BytesIO, int]:
    """Arma un ZIP con todos los datos. Devuelve (buffer, cantidad de archivos)."""
    paths = get_data_paths()
    buf = io.BytesIO()
    agregados = 0
    stamp = datetime.now(timezone_ar).isoformat()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "generado": stamp,
            "origen": "postgresql" if use_database() else "json",
            "archivos": [],
        }
        for entity, nombre_en_zip in BACKUP_ENTITIES:
            path = paths.get(entity)
            if not path:
                continue
            data = _cargar_entidad(entity, path)
            zf.writestr(
                nombre_en_zip,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
            manifest["archivos"].append(
                {
                    "archivo": nombre_en_zip,
                    "registros": len(data) if isinstance(data, list) else len(data.keys()),
                }
            )
            agregados += 1
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        agregados += 1

    buf.seek(0)
    return buf, agregados


def backup_zip_filename() -> str:
    stamp = datetime.now(timezone_ar).strftime("%Y%m%d_%H%M")
    return f"backup_consultorio_{stamp}.zip"
