"""Envío de emails por SMTP (confirmación de turnos online al paciente)."""

from __future__ import annotations

import logging
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape
from urllib.parse import quote, urlencode

import pytz

from consultorio.paths import timezone_ar

logger = logging.getLogger(__name__)

# Formato básico: local@dominio.tld (sin espacios)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_DIA_ES = {
    0: "LUNES",
    1: "MARTES",
    2: "MIERCOLES",
    3: "JUEVES",
    4: "VIERNES",
    5: "SABADO",
    6: "DOMINGO",
}


def formatear_fecha_mail(fecha: str) -> str:
    """YYYY-MM-DD → 'LUNES 27-07-2026'. Si falla, devuelve la fecha original."""
    try:
        dt = datetime.strptime(fecha.strip(), "%Y-%m-%d")
    except ValueError:
        return fecha
    dia = _DIA_ES[dt.weekday()]
    return f"{dia} {dt.strftime('%d-%m-%Y')}"


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


def _duracion_turno_minutos() -> int:
    try:
        return max(5, min(180, int(os.environ.get("CONSULTORIO_TURNO_MINUTOS", "30"))))
    except ValueError:
        return 30


def _parse_inicio(fecha: str, hora: str) -> datetime | None:
    try:
        naive = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return timezone_ar.localize(naive)


def google_calendar_url(
    *,
    medico: str,
    fecha: str,
    hora: str,
    direccion: str = "",
) -> str | None:
    inicio = _parse_inicio(fecha, hora)
    if inicio is None:
        return None
    fin = inicio + timedelta(minutes=_duracion_turno_minutos())
    inicio_utc = inicio.astimezone(pytz.UTC)
    fin_utc = fin.astimezone(pytz.UTC)
    params = {
        "action": "TEMPLATE",
        "text": f"Turno · {medico} · Colom Bobbiesi",
        "dates": (
            f"{inicio_utc.strftime('%Y%m%dT%H%M%SZ')}/"
            f"{fin_utc.strftime('%Y%m%dT%H%M%SZ')}"
        ),
        "details": (
            f"Turno con {medico}\n"
            f"Consultorio Colom · Bobbiesi\n"
            f"{fecha} {hora}"
        ),
    }
    if direccion:
        params["location"] = direccion
    return "https://calendar.google.com/calendar/render?" + urlencode(params, quote_via=quote)


def build_ics(
    *,
    medico: str,
    fecha: str,
    hora: str,
    direccion: str = "",
) -> str | None:
    inicio = _parse_inicio(fecha, hora)
    if inicio is None:
        return None
    fin = inicio + timedelta(minutes=_duracion_turno_minutos())
    uid = f"turno-{fecha}-{hora.replace(':', '')}-{hash(medico) & 0xFFFFFFFF}@colombobbiesi"
    stamp = datetime.now(pytz.UTC).strftime("%Y%m%dT%H%M%SZ")
    # Usar valores locales con TZID (compatible Outlook / Apple / Google)
    fmt = "%Y%m%dT%H%M%S"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Colom Bobbiesi//Turnos//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID=America/Argentina/Buenos_Aires:{inicio.strftime(fmt)}",
        f"DTEND;TZID=America/Argentina/Buenos_Aires:{fin.strftime(fmt)}",
        f"SUMMARY:Turno · {medico} · Colom Bobbiesi",
        "DESCRIPTION:Turno en consultorio Colom · Bobbiesi",
    ]
    if direccion:
        lines.append(f"LOCATION:{direccion}")
    lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(lines)


