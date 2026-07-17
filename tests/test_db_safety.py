"""Tests de protecciones anti-borrado masivo."""

import os
import unittest

from consultorio.db_safety import (
    allow_remote_data_migrate,
    is_local_database_url,
    refuse_empty_replace,
    refuse_mass_delete,
)


class DbSafetyTests(unittest.TestCase):
    def test_local_url(self):
        self.assertTrue(is_local_database_url("postgresql://u:p@localhost:5432/db"))
        self.assertTrue(is_local_database_url("postgresql://u:p@127.0.0.1:5432/db"))
        self.assertFalse(
            is_local_database_url("postgresql://u:p@dpg-xxx.render.com:5432/db")
        )

    def test_refuse_empty(self):
        with self.assertRaises(ValueError):
            refuse_empty_replace("pacientes", 0, 10)
        refuse_empty_replace("pacientes", 0, 0)
        refuse_empty_replace("pacientes", 5, 10)

    def test_refuse_mass_delete(self):
        with self.assertRaises(ValueError):
            refuse_mass_delete("turnos", 10, 1000)
        refuse_mass_delete("turnos", 900, 1000)
        refuse_mass_delete("turnos", 1, 50)  # below min_existing

    def test_allow_destructive_override(self):
        os.environ["ALLOW_DESTRUCTIVE_REPLACE"] = "1"
        try:
            refuse_mass_delete("turnos", 1, 1000)
        finally:
            os.environ.pop("ALLOW_DESTRUCTIVE_REPLACE", None)

    def test_remote_migrate_flag(self):
        os.environ.pop("ALLOW_REMOTE_DATA_MIGRATE", None)
        self.assertFalse(allow_remote_data_migrate())
        os.environ["ALLOW_REMOTE_DATA_MIGRATE"] = "I_UNDERSTAND"
        try:
            self.assertTrue(allow_remote_data_migrate())
        finally:
            os.environ.pop("ALLOW_REMOTE_DATA_MIGRATE", None)


if __name__ == "__main__":
    unittest.main()
