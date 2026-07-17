"""Restore pacientes from ZIP backup + fill gaps from pagos/historias/turnos.

Safe: INSERT/UPDATE only. Never deletes. Does not touch other tables.
"""
from __future__ import annotations

import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from consultorio import create_app
from consultorio.extensions import db
from consultorio.models import Paciente
from consultorio.storage.db_storage import _fecha_nacimiento_db

BACKUP = Path(r"C:\Users\nicfe\Downloads\backup_consultorio_20260704_1229.zip")
TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def split_nombre_completo(nombre_completo: str) -> tuple[str, str]:
    texto = " ".join((nombre_completo or "").strip().split())
    if not texto:
        return ("Sin nombre", "Sin apellido")
    parts = texto.split(" ")
    if len(parts) == 1:
        return (parts[0], "-")
    # Convención habitual: último token = apellido
    return (" ".join(parts[:-1]), parts[-1])


def upsert_pacientes(items: list[dict], *, source: str) -> tuple[int, int]:
    """Insert or update by DNI. Never deletes. Returns (inserted, updated)."""
    inserted = updated = 0
    existing = {p.dni: p for p in Paciente.query.all()}

    for item in items:
        dni = str(item.get("dni") or "").strip()
        if not dni:
            continue
        nombre = (item.get("nombre") or "").strip() or "Sin nombre"
        apellido = (item.get("apellido") or "").strip() or "Sin apellido"
        row = existing.get(dni)
        if row is None:
            db.session.add(
                Paciente(
                    dni=dni,
                    nombre=nombre,
                    apellido=apellido,
                    fecha_nacimiento=_fecha_nacimiento_db(item.get("fecha_nacimiento")),
                    obra_social=item.get("obra_social") or None,
                    numero_obra_social=item.get("numero_obra_social") or None,
                    celular=item.get("celular") or None,
                    fecha_registro=item.get("fecha_registro")
                    or datetime.now(TZ).isoformat(),
                )
            )
            inserted += 1
        else:
            # Solo completar vacíos / actualizar si viene del backup completo
            if source == "backup":
                row.nombre = nombre
                row.apellido = apellido
                if item.get("fecha_nacimiento"):
                    row.fecha_nacimiento = _fecha_nacimiento_db(item.get("fecha_nacimiento"))
                if item.get("obra_social") is not None:
                    row.obra_social = item.get("obra_social") or row.obra_social
                if item.get("numero_obra_social") is not None:
                    row.numero_obra_social = (
                        item.get("numero_obra_social") or row.numero_obra_social
                    )
                if item.get("celular") is not None:
                    row.celular = item.get("celular") or row.celular
                if item.get("fecha_registro"):
                    row.fecha_registro = item.get("fecha_registro")
            else:
                # reconstrucción: no pisar datos ya presentes
                if (not row.nombre or row.nombre == "Sin nombre") and nombre != "Sin nombre":
                    row.nombre = nombre
                if (not row.apellido or row.apellido in ("Sin apellido", "-")) and apellido not in (
                    "Sin apellido",
                    "-",
                ):
                    row.apellido = apellido
                if not row.obra_social and item.get("obra_social"):
                    row.obra_social = item.get("obra_social")
                if not row.numero_obra_social and item.get("numero_obra_social"):
                    row.numero_obra_social = item.get("numero_obra_social")
                if not row.celular and item.get("celular"):
                    row.celular = item.get("celular")
            updated += 1

    db.session.commit()
    return inserted, updated


def load_backup_pacientes() -> list[dict]:
    with zipfile.ZipFile(BACKUP) as zf:
        data = json.loads(zf.read("pacientes.json"))
    if not isinstance(data, list):
        raise SystemExit("pacientes.json del backup no es una lista")
    return data


def reconstruct_missing() -> list[dict]:
    existing_dnis = {p.dni for p in Paciente.query.all()}
    live_dnis = {
        r[0]
        for r in db.session.execute(
            text(
                """
                SELECT dni_paciente FROM turnos
                UNION
                SELECT dni_paciente FROM pagos
                UNION
                SELECT dni FROM historias_clinicas
                """
            )
        ).fetchall()
        if r[0]
    }
    missing = sorted(live_dnis - existing_dnis)
    if not missing:
        return []

    # Mejor fila de pagos por DNI (más reciente con nombre)
    pago_rows = db.session.execute(
        text(
            """
            SELECT DISTINCT ON (dni_paciente)
                dni_paciente, nombre_paciente, obra_social
            FROM pagos
            WHERE dni_paciente = ANY(:dnis)
            ORDER BY dni_paciente,
                     CASE WHEN nombre_paciente IS NOT NULL AND nombre_paciente <> '' THEN 0 ELSE 1 END,
                     id DESC
            """
        ),
        {"dnis": missing},
    ).fetchall()
    pagos_by_dni = {r[0]: r for r in pago_rows}

    rebuilt: list[dict] = []
    now = datetime.now(TZ).isoformat()
    for dni in missing:
        pago = pagos_by_dni.get(dni)
        nombre_completo = (pago[1] if pago else "") or ""
        obra = (pago[2] if pago else "") or ""
        nombre, apellido = split_nombre_completo(nombre_completo)
        rebuilt.append(
            {
                "dni": dni,
                "nombre": nombre,
                "apellido": apellido,
                "obra_social": obra,
                "fecha_registro": now,
                "_from_pago": bool(nombre_completo),
            }
        )
    return rebuilt


def main() -> None:
    if not BACKUP.exists():
        raise SystemExit(f"No existe backup: {BACKUP}")

    app = create_app()
    with app.app_context():
        before = Paciente.query.count()
        print(f"pacientes antes: {before}")

        backup_items = load_backup_pacientes()
        print(f"backup pacientes: {len(backup_items)}")
        ins, upd = upsert_pacientes(backup_items, source="backup")
        print(f"backup applied: inserted={ins} updated={upd}")
        print(f"pacientes tras backup: {Paciente.query.count()}")

        rebuilt = reconstruct_missing()
        from_pago = sum(1 for x in rebuilt if x.get("_from_pago"))
        print(f"faltantes a reconstruir: {len(rebuilt)} (con nombre en pagos: {from_pago})")
        if rebuilt:
            # quitar meta
            clean = [{k: v for k, v in x.items() if not k.startswith("_")} for x in rebuilt]
            ins2, upd2 = upsert_pacientes(clean, source="reconstruct")
            print(f"reconstruct applied: inserted={ins2} updated={upd2}")

        after = Paciente.query.count()
        print(f"pacientes final: {after}")

        # cobertura
        live = {
            r[0]
            for r in db.session.execute(
                text(
                    """
                    SELECT dni_paciente FROM turnos
                    UNION
                    SELECT dni_paciente FROM pagos
                    UNION
                    SELECT dni FROM historias_clinicas
                    """
                )
            ).fetchall()
            if r[0]
        }
        have = {p.dni for p in Paciente.query.all()}
        still_missing = live - have
        print(f"DNIs live cubiertos: {len(live & have)}/{len(live)}")
        print(f"aún sin paciente: {len(still_missing)}")


if __name__ == "__main__":
    main()
