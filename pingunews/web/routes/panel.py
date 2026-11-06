"""Panel principal (listado, filtros, búsqueda) y recolección manual."""
from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from pingunews.collector import ejecutar_recoleccion
from pingunews.collector.classifier import CATEGORIA_LABELS, CATEGORIA_ORDEN
from pingunews.web import busqueda, csrf
from pingunews.web.deps import get_ajustes, get_db, render, usuario_actual
from pingunews.web.noticias import agrupar_por_categoria, enriquecer_items

router = APIRouter()
logger = logging.getLogger("herramienta.web.panel")

_RECOLECCION = {"ultima": 0.0, "lock": threading.Lock()}
RECOLECCION_ENFRIAMIENTO = 300


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    dias: Optional[int] = None,
    categorias: Optional[List[str]] = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    q: str = Query(default="", max_length=300),
):
    ajustes = get_ajustes(request)
    db = get_db(request)
    q = busqueda.limpiar_consulta(q)
    dias = dias if dias in ajustes.opciones_dias else ajustes.dias_por_defecto
    categorias_activas = [c for c in (categorias or []) if c in ajustes.todas_las_categorias] or ajustes.todas_las_categorias
    usuario = usuario_actual(request)

    # Ya vienen ordenados por cobertura (nº de fuentes que cubren la misma
    # noticia) y luego por fecha, ver Database.items_recientes: lo más relevante
    # siempre queda primero, también después de paginar.
    items = db.items_recientes(dias, categorias_activas)
    if q:
        items = busqueda.filtrar(items, q)
    enriquecer_items(db, items, usuario)

    # Lo más comentado: cubierto por varias fuentes independientes, buena
    # señal gratuita de qué es relevante de verdad (útil para un directo).
    # Solo se muestra en la primera página: es un destacado, no tiene sentido
    # repetirlo en cada página.
    destacados = (
        [i for i in items if i["cobertura"] >= ajustes.destacados_cobertura_minima][: ajustes.destacados_max]
        if pagina == 1
        else []
    )

    conteo_por_categoria = {cat: len(lista) for cat, lista in agrupar_por_categoria(items).items()}
    categorias_disponibles = [(cat, CATEGORIA_LABELS[cat]) for cat in CATEGORIA_ORDEN]

    # Una única lista con todas las noticias (las categorías se filtran con el
    # desplegable), de más recientes a más antiguas y paginada en conjunto.
    ordenadas = sorted(items, key=lambda i: i["fecha"], reverse=True)
    total_paginas = max(1, math.ceil(len(ordenadas) / ajustes.items_por_pagina))
    pagina = min(max(pagina, 1), total_paginas)
    inicio = (pagina - 1) * ajustes.items_por_pagina
    noticias = ordenadas[inicio:inicio + ajustes.items_por_pagina]

    categorias_qs = ""
    if set(categorias_activas) != set(ajustes.todas_las_categorias):
        categorias_qs = "&" + urlencode({"categorias": categorias_activas}, doseq=True)
    if q:
        # La búsqueda viaja en todos los enlaces (rango, paginación, actualizar).
        categorias_qs += "&" + urlencode({"q": q})

    ultima_recoleccion_raw = db.get_meta("ultima_recoleccion")
    ultima_recoleccion = None
    if ultima_recoleccion_raw:
        ultima_recoleccion = datetime.fromisoformat(ultima_recoleccion_raw).strftime("%d/%m/%Y %H:%M UTC")

    return render(request, "dashboard.html.j2", {
        "usuario": usuario,
        "csrf_token": csrf.token_csrf(request),
        "dias": dias,
        "q": q,
        "opciones_dias": ajustes.opciones_dias,
        "categorias_disponibles": categorias_disponibles,
        "categorias_activas": categorias_activas,
        "categorias_qs": categorias_qs,
        "noticias": noticias,
        "destacados": destacados,
        "destacados_cobertura_minima": ajustes.destacados_cobertura_minima,
        "conteo_por_categoria": conteo_por_categoria,
        "total_items": len(items),
        "pagina": pagina,
        "total_paginas": total_paginas,
        "ultima_recoleccion": ultima_recoleccion,
        "twitter_activo": ajustes.twitter_activo,
    })


@router.post("/actualizar")
def actualizar(
    request: Request,
    csrf_token: str = Form(...),
    dias: Optional[int] = None,
    categorias: Optional[List[str]] = Query(default=None),
    q: str = Query(default="", max_length=300),
):
    """Lanza una recolección nueva (bloqueante) y vuelve al panel."""
    csrf.exigir_csrf(request, csrf_token)
    # Una recolección a la vez y como mucho una cada 5 minutos para todo el
    # servicio: evita usar el botón para saturar la app o las fuentes externas.
    ahora = time.time()
    if ahora - _RECOLECCION["ultima"] >= RECOLECCION_ENFRIAMIENTO and _RECOLECCION["lock"].acquire(blocking=False):
        try:
            _RECOLECCION["ultima"] = ahora
            logger.info("Recolección manual solicitada desde el panel web")
            ejecutar_recoleccion(request.app.state.config, get_db(request))
        finally:
            _RECOLECCION["lock"].release()

    query = {"dias": dias if dias is not None else get_ajustes(request).dias_por_defecto}
    if categorias:
        query["categorias"] = categorias
    if q.strip():
        query["q"] = busqueda.limpiar_consulta(q)
    return RedirectResponse(url=f"/?{urlencode(query, doseq=True)}", status_code=303)
