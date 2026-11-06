"""Preparación de ítems para mostrarlos (fechas, likes, guardados, agrupado)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from starlette.requests import Request

from pingunews.models import SEPARADOR_FUENTES
from pingunews.storage import Database

_RE_HASH = re.compile(r"[A-Za-z0-9_-]{1,128}")


def agrupar_por_categoria(items: List[dict]) -> dict:
    grupos = defaultdict(list)
    for item in items:
        grupos[item["categoria"]].append(item)
    return grupos


def enriquecer_items(db: Database, items: List[dict], usuario: Optional[dict]) -> None:
    """Añade a cada ítem: fecha formateada, lista de fuentes de cobertura,
    nº de likes totales y si el usuario actual le dio like / lo guardó."""
    hashes = [item["hash"] for item in items]
    conteo_likes = db.conteo_likes(hashes)
    guardados_usuario = db.hashes_guardados(usuario["id"], hashes) if usuario else set()
    likes_usuario = db.hashes_con_like(usuario["id"], hashes) if usuario else set()

    for item in items:
        fecha = datetime.fromisoformat(item["fecha"])
        item["fecha_fmt"] = fecha.strftime("%d/%m %H:%M")
        item["fuentes_cobertura_lista"] = (
            item["fuentes_cobertura"].split(SEPARADOR_FUENTES)
            if item.get("fuentes_cobertura")
            else [item["fuente"]]
        )
        item["likes"] = conteo_likes.get(item["hash"], 0)
        item["guardado"] = item["hash"] in guardados_usuario
        item["le_gusta"] = item["hash"] in likes_usuario


def hash_valido(db: Database, item_hash: str) -> bool:
    return bool(_RE_HASH.fullmatch(item_hash)) and db.existe_item(item_hash)


def destino_tras_accion(request: Request, item_hash: str = "") -> str:
    """A dónde volver tras guardar/dar like: la misma página desde la que se
    pulsó el botón. Solo se aceptan rutas de ESTE sitio (el Referer lo manda el
    navegador, pero no se redirige a hosts externos) y se añade un ancla a la
    noticia para no perder la posición de lectura."""
    destino = "/"
    referer = request.headers.get("referer") or ""
    if referer:
        u = urlparse(referer)
        if u.netloc == request.headers.get("host", "") and u.path.startswith("/") and not u.path.startswith("//"):
            destino = u.path + (f"?{u.query}" if u.query else "")
    if item_hash and _RE_HASH.fullmatch(item_hash):
        destino += f"#item-{item_hash}"
    return destino
