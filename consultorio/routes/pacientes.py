from datetime import date, datetime

from flask import Blueprint, jsonify, make_response, render_template, request

from consultorio.auth.decorators import login_requerido, rol_permitido, rol_requerido
from consultorio.paths import DATA_FILE, PACIENTES_FILE, TURNOS_FILE, timezone_ar
from consultorio.storage import cargar_json, guardar_json
from consultorio.storage.queries import (
    buscar_pacientes_paginado as buscar_pacientes_paginado_query,
    load_pacientes_liviano,
    load_pagos_fecha,
    load_turnos_fecha,
    obtener_paciente,
)
from consultorio.utils.fechas import hoy_ar_iso, normalizar_fecha_nacimiento
from consultorio.utils.helpers import (
    listar_pacientes_dedup,
    listar_recepcionados,
    listar_sala_espera,
)

bp = Blueprint("pacientes", __name__)


@bp.route("/pacientes", endpoint="vista_pacientes")
@login_requerido
@rol_requerido("secretaria")
def vista_pacientes():
    r = make_response(render_template("pacientes.html"))
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r



@bp.route("/api/pacientes", methods=["GET"], endpoint="obtener_pacientes")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_pacientes():
    return jsonify(listar_pacientes_dedup())



@bp.route("/api/pacientes/buscar", methods=["GET"], endpoint="buscar_pacientes_paginado")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def buscar_pacientes_paginado():
    """Buscar pacientes con paginación (consulta optimizada en PostgreSQL)."""
    busqueda = request.args.get("busqueda", "").strip()
    pagina = int(request.args.get("pagina", 1))
    por_pagina = min(int(request.args.get("por_pagina", 10)), 50)
    return jsonify(buscar_pacientes_paginado_query(busqueda, pagina, por_pagina))


@bp.route("/api/pacientes/<dni>", methods=["GET"], endpoint="obtener_paciente_por_dni")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_paciente_por_dni(dni):
    paciente = obtener_paciente(dni)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    return jsonify(paciente)



@bp.route("/api/pacientes/estadisticas", methods=["GET"], endpoint="estadisticas_pacientes")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def estadisticas_pacientes():
    """Estadísticas para la vista de pacientes: total, hoy, último registro (por fecha real)"""
    pacientes_raw = cargar_json(PACIENTES_FILE)
    vistos = set()
    pacientes = []
    for p in pacientes_raw:
        if p.get("dni") and p["dni"] not in vistos:
            vistos.add(p["dni"])
            pacientes.append(p)

    hoy = date.today().isoformat()
    pacientes_hoy = [p for p in pacientes if (p.get("fecha_registro") or "")[:10] == hoy]
    total = len(pacientes)

    # Último registro: por fecha_registro si existe, sino por orden en archivo
    ultimo = None
    con_fecha = [p for p in pacientes if p.get("fecha_registro")]
    if con_fecha:
        ultimo_p = max(con_fecha, key=lambda p: p.get("fecha_registro", ""))
        ultimo = {"nombre": ultimo_p.get("nombre", ""), "apellido": ultimo_p.get("apellido", "")}
    elif pacientes:
        ultimo_p = pacientes[-1]
        ultimo = {"nombre": ultimo_p.get("nombre", ""), "apellido": ultimo_p.get("apellido", "")}

    return jsonify({
        "total": total,
        "pacientes_hoy": len(pacientes_hoy),
        "ultimo_registro": ultimo
    })



@bp.route("/api/pacientes", methods=["POST"], endpoint="registrar_paciente")
@login_requerido
@rol_requerido("secretaria")
def registrar_paciente():
    data = request.json
    campos = ["nombre", "apellido", "dni", "obra_social", "numero_obra_social", "celular", "fecha_nacimiento"]
    for campo in campos:
        if not data.get(campo) or not str(data[campo]).strip():
            return jsonify({"error": f"El campo '{campo}' es obligatorio"}), 400
    
    # La edad se calculará dinámicamente cuando se consulte

    pacientes = cargar_json(PACIENTES_FILE)
    if any(p["dni"] == data["dni"] for p in pacientes):
        return jsonify({"error": "Ya existe un paciente con ese DNI"}), 400

    fecha = normalizar_fecha_nacimiento(data.get("fecha_nacimiento"))
    if not fecha:
        return jsonify({"error": "Fecha de nacimiento inválida. Use el formato dd/mm/aaaa."}), 400
    data["fecha_nacimiento"] = fecha
    data.pop("edad", None)

    data["fecha_registro"] = datetime.now(timezone_ar).isoformat()
    pacientes.append(data)
    guardar_json(PACIENTES_FILE, pacientes)
    return jsonify({"mensaje": "Paciente registrado correctamente"})


