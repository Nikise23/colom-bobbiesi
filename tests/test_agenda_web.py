import os
import unittest
from datetime import date
from unittest.mock import patch

from consultorio import create_app
from consultorio.utils import agenda_web as aw
from consultorio.utils import turnos_publicos as tp


AGENDA = {
    "Dr Test": {
        "LUNES": ["09:00", "09:30", "10:00"],
        "MARTES": ["14:00", "14:30"],
        "MIERCOLES": [],
        "JUEVES": ["11:00"],
        "VIERNES": ["08:00", "08:30", "09:00"],
        "SABADO": ["10:15"],
    },
    "Dr Oculto": {
        "LUNES": ["11:00"],
        "MARTES": [],
        "MIERCOLES": [],
        "JUEVES": [],
        "VIERNES": [],
        "SABADO": [],
    },
}

AGENDA_WEB = {
    "Dr Test": {
        "visible": True,
        "dias": {
            "LUNES": ["09:00", "09:30"],
            "MARTES": ["14:00"],
            "MIERCOLES": [],
            "JUEVES": [],
            "VIERNES": ["08:00", "08:30", "09:00"],
            "SABADO": [],
        },
    },
    "Dr Oculto": {
        "visible": False,
        "dias": {"LUNES": ["11:00"], "MARTES": [], "MIERCOLES": [], "JUEVES": [], "VIERNES": [], "SABADO": []},
    },
}

BLOQUEOS = []
TURNOS = []
PACIENTES = [{"dni": "12345678", "nombre": "Ana", "apellido": "Test"}]


def _store(path):
    if path.endswith("agenda.json"):
        return AGENDA
    if path.endswith("agenda_web.json"):
        return AGENDA_WEB
    if path.endswith("bloqueos_web.json"):
        return list(BLOQUEOS)
    if path.endswith("turnos.json"):
        return list(TURNOS)
    if path.endswith("pacientes.json"):
        return list(PACIENTES)
    return []


class AgendaWebPublicTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ["PUBLIC_API_KEY"] = "test-key"
        os.environ["PUBLIC_API_CORS_ORIGIN"] = "http://localhost:5173"
        os.environ["PUBLIC_API_MAX_DIAS"] = "60"
        os.environ["PUBLIC_API_CACHE_SECONDS"] = "0"
        os.environ.pop("DATABASE_URL", None)
        BLOQUEOS.clear()
        TURNOS.clear()
        tp._RANGO_CACHE.clear()
        self.app = create_app()
        self.client = self.app.test_client()
        self.headers = {"X-API-Key": "test-key"}

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        tp._RANGO_CACHE.clear()

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    def test_listar_solo_visibles(self, *_):
        self.assertEqual(tp.listar_medicos(), ["Dr Test"])
        res = self.client.get("/api/public/v1/medicos", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["medicos"], ["Dr Test"])
        self.assertEqual(
            body["detalle"],
            [
                {
                    "nombre": "Dr Test",
                    "agenda": "Lunes y viernes por la mañana. Martes por la tarde",
                }
            ],
        )

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_disponibilidad_usa_subset_web(self, mock_aw_date, mock_tp_date, *_):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        # 2026-07-06 = lunes
        slots, err = tp.slots_disponibles("Dr Test", "2026-07-06")
        self.assertIsNone(err)
        self.assertEqual(slots, ["09:00", "09:30"])
        self.assertNotIn("10:00", slots)

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_bloqueo_dia_completo(self, mock_aw_date, mock_tp_date, *_):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        BLOQUEOS.append(
            {"id": 1, "medico": "Dr Test", "tipo": "dia", "fecha": "2026-07-06", "activo": True}
        )
        slots, err = tp.slots_disponibles("Dr Test", "2026-07-06")
        self.assertIsNone(err)
        self.assertEqual(slots, [])

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_bloqueo_rango_horas(self, mock_aw_date, mock_tp_date, *_):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        BLOQUEOS.append(
            {
                "id": 2,
                "medico": "Dr Test",
                "tipo": "rango_horas",
                "fecha": "2026-07-06",
                "hora_desde": "09:00",
                "hora_hasta": "09:30",
                "activo": True,
            }
        )
        slots, err = tp.slots_disponibles("Dr Test", "2026-07-06")
        self.assertIsNone(err)
        self.assertEqual(slots, ["09:30"])

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_bloqueo_semanal(self, mock_aw_date, mock_tp_date, *_):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        BLOQUEOS.append(
            {
                "id": 3,
                "medico": "Dr Test",
                "tipo": "semanal",
                "dia_semana": "VIERNES",
                "hora_desde": "08:00",
                "hora_hasta": "09:00",
                "activo": True,
            }
        )
        # 2026-07-10 = viernes
        slots, err = tp.slots_disponibles("Dr Test", "2026-07-10")
        self.assertIsNone(err)
        self.assertEqual(slots, ["09:00"])

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.guardar_json")
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_reserva_rechaza_slot_no_web(self, mock_aw_date, mock_tp_date, mock_guardar, *_):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        body, status = tp.reservar_turno(
            {
                "medico": "Dr Test",
                "fecha": "2026-07-06",
                "hora": "10:00",
                "dni": "12345678",
            }
        )
        self.assertEqual(status, 409)
        self.assertIn("no está disponible", body["error"])
        mock_guardar.assert_not_called()

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.cargar_json", side_effect=_store)
    @patch("consultorio.utils.turnos_publicos.date")
    @patch("consultorio.utils.agenda_web.date")
    def test_reserva_rechaza_bloqueado(self, mock_aw_date, mock_tp_date, *_):
        mock_aw_date.today.return_value = date(2026, 7, 1)
        mock_tp_date.today.return_value = date(2026, 7, 1)
        BLOQUEOS.append(
            {"id": 4, "medico": "Dr Test", "tipo": "dia", "fecha": "2026-07-06", "activo": True}
        )
        body, status = tp.reservar_turno(
            {
                "medico": "Dr Test",
                "fecha": "2026-07-06",
                "hora": "09:00",
                "dni": "12345678",
            }
        )
        self.assertEqual(status, 409)

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    def test_validar_subset_interno(self, *_):
        err = aw.validar_dias_subset(
            "Dr Test",
            {"LUNES": ["09:00", "12:00"], "MARTES": [], "MIERCOLES": [], "JUEVES": [], "VIERNES": [], "SABADO": []},
        )
        self.assertIn("no está en la agenda interna", err)


class AgendaWebStaffApiTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ.pop("DATABASE_URL", None)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test"
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["usuario"] = "secre"
            sess["rol"] = "secretaria"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    def test_get_agenda_web(self, *_):
        res = self.client.get("/api/agenda-web")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("Dr Test", data)
        self.assertTrue(data["Dr Test"]["visible"])

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.agenda_web.guardar_json")
    @patch("consultorio.utils.agenda_web.use_database", return_value=False)
    def test_put_agenda_web_ok(self, _db, mock_guardar, *_):
        res = self.client.put(
            "/api/agenda-web/Dr%20Test",
            json={
                "visible": True,
                "dias": {
                    "LUNES": ["09:00"],
                    "MARTES": [],
                    "MIERCOLES": [],
                    "JUEVES": [],
                    "VIERNES": [],
                    "SABADO": [],
                },
            },
        )
        self.assertEqual(res.status_code, 200)
        mock_guardar.assert_called()

    @patch("consultorio.utils.agenda_web.cargar_json", side_effect=_store)
    @patch("consultorio.utils.agenda_web.guardar_json")
    @patch("consultorio.utils.agenda_web.use_database", return_value=False)
    def test_crear_y_listar_bloqueo(self, _db, mock_guardar, *_):
        res = self.client.post(
            "/api/bloqueos-web",
            json={
                "medico": "Dr Test",
                "tipo": "semanal",
                "dia_semana": "LUNES",
                "hora_desde": "09:00",
                "hora_hasta": "10:00",
                "motivo": "Guardia",
            },
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["bloqueo"]["tipo"], "semanal")
        mock_guardar.assert_called()


if __name__ == "__main__":
    unittest.main()
