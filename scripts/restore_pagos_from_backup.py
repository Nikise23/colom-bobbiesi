"""Restore pagos from JSON backup. Upsert by id only — never deletes."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from consultorio import create_app
from consultorio.extensions import db
from consultorio.models import Pago
from consultorio.storage.db_storage import _normalizar_hora

BACKUP = Path(r"C:\Backups\colom-bobbiesi\pagos.json")


def main() -> None:
    items = json.loads(BACKUP.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("El backup no es una lista JSON")
    print(f"archivo pagos: {len(items)}")

    app = create_app()
    with app.app_context():
        before = Pago.query.count()
        print(f"pagos antes: {before}")

        existing = {p.id: p for p in Pago.query.all()}
        inserted = updated = skipped = 0

        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            dni = str(item.get("dni_paciente") or "").strip()
            fecha = str(item.get("fecha") or "").strip()
            if not dni or not fecha:
                skipped += 1
                continue
            try:
                pid = int(item["id"])
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue

            row = existing.get(pid)
            if row is None:
                row = Pago(id=pid)
                db.session.add(row)
                existing[pid] = row
                inserted += 1
            else:
                updated += 1

            row.dni_paciente = dni[:20]
            row.nombre_paciente = item.get("nombre_paciente")
            row.monto = item.get("monto", 0)
            row.fecha = fecha[:30]
            row.hora = _normalizar_hora(item.get("hora")) or None
            row.tipo_pago = item.get("tipo_pago")
            row.obra_social = item.get("obra_social")
            row.observaciones = item.get("observaciones")
            row.fecha_registro = item.get("fecha_registro")

        db.session.commit()
        db.session.execute(
            text(
                "SELECT setval("
                "pg_get_serial_sequence('pagos', 'id'), "
                "COALESCE((SELECT MAX(id) FROM pagos), 1))"
            )
        )
        db.session.commit()

        print(f"inserted={inserted} updated={updated} skipped={skipped}")
        print(f"pagos final: {Pago.query.count()}")


if __name__ == "__main__":
    main()
