import os
import shutil

import pytz

from consultorio.config import DIAS_AGENDA, get_data_paths

timezone_ar = pytz.timezone("America/Argentina/Buenos_Aires")

_paths = get_data_paths()
DATA_FILE = _paths["historias"]
USUARIOS_FILE = _paths["usuarios"]
PACIENTES_FILE = _paths["pacientes"]
TURNOS_FILE = _paths["turnos"]
AGENDA_FILE = _paths["agenda"]
PAGOS_FILE = _paths["pagos"]


def mover_a_persistencia(nombre_archivo: str) -> None:
    origen = nombre_archivo
    destino = f"/data/{nombre_archivo}"

    if os.path.exists(origen) and not os.path.exists(destino):
        try:
            shutil.copy(origen, destino)
            print(f"Archivo '{nombre_archivo}' copiado a /data")
        except Exception as e:
            print(f"Error al copiar '{nombre_archivo}':", e)
    else:
        print(f"'{nombre_archivo}' ya existe en /data o no se encontró en el origen.")


def copiar_json_a_persistencia() -> None:
    if os.path.exists("/data") and not os.environ.get("DATABASE_URL"):
        for archivo in [
            "historias_clinicas.json",
            "usuarios.json",
            "pacientes.json",
            "turnos.json",
            "agenda.json",
            "pagos.json",
        ]:
            mover_a_persistencia(archivo)
