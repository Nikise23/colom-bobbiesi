import csv
import io
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, make_response, request

from consultorio.auth.decorators import login_requerido, rol_requerido
from consultorio.paths import AGENDA_FILE, PACIENTES_FILE, PAGOS_FILE, TURNOS_FILE
from consultorio.storage import cargar_json
from consultorio.utils.helpers import calcular_edad

bp = Blueprint("reportes", __name__)


@bp.route("/api/reportes/personalizado", methods=["GET"], endpoint="generar_reporte_personalizado")
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

@bp.route("/api/obras-sociales", methods=["GET"], endpoint="obtener_obras_sociales")
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


@bp.route("/api/medicos", methods=["GET"], endpoint="obtener_medicos")
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


@bp.route("/api/reportes/turnos", methods=["GET"], endpoint="obtener_reporte_turnos")
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


@bp.route("/api/reportes/pacientes", methods=["GET"], endpoint="obtener_reporte_pacientes")
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


@bp.route("/api/reportes/ocupacion", methods=["GET"], endpoint="obtener_reporte_ocupacion")
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
            elif dia_semana == "SATURDAY":
                dia_es = "SABADO"
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


@bp.route("/api/reportes/dashboard-ejecutivo", methods=["GET"], endpoint="obtener_dashboard_ejecutivo")
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


@bp.route("/api/reportes/ingresos-anual", methods=["GET"], endpoint="generar_reporte_ingresos_anual")
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


@bp.route("/api/reportes/ingresos-anual-data", methods=["GET"], endpoint="obtener_ingresos_anual_data")
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
