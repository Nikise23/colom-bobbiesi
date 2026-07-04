"""Esquema inicial — tablas del consultorio médico."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("usuario", sa.String(255), primary_key=True),
        sa.Column("contrasena", sa.Text(), nullable=False),
        sa.Column("rol", sa.String(50), nullable=False),
    )
    op.create_table(
        "pacientes",
        sa.Column("dni", sa.String(8), primary_key=True),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("apellido", sa.String(255), nullable=False),
        sa.Column("fecha_nacimiento", sa.String(10)),
        sa.Column("obra_social", sa.String(255)),
        sa.Column("numero_obra_social", sa.String(255)),
        sa.Column("celular", sa.String(50)),
        sa.Column("fecha_registro", sa.String(50)),
    )
    op.create_table(
        "turnos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medico", sa.String(255), nullable=False),
        sa.Column("fecha", sa.String(10), nullable=False),
        sa.Column("hora", sa.String(5), nullable=False),
        sa.Column("dni_paciente", sa.String(8), nullable=False),
        sa.Column("estado", sa.String(50)),
        sa.Column("observacion", sa.Text()),
        sa.Column("hora_recepcion", sa.String(5)),
        sa.Column("hora_sala_espera", sa.String(5)),
        sa.Column("pago_registrado", sa.Boolean()),
        sa.Column("monto_pagado", sa.Float()),
        sa.Column("observacion_pago", sa.Text()),
        sa.Column("borrador_consulta", sa.Text()),
        sa.Column("borrador_fecha_consulta", sa.String(50)),
        sa.Column("borrador_actualizado", sa.String(50)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dni_paciente", "fecha", "hora", name="uq_turno_paciente_fecha_hora"),
    )
    op.create_table(
        "agenda_horarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medico", sa.String(255), nullable=False),
        sa.Column("dia", sa.String(20), nullable=False),
        sa.Column("hora", sa.String(5), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("medico", "dia", "hora", name="uq_agenda_medico_dia_hora"),
    )
    op.create_table(
        "historias_clinicas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dni", sa.String(8), nullable=False),
        sa.Column("fecha_consulta", sa.String(10)),
        sa.Column("medico", sa.String(255)),
        sa.Column("consulta_medica", sa.Text()),
        sa.Column("fecha_creacion", sa.String(50)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_historias_clinicas_dni", "historias_clinicas", ["dni"])
    op.create_table(
        "pagos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dni_paciente", sa.String(8), nullable=False),
        sa.Column("nombre_paciente", sa.String(255)),
        sa.Column("monto", sa.Float()),
        sa.Column("fecha", sa.String(10), nullable=False),
        sa.Column("hora", sa.String(5)),
        sa.Column("tipo_pago", sa.String(50)),
        sa.Column("obra_social", sa.String(255)),
        sa.Column("observaciones", sa.Text()),
        sa.Column("fecha_registro", sa.String(50)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pagos_dni_paciente", "pagos", ["dni_paciente"])


def downgrade() -> None:
    op.drop_index("ix_pagos_dni_paciente", table_name="pagos")
    op.drop_table("pagos")
    op.drop_index("ix_historias_clinicas_dni", table_name="historias_clinicas")
    op.drop_table("historias_clinicas")
    op.drop_table("agenda_horarios")
    op.drop_table("turnos")
    op.drop_table("pacientes")
    op.drop_table("usuarios")
