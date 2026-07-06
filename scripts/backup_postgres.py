#!/usr/bin/env python3
"""
Respaldo local del consultorio (PostgreSQL en Render).

Genera dos archivos en la carpeta de salida:
  - backup_consultorio_YYYYMMDD_HHMM.zip   (JSON legible, mismo formato que el botón del admin)
  - backup_consultorio_YYYYMMDD_HHMM.dump  (pg_dump, si está instalado)

Uso:
  python scripts/backup_postgres.py --output-dir "C:\\Backups\\colom-bobbiesi"

Requiere en .env (o variable de entorno):
  DATABASE_URL=postgresql://...

Para pg_dump en Windows: instalá PostgreSQL client tools o agregá pg_dump al PATH.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consultorio.config import load_env_file
from consultorio.paths import timezone_ar
from consultorio.utils.backup import build_backup_zip


def _stamp() -> str:
    return datetime.now(timezone_ar).strftime("%Y%m%d_%H%M")


def _pg_dump(database_url: str, dest: Path) -> bool:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print("  [aviso] pg_dump no encontrado en PATH; se omitió el .dump")
        print("          Instalá PostgreSQL client tools o usá solo el ZIP JSON.")
        return False

    cmd = [
        pg_dump,
        database_url,
        "-F",
        "c",
        "-f",
        str(dest),
        "--no-owner",
        "--no-acl",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  OK dump PostgreSQL: {dest.name}")
        return True
    except subprocess.CalledProcessError as exc:
        print(f"  [error] pg_dump falló: {exc.stderr or exc}")
        return False


def _export_zip(dest: Path) -> bool:
    from consultorio import create_app

    app = create_app()
    with app.app_context():
        buf, agregados = build_backup_zip()
        if agregados == 0:
            print("  [error] No hay datos para exportar.")
            return False
        dest.write_bytes(buf.getvalue())
        print(f"  OK ZIP ({agregados} archivos): {dest.name}")
        return True


def _purge_old_backups(output_dir: Path, keep: int) -> None:
    if keep <= 0:
        return
    patterns = ("backup_consultorio_*.zip", "backup_consultorio_*.dump")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(output_dir.glob(pattern))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep * 2 :]:  # keep per type roughly
        try:
            old.unlink()
            print(f"  Eliminado backup antiguo: {old.name}")
        except OSError as exc:
            print(f"  [aviso] No se pudo borrar {old.name}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup local del consultorio (PostgreSQL)")
    parser.add_argument(
        "--output-dir",
        required=True,
        help=r'Carpeta destino, ej: C:\Backups\colom-bobbiesi',
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=8,
        help="Cantidad de backups recientes a conservar por tipo (default: 8)",
    )
    parser.add_argument(
        "--skip-dump",
        action="store_true",
        help="Solo generar ZIP JSON, sin pg_dump",
    )
    args = parser.parse_args()

    load_env_file()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("ERROR: Definí DATABASE_URL en .env o en variables de entorno.")
        print("       En Render: Database → Connections → External Database URL")
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = _stamp()
    print(f"Backup consultorio — {stamp}")
    print(f"Carpeta: {output_dir}")

    zip_path = output_dir / f"backup_consultorio_{stamp}.zip"
    dump_path = output_dir / f"backup_consultorio_{stamp}.dump"

    ok_zip = _export_zip(zip_path)
    ok_dump = False
    if not args.skip_dump:
        ok_dump = _pg_dump(database_url, dump_path)

    if not ok_zip and not ok_dump:
        return 1

    _purge_old_backups(output_dir, args.keep)
    print("Listo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
