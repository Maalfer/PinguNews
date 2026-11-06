"""Páginas legales y la frase motivadora de la portada."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.requests import Request

from pingunews.content.frases import frase_aleatoria
from pingunews.web.deps import render

router = APIRouter()

_PAGINAS_LEGALES = {
    "aviso-legal": "Aviso legal",
    "privacidad": "Política de privacidad",
    "cookies": "Política de cookies",
}


def _pagina_legal(request: Request, clave: str):
    return render(request, "legal.html.j2", {"titulo": _PAGINAS_LEGALES[clave], "pagina": clave})


@router.get("/aviso-legal", response_class=HTMLResponse)
def aviso_legal(request: Request):
    return _pagina_legal(request, "aviso-legal")


@router.get("/privacidad", response_class=HTMLResponse)
def privacidad(request: Request):
    return _pagina_legal(request, "privacidad")


@router.get("/cookies", response_class=HTMLResponse)
def cookies(request: Request):
    return _pagina_legal(request, "cookies")


@router.get("/frase")
def otra_frase(actual: str = Query("", max_length=400)):
    """Devuelve una frase distinta de la que el usuario ya está viendo.
    Solo lee de la reserva en memoria / lista local: no hace llamadas externas."""
    f = frase_aleatoria()
    for _ in range(8):
        if f["texto"] != actual:
            break
        f = frase_aleatoria()
    return JSONResponse({"texto": f["texto"], "autor": f.get("autor", "")}, headers={"Cache-Control": "no-store"})
