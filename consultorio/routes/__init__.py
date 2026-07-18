from consultorio.routes.administrador import bp as administrador_bp
from consultorio.routes.agenda import bp as agenda_bp
from consultorio.routes.agenda_web import bp as agenda_web_bp
from consultorio.routes.auth import bp as auth_bp
from consultorio.routes.historias import bp as historias_bp
from consultorio.routes.pacientes import bp as pacientes_bp
from consultorio.routes.pagos import bp as pagos_bp
from consultorio.routes.public_api import bp as public_api_bp
from consultorio.routes.reportes import bp as reportes_bp
from consultorio.routes.secretaria import bp as secretaria_bp
from consultorio.routes.turnos import bp as turnos_bp

_ALL_BLUEPRINTS = [
    auth_bp,
    historias_bp,
    pacientes_bp,
    turnos_bp,
    agenda_bp,
    agenda_web_bp,
    pagos_bp,
    secretaria_bp,
    administrador_bp,
    reportes_bp,
    public_api_bp,
]


def register_blueprints(app):
    for bp in _ALL_BLUEPRINTS:
        app.register_blueprint(bp)