@bp.route("/api/pacientes/<dni>", methods=["PUT"], endpoint="actualizar_paciente")
@login_requerido
@rol_requerido("secretaria")
def actualizar_paciente(dni):
    data = request.json
    campos = ["nombre", "apellido", "dni", "obra_social", "numero_obra_social", "celular"]
    for campo in campos:
        if not data.get(campo):
            return jsonify({"error": f"El campo '{campo}' es obligatorio"}), 400
    
    # Validar formato del DNI
    if not data["dni"].isdigit() or len(data["dni"]) not in [7, 8]:
        return jsonify({"error": "DNI inválido"}), 400

    # La edad se calculará dinámicamente cuando se consulte

    pacientes = cargar_json(PACIENTES_FILE)

    # Si el DNI cambió, verificar que el nuevo DNI no esté en uso
    if data["dni"] != dni:
        if any(p["dni"] == data["dni"] for p in pacientes):
            return jsonify({"error": "Ya existe un paciente con ese DNI"}), 400
    
    
    for i, paciente in enumerate(pacientes):
        if paciente["dni"] == dni:
            if "fecha_nacimiento" in data:
                fecha = normalizar_fecha_nacimiento(data.get("fecha_nacimiento"))
                if not fecha:
                    return jsonify({"error": "Fecha de nacimiento inválida. Use el formato dd/mm/aaaa."}), 400
                data["fecha_nacimiento"] = fecha
            data.pop("edad", None)
            for campo, valor in data.items():
                pacientes[i][campo] = valor
            
            guardar_json(PACIENTES_FILE, pacientes)
            return jsonify({"mensaje": "Paciente actualizado correctamente"})
    
    return jsonify({"error": "Paciente no encontrado"}), 404


@bp.route("/api/pacientes/<dni>", methods=["DELETE"], endpoint="eliminar_paciente")
@login_requerido
@rol_requerido("secretaria")
def eliminar_paciente(dni):
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Verificar si el paciente tiene turnos asociados
    turnos = cargar_json(TURNOS_FILE)
    turnos_del_paciente = [t for t in turnos if t.get("dni_paciente") == dni]
    
    if turnos_del_paciente:
        return jsonify({
            "error": f"No se puede eliminar el paciente. Tiene {len(turnos_del_paciente)} turno(s) asociado(s). Primero cancele todos sus turnos."
        }), 400
    
    # Buscar y eliminar el paciente
    for i, paciente in enumerate(pacientes):
        if paciente["dni"] == dni:
            pacientes.pop(i)
            guardar_json(PACIENTES_FILE, pacientes)
            
            # También eliminar historias clínicas del paciente
            historias = cargar_json(DATA_FILE)
            historias_filtradas = [h for h in historias if h.get("dni") != dni]
            guardar_json(DATA_FILE, historias_filtradas)
            
            return jsonify({"mensaje": "Paciente eliminado correctamente"})
    
    return jsonify({"error": "Paciente no encontrado"}), 404

@bp.route("/api/pacientes/recepcionados", methods=["GET"], endpoint="obtener_pacientes_recepcionados")
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_pacientes_recepcionados():
    """Obtiene pacientes que están recepcionados y pendientes de pago"""
    fecha = request.args.get("fecha", hoy_ar_iso())
    pacientes = load_pacientes_liviano()
    turnos_raw = load_turnos_fecha(fecha)
    pagos = load_pagos_fecha(fecha)
    return jsonify(listar_recepcionados(turnos_raw, pacientes, pagos, fecha))


@bp.route("/api/pacientes/sala-espera", methods=["GET"], endpoint="obtener_pacientes_sala_espera")
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_pacientes_sala_espera():
    """Obtiene pacientes que están en sala de espera (ya cobrados)"""
    fecha = request.args.get("fecha", hoy_ar_iso())
    pacientes = load_pacientes_liviano()
    turnos_raw = load_turnos_fecha(fecha)
    pagos = load_pagos_fecha(fecha)
    return jsonify(listar_sala_espera(turnos_raw, pacientes, pagos, fecha))

# ======================= SISTEMA DE RECEPCIÓN =======================
