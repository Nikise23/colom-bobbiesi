#!/usr/bin/env python3
"""Elimina turnos vencidos (JSON o PostgreSQL según DATABASE_URL)."""

import os
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask

from consultorio.config import get_data_paths
from consultorio.database import init_db
from consultorio.storage import cargar_json, guardar_json

TURNOS_FILE = get_data_paths()["turnos"]
BACKUP = "turnos_backup.json"


def main():
    app = Flask(__name__)
    init_db(app)

    with app.app_context():
        if os.path.exists(TURNOS_FILE) and not os.environ.get("DATABASE_URL"):
            shutil.copy2(TURNOS_FILE, BACKUP)
            print(f"Backup creado: {BACKUP}")

        turnos = cargar_json(TURNOS_FILE)
        if not isinstance(turnos, list):
            turnos = []

        ahora = datetime.now()
        turnos_filtrados = []
        eliminados = []

        for t in turnos:
            fecha_hora_str = f"{t.get('fecha', '')} {t.get('hora', '00:00')}"
            try:
                fecha_hora = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
            except Exception:
                turnos_filtrados.append(t)
                continue
            if t.get("estado", "").lower() == "sin atender" and fecha_hora < ahora - timedelta(hours=24):
                eliminados.append(t)
            else:
                turnos_filtrados.append(t)

        guardar_json(TURNOS_FILE, turnos_filtrados)

        print(f"Turnos eliminados: {len(eliminados)}")
        if eliminados:
            for t in eliminados:
                print(f"- {t.get('fecha')} {t.get('hora')} | {t.get('medico')} | {t.get('dni_paciente')} | {t.get('estado')}")
        else:
            print("No se eliminaron turnos.")


if __name__ == "__main__":
    main()
