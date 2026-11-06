"""Configuración del logging de la aplicación."""
from __future__ import annotations

import logging
from pathlib import Path

LOGGER_RAIZ = "herramienta"


def setup_logging(log_path: str, level: str = "INFO") -> logging.Logger:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_RAIZ)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)
    return logger
