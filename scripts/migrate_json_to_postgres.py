#!/usr/bin/env python3
"""Importa archivos JSON a PostgreSQL.

SOLO para bases LOCALES por defecto.
Nunca uses este script contra producción salvo emergencia controlada.

Uso seguro:
  python scripts/migrate_json_to_postgres.py              # dry-run (no escribe)
  python scripts/migrate_json_to_postgres.py --write       # escribe en localhost
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

from consultorio.config import get_data_paths, load_env_file
from consultorio.database import init_db
from consultorio.db_safety import (
    allow_remote_data_migrate,
    database_hostname,
    is_local_database_url,
    normalize_database_url,
    require_local_database,
)
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
    """Carga JSON. Missing/vacío → None (no migrar esa entidad)."""
    if not os.path.exists(path):
        print(f"  {entity}: archivo ausente ({path}) — se omite")
        return None
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if entity == "agenda":
        if not isinstance(data, dict) or not data:
            print(f"  {entity}: vacío o inválido — se omite")
            return None
        return data
    if not isinstance(data, list) or len(data) == 0:
        print(f"  {entity}: lista vacía — se omite (no se toca la BD)")
        return None
    return data


def migrate(
    data_dir: str | None = None,
    write: bool = False,
    only: list[str] | None = None,
    allow_remote: bool = False,
) -> None:
    load_env_file()
    database_url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    if not database_url:
        print("Error: DATABASE_URL no está configurada.")
        print("Ejemplo local: postgresql://usuario:clave@localhost:5432/colom_bobbiesi")
        sys.exit(1)
    os.environ["DATABASE_URL"] = database_url

    host = database_hostname(database_url) or "(sin host)"
    print(f"Destino DATABASE_URL host: {host}")

    if not is_local_database_url(database_url):
        if not allow_remote or not allow_remote_data_migrate():
            print("Error: DATABASE_URL apunta a un servidor remoto.")
            print("Este script solo escribe en localhost.")
            print("Para una emergencia remota (NO recomendado):")
            print('  set ALLOW_REMOTE_DATA_MIGRATE=I_UNDERSTAND')
            print("  python scripts/migrate_json_to_postgres.py --allow-remote --write")
            sys.exit(1)
        print("ADVERTENCIA: migración REMOTA habilitada explícitamente.")
    else:
        # Revalida por claridad en logs
        require_local_database("migrate_json_to_postgres")

    if not write:
        print("Modo dry-run (no se escribe). Para aplicar: agregá --write")

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

    with app.app_context():
        for entity in entities:
            data = load_json_file(paths[entity], entity)
            if data is None:
                continue
            if entity == "pacientes" and isinstance(data, list):
                data = _sanitizar_pacientes(data)
            if entity == "turnos" and isinstance(data, list):
                data = _sanitizar_turnos(data)
            if entity == "pagos" and isinstance(data, list):
                data = _sanitizar_pagos(data)

            count = len(data) if isinstance(data, (list, dict)) else 0
            existing = db_storage.cargar(entity)
            existing_count = (
                len(existing) if isinstance(existing, (list, dict)) else 0
            )
            print(f"  {entity}: JSON={count} BD={existing_count}")

            if not write:
                continue

            db_storage.guardar(entity, data)
            print(f"    → importado")

    if write:
        print("\nMigración completada.")
    else:
        print("\n(dry-run: no se escribió en la base de datos)")


def main():
    parser = argparse.ArgumentParser(
        description="Migrar JSON a PostgreSQL (solo localhost; dry-run por defecto)"
    )
    parser.add_argument(
        "--data-dir",
        help="Directorio con los archivos JSON (por defecto: raíz del proyecto o /data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias de compatibilidad: no escribe (es el comportamiento por defecto)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Confirma escritura en la base (sin esto solo muestra conteos)",
    )
    parser.add_argument(
        "--only",
        help="Solo importar estas entidades (coma-separadas)",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permitir remoto SOLO si ALLOW_REMOTE_DATA_MIGRATE=I_UNDERSTAND",
    )
    args = parser.parse_args()
    only = [e.strip() for e in args.only.split(",")] if args.only else None
    migrate(
        data_dir=args.data_dir,
        write=bool(args.write) and not args.dry_run,
        only=only,
        allow_remote=args.allow_remote,
    )


if __name__ == "__main__":
    main()
