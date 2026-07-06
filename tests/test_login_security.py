import os
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from consultorio import create_app
from consultorio.auth.login_limiter import reset_all

USUARIOS_FIXTURE = [
    {
        "usuario": "medico_test",
        "contrasena": generate_password_hash("clave_correcta"),
        "rol": "medico",
    }
]


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        os.environ.pop("RENDER", None)
        os.environ["LOGIN_MAX_ATTEMPTS"] = "3"
        os.environ["LOGIN_LOCKOUT_MINUTES"] = "15"
        reset_all()

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        reset_all()

    def _login(self, usuario="medico_test", contrasena="clave_correcta"):
        return self.client.post(
            "/login",
            data={"usuario": usuario, "contrasena": contrasena},
            follow_redirects=False,
        )

    @patch("consultorio.routes.auth.cargar_json")
    def test_login_exitoso_regenera_sesion(self, mock_cargar):
        mock_cargar.return_value = USUARIOS_FIXTURE
        res = self._login()
        self.assertEqual(res.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("usuario"), "medico_test")
            self.assertEqual(sess.get("rol"), "medico")

    @patch("consultorio.routes.auth.cargar_json")
    def test_login_fallido_incrementa_bloqueo(self, mock_cargar):
        mock_cargar.return_value = USUARIOS_FIXTURE
        for _ in range(2):
            res = self._login(contrasena="mala")
            self.assertEqual(res.status_code, 200)
        res = self._login(contrasena="mala")
        self.assertEqual(res.status_code, 429)
        self.assertIn(b"Demasiados intentos", res.data)
        res = self._login(contrasena="mala")
        self.assertEqual(res.status_code, 429)

    @patch("consultorio.routes.auth.cargar_json")
    def test_login_exitoso_limpia_intentos_fallidos(self, mock_cargar):
        mock_cargar.return_value = USUARIOS_FIXTURE
        self._login(contrasena="mala")
        self._login(contrasena="mala")
        res = self._login(contrasena="clave_correcta")
        self.assertEqual(res.status_code, 302)
        res = self._login(contrasena="mala")
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.status_code, 429)

    @patch("consultorio.routes.auth.cargar_json")
    def test_ruta_protegida_sin_sesion_redirige_login(self, mock_cargar):
        mock_cargar.return_value = USUARIOS_FIXTURE
        res = self.client.get("/secretaria")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.location)

    def test_cookies_seguras_en_produccion(self):
        os.environ["RENDER"] = "true"
        os.environ["SECRET_KEY"] = "clave-segura-de-prueba"
        app = create_app()
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")


if __name__ == "__main__":
    unittest.main()
