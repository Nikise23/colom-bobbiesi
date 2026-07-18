from flask import Blueprint, jsonify, request

from consultorio.auth.decorators import login_requerido, rol_requerido
from consultorio.utils import agenda_web as aw

bp = Blueprint("agenda_web", __name__)


@bp.route("/api/agenda-web", methods=["GET"], endpoint="obtener_agenda_web")
@login_requerido
@rol_requerido("secretaria")
def obtener_agenda_web():
    return jsonify(aw.listar_config_completa())


@bp.route("/api/agenda-web/<medico>", methods=["GET"], endpoint="obtener_medico_web")
@login_requerido
@rol_requerido("secretaria")
def obtener_medico_web(medico):
    cfg = aw.get_medico_web(medico)
    if cfg is None:
        return jsonify({"error": "Médico no encontrado"}), 404
    return jsonify(cfg)


@bp.route("/api/agenda-web/<medico>", methods=["PUT"], endpoint="actualizar_medico_web")
@login_requerido
@rol_requerido("secretaria")
def actualizar_medico_web(medico):
    data = request.get_json(silent=True) or {}
    if "dias" not in data or not isinstance(data["dias"], dict):
        return jsonify({"error": 'Formato inválido, se espera { "visible": bool, "dias": {...} }'}), 400
    visible = bool(data.get("visible", False))
    result, err = aw.save_medico_web(medico, visible, data["dias"])
    if err:
        status = 404 if "no encontrado" in err.lower() else 400
        return jsonify({"error": err}), status
    return jsonify({"mensaje": "Agenda web actualizada", "config": result})


@bp.route(
    "/api/agenda-web/<medico>/copiar-interna",
    methods=["POST"],
    endpoint="copiar_agenda_web",
)
@login_requerido
@rol_requerido("secretaria")
def copiar_agenda_web(medico):
    data = request.get_json(silent=True) or {}
    visible = data.get("visible")
    if visible is not None:
        visible = bool(visible)
    result, err = aw.copiar_desde_interna(medico, visible=visible)
    if err:
        status = 404 if "no encontrado" in err.lower() else 400
        return jsonify({"error": err}), status
    return jsonify({"mensaje": "Horarios web copiados desde agenda interna", "config": result})


@bp.route("/api/bloqueos-web", methods=["GET"], endpoint="listar_bloqueos_web")
@login_requerido
@rol_requerido("secretaria")
def listar_bloqueos_web():
    medico = (request.args.get("medico") or "").strip() or None
    return jsonify({"bloqueos": aw.listar_bloqueos(medico)})


@bp.route("/api/bloqueos-web", methods=["POST"], endpoint="crear_bloqueo_web")
@login_requerido
@rol_requerido("secretaria")
def crear_bloqueo_web():
    data = request.get_json(silent=True) or {}
    created, err = aw.crear_bloqueo(data)
    if err:
        status = 404 if "no encontrado" in err.lower() else 400
        return jsonify({"error": err}), status
    return jsonify({"mensaje": "Bloqueo creado", "bloqueo": created}), 201


@bp.route("/api/bloqueos-web/<int:bloqueo_id>", methods=["DELETE"], endpoint="eliminar_bloqueo_web")
@login_requerido
@rol_requerido("secretaria")
def eliminar_bloqueo_web(bloqueo_id):
    ok, err = aw.eliminar_bloqueo(bloqueo_id)
    if not ok:
        return jsonify({"error": err or "Bloqueo no encontrado"}), 404
    return jsonify({"mensaje": "Bloqueo eliminado"})
