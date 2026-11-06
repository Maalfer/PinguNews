"""Interacción con noticias: me gusta, guardar para más tarde y "Mis guardados"."""
from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from pingunews.web import csrf
from pingunews.web.deps import get_ajustes, get_db, render, usuario_actual
from pingunews.web.noticias import destino_tras_accion, enriquecer_items, hash_valido

router = APIRouter()


def _alternar(request: Request, item_hash: str, csrf_token: str, accion: str):
    usuario = usuario_actual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    csrf.exigir_csrf(request, csrf_token)
    db = get_db(request)
    if not hash_valido(db, item_hash):
        return RedirectResponse("/", status_code=303)
    getattr(db, accion)(usuario["id"], item_hash)
    return RedirectResponse(destino_tras_accion(request, item_hash), status_code=303)


@router.post("/guardar/{item_hash}")
def alternar_guardado(request: Request, item_hash: str, csrf_token: str = Form(...)):
    return _alternar(request, item_hash, csrf_token, "alternar_guardado")


@router.post("/like/{item_hash}")
def alternar_like(request: Request, item_hash: str, csrf_token: str = Form(...)):
    return _alternar(request, item_hash, csrf_token, "alternar_like")


@router.get("/guardados", response_class=HTMLResponse)
def ver_guardados(request: Request):
    usuario = usuario_actual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)

    db = get_db(request)
    items = db.items_guardados(usuario["id"])
    enriquecer_items(db, items, usuario)

    return render(request, "guardados.html.j2", {
        "usuario": usuario,
        "items": items,
        "csrf_token": csrf.token_csrf(request),
        "twitter_activo": get_ajustes(request).twitter_activo,
    })
