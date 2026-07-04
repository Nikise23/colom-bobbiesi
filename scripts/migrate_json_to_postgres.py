#!/usr/bin/env python3
"""Importa los archivos JSON existentes a PostgreSQL."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

from consultorio.config import get_data_paths
from consultorio.database import init_db
from consultorio.storage import db_storage, json_storage


def load_json_file(path: str, entity: str):
    if not os.path.exists(path):
        return db_storage.DEFAULTS[entity]
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if entity == "agenda" and not isinstance(data, dict):
        return {}
    if entity != "agenda" and not isinstance(data, list):
        return []
    return data


def migrate(data_dir: str | None = None, dry_run: bool = False) -> None:
    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL no está configurada.")
        print("Ejemplo: postgresql://usuario:clave@localhost:5432/colom_bobbiesi")
        sys.exit(1)

    paths = get_data_paths()
    if data_dir:
        paths = {
            key: os.path.join(data_dir, os.path.basename(path))
            for key, path in paths.items()
        }

    app = Flask(__name__)
    init_db(app)

    entities = ["usuarios", "pacientes", "agenda", "turnos", "historias", "pagos"]
    summary = {}

    with app.app_context():
        for entity in entities:
            data = load_json_file(paths[entity], entity)
            summary[entity] = len(data) if isinstance(data, (list, dict)) else 0
            if dry_run:
                continue
            db_storage.guardar(entity, data)
            print(f"  {entity}: {summary[entity]} registros importados")

    print("\nResumen de migración:")
    for entity in entities:
        data = load_json_file(paths[entity], entity)
        if entity == "agenda":
            count = len(data) if isinstance(data, dict) else 0
            label = "médicos en agenda"
        else:
            count = len(data) if isinstance(data, list) else 0
            label = "registros"
        print(f"  - {entity}: {count} {label}")

    if dry_run:
        print("\n(dry-run: no se escribió en la base de datos)")
    else:
        print("\nMigración completada.")


def main():
    parser = argparse.ArgumentParser(description="Migrar JSON a PostgreSQL")
    parser.add_argument(
        "--data-dir",
        help="Directorio con los archivos JSON (por defecto: raíz del proyecto o /data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar conteos sin escribir en la base",
    )
    args = parser.parse_args()
    migrate(data_dir=args.data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
