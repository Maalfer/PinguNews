"""Recopilación de ofertas de empleo de ciberseguridad/IT sin usar APIs de pago.

Decisiones tomadas (ver README para más detalle):
  - LinkedIn: NO se scrapea. Requiere login, y su ToS prohíbe explícitamente
    el scraping automatizado; no es una vía fiable ni legal.
  - Tecnoempleo.com: NO se usa. Su robots.txt bloquea explícitamente a los
    bots de Anthropic/Claude ("User-agent: Claude" / "ClaudeBot" -> Disallow: /),
    así que esta herramienta respeta esa directiva y no la scrapea.
  - RemoteOK: se usa su API JSON pública y sin autenticación (remoteok.com/api),
    que ellos mismos ofrecen para reutilización (con atribución).
  - Jobicy: se usa su API JSON pública y sin autenticación (jobicy.com/api),
    filtrando por su propio campo "jobIndustry" (p. ej. "Cybersecurity"), que
    es más preciso que buscar palabras sueltas en el título.
  - We Work Remotely: se usa su RSS público por categoría.
  - Cualquier otro feed RSS de empleo al que el usuario tenga acceso legítimo
    se puede añadir en config.yaml -> empleo.fuentes_rss sin tocar código.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import requests

from pingunews.collector.classifier import resumir
from pingunews.collector.sources.rss import recopilar as recopilar_rss
from pingunews.models import Item
from pingunews.text import coincide_palabra_completa, normalize

logger = logging.getLogger("herramienta.empleo")

USER_AGENT = "herramienta-ciberseguridad/1.0 (+https://github.com/; uso personal)"


def es_relevante(texto: str, filtro_relevancia: List[str]) -> bool:
    """Comprueba relevancia por palabra completa contra el texto dado (normalizado)."""
    texto_normalizado = normalize(texto)
    return any(
        coincide_palabra_completa(texto_normalizado, normalize(palabra))
        for palabra in filtro_relevancia
    )


def _recopilar_remoteok(cfg: dict, filtro_relevancia: List[str], lookback_hours: int) -> List[Item]:
    items: List[Item] = []
    if not cfg.get("enabled", False):
        return items

    url = cfg.get("url", "https://remoteok.com/api")
    limite = datetime.now(timezone.utc).timestamp() - lookback_hours * 3600

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("RemoteOK FALLO -> %s", exc)
        return items

    # El primer elemento es metadata ("legal", "last_updated"), no una oferta.
    ofertas = [d for d in data if isinstance(d, dict) and d.get("id")]

    for oferta in ofertas:
        puesto = oferta.get("position", "")
        tags = [normalize(t) for t in (oferta.get("tags", []) or [])]

        # Solo se mira el título real del puesto: no nos fiamos de los "tags"
        # de RemoteOK, que etiquetan como "infosec" puestos genéricos de Cloud/Sales.
        if not es_relevante(puesto, filtro_relevancia):
            continue

        try:
            fecha = datetime.fromisoformat(oferta["date"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            fecha = datetime.now(timezone.utc)
        if fecha.timestamp() < limite:
            continue

        empresa = oferta.get("company", "")
        items.append(
            Item(
                titulo=f"{puesto} — {empresa}".strip(" —"),
                url=oferta.get("url") or oferta.get("apply_url", ""),
                fuente="RemoteOK",
                categoria="empleo",
                fecha=fecha,
                resumen=resumir(oferta.get("description", "")),
                autor=empresa,
                origen_tipo="empleo",
                extra={"tags": tags},
            )
        )

    logger.info("RemoteOK OK: %d ofertas relevantes de %d totales", len(items), len(ofertas))
    return items


def _recopilar_jobicy(cfg: dict, lookback_hours: int) -> List[Item]:
    items: List[Item] = []
    if not cfg.get("enabled", False):
        return items

    url = cfg.get("url", "https://jobicy.com/api/v2/remote-jobs?count=100")
    industrias_objetivo = {normalize(i) for i in cfg.get("filtro_industrias", [])}
    limite = datetime.now(timezone.utc).timestamp() - lookback_hours * 3600

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Jobicy FALLO -> %s", exc)
        return items

    ofertas = data.get("jobs", [])

    for oferta in ofertas:
        industrias = {normalize(i) for i in (oferta.get("jobIndustry") or [])}
        if not industrias & industrias_objetivo:
            continue

        try:
            fecha = datetime.fromisoformat(oferta["pubDate"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            fecha = datetime.now(timezone.utc)
        if fecha.timestamp() < limite:
            continue

        empresa = oferta.get("companyName", "")
        puesto = oferta.get("jobTitle", "")
        items.append(
            Item(
                titulo=f"{puesto} — {empresa}".strip(" —"),
                url=oferta.get("url", ""),
                fuente="Jobicy",
                categoria="empleo",
                fecha=fecha,
                resumen=resumir(oferta.get("jobExcerpt") or oferta.get("jobDescription", "")),
                autor=empresa,
                origen_tipo="empleo",
                extra={"industrias": list(industrias)},
            )
        )

    logger.info("Jobicy OK: %d ofertas relevantes de %d totales", len(items), len(ofertas))
    return items


def recopilar(empleo_config: dict, keywords: dict, lookback_hours_defecto: int) -> List[Item]:
    items: List[Item] = []
    lookback_hours = empleo_config.get("lookback_hours", lookback_hours_defecto)
    filtro_relevancia = empleo_config.get("filtro_relevancia", [])

    fuentes_rss = empleo_config.get("fuentes_rss", [])
    if fuentes_rss:
        candidatos_rss = recopilar_rss(fuentes_rss, keywords, lookback_hours)
        relevantes_rss = [
            i
            for i in candidatos_rss
            # El título suele venir como "Empresa: Puesto" (p. ej. We Work
            # Remotely). Solo se mira la parte del puesto, no la empresa ni el
            # resumen: una empresa de seguridad (p. ej. "Keeper Security")
            # repite esa palabra en toda la descripción aunque el puesto en
            # concreto sea de Ventas o Soporte, así que el resumen da ruido.
            if es_relevante(i.titulo.split(":", 1)[-1], filtro_relevancia)
        ]
        # Un feed de empleo es siempre empleo, sin importar qué palabras técnicas
        # tenga el título (si no, "DevOps Engineer" se reclasificaría como
        # desarrollo_it y desaparecería de la sección de empleo).
        for item in relevantes_rss:
            item.categoria = "empleo"
        logger.info(
            "RSS empleo: %d ofertas relevantes de %d totales", len(relevantes_rss), len(candidatos_rss)
        )
        items.extend(relevantes_rss)

    remoteok_cfg = empleo_config.get("remoteok", {})
    items.extend(_recopilar_remoteok(remoteok_cfg, filtro_relevancia, lookback_hours))

    jobicy_cfg = empleo_config.get("jobicy", {})
    items.extend(_recopilar_jobicy(jobicy_cfg, lookback_hours))

    return items
