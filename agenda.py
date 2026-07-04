#!/usr/bin/env python3
"""
DEPRECADO — No usar.

Este mini-servidor Flask duplicaba rutas de agenda que ya existen en app.py:
  GET  /api/agenda
  PUT  /api/agenda/<medico>/<dia>
  PUT  /api/agenda/<medico>

Usar la aplicación principal (python app.py) o admin_agenda.py para gestión CLI.
"""

import sys

print(__doc__)
sys.exit(1)
