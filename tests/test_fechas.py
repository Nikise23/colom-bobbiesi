import unittest

from consultorio.utils.fechas import normalizar_fecha_nacimiento


class FechaNacimientoTests(unittest.TestCase):
    def test_formato_con_barras(self):
        self.assertEqual(normalizar_fecha_nacimiento("15/05/1990"), "1990-05-15")

    def test_formato_iso(self):
        self.assertEqual(normalizar_fecha_nacimiento("1990-05-15"), "1990-05-15")

    def test_ocho_digitos_sin_barras(self):
        self.assertEqual(normalizar_fecha_nacimiento("15051990"), "1990-05-15")

    def test_invalida(self):
        self.assertIsNone(normalizar_fecha_nacimiento("99/99/1990"))

    def test_anio_tres_digitos_invalido(self):
        self.assertIsNone(normalizar_fecha_nacimiento("20/04/320"))

    def test_anio_fuera_de_rango_invalido(self):
        self.assertIsNone(normalizar_fecha_nacimiento("20/04/1880"))


if __name__ == "__main__":
    unittest.main()
