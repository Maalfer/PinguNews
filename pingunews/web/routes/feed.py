"""Feed RSS 2.0 del panel (`/feed.xml`).

Permite suscribirse con cualquier lector RSS sin pasar por el login. Reutiliza
los mismos datos y filtros que el panel (ver routes/panel.py), pero:
  - en orden puramente cronológico (lo que espera cualquier lector RSS, al
    contrario que el panel, que ordena por cobertura para destacar lo más
    comentado);
  - sin disparar una recolección nueva: se construye solo con lo que ya hay
    en la base de datos, para no convertir cada sondeo de un lector RSS en
    una recolección contra las fuentes externas.

Admite los mismos filtros que el panel vía query string, por ejemplo para
suscribirse solo a una categoría:
    /feed.xml?categorias=ciberseguridad
    /feed.xml?categorias=empleo&categorias=tendencias_sector&dias=7
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from typing import List, Optional
from xml.sax.saxutils import escape, quoteattr

from fastapi import APIRouter, Query
from fastapi.responses import Response
from starlette.requests import Request

from pingunews.collector.classifier import CATEGORIA_LABELS
from pingunews.web.deps import get_ajustes, get_db
from pingunews.web.plantillas import autor_limpio, etiqueta_categoria

router = APIRouter()

MEDIA_TYPE = "application/rss+xml; charset=utf-8"
LIMITE_ITEMS_DEFECTO = 60
LIMITE_ITEMS_MAX = 200
# El timer de recolección corre cada 2h (ver pingunews-recoleccion.timer en el
# servidor): se usa el mismo valor como <ttl> para que los lectores RSS no
# sondeen más a menudo de lo que el contenido puede cambiar realmente.
TTL_MINUTOS = 120
# Espacio de nombres propio para los campos que no existen en RSS 2.0 pero sí
# tienen sentido aquí: cuántas fuentes distintas cubren cada noticia (ver
# collector/dedup.py), que es justo la señal diferencial de esta herramienta.
NS_PINGUNEWS = "https://pingunews.dockerlabs.es/xmlns/rss/1.0"


def _fecha_rfc822(fecha_iso: str) -> str:
    """ISO 8601 (como se guarda en la BD, ver models.Item.fecha_iso) -> RFC 822
    (lo que exige el formato RSS 2.0 para pubDate / lastBuildDate)."""
    dt = datetime.fromisoformat(fecha_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc))


def _item_xml(item: dict) -> str:
    creador = autor_limpio(item.get("autor")) or item["fuente"]
    fuentes_cobertura = (
        item["fuentes_cobertura"].split(" | ") if item.get("fuentes_cobertura") else [item["fuente"]]
    )

    return (
        "<item>"
        f"<title>{escape(item['titulo'])}</title>"
        f"<link>{escape(item['url'])}</link>"
        f'<guid isPermaLink="false">pingunews-{escape(item["hash"])}</guid>'
        f"<pubDate>{_fecha_rfc822(item['fecha'])}</pubDate>"
        f"<category>{escape(etiqueta_categoria(item['categoria']))}</category>"
        f"<dc:creator>{escape(creador)}</dc:creator>"
        f"<description>{escape(item.get('resumen') or '')}</description>"
        f"<pingunews:cobertura>{int(item.get('cobertura') or 1)}</pingunews:cobertura>"
        f"<pingunews:fuentes>{escape(' | '.join(fuentes_cobertura))}</pingunews:fuentes>"
        "</item>"
    )


@router.get("/feed.xml")
def feed_rss(
    request: Request,
    categorias: Optional[List[str]] = Query(default=None),
    dias: Optional[int] = Query(default=None, ge=1, le=365),
    limite: int = Query(default=LIMITE_ITEMS_DEFECTO, ge=1, le=LIMITE_ITEMS_MAX),
):
    ajustes = get_ajustes(request)
    db = get_db(request)

    categorias_activas = [c for c in (categorias or []) if c in ajustes.todas_las_categorias] or None
    ventana_dias = dias or max(ajustes.opciones_dias)

    items = db.items_recientes(ventana_dias, categorias_activas)
    items.sort(key=lambda i: i["fecha"], reverse=True)
    items = items[:limite]

    base = str(request.base_url).rstrip("/")
    url_propia = str(request.url)

    if categorias_activas:
        etiquetas = [CATEGORIA_LABELS.get(c, c).split(" (")[0] for c in categorias_activas]
        titulo_canal = "PinguNews — " + ", ".join(etiquetas)
    else:
        titulo_canal = "PinguNews — Ciberseguridad, hacking, empleo y desarrollo IT"

    descripcion_canal = (
        "Agregador de noticias de ciberseguridad, hacking, tendencias del sector, "
        "empleo y desarrollo IT en español, con deduplicado y señal de cobertura "
        "entre varias fuentes."
    )

    ultima_recoleccion = db.get_meta("ultima_recoleccion")
    if ultima_recoleccion:
        last_build = _fecha_rfc822(ultima_recoleccion)
    elif items:
        last_build = _fecha_rfc822(items[0]["fecha"])
    else:
        last_build = format_datetime(datetime.now(timezone.utc))

    items_xml = "".join(_item_xml(i) for i in items)
    imagen_canal = escape(f"{base}/static/logo-128.png")
    enlace_canal = escape(f"{base}/")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" '
        'xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        f'xmlns:pingunews="{NS_PINGUNEWS}">\n'
        "<channel>"
        f"<title>{escape(titulo_canal)}</title>"
        f"<link>{enlace_canal}</link>"
        f"<atom:link href={quoteattr(url_propia)} rel=\"self\" type=\"application/rss+xml\" />"
        f"<description>{escape(descripcion_canal)}</description>"
        "<language>es</language>"
        f"<lastBuildDate>{last_build}</lastBuildDate>"
        "<generator>PinguNews</generator>"
        f"<ttl>{TTL_MINUTOS}</ttl>"
        f"<image><url>{imagen_canal}</url><title>{escape(titulo_canal)}</title><link>{enlace_canal}</link></image>"
        f"{items_xml}"
        "</channel>"
        "</rss>"
    )

    return Response(content=xml, media_type=MEDIA_TYPE, headers={"Cache-Control": "public, max-age=600"})
