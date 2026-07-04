import copy
import json
import os

_json_cache: dict[str, tuple[float, object]] = {}


def invalidar_cache(path: str) -> None:
    _json_cache.pop(path, None)


def cargar(path: str):
    if not os.path.exists(path):
        return []
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    cached = _json_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return copy.deepcopy(cached[1])
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    _json_cache[path] = (mtime, data)
    return copy.deepcopy(data)


def guardar(path: str, data) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
    os.replace(tmp_path, path)
    invalidar_cache(path)
