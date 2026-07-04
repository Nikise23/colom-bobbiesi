"""Ampliar columnas DNI — algunos registros en /data superan 8 caracteres."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_widen_dni_columns"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("pacientes", "dni", type_=sa.String(20), existing_type=sa.String(8))
    op.alter_column("turnos", "dni_paciente", type_=sa.String(20), existing_type=sa.String(8))
    op.alter_column("historias_clinicas", "dni", type_=sa.String(20), existing_type=sa.String(8))
    op.alter_column("pagos", "dni_paciente", type_=sa.String(20), existing_type=sa.String(8))


def downgrade() -> None:
    op.alter_column("pagos", "dni_paciente", type_=sa.String(8), existing_type=sa.String(20))
    op.alter_column("historias_clinicas", "dni", type_=sa.String(8), existing_type=sa.String(20))
    op.alter_column("turnos", "dni_paciente", type_=sa.String(8), existing_type=sa.String(20))
    op.alter_column("pacientes", "dni", type_=sa.String(8), existing_type=sa.String(20))
