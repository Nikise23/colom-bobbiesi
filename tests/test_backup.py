import json
import os
import unittest
from unittest.mock import patch

from consultorio import create_app
from consultorio.utils.backup import build_backup_zip


class BackupZipTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ.pop("DATABASE_URL", None)
        self.app = create_app()
        self.app.config["TESTING"] = True

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_build_backup_zip_incluye_manifest(self):
        fixture = {
            "pagos.json": [{"id": 1, "monto": 100}],
            "historias_clinicas.json": [{"dni": "123", "diagnostico": "test"}],
            "turnos.json": [],
            "pacientes.json": [{"dni": "123", "nombre": "A"}],
            "agenda.json": {"Dr X": {"LUNES": ["09:00"]}},
            "usuarios.json": [{"usuario": "admin", "rol": "administrador"}],
        }

        def fake_cargar(path):
            import os as _os

            base = _os.path.basename(path)
            if base == "agenda.json":
                return fixture.get("agenda.json", {})
            key = base
            return fixture.get(key, [])

        with self.app.app_context():
            with patch("consultorio.utils.backup.cargar_json", side_effect=fake_cargar):
                with patch("consultorio.utils.backup.use_database", return_value=False):
                    buf, count = build_backup_zip()
        self.assertGreaterEqual(count, 6)
        import zipfile

        with zipfile.ZipFile(buf) as zf:
            names = set(zf.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("pacientes.json", names)
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["origen"], "json")


if __name__ == "__main__":
    unittest.main()
