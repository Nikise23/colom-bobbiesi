"""Envío de emails por SMTP (aviso de turnos online, etc.)."""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(
        os.environ.get("SMTP_HOST", "").strip()
        and os.environ.get("SMTP_USER", "").strip()
        and os.environ.get("SMTP_PASS", "").strip()
    )


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


def avisar_turno_online(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
    paciente_nuevo: bool,
) -> bool:
    """Arma y envía el aviso de un turno reservado por la API pública."""
    asunto = f"Nuevo turno online · {medico} · {fecha} {hora}"
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

    lineas.append("Origen: Turno web / API pública")
    return enviar_email(asunto, "\n".join(lineas))