def enviar_email(
    asunto: str,
    cuerpo: str,
    destino: str | None = None,
    *,
    html: str | None = None,
    ics_content: str | None = None,
    ics_filename: str = "turno.ics",
) -> bool:
    """
    Envía un email (texto + HTML opcional + adjunto ICS opcional).
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
    if not to_addr:
        logger.warning("Sin destinatario de email; se omite el envío.")
        return False

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
    if html:
        msg.add_alternative(html, subtype="html")
    if ics_content:
        msg.add_attachment(
            ics_content.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename=ics_filename,
        )

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
        logger.exception(
            "Error al enviar email (asunto=%r, destino=%s)", asunto, to_addr
        )
        return False


def _cuerpo_texto_paciente(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
    calendar_url: str | None,
) -> str:
    nombre = (paciente.get("nombre") or "").strip()
    apellido = (paciente.get("apellido") or "").strip()
    saludo = f"{nombre} {apellido}".strip() or "Hola"
    direccion = os.environ.get("CONSULTORIO_DIRECCION", "").strip()
    fecha_legible = formatear_fecha_mail(fecha)

    lineas = [
        f"{saludo},",
        "",
        "Tu turno en Colom · Bobbiesi quedó confirmado.",
        "",
        f"Médico: {medico}",
        f"Fecha: {fecha_legible}",
        f"Hora: {hora}",
    ]
    if direccion:
        lineas.append(f"Dirección: {direccion}")
    lineas.append("")
    if calendar_url:
        lineas.append(f"Agregar al calendario: {calendar_url}")
        lineas.append("(También adjuntamos un archivo .ics)")
        lineas.append("")
    lineas.extend(
        [
            "Guardá este mail o agregalo a tu calendario.",
            "",
            "Recuerde que su obra social puede estar sujeta a un copago. "
            "Cualquier duda contactarse por WhatsApp.",
            "",
            "Colom · Bobbiesi",
        ]
    )
    return "\n".join(lineas)


def _html_confirmacion_paciente(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
    calendar_url: str | None,
) -> str:
    nombre = escape((paciente.get("nombre") or "").strip())
    apellido = escape((paciente.get("apellido") or "").strip())
    saludo = f"{nombre} {apellido}".strip() or "Hola"
    medico_e = escape(medico)
    fecha_e = escape(formatear_fecha_mail(fecha))
    hora_e = escape(hora)
    direccion = os.environ.get("CONSULTORIO_DIRECCION", "").strip()
    logo_url = os.environ.get("CONSULTORIO_LOGO_URL", "").strip()

    if logo_url:
        header_brand = (
            f'<img src="{escape(logo_url)}" alt="Colom Bobbiesi" '
            f'width="160" style="display:block;margin:0 auto 12px;max-width:160px;height:auto;" />'
        )
    else:
        header_brand = (
            '<div style="font-size:22px;font-weight:700;letter-spacing:0.5px;">'
            "Colom · Bobbiesi</div>"
            '<div style="font-size:13px;opacity:0.9;margin-top:6px;">Oftalmología</div>'
        )

    dir_row = ""
    if direccion:
        dir_row = (
            f'<tr><td style="padding:8px 0;color:#6c757d;width:110px;">Dirección</td>'
            f'<td style="padding:8px 0;color:#2c3e50;font-weight:600;">{escape(direccion)}</td></tr>'
        )

    calendar_block = ""
    if calendar_url:
        calendar_block = f"""
        <div style="text-align:center;margin:28px 0 8px;">
          <a href="{escape(calendar_url)}"
             style="display:inline-block;background:#27ae60;color:#ffffff;text-decoration:none;
                    font-weight:700;font-size:15px;padding:14px 28px;border-radius:8px;">
            Guardar en el calendario
          </a>
        </div>
        <p style="text-align:center;color:#6c757d;font-size:12px;margin:0 0 16px;">
          También podés abrir el archivo adjunto <strong>turno.ics</strong>
        </p>
        """

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /></head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f7;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;
                    box-shadow:0 8px 24px rgba(44,62,80,0.12);">
        <tr>
          <td style="background:linear-gradient(135deg,#2c3e50 0%,#3498db 100%);
                     color:#ffffff;text-align:center;padding:28px 24px;">
            {header_brand}
          </td>
        </tr>
        <tr>
          <td style="padding:28px 28px 8px;color:#2c3e50;">
            <p style="margin:0 0 8px;font-size:18px;font-weight:600;">{saludo},</p>
            <p style="margin:0 0 20px;font-size:15px;color:#5a6a7a;line-height:1.5;">
              Tu turno quedó <strong style="color:#27ae60;">confirmado</strong>.
            </p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                   style="background:#f7fafc;border-radius:8px;padding:4px 16px;
                          border:1px solid #e3eaf1;">
              <tr><td style="padding:8px 0;color:#6c757d;width:110px;">Médico</td>
                  <td style="padding:8px 0;color:#2c3e50;font-weight:600;">{medico_e}</td></tr>
              <tr><td style="padding:8px 0;color:#6c757d;">Fecha</td>
                  <td style="padding:8px 0;color:#2c3e50;font-weight:600;">{fecha_e}</td></tr>
              <tr><td style="padding:8px 0;color:#6c757d;">Hora</td>
                  <td style="padding:8px 0;color:#2c3e50;font-weight:600;">{hora_e}</td></tr>
              {dir_row}
            </table>
            {calendar_block}
            <p style="margin:16px 0 0;font-size:13px;color:#6c757d;line-height:1.5;">
              Guardá este mail o agregalo a tu calendario.
            </p>
            <p style="margin:16px 0 0;padding:12px 14px;background:#f7fafc;border:1px solid #e3eaf1;
                       border-radius:8px;font-size:13px;color:#5a6a7a;line-height:1.5;">
              Recuerde que su obra social puede estar sujeta a un copago.
              Cualquier duda contactarse por WhatsApp.
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 28px 28px;border-top:1px solid #eef2f7;
                     text-align:center;color:#95a5a6;font-size:12px;">
            Colom · Bobbiesi · Oftalmología
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def avisar_turno_online(
    *,
    medico: str,
    fecha: str,
    hora: str,
    paciente: dict,
    paciente_nuevo: bool = False,
    email_paciente: str | None = None,
) -> dict:
    """
    Envía confirmación solo al paciente (si hay email).
    Nunca lanza. Devuelve {"consultorio": None, "paciente": bool | None}.
    """
    resultado: dict = {"consultorio": None, "paciente": None}
    if not email_paciente:
        return resultado

    direccion = os.environ.get("CONSULTORIO_DIRECCION", "").strip()
    calendar_url = google_calendar_url(
        medico=medico, fecha=fecha, hora=hora, direccion=direccion
    )
    ics = build_ics(medico=medico, fecha=fecha, hora=hora, direccion=direccion)

    asunto = f"Confirmación de turno · {medico} · {fecha} {hora}"
    texto = _cuerpo_texto_paciente(
        medico=medico,
        fecha=fecha,
        hora=hora,
        paciente=paciente,
        calendar_url=calendar_url,
    )
    html = _html_confirmacion_paciente(
        medico=medico,
        fecha=fecha,
        hora=hora,
        paciente=paciente,
        calendar_url=calendar_url,
    )
    resultado["paciente"] = enviar_email(
        asunto,
        texto,
        destino=email_paciente,
        html=html,
        ics_content=ics,
    )
    return resultado
