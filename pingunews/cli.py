"""CLI de recolección: recopila de todas las fuentes y guarda en SQLite.

Es lo que ejecuta el temporizador de systemd (o un cron). La visualización
vive en la app web (`pingunews.web`), que lee de la misma base de datos.

    python -m pingunews.cli
"""
from __future__ import annotations

import sys

from pingunews.collector import ejecutar_recoleccion
from pingunews.config import cargar_config, ruta_db, ruta_log
from pingunews.logging_setup import setup_logging
from pingunews.storage import Database


def main() -> int:
    config = cargar_config()
    general = config.get("general", {})

    setup_logging(ruta_log(config), general.get("log_level", "INFO"))
    db = Database(ruta_db(config))

    nuevos = ejecutar_recoleccion(config, db)

    print(f"Ítems nuevos guardados: {len(nuevos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
