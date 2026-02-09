from flask import Flask, request, jsonify, render_template, redirect, url_for, session, make_response, send_file
import json
import os
import csv
import io
import shutil
from functools import wraps
from datetime import datetime, date, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_insegura_dev")

# Configurar zona horaria para Argentina (UTC-3)
import pytz
timezone_ar = pytz.timezone('America/Argentina/Buenos_Aires')

# Rutas de archivo usando el disco persistente
# En producción (Render) usa /data/, en desarrollo local usa la raíz
import os
if os.path.exists("/data"):
    # Producción en Render
    DATA_FILE = "/data/historias_clinicas.json"
    USUARIOS_FILE = "/data/usuarios.json"
    PACIENTES_FILE = "/data/pacientes.json"
    TURNOS_FILE = "/data/turnos.json"
    AGENDA_FILE = "/data/agenda.json"
    PAGOS_FILE = "/data/pagos.json"
else:
    # Desarrollo local
    DATA_FILE = "historias_clinicas.json"
    USUARIOS_FILE = "usuarios.json"
    PACIENTES_FILE = "pacientes.json"
    TURNOS_FILE = "turnos.json"
    AGENDA_FILE = "agenda.json"
    PAGOS_FILE = "pagos.json"

# (OPCIONAL) Copiar archivos antiguos si todavía existen en la raíz
def mover_a_persistencia(nombre_archivo):
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

# Solo ejecutar en producción si existe el directorio /data
if os.path.exists("/data"):
    archivos_para_mover = [
        "historias_clinicas.json",
        "usuarios.json",
        "pacientes.json",
        "turnos.json",
        "agenda.json",
        "pagos.json"
    ]

    for archivo in archivos_para_mover:
        mover_a_persistencia(archivo)


# ===================== Funciones auxiliares ======================

def cargar_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    return []


def guardar_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def calcular_edad(fecha_nacimiento):
    """Calcula la edad a partir de la fecha de nacimiento"""
    try:
        fecha_nac = datetime.strptime(fecha_nacimiento, "%Y-%m-%d").date()
        hoy = date.today()
        edad = hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))
        return edad
    except:
        return None

def validar_historia(data):
    campos_obligatorios = ["dni", "consulta_medica", "medico"]
    for campo in campos_obligatorios:
        if not data.get(campo) or not str(data[campo]).strip():
            return False, f"El campo '{campo}' es obligatorio."


    if not data["dni"].isdigit() or len(data["dni"]) not in [7, 8]:
        return False, "DNI inválido."


    for campo in ["fecha_consulta"]:
        fecha = data.get(campo)
        if fecha:
            try:
                f = datetime.strptime(fecha, "%Y-%m-%d")
                # Convertir a timezone-aware para comparar
                f = f.replace(tzinfo=timezone_ar)
                ahora = datetime.now(timezone_ar)
                if f > ahora:
                    return False, f"La fecha '{campo}' no puede ser futura."
            except ValueError:
                return False, f"Formato de fecha inválido en '{campo}'."


    return True, ""


def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def rol_requerido(rol_permitido):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("rol") != rol_permitido:
                return redirect(url_for("inicio"))
            return f(*args, **kwargs)
        return decorated
    return wrapper


def rol_permitido(varios_roles):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("rol") not in varios_roles:
                return redirect(url_for("inicio"))
            return f(*args, **kwargs)
        return decorated
    return wrapper


# ========================== RUTAS GENERALES ============================

@app.route('/descargar/<archivo>')
@login_requerido
@rol_requerido("administrador")
def descargar_archivo(archivo):
    # En producción usa /data/, en desarrollo local usa la raíz
    if os.path.exists("/data"):
        ruta = f"/data/{archivo}"
    else:
        ruta = archivo
    
    if os.path.exists(ruta):
        return send_file(ruta, as_attachment=True)
    else:
        return f"Archivo '{archivo}' no encontrado", 404


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        contrasena = request.form.get("contrasena")
        usuarios = cargar_json(USUARIOS_FILE)


        for u in usuarios:
            if u["usuario"] == usuario and check_password_hash(u["contrasena"], contrasena):
                session["usuario"] = usuario
                session["rol"] = u.get("rol", "")
                # Redirigir según el rol
                if u.get("rol") == "secretaria":
                    return redirect(url_for("vista_secretaria"))
                elif u.get("rol") == "administrador":
                    return redirect(url_for("vista_administrador"))
                else:
                    return redirect(url_for("inicio"))
        return render_template("login.html", error="Usuario o contraseña incorrectos")


    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    session.pop("rol", None)
    return redirect(url_for("login"))


@app.route("/")
@login_requerido
def inicio():
    return render_template("index.html")


@app.route("/api/session-info")
@login_requerido
def session_info():
    return jsonify({
        "usuario": session.get("usuario"),
        "rol": session.get("rol")
    })


# ========================== MÉDICO ============================


@app.route("/historias", methods=["GET"])
@login_requerido
@rol_requerido("medico")
def ver_historia_clinica():
    dni = request.args.get("dni", "").strip()
    if not dni:
        return "DNI no especificado", 400
    return render_template("historia_clinica.html", dni=dni)


@app.route("/api/historias", methods=["GET"])
@login_requerido
@rol_requerido("medico")
def obtener_todas_las_historias():
    historias = cargar_json(DATA_FILE)
    return jsonify(historias)


@app.route("/historias", methods=["POST"])
@login_requerido
@rol_requerido("medico")
def crear_historia():
    historias = cargar_json(DATA_FILE)
    nueva = request.json


    valido, mensaje = validar_historia(nueva)
    if not valido:
        return jsonify({"error": mensaje}), 400


    # Agregar ID único para la consulta
    nueva["id"] = len(historias) + 1
    nueva["fecha_creacion"] = datetime.now(timezone_ar).isoformat()


    historias.append(nueva)
    guardar_json(DATA_FILE, historias)
    return jsonify({"mensaje": "Consulta registrada correctamente"}), 201


@app.route("/historias/<dni>", methods=["GET", "PUT", "DELETE"])
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


@app.route("/pacientes")
@login_requerido
@rol_requerido("secretaria")
def vista_pacientes():
    r = make_response(render_template("pacientes.html"))
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


