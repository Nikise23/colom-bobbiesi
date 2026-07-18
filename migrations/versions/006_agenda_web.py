"""Revision ID: 006_agenda_web

Agenda pública separada: visibilidad, horarios web y bloqueos.
Seed inicial: Marianela Bobbiesi y Francisco Colom visibles con su agenda interna.
"""

from alembic import op
import sqlalchemy as sa


revision = "006_agenda_web"
down_revision = "005_performance_indexes"
branch_labels = None
depends_on = None

SEED_MEDICOS = ("Marianela Bobbiesi", "Francisco Colom")


def upgrade() -> None:
    op.create_table(
        "medicos_web",
        sa.Column("medico", sa.String(length=255), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("medico"),
    )
    op.create_table(
        "agenda_web_horarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medico", sa.String(length=255), nullable=False),
        sa.Column("dia", sa.String(length=20), nullable=False),
        sa.Column("hora", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("medico", "dia", "hora", name="uq_agenda_web_medico_dia_hora"),
    )
    op.create_index("ix_agenda_web_horarios_medico", "agenda_web_horarios", ["medico"])
    op.create_table(
        "bloqueos_web",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("medico", sa.String(length=255), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("fecha", sa.String(length=30), nullable=True),
        sa.Column("dia_semana", sa.String(length=20), nullable=True),
        sa.Column("hora_desde", sa.String(length=10), nullable=True),
        sa.Column("hora_hasta", sa.String(length=10), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bloqueos_web_medico", "bloqueos_web", ["medico"])

    conn = op.get_bind()
    agenda = sa.table(
        "agenda_horarios",
        sa.column("medico", sa.String),
        sa.column("dia", sa.String),
        sa.column("hora", sa.String),
    )
    medicos_web = sa.table(
        "medicos_web",
        sa.column("medico", sa.String),
        sa.column("visible", sa.Boolean),
    )
    agenda_web = sa.table(
        "agenda_web_horarios",
        sa.column("medico", sa.String),
        sa.column("dia", sa.String),
        sa.column("hora", sa.String),
    )

    for medico in SEED_MEDICOS:
        rows = conn.execute(
            sa.select(agenda.c.dia, agenda.c.hora).where(agenda.c.medico == medico)
        ).fetchall()
        if not rows:
            continue
        conn.execute(sa.insert(medicos_web).values(medico=medico, visible=True))
        for dia, hora in rows:
            conn.execute(
                sa.insert(agenda_web).values(medico=medico, dia=dia, hora=hora)
            )


def downgrade() -> None:
    op.drop_index("ix_bloqueos_web_medico", table_name="bloqueos_web")
    op.drop_table("bloqueos_web")
    op.drop_index("ix_agenda_web_horarios_medico", table_name="agenda_web_horarios")
    op.drop_table("agenda_web_horarios")
    op.drop_table("medicos_web")
