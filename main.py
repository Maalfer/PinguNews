#!/usr/bin/env python3
"""CLI de recolección: recopila de todas las fuentes y guarda en SQLite.

Pensado para programarse con cron/Task Scheduler. La visualización vive en
la app web (ver `app.py` / README), que lee directamente de la base de datos.

Uso manual:
    python main.py

Uso programado (cron, ejemplo diario a las 08:00):
    0 8 * * * cd /ruta/al/proyecto && ./venv/bin/python main.py >> logs/cron.log 2>&1
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from collector import ejecutar_recoleccion
from db import Database
from utils import setup_logging

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"


def cargar_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    config = cargar_config()
    general = config.get("general", {})

    setup_logging(
        str(BASE_DIR / general.get("log_path", "logs/app.log")),
        general.get("log_level", "INFO"),
    )

    db_path = str(BASE_DIR / general.get("db_path", "data/herramienta.db"))
    db = Database(db_path)

    nuevos = ejecutar_recoleccion(config, db)

    print(f"Ítems nuevos guardados: {len(nuevos)}")
    print("Consulta el panel web (ver README) para verlos agrupados por categoría.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
