import unittest
from unittest.mock import patch

from consultorio import create_app


class AtencionMedicoGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _session_medico(self, nombre="Julieta Colom"):
        with self.client.session_transaction() as sess:
            sess["usuario"] = nombre
            sess["rol"] = "medico"

    @patch("consultorio.routes.turnos.update_turno")
    @patch("consultorio.routes.turnos.get_turno")
    def test_estado_rechaza_turno_de_otro_medico(self, mock_get, mock_update):
        self._session_medico("Julieta Colom")
        mock_get.return_value = {
            "dni_paciente": "42887120",
            "fecha": "2026-08-12",
            "hora": "15:30",
            "medico": "Francisco Colom",
            "estado": "sala de espera",
        }
        res = self.client.put(
            "/api/turnos/estado",
            json={
                "dni_paciente": "42887120",
                "fecha": "2026-08-12",
                "hora": "15:30",
                "estado": "atendiendo",
            },
        )
        self.assertEqual(res.status_code, 403)
        mock_update.assert_not_called()

    @patch("consultorio.routes.historias.update_turno")
    @patch("consultorio.routes.historias.get_turno", create=True)
    @patch("consultorio.routes.historias.use_database", return_value=False)
    @patch("consultorio.routes.historias.guardar_json")
    @patch("consultorio.routes.historias.cargar_json", return_value=[])
    def test_crear_historia_rechaza_turno_ajeno(
        self, _cargar, _guardar, _db, mock_get, mock_update
    ):
        # Patch get_turno where crear_historia imports it
        with patch("consultorio.storage.queries.get_turno") as mock_qget:
            mock_qget.return_value = {
                "dni_paciente": "42887120",
                "fecha": "2026-08-12",
                "hora": "15:30",
                "medico": "Francisco Colom",
                "estado": "atendiendo",
            }
            self._session_medico("Julieta Colom")
            res = self.client.post(
                "/historias",
                json={
                    "dni": "42887120",
                    "consulta_medica": "texto",
                    "fecha_consulta": "2026-08-12",
                    "fecha_turno": "2026-08-12",
                    "hora_turno": "15:30",
                },
            )
        self.assertEqual(res.status_code, 403)
        mock_update.assert_not_called()

    @patch("consultorio.routes.turnos.update_turno", return_value=True)
    @patch("consultorio.routes.turnos.get_turno")
    def test_borrador_no_reescribe_lista_completa(self, mock_get, mock_update):
        self._session_medico("Julieta Colom")
        mock_get.return_value = {
            "dni_paciente": "42887120",
            "fecha": "2026-08-12",
            "hora": "15:30",
            "medico": "Julieta Colom",
            "estado": "atendiendo",
        }
        with patch("consultorio.routes.turnos.guardar_json") as mock_save_all:
            res = self.client.put(
                "/api/turnos/42887120/2026-08-12/15:30/borrador-consulta",
                json={"consulta_medica": "borrador", "fecha_consulta": "2026-08-12"},
            )
            self.assertEqual(res.status_code, 200)
            mock_save_all.assert_not_called()
            mock_update.assert_called_once()
            args = mock_update.call_args[0]
            self.assertEqual(args[0], "42887120")
            self.assertIn("borrador_consulta", args[3])
            self.assertNotIn("medico", args[3])


if __name__ == "__main__":
    unittest.main()
