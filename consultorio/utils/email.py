"""Envío de emails por SMTP (aviso de turnos online, etc.)."""

from __future__ import annotations

import logging
import os
import re
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

# Formato básico: local@dominio.tld (sin espacios)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def smtp_configured() -> bool:
    return bool(
        os.environ.get("SMTP_HOST", "").strip()
        and os.environ.get("SMTP_USER", "").strip()
        and os.environ.get("SMTP_PASS", "").strip()
    )


def validar_email(valor: str | None) -> tuple[str | None, str | None]:
    """
    Normaliza y valida un email opcional.
    Devuelve (email_normalizado | None, error | None).
    None/vacío → (None, None) — no hay email, no es error.
    """
    if valor is None:
        return None, None
    email = str(valor).strip()
    if not email:
        return None, None
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return None, "Email inválido"
    return email.lower(), None


def enviar_email(asunto: str, cuerpo: str, destino: str | None = None) -> bool:
    """
    Envía un email de texto plano.
    Devuelve True si se envió; False si no hay config o falló (nunca lanza).
    No registra SMTP_PASS en logs.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    if not host or not user or not password:
        logger.warning(
            "SMTP no configurado (faltan SMTP_HOST, SMTP_USER o SMTP_PASS); "
            "se omite el envío de email."
        )
        return False

    to_addr = (destino or os.environ.get("SMTP_TO", "") or user).strip()
    from_addr = (os.environ.get("SMTP_FROM", "") or user).strip()
    try:
        port = int(os.environ.get("SMTP_PORT", "587") or "587")
    except ValueError:
        port = 587
    secure = os.environ.get("SMTP_SECURE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(cuerpo)

    try:
        if secure:
            with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(msg)
        logger.info("Email enviado a %s: %s", to_addr, asunto)
        return True
    except Exception:
        # No incluir password ni detalles sensibles
        logger.exception(
            "Error al enviar email (asunto=%r, destino=%s)", asunto, to_addr
        )
        return False


def _cuerpo_aviso_consultorio(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
    paciente_nuevo: bool,
    email_paciente: str | None,
) -> str:
    lineas = [
        "Se reservó un turno desde el sitio web.",
        "",
        f"Médico: {medico}",
        f"Fecha: {fecha}",
        f"Hora: {hora}",
        f"DNI: {paciente.get('dni', '')}",
        "",
    ]
    if paciente_nuevo:
        lineas.extend(
            [
                "Paciente nuevo:",
                f"  Nombre: {paciente.get('nombre', '')}",
                f"  Apellido: {paciente.get('apellido', '')}",
                f"  Celular: {paciente.get('celular', '')}",
                f"  Obra social: {paciente.get('obra_social', '')}",
                f"  N° afiliado: {paciente.get('numero_obra_social', '')}",
                f"  Fecha de nacimiento: {paciente.get('fecha_nacimiento', '')}",
                "",
            ]
        )
    else:
        lineas.extend(["Paciente habitual", ""])

    if email_paciente:
        lineas.append(f"Email de confirmación (paciente): {email_paciente}")
        lineas.append("")

    lineas.append("Origen: Turno web / API pública")
    return "\n".join(lineas)


def _cuerpo_confirmacion_paciente(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
) -> str:
    nombre = (paciente.get("nombre") or "").strip()
    apellido = (paciente.get("apellido") or "").strip()
    saludo = f"{nombre} {apellido}".strip() or "Hola"

    lineas = [
        f"{saludo},",
        "",
        "Tu turno en Colom · Bobbiesi quedó confirmado.",
        "",
        f"Médico: {medico}",
        f"Fecha: {fecha}",
        f"Hora: {hora}",
    ]

    direccion = os.environ.get("CONSULTORIO_DIRECCION", "").strip()
    if direccion:
        lineas.append(f"Dirección: {direccion}")

    lineas.extend(
        [
            "",
            "Guardá este mail o agregalo a tu calendario.",
            "",
            "Colom · Bobbiesi",
        ]
    )
    return "\n".join(lineas)


def avisar_turno_online(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
    paciente_nuevo: bool,
    email_paciente: str | None = None,
) -> dict:
    """
    Envía aviso al consultorio y, si hay email_paciente, confirmación al paciente.
    Nunca lanza. Devuelve {"consultorio": bool, "paciente": bool | None}.
    """
    resultado: dict = {"consultorio": False, "paciente": None}

    asunto_consultorio = f"Nuevo turno online · {medico} · {fecha} {hora}"
    cuerpo_consultorio = _cuerpo_aviso_consultorio(
        medico=medico,
        fecha=fecha,
        hora=hora,
        paciente=paciente,
        paciente_nuevo=paciente_nuevo,
        email_paciente=email_paciente,
    )
    resultado["consultorio"] = enviar_email(asunto_consultorio, cuerpo_consultorio)

    if email_paciente:
        asunto_paciente = f"Confirmación de turno · {medico} · {fecha} {hora}"
        cuerpo_paciente = _cuerpo_confirmacion_paciente(
            medico=medico,
            fecha=fecha,
            hora=hora,
            paciente=paciente,
        )
        resultado["paciente"] = enviar_email(
            asunto_paciente, cuerpo_paciente, destino=email_paciente
        )

    return resultado
