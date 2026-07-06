import os

from flask import Flask

from consultorio.auth.security import configure_app_security
from consultorio.config import load_env_file
from consultorio.database import init_db
from consultorio.paths import copiar_json_a_persistencia
from consultorio.routes import register_blueprints

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app() -> Flask:
    load_env_file()
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    app.secret_key = os.environ.get("SECRET_KEY", "clave_insegura_dev")
    configure_app_security(app)

    init_db(app)
    copiar_json_a_persistencia()
    register_blueprints(app)

    return app
