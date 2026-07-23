import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from consultorio.utils import email as email_util
from consultorio.utils import turnos_publicos as tp


AGENDA_WEB = {
    "Dr Test": {
        "visible": True,
        "dias": {
            "LUNES": ["09:00", "09:30"],
            "MARTES": [],
            "MIERCOLES": [],
            "JUEVES": [],
            "VIERNES": [],
            "SABADO": [],
        },
    }
}

AGENDA = {
    "Dr Test": AGENDA_WEB["Dr Test"]["dias"],
}

PACIENTES = [
    {
        "dni": "12345678",
        "nombre": "Ana",
        "apellido": "Perez",
        "celular": "111",
        "obra_social": "OSDE",
        "numero_obra_social": "1",
        "fecha_nacimiento": "01/01/1990",
    }
]

TURNOS: list = []


def _store(path):
    if path.endswith("agenda.json"):
        return AGENDA
    if path.endswith("agenda_web.json"):
        return AGENDA_WEB
    if path.endswith("bloqueos_web.json"):
        return []
    if path.endswith("turnos.json"):
        return list(TURNOS)
    if path.endswith("pacientes.json"):
        return list(PACIENTES)
    return []


def _guardar(path, data):
    if path.endswith("turnos.json"):
        TURNOS.clear()
        TURNOS.extend(data)


class EmailSmtpTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        for key in (
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_SECURE",
            "SMTP_USER",
            "SMTP_PASS",
            "SMTP_FROM",
            "SMTP_TO",
        ):
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_sin_config_no_intenta_smtp(self):
        with patch("consultorio.utils.email.smtplib.SMTP") as mock_smtp:
            ok = email_util.enviar_email("Asunto", "Cuerpo")
            self.assertFalse(ok)
            mock_smtp.assert_not_called()

    def test_envia_con_starttls(self):
        os.environ["SMTP_HOST"] = "smtp.gmail.com"
        os.environ["SMTP_PORT"] = "587"
        os.environ["SMTP_SECURE"] = "false"
        os.environ["SMTP_USER"] = "colombobbiesi@gmail.com"
        os.environ["SMTP_PASS"] = "app-password-fake"
        os.environ["SMTP_FROM"] = "Colom Bobbiesi Turnos <colombobbiesi@gmail.com>"
        os.environ["SMTP_TO"] = "colombobbiesi@gmail.com"

        smtp_instance = MagicMock()
        with patch("consultorio.utils.email.smtplib.SMTP", return_value=smtp_instance) as mock_smtp:
            smtp_instance.__enter__.return_value = smtp_instance
            ok = email_util.enviar_email("Asunto test", "Hola")
            self.assertTrue(ok)
            mock_smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
            smtp_instance.starttls.assert_called_once()
            smtp_instance.login.assert_called_once_with(
                "colombobbiesi@gmail.com", "app-password-fake"
            )
            smtp_instance.send_message.assert_called_once()

    def test_smtp_error_no_lanza(self):
        os.environ["SMTP_HOST"] = "smtp.gmail.com"
        os.environ["SMTP_USER"] = "user@example.com"
        os.environ["SMTP_PASS"] = "secret"
        with patch(
            "consultorio.utils.email.smtplib.SMTP",
            side_effect=OSError("connection refused"),
        ):
            ok = email_util.enviar_email("Asunto", "Cuerpo")
            self.assertFalse(ok)

    def test_smtp_to_cae_en_user(self):
        os.environ["SMTP_HOST"] = "smtp.gmail.com"
        os.environ["SMTP_USER"] = "user@example.com"
        os.environ["SMTP_PASS"] = "secret"
        smtp_instance = MagicMock()
        with patch("consultorio.utils.email.smtplib.SMTP", return_value=smtp_instance):
            smtp_instance.__enter__.return_value = smtp_instance
            email_util.enviar_email("Asunto", "Cuerpo")
            msg = smtp_instance.send_message.call_args[0][0]
            self.assertEqual(msg["To"], "user@example.com")


class ReservaConEmailTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ.pop("DATABASE_URL", None)
        TURNOS.clear()
        tp._RANGO_CACHE.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        TURNOS.clear()
        tp._RANGO_CACHE.clear()

    @patch("consultorio.utils.turnos_publicos.avisar_turno_online")
    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.guardar_json", side_effect=_guardar)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_reserva_envia_aviso(
        self, mock_aw_date, mock_tp_date, _g, _c1, _c2, mock_avisar
    ):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        body, status = tp.reservar_turno(
            {
                "medico": "Dr Test",
                "fecha": "2026-07-06",
                "hora": "09:00",
                "dni": "12345678",
            }
        )
        self.assertEqual(status, 201)
        self.assertFalse(body["paciente_nuevo"])
        self.assertEqual(len(TURNOS), 1)
        mock_avisar.assert_called_once()
        kwargs = mock_avisar.call_args.kwargs
        self.assertEqual(kwargs["medico"], "Dr Test")
        self.assertEqual(kwargs["paciente_nuevo"], False)

    @patch(
        "consultorio.utils.turnos_publicos.avisar_turno_online",
        side_effect=RuntimeError("smtp down"),
    )
    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.guardar_json", side_effect=_guardar)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_reserva_ok_aunque_mail_falle(
        self, mock_aw_date, mock_tp_date, _g, _c1, _c2, _avisar
    ):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        body, status = tp.reservar_turno(
            {
                "medico": "Dr Test",
                "fecha": "2026-07-06",
                "hora": "09:30",
                "dni": "12345678",
            }
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(TURNOS), 1)
        self.assertIn("mensaje", body)

    @patch("consultorio.utils.email.smtplib.SMTP")
    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.guardar_json", side_effect=_guardar)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_sin_smtp_env_no_llama_smtp(
        self, mock_aw_date, mock_tp_date, _g, _c1, _c2, mock_smtp
    ):
        for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
            os.environ.pop(key, None)
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        body, status = tp.reservar_turno(
            {
                "medico": "Dr Test",
                "fecha": "2026-07-06",
                "hora": "09:00",
                "dni": "12345678",
            }
        )
        self.assertEqual(status, 201)
        mock_smtp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
