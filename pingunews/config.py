"""Configuración: rutas del proyecto, entorno y carga de `config/config.yaml`."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# Raíz del repositorio (config/, data/ y logs/ viven aquí, fuera del paquete).
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"

# "produccion" activa cookies de sesión solo-HTTPS. En local se deja
# desactivado para poder probar por http://127.0.0.1 sin HTTPS.
PRODUCCION = os.environ.get("ENTORNO", "local").strip().lower() == "produccion"


def cargar_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ruta_log(config: dict) -> str:
    return str(BASE_DIR / config.get("general", {}).get("log_path", "logs/app.log"))


def ruta_db(config: dict) -> str:
    return str(BASE_DIR / config.get("general", {}).get("db_path", "data/herramienta.db"))
