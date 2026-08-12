from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, session

from consultorio.auth.decorators import login_requerido, rol_requerido
from consultorio.config import use_database
from consultorio.paths import DATA_FILE, PACIENTES_FILE, timezone_ar
from consultorio.storage import cargar_json, guardar_json
from consultorio.storage.queries import update_turno
from consultorio.utils.helpers import validar_historia

bp = Blueprint("historias", __name__)


@bp.route("/historias", methods=["GET"], endpoint="ver_historia_clinica")
@login_requerido
@rol_requerido("medico")
def ver_historia_clinica():
    dni = request.args.get("dni", "").strip()
    if not dni:
        return "DNI no especificado", 400
    fecha_turno = request.args.get("fecha", "").strip()
    hora_turno = request.args.get("hora", "").strip()
    return render_template(
        "historia_clinica.html",
        dni=dni,
        fecha_turno=fecha_turno,
        hora_turno=hora_turno,
    )



@bp.route("/api/historias", methods=["GET"], endpoint="obtener_todas_las_historias")
@login_requerido
@rol_requerido("medico")
def obtener_todas_las_historias():
    dni = request.args.get("dni", "").strip()
    if dni and use_database():
        from consultorio.storage import db_storage

        return jsonify(db_storage.load_historias_dni(dni))

    historias = cargar_json(DATA_FILE)
    if dni:
        historias = [h for h in historias if h.get("dni") == dni]
    return jsonify(historias)



@bp.route("/historias", methods=["POST"], endpoint="crear_historia")
@login_requerido
@rol_requerido("medico")
def crear_historia():
    nueva = dict(request.json or {})
    fecha_turno = nueva.pop("fecha_turno", None)
    hora_turno = nueva.pop("hora_turno", None)
    usuario_medico = session.get("usuario", "")
    nueva["medico"] = usuario_medico

    valido, mensaje = validar_historia(nueva)
    if not valido:
        return jsonify({"error": mensaje}), 400

    if fecha_turno and hora_turno:
        from consultorio.storage.queries import get_turno

        turno = get_turno(nueva.get("dni"), fecha_turno, hora_turno)
        if not turno:
            return jsonify({"error": "Turno no encontrado"}), 404
        if turno.get("medico") != usuario_medico:
            return jsonify({"error": "No autorizado: el turno pertenece a otro médico"}), 403

    nueva["fecha_creacion"] = datetime.now(timezone_ar).isoformat()

    if use_database():
        from consultorio.storage import db_storage

        db_storage.insert_historia(nueva, fecha_turno, hora_turno)
        return jsonify({"mensaje": "Consulta registrada correctamente"}), 201

    historias = cargar_json(DATA_FILE)
    nueva["id"] = max((int(h.get("id") or 0) for h in historias), default=0) + 1
    historias.append(nueva)
    guardar_json(DATA_FILE, historias)

    if fecha_turno and hora_turno:
        update_turno(
            nueva.get("dni"),
            fecha_turno,
            hora_turno,
            {
                "estado": "atendido",
                "borrador_consulta": None,
                "borrador_fecha_consulta": None,
                "borrador_actualizado": None,
            },
        )

    return jsonify({"mensaje": "Consulta registrada correctamente"}), 201



@bp.route("/historias/<dni>", methods=["GET", "PUT", "DELETE"], endpoint="manejar_historia")
@login_requerido
@rol_requerido("medico")
def manejar_historia(dni):
    historias = cargar_json(DATA_FILE)


    if request.method == "GET":
        for h in historias:
            if h["dni"] == dni:
                return jsonify(h)
        return jsonify({"error": "Historia no encontrada"}), 404


    if request.method == "PUT":
        datos = request.json
        valido, mensaje = validar_historia(datos)
        if not valido:
            return jsonify({"error": mensaje}), 400


        for h in historias:
            if h["dni"] == dni:
                h.update(datos)
                guardar_json(DATA_FILE, historias)
                return jsonify({"mensaje": "Historia modificada"})
        return jsonify({"error": "Historia no encontrada"}), 404


    if request.method == "DELETE":
        nuevas = [h for h in historias if h["dni"] != dni]
        if len(nuevas) == len(historias):
            return jsonify({"error": "Historia no encontrada"}), 404
        guardar_json(DATA_FILE, nuevas)
        return jsonify({"mensaje": "Historia eliminada"})


