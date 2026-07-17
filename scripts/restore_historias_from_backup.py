"""Restore historias_clinicas from JSON by id. Upsert only — never deletes extras."""
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
from consultorio.models import HistoriaClinica

BACKUP = Path(r"C:\Backups\colom-bobbiesi\historias_clinicas.json")


def main() -> None:
    items = json.loads(BACKUP.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("El backup no es una lista JSON")
    print(f"archivo historias: {len(items)}")

    ids = [item.get("id") for item in items if isinstance(item, dict)]
    print(f"con id: {sum(1 for i in ids if i is not None)} unique ids: {len(set(ids))}")

    app = create_app()
    with app.app_context():
        before = HistoriaClinica.query.count()
        print(f"historias antes: {before}")

        existing = {h.id: h for h in HistoriaClinica.query.all()}
        inserted = updated = skipped = 0

        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            dni = str(item.get("dni") or "").strip()
            if not dni:
                skipped += 1
                continue
            try:
                hid = int(item["id"])
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue

            row = existing.get(hid)
            if row is None:
                row = HistoriaClinica(id=hid)
                db.session.add(row)
                existing[hid] = row
                inserted += 1
            else:
                updated += 1

            row.dni = dni[:20]
            row.fecha_consulta = item.get("fecha_consulta") or None
            row.medico = item.get("medico") or None
            row.consulta_medica = item.get("consulta_medica") or ""
            row.fecha_creacion = item.get("fecha_creacion") or None

        db.session.commit()
        db.session.execute(
            text(
                "SELECT setval("
                "pg_get_serial_sequence('historias_clinicas', 'id'), "
                "COALESCE((SELECT MAX(id) FROM historias_clinicas), 1))"
            )
        )
        db.session.commit()

        print(f"inserted={inserted} updated={updated} skipped={skipped}")
        print(f"historias final: {HistoriaClinica.query.count()}")


if __name__ == "__main__":
    main()
