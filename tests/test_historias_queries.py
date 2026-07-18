import unittest
from unittest.mock import Mock, patch

from consultorio.storage import db_storage


class HistoriasQueriesTests(unittest.TestCase):
    @patch("consultorio.storage.db_storage.HistoriaClinica")
    def test_load_historias_dni_filtra_en_base(self, historia_model):
        query = historia_model.query.filter_by.return_value
        ordered = query.order_by.return_value
        row = Mock()
        row.to_dict.return_value = {"id": 1, "dni": "12345678"}
        ordered.all.return_value = [row]

        result = db_storage.load_historias_dni("12345678")

        historia_model.query.filter_by.assert_called_once_with(dni="12345678")
        self.assertEqual(result, [{"id": 1, "dni": "12345678"}])


if __name__ == "__main__":
    unittest.main()
