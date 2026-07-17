# Archivos JSON de datos

Estos archivos (`pacientes.json`, `turnos.json`, etc.) **no son la base de
producción**. Con `DATABASE_URL` la app usa PostgreSQL.

Si están vacíos (`[]`) y alguien corre `migrate_json_to_postgres.py --write`
contra una base, antes podían borrar tablas enteras. Ahora:

- migrate solo escribe en **localhost**
- requiere `--write`
- **omite** JSON vacíos o ausentes

Para pruebas locales: copiá un backup ZIP a la raíz y corré
`python scripts/setup_postgres_local.py` con `DATABASE_URL` en localhost.
