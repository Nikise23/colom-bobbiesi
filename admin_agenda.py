#!/usr/bin/env python3
"""CLI para gestionar la agenda médica (JSON o PostgreSQL según DATABASE_URL)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask

from consultorio.config import DIAS_AGENDA, get_data_paths
from consultorio.database import init_db
from consultorio.storage import cargar_json, guardar_json

AGENDA_FILE = get_data_paths()["agenda"]


def _with_app_context(fn):
    app = Flask(__name__)
    init_db(app)
    with app.app_context():
        fn()


def cargar_agenda():
    data = cargar_json(AGENDA_FILE)
    return data if isinstance(data, dict) else {}


def guardar_agenda(agenda):
    guardar_json(AGENDA_FILE, agenda)


def input_horarios(dia):
    print(f"\nIngrese los horarios para {dia} separados por coma (ej: 14:05, 14:10, ...), o deje vacío para ninguno:")
    val = input(f"Horarios para {dia}: ").strip()
    return [h.strip() for h in val.split(",") if h.strip()] if val else []


def agregar_medico():
    agenda = cargar_agenda()
    nombre = input("Nombre completo del médico a agregar: ").strip()
    if not nombre:
        print("❌ Nombre no puede estar vacío.")
        return
    if nombre in agenda:
        print(f"❌ El médico '{nombre}' ya existe en la agenda.")
        return
    horarios = {dia: input_horarios(dia) for dia in DIAS_AGENDA}
    agenda[nombre] = horarios
    guardar_agenda(agenda)
    print(f"✅ Médico '{nombre}' agregado a la agenda.")


def borrar_medico():
    agenda = cargar_agenda()
    nombre = input("Nombre completo del médico a borrar: ").strip()
    if nombre not in agenda:
        print(f"❌ El médico '{nombre}' no existe en la agenda.")
        return
    confirm = input(f"¿Seguro que quieres borrar a '{nombre}'? (s/N): ").strip().lower()
    if confirm == "s":
        del agenda[nombre]
        guardar_agenda(agenda)
        print(f"✅ Médico '{nombre}' borrado de la agenda.")
    else:
        print("Operación cancelada.")


def menu():
    while True:
        print("\n=== ADMINISTRACIÓN DE AGENDA ===")
        print("1. Agregar médico y horarios")
        print("2. Borrar médico")
        print("3. Ver agenda actual")
        print("0. Salir")
        op = input("Opción: ").strip()
        if op == "1":
            _with_app_context(agregar_medico)
        elif op == "2":
            _with_app_context(borrar_medico)
        elif op == "3":
            _with_app_context(lambda: _mostrar_agenda())
        elif op == "0":
            print("¡Hasta luego!")
            break
        else:
            print("Opción inválida.")


def _mostrar_agenda():
    agenda = cargar_agenda()
    for med, dias in agenda.items():
        print(f"\n{med}:")
        for dia, hs in dias.items():
            print(f"  {dia}: {', '.join(hs) if hs else '-'}")


if __name__ == "__main__":
    menu()
