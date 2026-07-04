import unittest
from unittest.mock import patch

from consultorio.storage import queries as q


class InsertPagoTests(unittest.TestCase):
    @patch("consultorio.storage.queries.use_database", return_value=False)
    @patch("consultorio.storage.queries.guardar_json")
    @patch("consultorio.storage.queries.cargar_json")
    def test_nuevo_id_usa_maximo_existente(self, mock_cargar, _mock_guardar, _mock_db):
        mock_cargar.return_value = [
            {"id": 5, "dni_paciente": "1", "fecha": "2026-07-01"},
            {"id": 120, "dni_paciente": "2", "fecha": "2026-07-02"},
        ]
        nuevo = q.insert_pago({"dni_paciente": "3", "fecha": "2026-07-04", "monto": 100})
        self.assertEqual(nuevo["id"], 121)


if __name__ == "__main__":
    unittest.main()