@app.route("/api/pacientes", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_pacientes():
    pacientes_raw = cargar_json(PACIENTES_FILE)
    # Deduplicar por DNI (mantener primera aparición)
    vistos = set()
    pacientes = []
    for p in pacientes_raw:
        if p.get("dni") and p["dni"] not in vistos:
            vistos.add(p["dni"])
            pacientes.append(p)

    # Calcular edad dinámicamente para cada paciente
    for paciente in pacientes:
        if paciente.get("fecha_nacimiento"):
            edad_actual = calcular_edad(paciente["fecha_nacimiento"])
            paciente["edad"] = edad_actual

    pacientes.sort(key=lambda p: p.get("apellido", "").lower())
    return jsonify(pacientes)


@app.route("/api/pacientes/buscar", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def buscar_pacientes_paginado():
    """Buscar pacientes con paginación (evita cargar todos los datos)"""
    busqueda = request.args.get("busqueda", "").strip().lower()
    pagina = int(request.args.get("pagina", 1))
    por_pagina = min(int(request.args.get("por_pagina", 10)), 50)

    pacientes_raw = cargar_json(PACIENTES_FILE)
    vistos = set()
    pacientes = []
    for p in pacientes_raw:
        if p.get("dni") and p["dni"] not in vistos:
            vistos.add(p["dni"])
            pacientes.append(p)

    for paciente in pacientes:
        if paciente.get("fecha_nacimiento"):
            paciente["edad"] = calcular_edad(paciente["fecha_nacimiento"])

    pacientes.sort(key=lambda p: p.get("apellido", "").lower())

    if busqueda:
        pacientes = [
            p for p in pacientes
            if (p.get("dni", "") and busqueda in p["dni"]) or
               (p.get("apellido", "").lower() and busqueda in p["apellido"].lower()) or
               (p.get("nombre", "").lower() and busqueda in p["nombre"].lower())
        ]

    total = len(pacientes)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(1, min(pagina, total_paginas))
    inicio = (pagina - 1) * por_pagina
    fin = min(inicio + por_pagina, total)
    pacientes_pagina = pacientes[inicio:fin]

    return jsonify({
        "pacientes": pacientes_pagina,
        "total": total,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "por_pagina": por_pagina,
    })


@app.route("/api/pacientes/estadisticas", methods=["GET"])
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


@app.route("/api/pacientes", methods=["POST"])
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

    data["fecha_registro"] = datetime.now(timezone_ar).isoformat()
    pacientes.append(data)
    guardar_json(PACIENTES_FILE, pacientes)
    return jsonify({"mensaje": "Paciente registrado correctamente"})

@app.route("/api/pacientes/<dni>", methods=["PUT"])
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
            # Actualizar todos los campos incluyendo el DNI
            for campo, valor in data.items():
                pacientes[i][campo] = valor
            
            guardar_json(PACIENTES_FILE, pacientes)
            return jsonify({"mensaje": "Paciente actualizado correctamente"})
    
    return jsonify({"error": "Paciente no encontrado"}), 404

@app.route("/api/pacientes/<dni>", methods=["DELETE"])
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

# --- Rutas para turnos y agenda ---


@app.route("/api/turnos", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_turnos():
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)


    for t in turnos:
        paciente = next((p for p in pacientes if p["dni"] == t["dni_paciente"]), None)
        t["paciente"] = paciente
        t["estado"] = t.get("estado", "sin atender")
        # Formatear fecha DD/M/YYYY en servidor (evita desfase por zona horaria en frontend)
        if t.get("fecha"):
            parts = t["fecha"].split("-")
            if len(parts) >= 3:
                t["fecha_fmt"] = f"{int(parts[2])}/{int(parts[1])}/{parts[0]}"
            else:
                t["fecha_fmt"] = t["fecha"]
        else:
            t["fecha_fmt"] = ""
    return jsonify(turnos)


@app.route("/api/turnos", methods=["POST"])
@login_requerido
@rol_requerido("secretaria")
def asignar_turno():
    data = request.json
    campos = ["medico", "hora", "fecha", "dni_paciente"]
    for campo in campos:
        if not data.get(campo):
            return jsonify({"error": f"El campo '{campo}' es obligatorio"}), 400


    try:
        fecha_dt = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido (usar YYYY-MM-DD)"}), 400


    dia_semana = fecha_dt.strftime("%A").upper()
    if dia_semana not in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]:
        return jsonify({"error": "Solo se pueden asignar turnos de lunes a viernes"}), 400


    dia_es = {
        "MONDAY": "LUNES", "TUESDAY": "MARTES", "WEDNESDAY": "MIERCOLES",
        "THURSDAY": "JUEVES", "FRIDAY": "VIERNES"
    }[dia_semana]


    agenda = cargar_json(AGENDA_FILE)
    medico = data["medico"]
    if medico not in agenda:
        return jsonify({"error": "Médico no encontrado"}), 404


    horarios_disponibles = agenda[medico].get(dia_es, [])
    if data["hora"] not in horarios_disponibles:
        return jsonify({"error": f"La hora '{data['hora']}' no está disponible para el médico {medico} el día {dia_es}"}), 400


    turnos = cargar_json(TURNOS_FILE)
    if any(t["medico"] == medico and t.get("fecha") == data["fecha"] and t["hora"] == data["hora"] for t in turnos):
        return jsonify({"error": "Ya existe un turno asignado para ese horario y fecha"}), 400


    pacientes = cargar_json(PACIENTES_FILE)
    if not any(p["dni"] == data["dni_paciente"] for p in pacientes):
        return jsonify({"error": "Paciente no encontrado"}), 404


    turno_nuevo = {
        "medico": medico,
        "hora": data["hora"],
        "fecha": data["fecha"],
        "dni_paciente": data["dni_paciente"],
        "estado": "sin atender"
    }


    turnos.append(turno_nuevo)
    guardar_json(TURNOS_FILE, turnos)
    return jsonify({"mensaje": "Turno asignado correctamente"})


@app.route("/api/turnos/estado", methods=["PUT"])
@login_requerido
@rol_permitido(["medico"])
def actualizar_estado_turno():
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    hora = data.get("hora")
    nuevo_estado = data.get("estado")


    if nuevo_estado not in ["sin atender", "llamado", "atendido", "ausente"]:
        return jsonify({"error": "Estado inválido"}), 400


    turnos = cargar_json(TURNOS_FILE)
    encontrado = False


    for turno in turnos:
        if turno["dni_paciente"] == dni_paciente and turno["fecha"] == fecha and turno["hora"] == hora:
            turno["estado"] = nuevo_estado
            encontrado = True
            break


    if not encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404


    guardar_json(TURNOS_FILE, turnos)
    return jsonify({"mensaje": "Estado actualizado correctamente"})


@app.route("/turnos")
@login_requerido
@rol_permitido(["secretaria", "medico"])
def ver_turnos():
    # Redirigir según el rol
    if session.get("rol") == "medico":
        return render_template("turnos_medico.html")
    else:
        return render_template("pacientes_turnos.html")

@app.route("/turnos/gestion")
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def gestion_turnos():
    return render_template("pacientes_turnos.html")

@app.route("/api/turnos/medico", methods=["GET"])
@login_requerido
@rol_requerido("medico")
def obtener_turnos_medico():
    usuario_medico = session.get("usuario")
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)


    turnos_medico = [t for t in turnos if t.get("medico") == usuario_medico]


    # Enriquecer con datos del paciente
    for t in turnos_medico:
        paciente = next((p for p in pacientes if p["dni"] == t["dni_paciente"]), {})
        t["paciente"] = paciente
        t["estado"] = t.get("estado", "sin atender")


    return jsonify(turnos_medico)

@app.route("/secretaria")
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def vista_secretaria():
    return render_template("secretaria.html")

@app.route("/agenda")
@login_requerido
@rol_requerido("secretaria")
def ver_agenda():
    return render_template("agenda.html")


@app.route("/api/agenda", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_agenda():
    try:
        agenda_data = cargar_json(AGENDA_FILE)
        return jsonify(agenda_data)
    except Exception as e:
        print(f"Error al cargar agenda: {e}")
        return jsonify({"error": "Error al cargar la agenda"}), 500


@app.route("/api/agenda/<medico>/<dia>", methods=["PUT"])
@login_requerido
@rol_requerido("secretaria")
def actualizar_agenda_dia(medico, dia):
    nuevos_horarios = request.json
    if dia.upper() not in ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]:
        return jsonify({"error": "Día inválido"}), 400
    if not isinstance(nuevos_horarios, dict) or "horarios" not in nuevos_horarios or not isinstance(nuevos_horarios["horarios"], list):
        return jsonify({"error": "Formato inválido, se espera un objeto con clave 'horarios' que sea una lista"}), 400
    nuevos_horarios = nuevos_horarios["horarios"]

    agenda = cargar_json(AGENDA_FILE)
    if medico not in agenda:
        agenda[medico] = {}


    agenda[medico][dia.upper()] = nuevos_horarios
    guardar_json(AGENDA_FILE, agenda)
    return jsonify({"mensaje": "Agenda actualizada correctamente"})

