#!/usr/bin/env python3
"""Diagnóstico rápido de la base (ejecutar en shell de Render)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consultorio import create_app
from consultorio.storage.queries import (
    count_pacientes,
    count_turnos_fecha,
    count_turnos_total,
    listar_atendidos_sin_pago,
    load_pagos_fecha,
    load_turnos_fecha,
)
from consultorio.utils.fechas import hoy_ar_iso


def main() -> int:
    app = create_app()
    with app.app_context():
        hoy = hoy_ar_iso()
        print("=== Colom Bobbiesi — health check ===")
        print(f"Fecha hoy (AR): {hoy}")
        print()

        t0 = time.perf_counter()
        total_turnos = count_turnos_total()
        t1 = time.perf_counter()
        turnos_hoy = load_turnos_fecha(hoy)
        t2 = time.perf_counter()
        pagos_hoy = load_pagos_fecha(hoy)
        t3 = time.perf_counter()
        sin_pago = listar_atendidos_sin_pago(hoy)
        t4 = time.perf_counter()

        atendidos_hoy = [t for t in turnos_hoy if t.get("estado") == "atendido"]

        print(f"Pacientes en sistema:     {count_pacientes()}")
        print(f"Turnos TOTAL en DB:       {total_turnos}  ({(t1-t0)*1000:.0f} ms)")
        print(f"Turnos HOY ({hoy}):       {len(turnos_hoy)}  ({(t2-t1)*1000:.0f} ms)")
        print(f"  - atendidos hoy:        {len(atendidos_hoy)}")
        print(f"Pagos HOY:                {len(pagos_hoy)}  ({(t3-t2)*1000:.0f} ms)")
        print(f"Atendidos SIN pago hoy:   {len(sin_pago)}  ({(t4-t3)*1000:.0f} ms)")
        print()

        if pagos_hoy:
            print("Pagos de hoy (máx. 5):")
            for p in pagos_hoy[:5]:
                print(
                    f"  id={p.get('id')} {p.get('nombre_paciente')} "
                    f"${p.get('monto')} {p.get('tipo_pago')} {p.get('hora', '')}"
                )
            print()

        if sin_pago:
            print("Atendidos sin pago (recuperar en secretaría):")
            for p in sin_pago[:10]:
                print(
                    f"  {p.get('hora_turno')} {p.get('apellido')}, {p.get('nombre')} "
                    f"DNI {p.get('dni')} — {p.get('medico')}"
                )
            if len(sin_pago) > 10:
                print(f"  ... y {len(sin_pago) - 10} más")
            print()

        futuros = [t for t in turnos_hoy if t.get("fecha", "") > hoy]
        if total_turnos > len(turnos_hoy):
            print("OK: Los turnos históricos/futuros siguen en la base.")
            print(f"    Solo se listan {len(turnos_hoy)} del día; el total es {total_turnos}.")
        print()
        print("=== Fin ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
