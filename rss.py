"""Recopilación de noticias desde feeds RSS/Atom configurables."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime
from typing import List

import feedparser

from classifier import clasificar, resumir
from utils import Item

logger = logging.getLogger("herramienta.rss")

USER_AGENT = "herramienta-ciberseguridad/1.0 (+https://github.com/; uso personal)"


def _fecha_entrada(entry) -> datetime:
    for campo in ("published_parsed", "updated_parsed"):
        valor = getattr(entry, campo, None)
        if valor:
            return datetime.fromtimestamp(mktime(valor), tz=timezone.utc)
    return datetime.now(timezone.utc)


def recopilar(feeds_config: List[dict], keywords: dict, lookback_hours: int) -> List[Item]:
    """Descarga y parsea cada feed configurado. Un feed caído no detiene al resto."""
    items: List[Item] = []
    limite = datetime.now(timezone.utc).timestamp() - lookback_hours * 3600

    for feed_cfg in feeds_config:
        nombre = feed_cfg.get("nombre", feed_cfg.get("url"))
        url = feed_cfg["url"]
        categoria_feed = feed_cfg.get("categoria", "actualidad")
        try:
            parsed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
            if parsed.bozo and not parsed.entries:
                raise RuntimeError(getattr(parsed, "bozo_exception", "feed vacío o inválido"))

            entradas_en_ventana = 0
            for entry in parsed.entries:
                fecha = _fecha_entrada(entry)
                if fecha.timestamp() < limite:
                    continue
                entradas_en_ventana += 1

                titulo = getattr(entry, "title", "(sin título)")
                link = getattr(entry, "link", "")
                contenido = getattr(entry, "summary", "") or getattr(entry, "description", "")
                autor = getattr(entry, "author", None)

                categoria = clasificar(titulo, contenido, keywords, categoria_sugerida=categoria_feed)

                items.append(
                    Item(
                        titulo=titulo.strip(),
                        url=link,
                        fuente=nombre,
                        categoria=categoria,
                        fecha=fecha,
                        resumen=resumir(contenido),
                        autor=autor,
                        origen_tipo="rss",
                    )
                )
            logger.info(
                "RSS OK: %s (%d entradas recientes de %d totales)",
                nombre, entradas_en_ventana, len(parsed.entries),
            )
        except Exception as exc:  # noqa: BLE001 - un feed caído no debe parar el resto
            logger.warning("RSS FALLO: %s (%s) -> %s", nombre, url, exc)
            continue

    return items
