"""Lógica de recolección compartida entre la CLI (main.py) y la app web (app.py)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import empleo
import rss
import twitter
from db import Database
from dedup import agrupar_por_titulo, separar_duplicados_de_historico
from utils import Item

BASE_DIR = Path(__file__).parent
logger = logging.getLogger("herramienta.collector")


def ejecutar_recoleccion(config: dict, db: Database) -> List[Item]:
    """Recopila de todas las fuentes, deduplica contra el histórico y guarda.

    Devuelve la lista de ítems nuevos (no vistos antes) que se acaban de guardar.
    """
    general = config.get("general", {})
    lookback_hours = general.get("lookback_hours", 168)
    keywords = config.get("keywords", {})

    logger.info("=== Inicio de recopilación (ventana: %dh) ===", lookback_hours)

    todos_los_items: List[Item] = []

    feeds = config.get("rss_feeds", [])
    items_rss = rss.recopilar(feeds, keywords, lookback_hours)
    logger.info("RSS: %d ítems recopilados en total", len(items_rss))
    todos_los_items.extend(items_rss)

    twitter_cfg = config.get("twitter", {})
    items_twitter = twitter.recopilar(twitter_cfg, keywords, lookback_hours)
    logger.info("Twitter/X: %d ítems recopilados en total", len(items_twitter))
    todos_los_items.extend(items_twitter)

    empleo_cfg = config.get("empleo", {})
    items_empleo = empleo.recopilar(empleo_cfg, keywords, lookback_hours)
    logger.info("Empleo: %d ítems recopilados en total", len(items_empleo))
    todos_los_items.extend(items_empleo)

    logger.info("Total bruto recopilado: %d ítems", len(todos_los_items))

    vistos_en_esta_tanda = set()
    unicos = []
    for item in todos_los_items:
        if item.hash in vistos_en_esta_tanda:
            continue
        vistos_en_esta_tanda.add(item.hash)
        unicos.append(item)

    # Dos fuentes distintas cubriendo la misma noticia (p. ej. el mismo CVE en
    # Hispasec y en MuySeguridad) tienen URLs distintas y por tanto hashes
    # distintos, así que el filtro de arriba no las detecta. Se agrupan por
    # similitud de título, primero dentro de esta misma tanda: el ítem
    # superviviente se queda con cuántas fuentes lo cubrieron (item.cobertura),
    # que es la señal usada para destacar lo más comentado del sector.
    dedup_cfg = general.get("dedup_similitud", {})
    dias_dedup = dedup_cfg.get("dias", 30)
    umbral_dedup = dedup_cfg.get("umbral", 0.55)

    antes_similitud = len(unicos)
    unicos = agrupar_por_titulo(unicos, umbral_dedup)
    if antes_similitud != len(unicos):
        logger.info(
            "Agrupado por título (misma tanda): %d -> %d ítems",
            antes_similitud, len(unicos),
        )

    nuevos = db.filtrar_nuevos(unicos)
    logger.info("Ítems nuevos tras deduplicar contra histórico (por hash): %d", len(nuevos))

    # ...y también contra el histórico reciente, por si la misma noticia ya se
    # guardó en una ejecución anterior con un titular ligeramente distinto: en
    # vez de descartarla sin más, se suma como fuente nueva a la cobertura de
    # la fila ya existente.
    existentes = db.existentes_para_dedup(dias_dedup)
    antes_historico = len(nuevos)
    nuevos, incrementos = separar_duplicados_de_historico(nuevos, existentes, umbral_dedup)
    if antes_historico != len(nuevos):
        logger.info(
            "Deduplicado por título (contra histórico de %d días): %d -> %d ítems nuevos, "
            "%d ya existentes con cobertura ampliada",
            dias_dedup, antes_historico, len(nuevos), len(incrementos),
        )
    for hash_existente, fuentes_nuevas in incrementos:
        db.incrementar_cobertura(hash_existente, fuentes_nuevas)

    db.guardar(nuevos)
    db.set_meta("ultima_recoleccion", datetime.now(timezone.utc).isoformat())

    logger.info("=== Fin de recopilación ===")
    return nuevos
