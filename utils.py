"""Utilidades compartidas: normalización de texto, logging y modelo de ítem."""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

SEPARADOR_FUENTES = " | "


def normalize(text: str) -> str:
    """Minúsculas y sin acentos, para comparación de palabras clave."""
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def coincide_palabra_completa(texto_normalizado: str, palabra_normalizada: str) -> bool:
    """Compara por palabra completa, no por subcadena.

    Imprescindible para palabras cortas: "ere" (de "ERE") aparece como
    subcadena dentro de montones de palabras españolas normales
    ("dif**ere**ntes", "qu**ere**r"...), igual que "soc" dentro de "social"
    o "apt" dentro de "adaptar".
    """
    return re.search(rf"\b{re.escape(palabra_normalizada)}\b", texto_normalizado) is not None


def strip_html(html: str) -> str:
    """Elimina etiquetas HTML de un texto, dejando solo el contenido legible."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def content_hash(url: str, title: str) -> str:
    """Hash estable usado como clave de deduplicado."""
    base = (url or "") + "|" + (title or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def setup_logging(log_path: str, level: str = "INFO") -> logging.Logger:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("herramienta")
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


@dataclass
class Item:
    """Representa un ítem de contenido recopilado de cualquier fuente."""

    titulo: str
    url: str
    fuente: str
    categoria: str
    fecha: datetime
    resumen: str = ""
    autor: Optional[str] = None
    origen_tipo: str = "rss"  # rss | twitter | empleo
    extra: dict = field(default_factory=dict)
    # Cuántas fuentes distintas cubren esta misma noticia (ver dedup.py). Es
    # la señal usada para destacar lo más comentado: si 3 medios distintos
    # cubren lo mismo, probablemente sea más relevante que algo que solo
    # cubrió uno.
    cobertura: int = 1
    fuentes_cobertura: List[str] = field(default_factory=list)

    @property
    def hash(self) -> str:
        return content_hash(self.url, self.titulo)

    def fecha_iso(self) -> str:
        return self.fecha.astimezone(timezone.utc).isoformat()

    def fuentes_cobertura_texto(self) -> str:
        return SEPARADOR_FUENTES.join(self.fuentes_cobertura or [self.fuente])
