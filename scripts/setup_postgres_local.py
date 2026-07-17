#!/usr/bin/env python3
"""
Configura PostgreSQL local: crea la BD, aplica migraciones e importa JSON.

Uso:
  1. Iniciá el servicio PostgreSQL
  2. Editá .env con DATABASE_URL=...@localhost...
  3. python scripts/setup_postgres_local.py

Por seguridad, este script rechaza servidores remotos.
"""

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from consultorio.db_safety import require_local_database


def load_env_file():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def parse_db_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?")[0]


def create_database_if_needed(url: str) -> None:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    db_name = parse_db_name(url)
    admin_url = url.rsplit("/", 1)[0] + "/postgres"

    print(f"Conectando a {admin_url.split('@')[-1]}...")
    conn = psycopg2.connect(admin_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    if cur.fetchone():
        print(f"  Base '{db_name}' ya existe.")
    else:
        cur.execute(f'CREATE DATABASE "{db_name}"')
        print(f"  Base '{db_name}' creada.")
    cur.close()
    conn.close()


def run_alembic():
    print("\nAplicando migraciones (alembic upgrade head)...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def run_json_migration():
    print("\nImportando datos JSON (solo si los archivos tienen contenido)...")
    result = subprocess.run(
        [
            sys.executable,
            os.path.join(ROOT, "scripts", "migrate_json_to_postgres.py"),
            "--write",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        sys.exit(result.returncode)


def verify_data():
    from flask import Flask

    from consultorio.database import init_db
    from consultorio.storage import cargar_json
    from consultorio.paths import USUARIOS_FILE, AGENDA_FILE

    app = Flask(__name__)
    init_db(app)
    with app.app_context():
        usuarios = cargar_json(USUARIOS_FILE)
        agenda = cargar_json(AGENDA_FILE)
        medicos = len(agenda) if isinstance(agenda, dict) else 0
        print("\nVerificación OK:")
        print(f"  - Usuarios en PostgreSQL: {len(usuarios)}")
        print(f"  - Médicos en agenda: {medicos}")


def main():
    parser = argparse.ArgumentParser(
        description="Crear y poblar una base PostgreSQL local desde los JSON."
    )
    parser.parse_args()

    load_env_file()
    url = require_local_database("setup_postgres_local")
    os.environ["DATABASE_URL"] = url

    try:
        create_database_if_needed(url)
    except Exception as e:
        print(f"\nError de conexión: {e}")
        print("\n--- ¿PostgreSQL no está corriendo? ---")
        print("Opción A — Servicios de Windows (como administrador):")
        print('  Win+R → services.msc → buscá "postgresql" → Iniciar')
        print("\nOpción B — PowerShell como administrador:")
        print("  net start postgresql")
        print("\nOpción C — pgAdmin: conectate al servidor local; si falla, el servicio está detenido.")
        sys.exit(1)

    run_alembic()
    run_json_migration()
    verify_data()
    print("\nListo. Iniciá la app con: python app.py")


if __name__ == "__main__":
    main()
