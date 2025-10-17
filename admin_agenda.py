import json
import os
from datetime import datetime, timedelta
 
AGENDA_FILE = "agenda.json"
 
DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
 
def cargar_agenda():
    if not os.path.exists(AGENDA_FILE):
        return {}
    with open(AGENDA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
 
def guardar_agenda(agenda):
    with open(AGENDA_FILE, "w", encoding="utf-8") as f:
        json.dump(agenda, f, indent=2, ensure_ascii=False)
 
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
    horarios = {}
    for dia in DIAS:
        horarios[dia] = input_horarios(dia)
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
    if confirm == 's':
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
        if op == '1':
            agregar_medico()
        elif op == '2':
            borrar_medico()
        elif op == '3':
            agenda = cargar_agenda()
            for med, dias in agenda.items():
                print(f"\n{med}:")
                for dia, hs in dias.items():
                    print(f"  {dia}: {', '.join(hs) if hs else '-'}")
        elif op == '0':
            print("¡Hasta luego!")
            break
        else:
            print("Opción inválida.")
 
if __name__ == "__main__":
    menu()