@app.route("/api/turnos/<dni>/<fecha>/<hora>", methods=["PUT"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def editar_turno(dni, fecha, hora):
    data = request.json
    turnos = cargar_json(TURNOS_FILE)
    
    # Encontrar el turno específico
    turno_encontrado = None
    for turno in turnos:
        if turno["dni_paciente"] == dni and turno["fecha"] == fecha and turno["hora"] == hora:
            turno_encontrado = turno
            break
    
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
    
    # Actualizar los campos permitidos
    if "nueva_hora" in data:
        nueva_hora = data["nueva_hora"]
        nueva_fecha = data.get("nueva_fecha", fecha)
        # Verificar que la nueva hora no esté ocupada en la fecha correspondiente
        if any(t["medico"] == turno_encontrado["medico"] and t["fecha"] == nueva_fecha and t["hora"] == nueva_hora and 
               not (t["dni_paciente"] == dni and t["fecha"] == fecha and t["hora"] == hora) for t in turnos):
            return jsonify({"error": "La nueva hora ya está ocupada"}), 400
        turno_encontrado["hora"] = nueva_hora
    
    if "nueva_fecha" in data:
        nueva_fecha = data["nueva_fecha"]
        nueva_hora = data.get("nueva_hora", turno_encontrado["hora"])
        # Verificar que la nueva fecha/hora no esté ocupada
        if any(t["medico"] == turno_encontrado["medico"] and t["fecha"] == nueva_fecha and t["hora"] == nueva_hora and 
               not (t["dni_paciente"] == dni and t["fecha"] == fecha and t["hora"] == hora) for t in turnos):
            return jsonify({"error": "La nueva fecha/hora ya está ocupada"}), 400
        turno_encontrado["fecha"] = nueva_fecha
    
    if "nuevo_medico" in data:
        turno_encontrado["medico"] = data["nuevo_medico"]
    
    if "nuevo_estado" in data:
        estados_validos = ["sin atender", "recepcionado", "sala de espera", "llamado", "atendido", "ausente"]
        if data["nuevo_estado"] in estados_validos:
            turno_encontrado["estado"] = data["nuevo_estado"]

    guardar_json(TURNOS_FILE, turnos)
    return jsonify({"mensaje": "Turno actualizado correctamente"})

@app.route("/api/turnos/<dni>/<fecha>/<hora>", methods=["DELETE"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def eliminar_turno(dni, fecha, hora):
    turnos = cargar_json(TURNOS_FILE)
    
    # Filtrar el turno a eliminar
    turnos_filtrados = [
        t for t in turnos 
        if not (t["dni_paciente"] == dni and t["fecha"] == fecha and t["hora"] == hora)
    ]
    
    if len(turnos_filtrados) == len(turnos):
        return jsonify({"error": "Turno no encontrado"}), 404
    
    guardar_json(TURNOS_FILE, turnos_filtrados)
    return jsonify({"mensaje": "Turno eliminado correctamente"})

# ======================= SISTEMA DE PAGOS =======================

@app.route("/api/pagos", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def obtener_pagos():
    pagos = cargar_json(PAGOS_FILE)
    return jsonify(pagos)

@app.route("/api/pagos", methods=["POST"])
@login_requerido
@rol_requerido("secretaria")
def registrar_pago():
    data = request.json
    campos_requeridos = ["dni_paciente", "fecha"]
    
    for campo in campos_requeridos:
        if not data.get(campo):
            return jsonify({"error": f"El campo '{campo}' es requerido"}), 400
        
    # Validar monto (puede ser 0 para obra social)
    try:
        monto = float(data.get("monto", 0))
        if monto < 0:
             return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    
    # Validar tipo de pago (solo para pagos particulares)
    tipo_pago = data.get("tipo_pago", "efectivo")
    if monto > 0 and tipo_pago not in ["efectivo", "transferencia"]:
        return jsonify({"error": "Tipo de pago inválido. Debe ser 'efectivo' o 'transferencia'"}), 400
    
    # Para obra social, el tipo de pago siempre es "obra_social"
    if monto == 0:
        tipo_pago = "obra_social"
    
    # Verificar que el paciente existe
    pacientes = cargar_json(PACIENTES_FILE)
    paciente = next((p for p in pacientes if p["dni"] == data["dni_paciente"]), None)
    
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    
    # Verificar si ya existe un pago para este paciente en esta fecha y hora
    pagos = cargar_json(PAGOS_FILE)
    hora = data.get("hora", "")
    pago_existente = next((p for p in pagos if 
                          p["dni_paciente"] == data["dni_paciente"] and 
                          p["fecha"] == data["fecha"] and 
                          p.get("hora", "") == hora), None)
     
    if pago_existente and hora:
        return jsonify({"error": "Ya existe un pago registrado para este paciente en esta fecha y hora"}), 400
     
    nuevo_pago = {
        "id": len(pagos) + 1,
        "dni_paciente": data["dni_paciente"],
        "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
        "monto": monto,
        "fecha": data["fecha"],
        "hora": data.get("hora", ""),
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
        "observaciones": data.get("observaciones", ""),
        "obra_social": paciente.get("obra_social", ""),
        "tipo_pago": tipo_pago
    }
    
    pagos.append(nuevo_pago)
    guardar_json(PAGOS_FILE, pagos)
    
    return jsonify({"mensaje": "Pago registrado correctamente", "pago": nuevo_pago}), 201

@app.route("/api/pagos/<int:pago_id>", methods=["DELETE"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def eliminar_pago(pago_id):
    pagos = cargar_json(PAGOS_FILE)
     
    # Filtrar el pago a eliminar
    pagos_filtrados = [p for p in pagos if p.get("id") != pago_id]
     
    if len(pagos_filtrados) == len(pagos):
        return jsonify({"error": "Pago no encontrado"}), 404
     
    guardar_json(PAGOS_FILE, pagos_filtrados)
    return jsonify({"mensaje": "Pago eliminado correctamente"})
 

@app.route("/api/pagos/estadisticas", methods=["GET"])
@login_requerido
@rol_requerido("secretaria")
def obtener_estadisticas_pagos():
    pagos = cargar_json(PAGOS_FILE)
    hoy = date.today()
    # Permitir filtrar por fecha específica
    fecha_param = request.args.get("fecha")
    if fecha_param:
        try:
            fecha_dia = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            fecha_dia = hoy
    else:
        fecha_dia = hoy
    mes_param = request.args.get("mes", fecha_dia.strftime("%Y-%m"))
    
    # Filtrar pagos del día
    pagos_hoy = [p for p in pagos if p["fecha"] == fecha_dia.isoformat()]
    total_dia = sum(p["monto"] for p in pagos_hoy)
    
    # Filtrar pagos del mes especificado
    pagos_mes = [p for p in pagos if p["fecha"].startswith(mes_param)]
    total_mes = sum(p["monto"] for p in pagos_mes)
    
    # Estadísticas por tipo de pago del día
    pagos_efectivo_hoy = [p for p in pagos_hoy if p.get("tipo_pago") == "efectivo"]
    pagos_transferencia_hoy = [p for p in pagos_hoy if p.get("tipo_pago") == "transferencia"]
    pagos_obra_social_hoy = [p for p in pagos_hoy if p.get("tipo_pago") == "obra_social"]
    
    total_efectivo_hoy = sum(p["monto"] for p in pagos_efectivo_hoy)
    total_transferencia_hoy = sum(p["monto"] for p in pagos_transferencia_hoy)
    total_obra_social_hoy = sum(p["monto"] for p in pagos_obra_social_hoy)


    # Estadísticas por día del mes
    pagos_por_dia = {}
    pagos_obra_social = 0
    pagos_particulares = 0
     
    for pago in pagos_mes:
        dia = pago["fecha"]
        if dia not in pagos_por_dia:
            pagos_por_dia[dia] = {"cantidad": 0, "monto": 0, "pacientes": []}
         
        pagos_por_dia[dia]["cantidad"] += 1
        pagos_por_dia[dia]["monto"] += pago["monto"]
        pagos_por_dia[dia]["pacientes"].append({
            "nombre": pago["nombre_paciente"],
            "monto": pago["monto"],
            "obra_social": pago.get("obra_social", ""),
            "tipo_pago": pago.get("tipo_pago", "efectivo")
        })
         
        if pago["monto"] == 0:
            pagos_obra_social += 1
        else:
             pagos_particulares += 1
     
    # Ordenar días por fecha
    pagos_por_dia_ordenados = dict(sorted(pagos_por_dia.items()))
    
    return jsonify({
        "total_dia": total_dia,
        "total_mes": total_mes,
        "cantidad_pagos_dia": len(pagos_hoy),
        "cantidad_pagos_mes": len(pagos_mes),
        "pagos_obra_social": pagos_obra_social,
        "pagos_particulares": pagos_particulares,
        "fecha": fecha_dia.isoformat(),
        "mes_consultado": mes_param,
        "detalle_por_dia": pagos_por_dia_ordenados,
        # Nuevas estadísticas por tipo de pago
        "pagos_efectivo_hoy": len(pagos_efectivo_hoy),
        "pagos_transferencia_hoy": len(pagos_transferencia_hoy),
        "pagos_obra_social_hoy": len(pagos_obra_social_hoy),
        "total_efectivo_hoy": total_efectivo_hoy,
        "total_transferencia_hoy": total_transferencia_hoy,
        "total_obra_social_hoy": total_obra_social_hoy
    })
@app.route("/api/pagos/exportar", methods=["GET"])
@login_requerido
@rol_requerido("secretaria")
def exportar_pagos_csv():
    pagos = cargar_json(PAGOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)

    # Obtener la fecha seleccionada (o hoy por defecto)
    
    fecha_param = request.args.get("fecha")
    if fecha_param:
        try:
            fecha_dia = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            fecha_dia = date.today()
    else:
        fecha_dia = date.today()
    
    # Filtrar pagos de la fecha seleccionada
    pagos_dia = [p for p in pagos if p["fecha"] == fecha_dia.isoformat()]
    
    # Calcular subtotales
    subtotal_efectivo = sum(p["monto"] for p in pagos_dia if p.get("tipo_pago") == "efectivo")
    subtotal_transferencia = sum(p["monto"] for p in pagos_dia if p.get("tipo_pago") == "transferencia")
    total = subtotal_efectivo + subtotal_transferencia
    
    # Crear archivo CSV en memoria
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados
    writer.writerow(['Fecha', 'Apellido', 'Nombre', 'DNI', 'Monto', 'Tipo de Pago', 'Observaciones'])
    
    # Datos
    for pago in pagos_dia:
        paciente = next((p for p in pacientes if p["dni"] == pago["dni_paciente"]), {})
        writer.writerow([
            pago["fecha"],
            paciente.get("apellido", ""),
            paciente.get("nombre", ""),
            pago["dni_paciente"],
            pago.get("tipo_pago", "efectivo"),
            pago.get("observaciones", "")
        ])
    # Fila vacía
    
    writer.writerow([])
    # Subtotales
    writer.writerow(["", "", "", "", "Subtotal Efectivo", subtotal_efectivo, ""])
    writer.writerow(["", "", "", "", "Subtotal Transferencia", subtotal_transferencia, ""])
    writer.writerow(["", "", "", "", "TOTAL", total, ""])

    # Preparar respuesta
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=pagos_{fecha_dia.isoformat()}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response

@app.route("/api/pacientes/atendidos", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico"])
def obtener_pacientes_atendidos():
    """Obtiene pacientes que fueron atendidos y aún no tienen pago registrado para una fecha específica"""
    fecha = request.args.get("fecha", date.today().isoformat())
    
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    pagos = cargar_json(PAGOS_FILE)
    
    # Filtrar turnos atendidos en la fecha especificada
    turnos_atendidos = [t for t in turnos if t["fecha"] == fecha and t["estado"] == "atendido"]
    
    # Obtener DNIs que ya tienen pago registrado en esa fecha
    dnis_con_pago = {p["dni_paciente"] for p in pagos if p["fecha"] == fecha}
    
    # Filtrar pacientes atendidos sin pago
    pacientes_sin_pago = []
    for turno in turnos_atendidos:
        if turno["dni_paciente"] not in dnis_con_pago:
            paciente = next((p for p in pacientes if p["dni"] == turno["dni_paciente"]), None)
            if paciente:
                pacientes_sin_pago.append({
                    "dni": paciente["dni"],
                    "nombre": paciente["nombre"],
                    "apellido": paciente["apellido"],
                    "obra_social": paciente.get("obra_social", ""),
                    "hora_turno": turno["hora"],
                    "medico": turno["medico"]
                })
    
    return jsonify(pacientes_sin_pago)

@app.route("/api/pacientes/recepcionados", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_pacientes_recepcionados():
    """Obtiene pacientes que están recepcionados y pendientes de pago"""
    fecha = request.args.get("fecha", date.today().isoformat())
    
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    pagos = cargar_json(PAGOS_FILE)
    
    # Filtrar turnos recepcionados en la fecha especificada
    turnos_recepcionados = [t for t in turnos if t.get("fecha") == fecha and t.get("estado") == "recepcionado"]
    
    # Obtener DNIs que ya tienen pago registrado en esa fecha
    dnis_con_pago = {p["dni_paciente"] for p in pagos if p["fecha"] == fecha}
    
    # Filtrar pacientes recepcionados sin pago
    pacientes_recepcionados = []
    for turno in turnos_recepcionados:
        if turno["dni_paciente"] not in dnis_con_pago:
            paciente = next((p for p in pacientes if p["dni"] == turno["dni_paciente"]), None)
            if paciente:
                pacientes_recepcionados.append({
                    "dni": paciente["dni"],
                    "nombre": paciente["nombre"],
                    "apellido": paciente["apellido"],
                    "obra_social": paciente.get("obra_social", ""),
                    "celular": paciente.get("celular", ""),
                    "hora_turno": turno["hora"],
                    "medico": turno["medico"],
                    "fecha": turno["fecha"],
                    "hora_recepcion": turno.get("hora_recepcion", "")
                })
    
    # Ordenar por hora de turno
    pacientes_recepcionados.sort(key=lambda p: p.get("hora_turno", "00:00"))
    
    return jsonify(pacientes_recepcionados)

@app.route("/api/pacientes/sala-espera", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_pacientes_sala_espera():
    """Obtiene pacientes que están en sala de espera (ya cobrados)"""
    fecha = request.args.get("fecha", date.today().isoformat())
    
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    pagos = cargar_json(PAGOS_FILE)
    
    # Filtrar turnos en sala de espera en la fecha especificada
    turnos_sala_espera = [t for t in turnos if t.get("fecha") == fecha and t.get("estado") == "sala de espera"]
    
    # Obtener información de pagos para estos pacientes
    pacientes_sala_espera = []
    for turno in turnos_sala_espera:
        paciente = next((p for p in pacientes if p["dni"] == turno["dni_paciente"]), None)
        pago = next((p for p in pagos if p["dni_paciente"] == turno["dni_paciente"] and p["fecha"] == fecha), None)
        
        if paciente:
            pacientes_sala_espera.append({
                "dni": paciente["dni"],
                "nombre": paciente["nombre"],
                "apellido": paciente["apellido"],
                "obra_social": paciente.get("obra_social", ""),
                "celular": paciente.get("celular", ""),
                "hora_turno": turno["hora"],
                "medico": turno["medico"],
                "fecha": turno["fecha"],
                "hora_recepcion": turno.get("hora_recepcion", ""),
                "hora_sala_espera": turno.get("hora_sala_espera", ""),
                "monto_pagado": pago.get("monto", 0) if pago else 0,
                "tipo_pago": pago.get("tipo_pago", "obra_social") if pago else "obra_social",
                "observaciones": pago.get("observaciones", "") if pago else ""
            })
    
    # Ordenar por hora de turno
    pacientes_sala_espera.sort(key=lambda p: p.get("hora_turno", "00:00"))
    
    return jsonify(pacientes_sala_espera)

# ======================= SISTEMA DE RECEPCIÓN =======================

@app.route("/api/turnos/recepcionar", methods=["PUT"])
@login_requerido
@rol_permitido(["secretaria"])
def recepcionar_paciente():
    """Cambiar el estado de un turno a 'recepcionado' cuando llega el paciente"""
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    hora = data.get("hora")
    
    if not all([dni_paciente, fecha, hora]):
        return jsonify({"error": "DNI, fecha y hora son requeridos"}), 400
    
    turnos = cargar_json(TURNOS_FILE)
    
    for turno in turnos:
        if (turno["dni_paciente"] == dni_paciente and 
            turno["fecha"] == fecha and 
            turno["hora"] == hora):
            
            turno["estado"] = "recepcionado"
            turno["hora_recepcion"] = datetime.now(timezone_ar).strftime("%H:%M")
            
            guardar_json(TURNOS_FILE, turnos)
            return jsonify({"mensaje": "Paciente recepcionado correctamente"})
    
    return jsonify({"error": "Turno no encontrado"}), 404

@app.route("/api/turnos/sala-espera", methods=["PUT"])
@login_requerido
@rol_permitido(["secretaria", "administrador"])
def mover_a_sala_espera():
    """Mover paciente recepcionado a sala de espera y registrar pago"""
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    hora = data.get("hora")
    monto = data.get("monto", 0)  # Puede ser 0 para obra social
    observaciones = data.get("observaciones", "")
    tipo_pago = data.get("tipo_pago", "efectivo")  # Nuevo campo para tipo de pago

     
    if not all([dni_paciente, fecha, hora]):
        return jsonify({"error": "DNI, fecha y hora son requeridos"}), 400
     
     # Validar monto
    try:
        monto = float(monto)
        if monto < 0:
            return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    # Validar tipo de pago
    if monto == 0:
        tipo_pago = "obra_social"
    elif tipo_pago not in ["efectivo", "transferencia"]:
        return jsonify({"error": "Tipo de pago inválido. Debe ser 'efectivo' o 'transferencia'"}), 400

    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
     
    # Buscar el turno
    turno_encontrado = None

    for turno in turnos:
        if (turno["dni_paciente"] == dni_paciente and 
            turno["fecha"] == fecha and 
            turno["hora"] == hora):
            turno_encontrado = turno
            break
     
    if not turno_encontrado:
        return jsonify({"error": "Turno no encontrado"}), 404
        
    if turno_encontrado.get("estado") != "recepcionado":
        return jsonify({"error": "El paciente debe estar recepcionado primero"}), 400
        
    # Verificar que el paciente existe

    paciente = next((p for p in pacientes if p["dni"] == dni_paciente), None)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
     
    # Verificar si ya existe un pago para este paciente en esta fecha y hora
    pagos = cargar_json(PAGOS_FILE)
    pago_existente = next((p for p in pagos if p["dni_paciente"] == dni_paciente and p["fecha"] == fecha and p.get("hora") == hora), None)
    
    if pago_existente:
        return jsonify({"error": "Ya existe un pago registrado para este paciente en este turno"}), 400
    
    
    # Registrar el pago
    nuevo_pago = {
        "id": len(pagos) + 1,
        "dni_paciente": dni_paciente,
        "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
        "monto": monto,
        "fecha": fecha,
        "hora": hora,  # Guardar la hora del turno en el pago
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
        "observaciones": observaciones,
        "obra_social": paciente.get("obra_social", ""),
        "tipo_pago": tipo_pago  # Agregar tipo de pago
    }
     
    pagos.append(nuevo_pago)
    guardar_json(PAGOS_FILE, pagos)
    # Mover a sala de espera
    turno_encontrado["estado"] = "sala de espera"
    turno_encontrado["hora_sala_espera"] = datetime.now(timezone_ar).strftime("%H:%M")
    turno_encontrado["pago_registrado"] = True
    turno_encontrado["monto_pagado"] = monto
     
    guardar_json(TURNOS_FILE, turnos)

    return jsonify({
        "mensaje": "Paciente movido a sala de espera y pago registrado",
        "pago": nuevo_pago
    })
    
@app.route("/api/pagos/cobrar-y-sala", methods=["PUT"])
@login_requerido
@rol_permitido(["secretaria"])
def cobrar_y_mover_a_sala():
    """Cobrar a un paciente recepcionado y moverlo a sala de espera desde gestión de pagos"""
    data = request.json
    dni_paciente = data.get("dni_paciente")
    fecha = data.get("fecha")
    monto = data.get("monto", 0)
    observaciones = data.get("observaciones", "")
    
    if not all([dni_paciente, fecha]):
        return jsonify({"error": "DNI y fecha son requeridos"}), 400
    
    # Validar monto
    try:
        monto = float(monto)
        if monto < 0:
            return jsonify({"error": "El monto no puede ser negativo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Monto inválido"}), 400
    
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Buscar el turno recepcionado
    turno_encontrado = None
    for turno in turnos:
        if (turno["dni_paciente"] == dni_paciente and 
            turno["fecha"] == fecha and 
            turno.get("estado") == "recepcionado"):
            turno_encontrado = turno
            break

    if not turno_encontrado:
        return jsonify({"error": "No se encontró un turno recepcionado para este paciente en esta fecha"}), 404
    
    # Verificar que el paciente existe
    paciente = next((p for p in pacientes if p["dni"] == dni_paciente), None)
    if not paciente:
        return jsonify({"error": "Paciente no encontrado"}), 404
    
    # Verificar si ya existe un pago para este paciente en esta fecha
    pagos = cargar_json(PAGOS_FILE)
    pago_existente = next((p for p in pagos if p["dni_paciente"] == dni_paciente and p["fecha"] == fecha), None)
    
    if pago_existente:
        return jsonify({"error": "Ya existe un pago registrado para este paciente en esta fecha"}), 400
    # Determinar tipo de pago
    tipo_pago = data.get("tipo_pago", "efectivo")
    if monto == 0:
        tipo_pago = "obra_social"
    elif tipo_pago not in ["efectivo", "transferencia"]:
        return jsonify({"error": "Tipo de pago inválido"}), 400
    
    # Registrar el pago
    nuevo_pago = {
        "id": len(pagos) + 1,
        "dni_paciente": dni_paciente,
        "nombre_paciente": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
        "monto": monto,
        "fecha": fecha,
        "fecha_registro": datetime.now(timezone_ar).isoformat(),
        "observaciones": observaciones,
        "obra_social": paciente.get("obra_social", ""),
        "tipo_pago": tipo_pago
    }
    
    pagos.append(nuevo_pago)
    guardar_json(PAGOS_FILE, pagos)
    
    # Mover a sala de espera
    turno_encontrado["estado"] = "sala de espera"
    turno_encontrado["hora_sala_espera"] = datetime.now(timezone_ar).strftime("%H:%M")
    turno_encontrado["pago_registrado"] = True
    turno_encontrado["monto_pagado"] = monto
    
    guardar_json(TURNOS_FILE, turnos)
    return jsonify({
        "mensaje": "Pago registrado y paciente movido a sala de espera",
        "pago": nuevo_pago
    })

@app.route("/api/turnos/dia", methods=["GET"])
@login_requerido
@rol_permitido(["secretaria", "medico", "administrador"])
def obtener_turnos_dia():
    """Obtener todos los turnos de una fecha específica (por defecto hoy)"""
    fecha = request.args.get("fecha", date.today().isoformat())
    
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    turnos_dia = [t for t in turnos if t.get("fecha") == fecha]
    
    # Enriquecer con datos del paciente
    for turno in turnos_dia:
        paciente = next((p for p in pacientes if p["dni"] == turno["dni_paciente"]), {})
        turno["paciente"] = paciente
        if "estado" not in turno:
            turno["estado"] = "sin atender"
    
    # Ordenar por hora
    turnos_dia.sort(key=lambda t: t.get("hora", "00:00"))
    
    return jsonify(turnos_dia)

@app.route('/api/turnos/limpiar-vencidos', methods=['POST'])
@login_requerido
@rol_requerido('secretaria')
def limpiar_turnos_vencidos():
    
    turnos = cargar_json(TURNOS_FILE)
    ahora = datetime.now()
    nuevos = []
    eliminados = 0
    for t in turnos:
        fecha_hora_str = f"{t.get('fecha', '')} {t.get('hora', '00:00')}"
        try:
            fecha_hora = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
        except Exception:
            nuevos.append(t)
            continue
        if t.get('estado', '').lower() == 'sin atender' and fecha_hora < ahora - timedelta(hours=24):
            eliminados += 1
        else:
            nuevos.append(t)
    guardar_json(TURNOS_FILE, nuevos)
    return jsonify({"eliminados": eliminados, "ok": True})


# ========================== HISTORIAS CLÍNICAS ==================

@app.route("/historias-gestion")
@login_requerido
@rol_requerido("medico")
def ver_historias_gestion():
    return render_template("historias_gestion.html")

@app.route("/api/historias/buscar", methods=["GET"])
@login_requerido
@rol_requerido("medico")
def buscar_historias():
    historias = cargar_json(DATA_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Parámetros de búsqueda
    busqueda = request.args.get("busqueda", "").strip().lower()
    pagina = int(request.args.get("pagina", 1))
    por_pagina = int(request.args.get("por_pagina", 10))
    ordenar_por = request.args.get("ordenar_por", "apellido")
    orden = request.args.get("orden", "asc")
    
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

@app.route("/administrador")
@login_requerido
@rol_requerido("administrador")
def vista_administrador():
    return render_template("administrador.html")

@app.route("/api/pagos/estadisticas-admin", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_estadisticas_pagos_admin():
    """Obtener estadísticas de pagos para administradores"""
    mes = request.args.get("mes")
    if not mes:
        mes = datetime.now().strftime("%Y-%m")
    
    pagos = cargar_json(PAGOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Filtrar pagos del mes
    pagos_mes = [p for p in pagos if p.get("fecha", "").startswith(mes)]
    
    # Calcular estadísticas generales
    total_mes = sum(p.get("monto", 0) for p in pagos_mes)
    pagos_particulares = len([p for p in pagos_mes if p.get("monto", 0) > 0])
    pagos_obra_social = len([p for p in pagos_mes if p.get("monto", 0) == 0])
    cantidad_pagos_mes = len(pagos_mes)
    
    # Estadísticas por tipo de pago
    pagos_efectivo = [p for p in pagos_mes if p.get("tipo_pago") == "efectivo"]
    pagos_transferencia = [p for p in pagos_mes if p.get("tipo_pago") == "transferencia"]
    pagos_obra_social_list = [p for p in pagos_mes if p.get("tipo_pago") == "obra_social"]
    
    total_efectivo = sum(p.get("monto", 0) for p in pagos_efectivo)
    total_transferencia = sum(p.get("monto", 0) for p in pagos_transferencia)
    total_obra_social = sum(p.get("monto", 0) for p in pagos_obra_social_list)
    
    
    # Agrupar por día
    detalle_por_dia = {}
    for pago in pagos_mes:
        fecha = pago.get("fecha")
        if fecha not in detalle_por_dia:
            detalle_por_dia[fecha] = {
                "cantidad": 0,
                "monto": 0,
                "pacientes": []
            }
        detalle_por_dia[fecha]["cantidad"] += 1
        detalle_por_dia[fecha]["monto"] += pago.get("monto", 0)
        
        # Buscar datos del paciente
        paciente = next((p for p in pacientes if p["dni"] == pago.get("dni_paciente")), {})
        detalle_por_dia[fecha]["pacientes"].append({
            "nombre": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
            "monto": pago.get("monto", 0),
            "tipo_pago": pago.get("tipo_pago", "efectivo")
        })
    
    return jsonify({
        "total_mes": total_mes,
        "pagos_particulares": pagos_particulares,
        "pagos_obra_social": pagos_obra_social,
        "cantidad_pagos_mes": cantidad_pagos_mes,
        "detalle_por_dia": detalle_por_dia,
        # Nuevas estadísticas por tipo de pago
        "pagos_efectivo": len(pagos_efectivo),
        "pagos_transferencia": len(pagos_transferencia),
        "pagos_obra_social_count": len(pagos_obra_social_list),
        "total_efectivo": total_efectivo,
        "total_transferencia": total_transferencia,
        "total_obra_social": total_obra_social
    })

@app.route("/api/pagos/exportar-admin", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def exportar_pagos_csv_admin():
    """Exportar pagos a CSV para administradores"""
    
    pagos = cargar_json(PAGOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    fecha_param = request.args.get("fecha")
    mes = request.args.get("mes")
    pagos_filtrados = pagos
    nombre_archivo = "pagos"
    
    if fecha_param:
        try:
            fecha_dia = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        except ValueError:
            fecha_dia = date.today()
        pagos_filtrados = [p for p in pagos if p.get("fecha", "") == fecha_dia.isoformat()]
        nombre_archivo += f"_{fecha_dia.isoformat()}"
    elif mes:
        pagos_filtrados = [p for p in pagos if p.get("fecha", "").startswith(mes)]
        nombre_archivo += f"_{mes}"
    else:
        mes_actual = datetime.now().strftime("%Y-%m")
        pagos_filtrados = [p for p in pagos if p.get("fecha", "").startswith(mes_actual)]
        nombre_archivo += f"_{mes_actual}"
    
    # Calcular subtotales si es por día
    if fecha_param:
        subtotal_efectivo = sum(p["monto"] for p in pagos_filtrados if p.get("tipo_pago") == "efectivo")
        subtotal_transferencia = sum(p["monto"] for p in pagos_filtrados if p.get("tipo_pago") == "transferencia")
        subtotal_obra_social = sum(p["monto"] for p in pagos_filtrados if p.get("tipo_pago") == "obra_social")
        total = subtotal_efectivo + subtotal_transferencia
    
    # Crear CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Fecha', 'DNI', 'Nombre', 'Apellido', 'Monto', 'Tipo de Pago', 'Obra Social', 'Observaciones'])
    
    for pago in pagos_filtrados:
        paciente = next((p for p in pacientes if p["dni"] == pago.get("dni_paciente")), {})
        writer.writerow([
            pago.get("fecha", ""),
            pago.get("dni_paciente", ""),
            paciente.get("nombre", ""),
            paciente.get("apellido", ""),
            pago.get("monto", 0),
            pago.get("tipo_pago", "efectivo"),
            paciente.get("obra_social", ""),
            pago.get("observaciones", "")
        ])
    
    # Subtotales solo si es por día
    
    if fecha_param:
        writer.writerow([])
        writer.writerow(["", "", "", "", "Subtotal Efectivo", subtotal_efectivo, "", ""])
        writer.writerow(["", "", "", "", "Subtotal Transferencia", subtotal_transferencia, "", ""])
        writer.writerow(["", "", "", "", "Subtotal Obra Social", subtotal_obra_social, "", ""])
        writer.writerow(["", "", "", "", "TOTAL", total, "", ""])
    
    output.seek(0)
    return make_response(
        output.getvalue(),
        200,
        {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename={nombre_archivo}.csv'
        }
    )

# ======================= REPORTES PERSONALIZADOS =======================

@app.route("/api/reportes/personalizado", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def generar_reporte_personalizado():
    """Generar reporte personalizado con filtros de fecha, médico y obra social"""
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    medico = request.args.get("medico", "")
    obra_social = request.args.get("obra_social", "")
    formato = request.args.get("formato", "json")  # json, csv, excel
    
    if not fecha_inicio or not fecha_fin:
        return jsonify({"error": "Las fechas de inicio y fin son requeridas"}), 400
    
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
    
    if fecha_inicio_dt > fecha_fin_dt:
        return jsonify({"error": "La fecha de inicio no puede ser mayor que la fecha de fin"}), 400
    
    # Cargar datos
    turnos = cargar_json(TURNOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    pagos = cargar_json(PAGOS_FILE)
    
    # Filtrar turnos por fecha
    turnos_filtrados = []
    for turno in turnos:
        try:
            fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
            if fecha_inicio_dt <= fecha_turno <= fecha_fin_dt:
                turnos_filtrados.append(turno)
        except (ValueError, TypeError):
            continue
    
    # Aplicar filtros adicionales
    if medico:
        turnos_filtrados = [t for t in turnos_filtrados if t.get("medico") == medico]
    
    # Crear diccionario de pacientes para búsqueda rápida
    pacientes_dict = {p["dni"]: p for p in pacientes}
    
    # Procesar datos del reporte
    reporte_data = []
    pacientes_unicos = set()
    pacientes_atendidos = set()
    
    for turno in turnos_filtrados:
        dni_paciente = turno.get("dni_paciente")
        paciente = pacientes_dict.get(dni_paciente)
        
        if not paciente:
            continue
        
        # Aplicar filtro de obra social si se especifica (sin distinguir mayúsculas/minúsculas)
        if obra_social and paciente.get("obra_social", "").lower().strip() != obra_social.lower().strip():
            continue
        
        # Solo incluir pacientes que fueron atendidos
        if turno.get("estado") != "atendido":
            continue
        
        # Agregar a pacientes únicos (solo atendidos)
        pacientes_unicos.add(dni_paciente)
        
        # Agregar a pacientes atendidos
        pacientes_atendidos.add(dni_paciente)
        
        # Buscar pago correspondiente
        pago = next((p for p in pagos if 
                    p.get("dni_paciente") == dni_paciente and 
                    p.get("fecha") == turno.get("fecha")), None)
        
        reporte_data.append({
            "dni": dni_paciente,
            "nombre": paciente.get("nombre", ""),
            "apellido": paciente.get("apellido", ""),
            "obra_social": paciente.get("obra_social", ""),
            "numero_obra_social": paciente.get("numero_obra_social", ""),
            "fecha_turno": turno.get("fecha", ""),
            "hora_turno": turno.get("hora", ""),
            "medico": turno.get("medico", ""),
            "estado": turno.get("estado", "sin atender"),
            "monto_pagado": pago.get("monto", 0) if pago else 0,
            "tipo_pago": pago.get("tipo_pago", "obra_social") if pago else "obra_social"
        })
    
    # Estadísticas
    total_pacientes = len(pacientes_unicos)
    total_atendidos = len(pacientes_atendidos)
    
    # Ordenar por fecha y hora
    reporte_data.sort(key=lambda x: (x["fecha_turno"], x["hora_turno"]))
    
    resultado = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "medico_filtro": medico,
        "obra_social_filtro": obra_social,
        "total_pacientes": total_pacientes,
        "total_atendidos": total_atendidos,
        "total_consultas": len(reporte_data),
        "datos": reporte_data
    }
    
    # Si se solicita CSV o Excel, generar archivo
    if formato in ["csv", "excel"]:
        return generar_archivo_reporte_personalizado(resultado, formato)
    
    return jsonify(resultado)

def generar_archivo_reporte_personalizado(datos, formato):
    """Generar archivo CSV o Excel para el reporte personalizado"""
    import io
    from datetime import datetime
    
    # Crear archivo en memoria
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados
    writer.writerow([
        'DNI', 'Nombre', 'Apellido', 'Obra Social', 'Número Obra Social',
        'Fecha Turno', 'Hora Turno', 'Médico', 'Estado', 'Monto Pagado', 'Tipo Pago'
    ])
    
    # Datos
    for fila in datos["datos"]:
        writer.writerow([
            fila["dni"],
            fila["nombre"],
            fila["apellido"],
            fila["obra_social"],
            fila["numero_obra_social"],
            fila["fecha_turno"],
            fila["hora_turno"],
            fila["medico"],
            fila["estado"],
            fila["monto_pagado"],
            fila["tipo_pago"]
        ])
    
    # Agregar resumen
    writer.writerow([])
    writer.writerow(['RESUMEN', '', '', '', '', '', '', '', '', '', ''])
    writer.writerow(['Total Pacientes Únicos', datos["total_pacientes"], '', '', '', '', '', '', '', '', ''])
    writer.writerow(['Total Atendidos', datos["total_atendidos"], '', '', '', '', '', '', '', '', ''])
    writer.writerow(['Total Consultas', datos["total_consultas"], '', '', '', '', '', '', '', '', ''])
    
    # Preparar respuesta
    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Construir nombre del archivo con información del filtro
    nombre_base = "reporte_personalizado"
    
    # Agregar médico si hay filtro
    if datos.get("medico_filtro"):
        medico_limpio = datos["medico_filtro"].replace(" ", "_").lower()
        nombre_base += f"_{medico_limpio}"
    
    # Agregar obra social si hay filtro
    if datos.get("obra_social_filtro"):
        obra_social_limpia = datos["obra_social_filtro"].replace(" ", "_").lower()
        nombre_base += f"_{obra_social_limpia}"
    
    # Agregar fechas
    fecha_inicio_limpia = datos["fecha_inicio"].replace("-", "")
    fecha_fin_limpia = datos["fecha_fin"].replace("-", "")
    nombre_base += f"_{fecha_inicio_limpia}_{fecha_fin_limpia}"
    
    nombre_archivo = f"{nombre_base}_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={nombre_archivo}"
    response.headers["Content-type"] = "text/csv"
    
    return response

@app.route("/api/obras-sociales", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_obras_sociales():
    """Obtener lista de obras sociales para filtros"""
    pacientes = cargar_json(PACIENTES_FILE)
    obras_sociales = set()
    
    for paciente in pacientes:
        obra_social = paciente.get("obra_social", "").strip()
        if obra_social and obra_social != "0":
            # Normalizar: primera letra mayúscula, resto minúsculas
            obra_social_normalizada = obra_social.capitalize()
            obras_sociales.add(obra_social_normalizada)
    
    obras_sociales_list = sorted(list(obras_sociales))
    return jsonify(obras_sociales_list)

@app.route("/api/medicos", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_medicos():
    """Obtener lista de médicos que han atendido pacientes"""
    turnos = cargar_json(TURNOS_FILE)
    medicos = set()
    
    for turno in turnos:
        medico = turno.get("medico", "").strip()
        if medico:
            medicos.add(medico)
    
    medicos_list = sorted(list(medicos))
    return jsonify(medicos_list)

# ======================= REPORTES DE TURNOS =======================

@app.route("/api/reportes/turnos", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_reporte_turnos():
    """Obtener reporte de turnos por período"""
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    medico = request.args.get("medico", "")
    
    if not fecha_inicio or not fecha_fin:
        return jsonify({"error": "Las fechas de inicio y fin son requeridas"}), 400
    
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
    
    # Cargar datos
    turnos = cargar_json(TURNOS_FILE)
    
    # Filtrar turnos por fecha
    turnos_filtrados = []
    for turno in turnos:
        try:
            fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
            if fecha_inicio_dt <= fecha_turno <= fecha_fin_dt:
                turnos_filtrados.append(turno)
        except (ValueError, TypeError):
            continue
    
    # Aplicar filtro de médico si se especifica
    if medico:
        turnos_filtrados = [t for t in turnos_filtrados if t.get("medico") == medico]
    
    # Calcular estadísticas (considerando turnos vencidos como ausentes)
    total_turnos = len(turnos_filtrados)
    turnos_atendidos = len([t for t in turnos_filtrados if t.get("estado") == "atendido"])
    
    # Contar ausentes reales + turnos vencidos (más de 24 horas sin atender)
    turnos_ausentes_reales = len([t for t in turnos_filtrados if t.get("estado") == "ausente"])
    turnos_vencidos = 0
    ahora = datetime.now()
    
    for turno in turnos_filtrados:
        if turno.get("estado") in ["sin atender", "recepcionado", "sala de espera"]:
            try:
                fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
                hora_turno = turno.get("hora", "00:00")
                fecha_hora_turno = datetime.combine(fecha_turno, datetime.strptime(hora_turno, "%H:%M").time())
                
                # Si el turno pasó hace más de 24 horas y no fue atendido, considerarlo ausente
                if (ahora - fecha_hora_turno).total_seconds() > 24 * 3600:
                    turnos_vencidos += 1
            except (ValueError, TypeError):
                continue
    
    turnos_ausentes = turnos_ausentes_reales + turnos_vencidos
    turnos_pendientes = len([t for t in turnos_filtrados if t.get("estado") in ["sin atender", "recepcionado", "sala de espera"]]) - turnos_vencidos
    
    # Estadísticas por médico (considerando turnos vencidos)
    stats_por_medico = {}
    for turno in turnos_filtrados:
        medico_nombre = turno.get("medico", "Sin médico")
        if medico_nombre not in stats_por_medico:
            stats_por_medico[medico_nombre] = {"total": 0, "atendidos": 0, "ausentes": 0}
        
        stats_por_medico[medico_nombre]["total"] += 1
        if turno.get("estado") == "atendido":
            stats_por_medico[medico_nombre]["atendidos"] += 1
        elif turno.get("estado") == "ausente":
            stats_por_medico[medico_nombre]["ausentes"] += 1
        elif turno.get("estado") in ["sin atender", "recepcionado", "sala de espera"]:
            # Verificar si el turno está vencido (más de 24 horas)
            try:
                fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
                hora_turno = turno.get("hora", "00:00")
                fecha_hora_turno = datetime.combine(fecha_turno, datetime.strptime(hora_turno, "%H:%M").time())
                
                if (ahora - fecha_hora_turno).total_seconds() > 24 * 3600:
                    stats_por_medico[medico_nombre]["ausentes"] += 1
            except (ValueError, TypeError):
                pass
    
    # Estadísticas por día (considerando turnos vencidos)
    stats_por_dia = {}
    for turno in turnos_filtrados:
        fecha = turno.get("fecha", "")
        if fecha not in stats_por_dia:
            stats_por_dia[fecha] = {"total": 0, "atendidos": 0, "ausentes": 0}
        
        stats_por_dia[fecha]["total"] += 1
        if turno.get("estado") == "atendido":
            stats_por_dia[fecha]["atendidos"] += 1
        elif turno.get("estado") == "ausente":
            stats_por_dia[fecha]["ausentes"] += 1
        elif turno.get("estado") in ["sin atender", "recepcionado", "sala de espera"]:
            # Verificar si el turno está vencido (más de 24 horas)
            try:
                fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
                hora_turno = turno.get("hora", "00:00")
                fecha_hora_turno = datetime.combine(fecha_turno, datetime.strptime(hora_turno, "%H:%M").time())
                
                if (ahora - fecha_hora_turno).total_seconds() > 24 * 3600:
                    stats_por_dia[fecha]["ausentes"] += 1
            except (ValueError, TypeError):
                pass
    
    # Calcular porcentajes
    porcentaje_atencion = round((turnos_atendidos / total_turnos * 100) if total_turnos > 0 else 0, 1)
    porcentaje_ausencias = round((turnos_ausentes / total_turnos * 100) if total_turnos > 0 else 0, 1)
    
    return jsonify({
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "medico_filtro": medico,
        "total_turnos": total_turnos,
        "turnos_atendidos": turnos_atendidos,
        "turnos_ausentes": turnos_ausentes,
        "turnos_ausentes_reales": turnos_ausentes_reales,
        "turnos_vencidos": turnos_vencidos,
        "turnos_pendientes": turnos_pendientes,
        "porcentaje_atencion": porcentaje_atencion,
        "porcentaje_ausencias": porcentaje_ausencias,
        "stats_por_medico": stats_por_medico,
        "stats_por_dia": stats_por_dia
    })

@app.route("/api/reportes/pacientes", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_reporte_pacientes():
    """Obtener reporte de pacientes"""
    pacientes = cargar_json(PACIENTES_FILE)
    turnos = cargar_json(TURNOS_FILE)
    
    # Estadísticas básicas
    total_pacientes = len(pacientes)
    
    # Pacientes con turnos
    dnis_con_turnos = set(t.get("dni_paciente") for t in turnos)
    pacientes_sin_turnos = total_pacientes - len(dnis_con_turnos)
    
    # Estadísticas por obra social (normalizadas)
    obras_sociales = {}
    for paciente in pacientes:
        obra_social = paciente.get("obra_social", "Sin obra social")
        if obra_social == "0" or not obra_social:
            obra_social = "Particular"
        else:
            # Normalizar: primera letra mayúscula, resto minúsculas
            obra_social = obra_social.capitalize()
        obras_sociales[obra_social] = obras_sociales.get(obra_social, 0) + 1
    
    # Estadísticas por edad
    edades = []
    rangos_edad = {
        "0-18": 0,
        "19-30": 0,
        "31-50": 0,
        "51-65": 0,
        "65+": 0
    }
    
    for paciente in pacientes:
        # Calcular edad dinámicamente
        if paciente.get("fecha_nacimiento"):
            edad = calcular_edad(paciente["fecha_nacimiento"])
            if edad:
                edades.append(edad)
                if edad <= 18:
                    rangos_edad["0-18"] += 1
                elif edad <= 30:
                    rangos_edad["19-30"] += 1
                elif edad <= 50:
                    rangos_edad["31-50"] += 1
                elif edad <= 65:
                    rangos_edad["51-65"] += 1
                else:
                    rangos_edad["65+"] += 1
    
    edad_promedio = round(sum(edades) / len(edades), 1) if edades else 0
    
    # Pacientes más activos (por número de turnos)
    turnos_por_paciente = {}
    for turno in turnos:
        dni = turno.get("dni_paciente")
        if dni:
            turnos_por_paciente[dni] = turnos_por_paciente.get(dni, 0) + 1
    
    pacientes_activos = []
    for dni, cantidad_turnos in sorted(turnos_por_paciente.items(), key=lambda x: x[1], reverse=True)[:10]:
        paciente = next((p for p in pacientes if p.get("dni") == dni), None)
        if paciente:
            pacientes_activos.append({
                "nombre": f"{paciente.get('nombre', '')} {paciente.get('apellido', '')}".strip(),
                "turnos": cantidad_turnos
            })
    
    return jsonify({
        "total_pacientes": total_pacientes,
        "pacientes_sin_turnos": pacientes_sin_turnos,
        "obras_sociales": obras_sociales,
        "estadisticas_edad": {
            "promedio": edad_promedio,
            "rangos": rangos_edad
        },
        "pacientes_activos": pacientes_activos
    })

@app.route("/api/reportes/ocupacion", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_reporte_ocupacion():
    """Obtener reporte de ocupación de agenda"""
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    
    if not fecha_inicio or not fecha_fin:
        # Por defecto, últimos 7 días
        fecha_fin = date.today().isoformat()
        fecha_inicio = (date.today() - timedelta(days=7)).isoformat()
    
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
    
    # Cargar datos
    turnos = cargar_json(TURNOS_FILE)
    agenda = cargar_json(AGENDA_FILE)
    
    # Filtrar turnos por fecha
    turnos_filtrados = []
    for turno in turnos:
        try:
            fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
            if fecha_inicio_dt <= fecha_turno <= fecha_fin_dt:
                turnos_filtrados.append(turno)
        except (ValueError, TypeError):
            continue
    
    # Calcular ocupación por médico
    ocupacion_por_medico = {}
    total_slots_disponibles = 0
    total_slots_ocupados = 0
    
    for medico, horarios_medico in agenda.items():
        slots_disponibles = 0
        slots_ocupados = 0
        
        # Contar slots disponibles en la agenda
        for dia, horarios in horarios_medico.items():
            if isinstance(horarios, list):
                slots_disponibles += len(horarios)
        
        # Contar slots ocupados por turnos
        turnos_medico = [t for t in turnos_filtrados if t.get("medico") == medico]
        slots_ocupados = len(turnos_medico)
        
        porcentaje_ocupacion = round((slots_ocupados / slots_disponibles * 100) if slots_disponibles > 0 else 0, 1)
        
        ocupacion_por_medico[medico] = {
            "slots_disponibles": slots_disponibles,
            "slots_ocupados": slots_ocupados,
            "porcentaje_ocupacion": porcentaje_ocupacion
        }
        
        total_slots_disponibles += slots_disponibles
        total_slots_ocupados += slots_ocupados
    
    # Calcular ocupación por día
    ocupacion_por_dia = {}
    for turno in turnos_filtrados:
        fecha = turno.get("fecha", "")
        if fecha not in ocupacion_por_dia:
            ocupacion_por_dia[fecha] = {"slots_disponibles": 0, "slots_ocupados": 0}
        ocupacion_por_dia[fecha]["slots_ocupados"] += 1
    
    # Calcular slots disponibles por día (aproximado)
    dias_semana = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
    for fecha_str in ocupacion_por_dia.keys():
        try:
            fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            dia_semana = fecha_obj.strftime("%A").upper()
            if dia_semana == "MONDAY":
                dia_es = "LUNES"
            elif dia_semana == "TUESDAY":
                dia_es = "MARTES"
            elif dia_semana == "WEDNESDAY":
                dia_es = "MIERCOLES"
            elif dia_semana == "THURSDAY":
                dia_es = "JUEVES"
            elif dia_semana == "FRIDAY":
                dia_es = "VIERNES"
            else:
                dia_es = None
            
            if dia_es:
                slots_dia = 0
                for medico, horarios_medico in agenda.items():
                    if dia_es in horarios_medico and isinstance(horarios_medico[dia_es], list):
                        slots_dia += len(horarios_medico[dia_es])
                ocupacion_por_dia[fecha_str]["slots_disponibles"] = slots_dia
        except:
            pass
    
    # Calcular porcentajes de ocupación por día
    for fecha in ocupacion_por_dia:
        stats = ocupacion_por_dia[fecha]
        stats["porcentaje_ocupacion"] = round((stats["slots_ocupados"] / stats["slots_disponibles"] * 100) if stats["slots_disponibles"] > 0 else 0, 1)
    
    # Ocupación promedio general
    ocupacion_promedio = round((total_slots_ocupados / total_slots_disponibles * 100) if total_slots_disponibles > 0 else 0, 1)
    
    return jsonify({
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "ocupacion_promedio": ocupacion_promedio,
        "total_slots_disponibles": total_slots_disponibles,
        "total_slots_ocupados": total_slots_ocupados,
        "ocupacion_por_medico": ocupacion_por_medico,
        "ocupacion_por_dia": ocupacion_por_dia
    })

@app.route("/api/reportes/dashboard-ejecutivo", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_dashboard_ejecutivo():
    """Obtener dashboard ejecutivo con métricas clave"""
    # Obtener datos de múltiples fuentes
    pacientes = cargar_json(PACIENTES_FILE)
    turnos = cargar_json(TURNOS_FILE)
    pagos = cargar_json(PAGOS_FILE)
    agenda = cargar_json(AGENDA_FILE)
    
    # Fecha actual para cálculos
    hoy = date.today()
    mes_actual = hoy.strftime("%Y-%m")
    
    # === MÉTRICAS DE PACIENTES ===
    total_pacientes = len(pacientes)
    
    # Pacientes con turnos
    dnis_con_turnos = set(t.get("dni_paciente") for t in turnos)
    pacientes_activos = len(dnis_con_turnos)
    pacientes_sin_turnos = total_pacientes - pacientes_activos
    
    # Edad promedio (calculada dinámicamente)
    edades = []
    for p in pacientes:
        if p.get("fecha_nacimiento"):
            edad = calcular_edad(p["fecha_nacimiento"])
            if edad and edad > 0:
                edades.append(edad)
    edad_promedio = round(sum(edades) / len(edades), 1) if edades else 0
    
    # === MÉTRICAS DE TURNOS DEL MES ===
    turnos_mes = [t for t in turnos if t.get("fecha", "").startswith(mes_actual)]
    total_turnos_mes = len(turnos_mes)
    turnos_atendidos_mes = len([t for t in turnos_mes if t.get("estado") == "atendido"])
    
    # Calcular turnos vencidos como ausentes
    turnos_ausentes_reales = len([t for t in turnos_mes if t.get("estado") == "ausente"])
    turnos_vencidos = 0
    ahora = datetime.now()
    
    for turno in turnos_mes:
        if turno.get("estado") in ["sin atender", "recepcionado", "sala de espera"]:
            try:
                fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
                hora_turno = turno.get("hora", "00:00")
                fecha_hora_turno = datetime.combine(fecha_turno, datetime.strptime(hora_turno, "%H:%M").time())
                
                if (ahora - fecha_hora_turno).total_seconds() > 24 * 3600:
                    turnos_vencidos += 1
            except (ValueError, TypeError):
                continue
    
    turnos_ausentes_mes = turnos_ausentes_reales + turnos_vencidos
    porcentaje_atencion = round((turnos_atendidos_mes / total_turnos_mes * 100) if total_turnos_mes > 0 else 0, 1)
    
    # === MÉTRICAS DE OCUPACIÓN ===
    # Calcular ocupación promedio (últimos 7 días)
    fecha_fin_ocupacion = hoy.isoformat()
    fecha_inicio_ocupacion = (hoy - timedelta(days=7)).isoformat()
    
    turnos_ocupacion = [t for t in turnos if fecha_inicio_ocupacion <= t.get("fecha", "") <= fecha_fin_ocupacion]
    
    total_slots_disponibles = 0
    total_slots_ocupados = len(turnos_ocupacion)
    
    for medico, horarios_medico in agenda.items():
        for dia, horarios in horarios_medico.items():
            if isinstance(horarios, list):
                total_slots_disponibles += len(horarios)
    
    ocupacion_promedio = round((total_slots_ocupados / total_slots_disponibles * 100) if total_slots_disponibles > 0 else 0, 1)
    
    # === MÉTRICAS DE INGRESOS ===
    pagos_mes = [p for p in pagos if p.get("fecha", "").startswith(mes_actual)]
    total_ingresos_mes = sum(p.get("monto", 0) for p in pagos_mes)
    cantidad_pagos_mes = len(pagos_mes)
    
    # === ESTADÍSTICAS POR MÉDICO ===
    stats_por_medico = {}
    for turno in turnos_mes:
        medico_nombre = turno.get("medico", "Sin médico")
        if medico_nombre not in stats_por_medico:
            stats_por_medico[medico_nombre] = {"total": 0, "atendidos": 0, "ausentes": 0}
        
        stats_por_medico[medico_nombre]["total"] += 1
        if turno.get("estado") == "atendido":
            stats_por_medico[medico_nombre]["atendidos"] += 1
        elif turno.get("estado") == "ausente":
            stats_por_medico[medico_nombre]["ausentes"] += 1
        elif turno.get("estado") in ["sin atender", "recepcionado", "sala de espera"]:
            # Verificar si el turno está vencido
            try:
                fecha_turno = datetime.strptime(turno.get("fecha", ""), "%Y-%m-%d").date()
                hora_turno = turno.get("hora", "00:00")
                fecha_hora_turno = datetime.combine(fecha_turno, datetime.strptime(hora_turno, "%H:%M").time())
                
                if (ahora - fecha_hora_turno).total_seconds() > 24 * 3600:
                    stats_por_medico[medico_nombre]["ausentes"] += 1
            except (ValueError, TypeError):
                pass
    
    # Calcular eficiencia por médico
    medicos_eficiencia = {}
    for medico, stats in stats_por_medico.items():
        eficiencia = round((stats["atendidos"] / stats["total"] * 100) if stats["total"] > 0 else 0, 1)
        medicos_eficiencia[medico] = {
            "total": stats["total"],
            "atendidos": stats["atendidos"],
            "eficiencia": eficiencia
        }
    
    # === DISTRIBUCIÓN POR OBRA SOCIAL ===
    obras_sociales = {}
    for paciente in pacientes:
        obra_social = paciente.get("obra_social", "Sin obra social")
        if obra_social == "0" or not obra_social:
            obra_social = "Particular"
        else:
            obra_social = obra_social.capitalize()
        obras_sociales[obra_social] = obras_sociales.get(obra_social, 0) + 1
    
    return jsonify({
        "fecha_consulta": hoy.isoformat(),
        "mes_actual": mes_actual,
        
        # Métricas de pacientes
        "total_pacientes": total_pacientes,
        "pacientes_activos": pacientes_activos,
        "pacientes_sin_turnos": pacientes_sin_turnos,
        "edad_promedio": edad_promedio,
        
        # Métricas de turnos
        "total_turnos_mes": total_turnos_mes,
        "turnos_atendidos_mes": turnos_atendidos_mes,
        "turnos_ausentes_mes": turnos_ausentes_mes,
        "turnos_vencidos": turnos_vencidos,
        "porcentaje_atencion": porcentaje_atencion,
        
        # Métricas de ocupación
        "ocupacion_promedio": ocupacion_promedio,
        "total_slots_disponibles": total_slots_disponibles,
        "total_slots_ocupados": total_slots_ocupados,
        
        # Métricas de ingresos
        "total_ingresos_mes": total_ingresos_mes,
        "cantidad_pagos_mes": cantidad_pagos_mes,
        
        # Estadísticas detalladas
        "medicos_eficiencia": medicos_eficiencia,
        "obras_sociales": obras_sociales
    })

@app.route("/api/reportes/ingresos-anual", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def generar_reporte_ingresos_anual():
    """Generar reporte de ingresos anual (descarga directa)"""
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    
    if not fecha_inicio or not fecha_fin:
        return jsonify({"error": "Las fechas de inicio y fin son requeridas"}), 400
    
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
    
    # Cargar datos
    pagos = cargar_json(PAGOS_FILE)
    pacientes = cargar_json(PACIENTES_FILE)
    
    # Filtrar pagos por fecha
    pagos_filtrados = []
    for pago in pagos:
        try:
            fecha_pago = datetime.strptime(pago.get("fecha", ""), "%Y-%m-%d").date()
            if fecha_inicio_dt <= fecha_pago <= fecha_fin_dt:
                pagos_filtrados.append(pago)
        except (ValueError, TypeError):
            continue
    
    # Crear diccionario de pacientes para búsqueda rápida
    pacientes_dict = {p["dni"]: p for p in pacientes}
    
    # Procesar datos del reporte
    reporte_data = []
    total_ingresos = 0
    total_efectivo = 0
    total_transferencia = 0
    total_obra_social = 0
    
    for pago in pagos_filtrados:
        dni_paciente = pago.get("dni_paciente")
        paciente = pacientes_dict.get(dni_paciente, {})
        
        monto = pago.get("monto", 0)
        tipo_pago = pago.get("tipo_pago", "efectivo")
        
        # Acumular totales
        total_ingresos += monto
        if tipo_pago == "efectivo":
            total_efectivo += monto
        elif tipo_pago == "transferencia":
            total_transferencia += monto
        elif tipo_pago == "obra_social":
            total_obra_social += 1  # Contar consultas, no monto
        
        reporte_data.append({
            "fecha": pago.get("fecha", ""),
            "dni": dni_paciente,
            "nombre": paciente.get("nombre", ""),
            "apellido": paciente.get("apellido", ""),
            "obra_social": paciente.get("obra_social", ""),
            "numero_obra_social": paciente.get("numero_obra_social", ""),
            "monto": monto,
            "tipo_pago": tipo_pago,
            "observaciones": pago.get("observaciones", "")
        })
    
    # Ordenar por fecha
    reporte_data.sort(key=lambda x: x["fecha"])
    
    # Crear archivo CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Encabezados
    writer.writerow([
        'Fecha', 'DNI', 'Nombre', 'Apellido', 'Obra Social', 'Número Obra Social',
        'Monto', 'Tipo Pago', 'Observaciones'
    ])
    
    # Datos
    for fila in reporte_data:
        writer.writerow([
            fila["fecha"],
            fila["dni"],
            fila["nombre"],
            fila["apellido"],
            fila["obra_social"],
            fila["numero_obra_social"],
            fila["monto"],
            fila["tipo_pago"],
            fila["observaciones"]
        ])
    
    # Agregar resumen
    writer.writerow([])
    writer.writerow(['RESUMEN ANUAL', '', '', '', '', '', '', '', ''])
    writer.writerow(['Total Ingresos', '', '', '', '', '', total_ingresos, '', ''])
    writer.writerow(['Total Efectivo', '', '', '', '', '', total_efectivo, '', ''])
    writer.writerow(['Total Transferencia', '', '', '', '', '', total_transferencia, '', ''])
    writer.writerow(['Consultas Obra Social', '', '', '', '', '', total_obra_social, '', ''])
    writer.writerow(['Total Pagos', '', '', '', '', '', len(pagos_filtrados), '', ''])
    
    # Preparar respuesta
    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"ingresos_anual_{fecha_inicio}_{fecha_fin}_{timestamp}.csv"
    
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename={nombre_archivo}"
    response.headers["Content-type"] = "text/csv"
    
    return response

@app.route("/api/reportes/ingresos-anual-data", methods=["GET"])
@login_requerido
@rol_requerido("administrador")
def obtener_ingresos_anual_data():
    """Obtener solo el total de ingresos anuales para mostrar en el dashboard"""
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")
    
    if not fecha_inicio or not fecha_fin:
        return jsonify({"error": "Fechas requeridas"}), 400
    
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400
    
    try:
        with open(PAGOS_FILE, 'r', encoding='utf-8') as f:
            pagos = json.load(f)
    except FileNotFoundError:
        return jsonify({"error": "Archivo de pagos no encontrado"}), 404
    
    # Filtrar pagos por rango de fechas
    pagos_filtrados = []
    for pago in pagos:
        try:
            fecha_pago = datetime.strptime(pago.get("fecha", ""), "%Y-%m-%d").date()
            if fecha_inicio_dt <= fecha_pago <= fecha_fin_dt:
                pagos_filtrados.append(pago)
        except (ValueError, TypeError):
            continue
    
    # Calcular total de ingresos y desglose por tipo
    total_ingresos = 0
    total_efectivo = 0
    total_transferencia = 0
    
    for pago in pagos_filtrados:
        monto = pago.get("monto", 0)
        tipo_pago = pago.get("tipo_pago", "obra_social")
        
        total_ingresos += monto
        
        if tipo_pago == "efectivo":
            total_efectivo += monto
        elif tipo_pago == "transferencia":
            total_transferencia += monto
    
    return jsonify({
        "total_ingresos": total_ingresos,
        "total_efectivo": total_efectivo,
        "total_transferencia": total_transferencia
    })

# ====================================================


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)