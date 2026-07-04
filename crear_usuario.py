#!/usr/bin/env python3
"""CLI para gestionar usuarios (JSON o PostgreSQL según DATABASE_URL)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from werkzeug.security import generate_password_hash

from consultorio.config import get_data_paths
from consultorio.database import init_db
from consultorio.storage import cargar_json, guardar_json

USUARIOS_FILE = get_data_paths()["usuarios"]


def _with_app_context(fn):
    app = Flask(__name__)
    init_db(app)
    with app.app_context():
        fn()


def cargar_usuarios():
    return cargar_json(USUARIOS_FILE)


def guardar_usuarios(usuarios):
    guardar_json(USUARIOS_FILE, usuarios)


def input_no_vacio(mensaje):
    while True:
        dato = input(mensaje).strip()
        if dato:
            return dato
        print("❌ El campo no puede quedar vacío.")


def crear_usuario():
    print("\n--- Crear nuevo usuario ---")
    usuario = input_no_vacio("Nombre de usuario: ")

    while True:
        contrasena = input_no_vacio("Contraseña: ")
        confirmar = input_no_vacio("Confirmar contraseña: ")
        if contrasena == confirmar:
            break
        print("❌ Las contraseñas no coinciden. Intentá de nuevo.")

    while True:
        rol = input_no_vacio("Rol (medico / secretaria / administrador): ").lower()
        if rol in ("medico", "secretaria", "administrador"):
            break
        print("❌ Rol inválido. Debe ser 'medico', 'secretaria' o 'administrador'.")

    usuarios = cargar_usuarios()
    if any(u["usuario"] == usuario for u in usuarios):
        print("❌ Ese usuario ya existe.")
        return

    usuarios.append({
        "usuario": usuario,
        "contrasena": generate_password_hash(contrasena),
        "rol": rol,
    })
    guardar_usuarios(usuarios)
    print(f"✅ Usuario '{usuario}' creado con rol '{rol}'.")


def eliminar_usuario():
    print("\n--- Eliminar usuario ---")
    usuarios = cargar_usuarios()
    if not usuarios:
        print("No hay usuarios registrados.")
        return

    print("Usuarios:")
    for u in usuarios:
        print(f" • {u['usuario']} ({u['rol']})")

    a_eliminar = input_no_vacio("Usuario a eliminar: ")
    nuevos = [u for u in usuarios if u["usuario"] != a_eliminar]

    if len(nuevos) == len(usuarios):
        print("❌ Usuario no encontrado.")
    else:
        guardar_usuarios(nuevos)
        print(f"✅ Usuario '{a_eliminar}' eliminado.")


def reiniciar_archivo():
    print("\n--- Reiniciar todos los usuarios ---")
    confirmar = input("Escribí 'SI' para confirmar que querés borrar TODOS los usuarios: ")
    if confirmar.upper() == "SI":
        guardar_usuarios([])
        print("✅ Usuarios reiniciados (lista vacía).")
    else:
        print("Operación cancelada.")


def menu():
    while True:
        print("\n=== Gestión de Usuarios ===")
        print("1. Crear nuevo usuario")
        print("2. Eliminar usuario")
        print("3. Reiniciar todos los usuarios")
        print("4. Salir")

        opcion = input("Elegí una opción: ").strip()
        if opcion == "1":
            _with_app_context(crear_usuario)
        elif opcion == "2":
            _with_app_context(eliminar_usuario)
        elif opcion == "3":
            _with_app_context(reiniciar_archivo)
        elif opcion == "4":
            print("¡Hasta luego!")
            break
        else:
            print("❌ Opción inválida.")


if __name__ == "__main__":
    menu()
