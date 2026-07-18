import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from consultorio import create_app
from consultorio.utils import turnos_publicos as tp


AGENDA_FIXTURE = {
    "Dr Test": {
        "LUNES": ["09:00", "09:30", "10:00"],
        "MARTES": ["14:00", "14:30"],
        "MIERCOLES": [],
        "JUEVES": ["11:00"],
        "VIERNES": ["08:00"],
        "SABADO": ["10:15"],
    }
}

AGENDA_WEB_FIXTURE = {
    "Dr Test": {
        "visible": True,
        "dias": AGENDA_FIXTURE["Dr Test"],
    }
}

TURNOS_FIXTURE = [
    {
        "medico": "Dr Test",
        "fecha": "2026-07-06",
        "hora": "09:00",
        "dni_paciente": "12345678",
    },
]


def _mock_cargar_json(path):
    if path.endswith("agenda.json"):
        return AGENDA_FIXTURE
    if path.endswith("agenda_web.json"):
        return AGENDA_WEB_FIXTURE
    if path.endswith("bloqueos_web.json"):
        return []
    if path.endswith("turnos.json"):
        return TURNOS_FIXTURE
    return []


class DisponibilidadRangoTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ["PUBLIC_API_KEY"] = "test-key"
        os.environ["PUBLIC_API_CORS_ORIGIN"] = "http://localhost:5173"
        os.environ["PUBLIC_API_MAX_DIAS"] = "60"
        os.environ["PUBLIC_API_MAX_DIAS_RANGO"] = "31"
        os.environ["PUBLIC_API_CACHE_SECONDS"] = "0"
        os.environ.pop("DATABASE_URL", None)
        tp._RANGO_CACHE.clear()

        self.app = create_app()
        self.client = self.app.test_client()
        self.headers = {"X-API-Key": "test-key"}
        self._patchers = [
            patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_mock_cargar_json),
            patch("consultorio.utils.agenda_web.cargar_json", side_effect=_mock_cargar_json),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        os.environ.clear()
        os.environ.update(self._env)
        tp._RANGO_CACHE.clear()

    @patch("consultorio.utils.turnos_publicos.date")
    def test_parity_con_disponibilidad_puntual(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        payload, err = tp.slots_disponibles_rango("Dr Test", "2026-07-07", "2026-07-11")
        self.assertIsNone(err)

        for dia in payload["dias"]:
            puntual, err_p = tp.slots_disponibles("Dr Test", dia["fecha"])
            self.assertIsNone(err_p)
            self.assertEqual(puntual, dia["horarios_disponibles"])

    @patch("consultorio.utils.turnos_publicos.date")
    def test_no_incluye_domingos(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        payload, err = tp.slots_disponibles_rango("Dr Test", "2026-07-04", "2026-07-10")
        self.assertIsNone(err)
        fechas = [d["fecha"] for d in payload["dias"]]
        self.assertNotIn("2026-07-05", fechas)
        self.assertEqual(fechas[0], "2026-07-04")
        self.assertEqual(fechas[-1], "2026-07-10")

    @patch("consultorio.utils.turnos_publicos.date")
    def test_rango_supera_limite_por_request(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        _, err = tp.slots_disponibles_rango("Dr Test", "2026-07-01", "2026-08-05")
        self.assertIn("31 días", err)

    @patch("consultorio.utils.turnos_publicos.date")
    def test_fecha_fuera_de_max_dias_reserva(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        lejana = (date(2026, 7, 1) + timedelta(days=61)).isoformat()
        _, err = tp.slots_disponibles_rango("Dr Test", lejana, lejana)
        self.assertIn("60 días", err)

    @patch("consultorio.utils.turnos_publicos.date")
    def test_medico_inexistente(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        _, err = tp.slots_disponibles_rango("No Existe", "2026-07-07", "2026-07-07")
        self.assertEqual(err, "Médico no encontrado")

    @patch("consultorio.utils.turnos_publicos.date")
    def test_endpoint_http_ok(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        res = self.client.get(
            "/api/public/v1/disponibilidad-rango"
            "?medico=Dr%20Test&desde=2026-07-07&hasta=2026-07-09",
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["medico"], "Dr Test")
        self.assertEqual(len(data["dias"]), 3)

    def test_sin_api_key_401(self):
        res = self.client.get(
            "/api/public/v1/disponibilidad-rango"
            "?medico=Dr%20Test&desde=2026-07-07&hasta=2026-07-09"
        )
        self.assertEqual(res.status_code, 401)

    @patch("consultorio.utils.turnos_publicos.date")
    def test_origen_no_autorizado_403(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        res = self.client.get(
            "/api/public/v1/disponibilidad-rango"
            "?medico=Dr%20Test&desde=2026-07-07&hasta=2026-07-09",
            headers={**self.headers, "Origin": "https://sitio-malicioso.com"},
        )
        self.assertEqual(res.status_code, 403)

    @patch("consultorio.utils.turnos_publicos.date")
    def test_disponibilidad_puntual_sin_cambios(self, mock_date):
        mock_date.today.return_value = date(2026, 7, 1)

        res = self.client.get(
            "/api/public/v1/disponibilidad?medico=Dr%20Test&fecha=2026-07-06",
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.get_json(),
            {
                "medico": "Dr Test",
                "fecha": "2026-07-06",
                "horarios_disponibles": ["09:30", "10:00"],
                "total": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
