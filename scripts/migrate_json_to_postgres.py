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
from consultorio.storage import db_storage
from consultorio.storage.db_storage import _normalizar_hora
from consultorio.utils.fechas import normalizar_fecha_nacimiento


def _sanitizar_pacientes(data: list) -> list:
    resultado = []
    for item in data:
        if not isinstance(item, dict) or not item.get("dni"):
            continue
        copia = dict(item)
        copia["dni"] = str(copia["dni"]).strip()[:20]
        fn = normalizar_fecha_nacimiento(copia.get("fecha_nacimiento"))
        if fn:
            copia["fecha_nacimiento"] = fn
        elif copia.get("fecha_nacimiento"):
            copia["fecha_nacimiento"] = str(copia["fecha_nacimiento"]).strip()[:30]
        resultado.append(copia)
    return resultado


def _sanitizar_turnos(data: list) -> list:
    vistos: dict[tuple, dict] = {}
    omitidos = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        dni = str(item.get("dni_paciente", "")).strip()
        fecha = str(item.get("fecha", "")).strip()
        hora = _normalizar_hora(item.get("hora"))
        if not dni or not fecha or not hora:
            omitidos += 1
            continue
        copia = dict(item)
        copia["dni_paciente"] = dni[:20]
        copia["fecha"] = fecha[:30]
        copia["hora"] = hora
        vistos[(dni, fecha, hora)] = copia
    if omitidos:
        print(f"  (turnos: {omitidos} registros omitidos por datos incompletos)")
    return list(vistos.values())


def _sanitizar_pagos(data: list) -> list:
    vistos: dict[int, dict] = {}
    sin_id: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        pago_id = item.get("id")
        if pago_id is None:
            sin_id.append(item)
            continue
        try:
            vistos[int(pago_id)] = item
        except (TypeError, ValueError):
            continue
    resultado = list(vistos.values()) + sin_id
    duplicados = len(data) - len(resultado)
    if duplicados > 0:
        print(f"  (pagos: {duplicados} registros duplicados omitidos por id)")
    return resultado


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


def migrate(data_dir: str | None = None, dry_run: bool = False, only: list[str] | None = None) -> None:
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
    if only:
        invalid = [e for e in only if e not in entities]
        if invalid:
            print(f"Entidades inválidas: {', '.join(invalid)}")
            sys.exit(1)
        entities = only
    summary = {}

    with app.app_context():
        for entity in entities:
            data = load_json_file(paths[entity], entity)
            if entity == "pacientes" and isinstance(data, list):
                data = _sanitizar_pacientes(data)
            if entity == "turnos" and isinstance(data, list):
                data = _sanitizar_turnos(data)
            if entity == "pagos" and isinstance(data, list):
                data = _sanitizar_pagos(data)
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
    parser.add_argument(
        "--only",
        help="Solo importar estas entidades (coma-separadas): usuarios,pacientes,agenda,turnos,historias,pagos",
    )
    args = parser.parse_args()
    only = [e.strip() for e in args.only.split(",")] if args.only else None
    migrate(data_dir=args.data_dir, dry_run=args.dry_run, only=only)


if __name__ == "__main__":
    main()
