"""Recopilación desde Twitter/X.

Sin Bearer Token de la API v2, la única vía es snscrape (scraping no oficial).
AVISO IMPORTANTE: X ha endurecido activamente las protecciones anti-scraping
desde 2023. snscrape puede:
  - devolver 0 resultados aunque existan tuits,
  - fallar directamente con errores de autenticación/consulta,
  - dejar de funcionar por completo si X cambia su web sin previo aviso.
Por eso este módulo está desactivado por defecto (twitter.enabled: false en
config.yaml) y sus fallos nunca detienen el resto de la herramienta.

Si en el futuro se dispone de un Bearer Token de la API v2 de X, lo correcto
es sustituir `_buscar_con_snscrape` por una llamada a
GET https://api.x.com/2/tweets/search/recent usando `requests`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from classifier import clasificar, resumir
from utils import Item

logger = logging.getLogger("herramienta.twitter")


def _buscar_con_snscrape(query: str, max_results: int, limite_timestamp: float):
    try:
        import snscrape.modules.twitter as sntwitter
    except ImportError as exc:
        raise RuntimeError(
            "snscrape no está instalado. Instálalo con: "
            "pip install git+https://github.com/JustAnotherArchivist/snscrape.git"
        ) from exc

    resultados = []
    scraper = sntwitter.TwitterSearchScraper(query)
    for i, tweet in enumerate(scraper.get_items()):
        if i >= max_results:
            break
        if tweet.date.timestamp() < limite_timestamp:
            break
        resultados.append(tweet)
    return resultados


def recopilar(twitter_config: dict, keywords: dict, lookback_hours: int) -> List[Item]:
    if not twitter_config.get("enabled", False):
        logger.info("Twitter/X desactivado en config.yaml (twitter.enabled: false)")
        return []

    limite_timestamp = datetime.now(timezone.utc).timestamp() - lookback_hours * 3600
    max_results = twitter_config.get("max_results_per_query", 30)

    consultas = list(twitter_config.get("hashtags", []))
    for cuenta in twitter_config.get("cuentas", []):
        consultas.append(f"from:{cuenta}")

    items: List[Item] = []
    for query in consultas:
        try:
            tweets = _buscar_con_snscrape(query, max_results, limite_timestamp)
            for tweet in tweets:
                # Filtrar retuits sin comentario (ruido sin contenido propio)
                if getattr(tweet, "retweetedTweet", None) is not None:
                    continue

                texto = tweet.rawContent if hasattr(tweet, "rawContent") else str(tweet.content)
                categoria = clasificar(texto, "", keywords, categoria_sugerida="ciberseguridad")

                items.append(
                    Item(
                        titulo=texto.splitlines()[0][:120] if texto else "(tuit sin texto)",
                        url=tweet.url,
                        fuente=f"X/@{tweet.user.username}",
                        categoria=categoria,
                        fecha=tweet.date,
                        resumen=resumir(texto),
                        autor=tweet.user.username,
                        origen_tipo="twitter",
                    )
                )
            logger.info("Twitter OK: '%s' (%d tuits)", query, len(tweets))
        except Exception as exc:  # noqa: BLE001 - un fallo de X no debe parar el resto
            logger.warning("Twitter FALLO para '%s' -> %s", query, exc)
            continue

    return items
