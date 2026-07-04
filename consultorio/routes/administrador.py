import csv
import io
import os
import zipfile
from datetime import date, datetime

from flask import Blueprint, jsonify, make_response, render_template, request, send_file
from werkzeug.security import generate_password_hash

from consultorio.auth.decorators import login_requerido, rol_requerido
from consultorio.paths import (
    AGENDA_FILE,
    DATA_FILE,
    DIAS_AGENDA,
    PACIENTES_FILE,
    PAGOS_FILE,
    TURNOS_FILE,
    USUARIOS_FILE,
    timezone_ar,
)
from consultorio.storage import cargar_json, guardar_json

bp = Blueprint("administrador", __name__)


@bp.route("/administrador", endpoint="vista_administrador")
@login_requerido
@rol_requerido("administrador")
def vista_administrador():
    return render_template("administrador.html")


def _agenda_vacia_medico():
    return {dia: [] for dia in DIAS_AGENDA}


@bp.route("/api/usuarios", methods=["GET"], endpoint="listar_usuarios")
@login_requerido
@rol_requerido("administrador")
def listar_usuarios():
    usuarios = cargar_json(USUARIOS_FILE)
    if not isinstance(usuarios, list):
        usuarios = []
    agenda = cargar_json(AGENDA_FILE)
    if not isinstance(agenda, dict):
        agenda = {}
    return jsonify([
        {"usuario": u.get("usuario"), "rol": u.get("rol"), "en_agenda": u.get("usuario") in agenda}
        for u in usuarios
        if u.get("usuario")
    ])



@bp.route("/api/usuarios", methods=["POST"], endpoint="crear_usuario_api")
@login_requerido
@rol_requerido("administrador")
def crear_usuario_api():
    data = request.json or {}
    usuario = (data.get("usuario") or "").strip()
    contrasena = data.get("contrasena") or ""
    rol = (data.get("rol") or "").strip().lower()

    if not usuario:
        return jsonify({"error": "El nombre de usuario es obligatorio"}), 400
    if len(contrasena) < 4:
        return jsonify({"error": "La contraseña debe tener al menos 4 caracteres"}), 400
    if rol not in ("medico", "secretaria"):
        return jsonify({"error": "El rol debe ser 'medico' o 'secretaria'"}), 400

    usuarios = cargar_json(USUARIOS_FILE)
    if not isinstance(usuarios, list):
        usuarios = []
    if any(u.get("usuario") == usuario for u in usuarios):
        return jsonify({"error": f"El usuario '{usuario}' ya existe"}), 400

    usuarios.append({
        "usuario": usuario,
        "contrasena": generate_password_hash(contrasena),
        "rol": rol,
    })
    guardar_json(USUARIOS_FILE, usuarios)

    en_agenda = False
    if rol == "medico":
        agenda = cargar_json(AGENDA_FILE)
        if not isinstance(agenda, dict):
            agenda = {}
        if usuario not in agenda:
            agenda[usuario] = _agenda_vacia_medico()
            guardar_json(AGENDA_FILE, agenda)
            en_agenda = True
        else:
            en_agenda = True

    mensaje = f"Usuario '{usuario}' creado como {rol}."
    if rol == "medico":
        mensaje += " Ya está disponible en la agenda para configurar horarios."
    return jsonify({"mensaje": mensaje, "usuario": usuario, "rol": rol, "en_agenda": en_agenda}), 201



@bp.route("/administrador/backup-datos", methods=["GET"], endpoint="descargar_backup_datos")
@login_requerido
@rol_requerido("administrador")
def descargar_backup_datos():
    """ZIP con pagos, historias clínicas, turnos y pacientes para respaldo manual."""
    parejas = [
        (PAGOS_FILE, "pagos.json"),
        (DATA_FILE, "historias_clinicas.json"),
        (TURNOS_FILE, "turnos.json"),
        (PACIENTES_FILE, "pacientes.json"),
    ]
    buf = io.BytesIO()
    agregados = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta, nombre_en_zip in parejas:
            if os.path.isfile(ruta):
                zf.write(ruta, arcname=nombre_en_zip)
                agregados += 1
    if agregados == 0:
        return jsonify({"error": "No se encontró ningún archivo de datos para respaldar."}), 404
    buf.seek(0)
    stamp = datetime.now(timezone_ar).strftime("%Y%m%d_%H%M")
    nombre_zip = f"backup_consultorio_{stamp}.zip"
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=nombre_zip,
    )



@bp.route("/api/pagos/estadisticas-admin", methods=["GET"], endpoint="obtener_estadisticas_pagos_admin")
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


@bp.route("/api/pagos/exportar-admin", methods=["GET"], endpoint="exportar_pagos_csv_admin")
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
