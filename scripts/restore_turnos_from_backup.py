"""Restore turnos from ZIP backup. INSERT/UPDATE only — never deletes."""
from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from consultorio import create_app
from consultorio.extensions import db
from consultorio.models import Turno
from consultorio.storage.db_storage import _normalizar_hora

BACKUP = Path(r"C:\Users\nicfe\Downloads\backup_consultorio_20260704_1229.zip")


def main() -> None:
    with zipfile.ZipFile(BACKUP) as zf:
        items = json.loads(zf.read("turnos.json"))
    print(f"backup turnos: {len(items)}")

    app = create_app()
    with app.app_context():
        before = Turno.query.count()
        print(f"turnos antes: {before}")

        existing = {
            (t.dni_paciente, t.fecha, t.hora): t for t in Turno.query.all()
        }
        pending: dict = {}
        inserted = updated = 0

        for item in items:
            if not isinstance(item, dict):
                continue
            hora = _normalizar_hora(item.get("hora"))
            dni = item.get("dni_paciente")
            fecha = item.get("fecha")
            if not dni or not fecha or not hora:
                continue
            key = (dni, fecha, hora)
            row = existing.get(key) or pending.get(key)
            if row is None:
                row = Turno(
                    medico=item.get("medico", ""),
                    fecha=fecha,
                    hora=hora,
                    dni_paciente=dni,
                )
                db.session.add(row)
                pending[key] = row
                inserted += 1
            else:
                updated += 1
            row.medico = item.get("medico", row.medico or "")
            row.estado = item.get("estado", "sin atender")
            row.observacion = item.get("observacion")
            row.hora_recepcion = _normalizar_hora(item.get("hora_recepcion")) or None
            row.hora_sala_espera = _normalizar_hora(item.get("hora_sala_espera")) or None
            row.pago_registrado = item.get("pago_registrado")
            row.monto_pagado = item.get("monto_pagado")
            row.observacion_pago = item.get("observacion_pago")
            row.borrador_consulta = item.get("borrador_consulta")
            row.borrador_fecha_consulta = item.get("borrador_fecha_consulta")
            row.borrador_actualizado = item.get("borrador_actualizado")

        db.session.commit()
        after = Turno.query.count()
        print(f"inserted={inserted} updated={updated}")
        print(f"turnos final: {after}")


if __name__ == "__main__":
    main()
