import copy

from consultorio.config import entity_for_path, get_data_paths, use_database
from . import db_storage, json_storage

_PATHS = get_data_paths()


def cargar_json(path: str):
    if use_database():
        entity = entity_for_path(path, _PATHS)
        if entity:
            return copy.deepcopy(db_storage.cargar(entity))
        return []

    data = json_storage.cargar(path)
    if path.endswith("agenda.json") and not isinstance(data, dict):
        return {}
    if path.endswith("agenda_web.json") and not isinstance(data, dict):
        return {}
    if path.endswith("bloqueos_web.json") and not isinstance(data, list):
        return []
    return data


def guardar_json(path: str, data) -> None:
    if use_database():
        entity = entity_for_path(path, _PATHS)
        if entity:
            db_storage.guardar(entity, data)
        return
    json_storage.guardar(path, data)


def invalidar_cache_json(path: str) -> None:
    json_storage.invalidar_cache(path)
