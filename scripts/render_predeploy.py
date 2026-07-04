#!/usr/bin/env python3
"""Pre-deploy en Render: aplica migraciones Alembic.

Si las tablas ya existían (p. ej. por db.create_all en un deploy anterior),
marca la revisión actual con `alembic stamp head` en lugar de fallar.
"""

import subprocess
import sys


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def main() -> int:
    upgrade = run(["alembic", "upgrade", "head"])
    if upgrade.returncode == 0:
        if upgrade.stdout:
            print(upgrade.stdout)
        return 0

    err = (upgrade.stderr or "") + (upgrade.stdout or "")
    if "DuplicateTable" in err or "already exists" in err:
        print("Las tablas ya existen; sincronizando estado de Alembic (stamp head)...")
        stamp = run(["alembic", "stamp", "head"])
        if stamp.stdout:
            print(stamp.stdout)
        if stamp.returncode != 0:
            print(stamp.stderr, file=sys.stderr)
        return stamp.returncode

    print(err, file=sys.stderr)
    return upgrade.returncode


if __name__ == "__main__":
    sys.exit(main())
