"""Modelo de dominio: un ítem de contenido recopilado de cualquier fuente."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

SEPARADOR_FUENTES = " | "


def content_hash(url: str, title: str) -> str:
    """Hash estable usado como clave de deduplicado."""
    base = (url or "") + "|" + (title or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


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
    # Cuántas fuentes distintas cubren esta misma noticia (ver collector/dedup.py).
    # Es la señal usada para destacar lo más comentado: si 3 medios distintos
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