# ========================== SECRETARIA ============================



@bp.route("/historias-gestion", endpoint="ver_historias_gestion")
@login_requerido
@rol_requerido("medico")
def ver_historias_gestion():
    return render_template("historias_gestion.html")


@bp.route("/api/historias/buscar", methods=["GET"], endpoint="buscar_historias")
@login_requerido
@rol_requerido("medico")
def buscar_historias():
    # Parámetros de búsqueda
    busqueda = request.args.get("busqueda", "").strip().lower()
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
        por_pagina = min(50, max(1, int(request.args.get("por_pagina", 10))))
    except (TypeError, ValueError):
        pagina, por_pagina = 1, 10
    ordenar_por = request.args.get("ordenar_por", "apellido")
    orden = request.args.get("orden", "asc")

    if use_database():
        from consultorio.storage import db_storage

        return jsonify(
            db_storage.buscar_historias_paginado(
                busqueda,
                pagina,
                por_pagina,
                ordenar_por,
                orden,
            )
        )

    historias = cargar_json(DATA_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Enriquecer historias con datos del paciente
    historias_enriquecidas = []
    for historia in historias:
        paciente = next((p for p in pacientes if p["dni"] == historia["dni"]), None)
        if paciente:
            historia_completa = historia.copy()
            historia_completa["paciente"] = paciente
            historias_enriquecidas.append(historia_completa)
    
    # Filtrar por búsqueda (apellido, nombre o DNI)
    if busqueda:
        historias_filtradas = []
        for h in historias_enriquecidas:
            paciente = h["paciente"]
            apellido = paciente.get("apellido", "").lower()
            nombre = paciente.get("nombre", "").lower()
            dni = paciente.get("dni", "").lower()
            
            if (busqueda in apellido or 
                busqueda in nombre or 
                busqueda in dni):
                historias_filtradas.append(h)
        historias_enriquecidas = historias_filtradas
    
    # Agrupar por paciente y obtener la última consulta de cada uno
    pacientes_unicos = {}
    for h in historias_enriquecidas:
        dni = h["dni"]
        if dni not in pacientes_unicos:
            pacientes_unicos[dni] = {
                "paciente": h["paciente"],
                "ultima_consulta": h["fecha_consulta"],
                "total_consultas": 1,
                "ultima_historia": h
            }
        else:
            pacientes_unicos[dni]["total_consultas"] += 1
            # Comparar fechas para encontrar la más reciente
            if h["fecha_consulta"] > pacientes_unicos[dni]["ultima_consulta"]:
                pacientes_unicos[dni]["ultima_consulta"] = h["fecha_consulta"]
                pacientes_unicos[dni]["ultima_historia"] = h
    
    # Convertir a lista para ordenamiento
    lista_pacientes = list(pacientes_unicos.values())
    
    # Ordenar
    if ordenar_por == "apellido":
        lista_pacientes.sort(
            key=lambda x: x["paciente"].get("apellido", "").lower(),
            reverse=(orden == "desc")
        )
    elif ordenar_por == "nombre":
        lista_pacientes.sort(
            key=lambda x: x["paciente"].get("nombre", "").lower(),
            reverse=(orden == "desc")
        )
    elif ordenar_por == "fecha":
        lista_pacientes.sort(
            key=lambda x: x["ultima_consulta"],
            reverse=(orden == "desc")
        )
    elif ordenar_por == "dni":
        lista_pacientes.sort(
            key=lambda x: x["paciente"].get("dni", ""),
            reverse=(orden == "desc")
        )
    
    # Paginación
    total = len(lista_pacientes)
    inicio = (pagina - 1) * por_pagina
    fin = inicio + por_pagina
    pacientes_pagina = lista_pacientes[inicio:fin]
    
    total_paginas = (total + por_pagina - 1) // por_pagina
    
    return jsonify({
        "pacientes": pacientes_pagina,
        "total": total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "por_pagina": por_pagina
    })



# ========================== ADMINISTRADOR ============================
