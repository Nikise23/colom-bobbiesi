from consultorio.extensions import db


class Usuario(db.Model):
    __tablename__ = "usuarios"

    usuario = db.Column(db.String(255), primary_key=True)
    contrasena = db.Column(db.Text, nullable=False)
    rol = db.Column(db.String(50), nullable=False)

    def to_dict(self) -> dict:
        return {"usuario": self.usuario, "contrasena": self.contrasena, "rol": self.rol}


class Paciente(db.Model):
    __tablename__ = "pacientes"

    dni = db.Column(db.String(20), primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    apellido = db.Column(db.String(255), nullable=False)
    fecha_nacimiento = db.Column(db.String(30))
    obra_social = db.Column(db.String(255))
    numero_obra_social = db.Column(db.String(255))
    celular = db.Column(db.String(50))
    fecha_registro = db.Column(db.String(50))

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "apellido": self.apellido,
            "dni": self.dni,
            "fecha_nacimiento": self.fecha_nacimiento or "",
            "obra_social": self.obra_social or "",
            "numero_obra_social": self.numero_obra_social or "",
            "celular": self.celular or "",
            "fecha_registro": self.fecha_registro or "",
        }


class Turno(db.Model):
    __tablename__ = "turnos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    medico = db.Column(db.String(255), nullable=False)
    fecha = db.Column(db.String(30), nullable=False)
    hora = db.Column(db.String(10), nullable=False)
    dni_paciente = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(50), default="sin atender")
    observacion = db.Column(db.Text)
    hora_recepcion = db.Column(db.String(10))
    hora_sala_espera = db.Column(db.String(10))
    pago_registrado = db.Column(db.Boolean)
    monto_pagado = db.Column(db.Float)
    observacion_pago = db.Column(db.Text)
    borrador_consulta = db.Column(db.Text)
    borrador_fecha_consulta = db.Column(db.String(50))
    borrador_actualizado = db.Column(db.String(50))

    __table_args__ = (
        db.UniqueConstraint("dni_paciente", "fecha", "hora", name="uq_turno_paciente_fecha_hora"),
    )

    def to_dict(self) -> dict:
        data = {
            "medico": self.medico,
            "fecha": self.fecha,
            "hora": self.hora,
            "dni_paciente": self.dni_paciente,
            "estado": self.estado or "sin atender",
        }
        optional_fields = [
            "observacion",
            "hora_recepcion",
            "hora_sala_espera",
            "pago_registrado",
            "monto_pagado",
            "observacion_pago",
            "borrador_consulta",
            "borrador_fecha_consulta",
            "borrador_actualizado",
        ]
        for field in optional_fields:
            value = getattr(self, field)
            if value is not None and value != "":
                data[field] = value
        return data


class AgendaHorario(db.Model):
    __tablename__ = "agenda_horarios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    medico = db.Column(db.String(255), nullable=False)
    dia = db.Column(db.String(20), nullable=False)
    hora = db.Column(db.String(10), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("medico", "dia", "hora", name="uq_agenda_medico_dia_hora"),
    )


class HistoriaClinica(db.Model):
    __tablename__ = "historias_clinicas"

    id = db.Column(db.Integer, primary_key=True)
    dni = db.Column(db.String(20), nullable=False, index=True)
    fecha_consulta = db.Column(db.String(30))
    medico = db.Column(db.String(255))
    consulta_medica = db.Column(db.Text)
    fecha_creacion = db.Column(db.String(50))

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "dni": self.dni,
            "consulta_medica": self.consulta_medica or "",
            "medico": self.medico or "",
        }
        if self.fecha_consulta:
            data["fecha_consulta"] = self.fecha_consulta
        if self.fecha_creacion:
            data["fecha_creacion"] = self.fecha_creacion
        return data


class Pago(db.Model):
    __tablename__ = "pagos"

    id = db.Column(db.Integer, primary_key=True)
    dni_paciente = db.Column(db.String(20), nullable=False, index=True)
    nombre_paciente = db.Column(db.String(255))
    monto = db.Column(db.Float, default=0)
    fecha = db.Column(db.String(30), nullable=False)
    hora = db.Column(db.String(10))
    tipo_pago = db.Column(db.String(50))
    obra_social = db.Column(db.String(255))
    observaciones = db.Column(db.Text)
    fecha_registro = db.Column(db.String(50))

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "dni_paciente": self.dni_paciente,
            "nombre_paciente": self.nombre_paciente or "",
            "monto": self.monto if self.monto is not None else 0,
            "fecha": self.fecha,
            "tipo_pago": self.tipo_pago or "efectivo",
            "obra_social": self.obra_social or "",
        }
        if self.hora:
            data["hora"] = self.hora
        if self.observaciones:
            data["observaciones"] = self.observaciones
        if self.fecha_registro:
            data["fecha_registro"] = self.fecha_registro
        return data
