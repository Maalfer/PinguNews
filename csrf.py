"""Protección CSRF basada en sesión (patrón "synchronizer token").

Cada sesión tiene un token aleatorio guardado en la cookie de sesión (firmada,
no accesible ni modificable por el navegador). Cada formulario que cambia
estado (login, registro, dar like, guardar, actualizar...) lo incluye como
campo oculto, y el servidor comprueba que coincide con el de la sesión antes
de aceptar la petición. Sin esto, cualquier página externa podría, por
ejemplo, incluir un <form> oculto que haga POST a /like/... o /actualizar
aprovechando que el navegador de la víctima ya tiene la cookie de sesión.
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException
from starlette.requests import Request


def token_csrf(request: Request) -> str:
    """Devuelve el token CSRF de la sesión actual, generándolo si no existe."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def exigir_csrf(request: Request, token_enviado: str) -> None:
    """Lanza 403 si el token enviado no coincide con el de la sesión."""
    token_sesion = request.session.get("csrf_token")
    valido = bool(token_sesion) and secrets.compare_digest(token_sesion, token_enviado or "")
    if not valido:
        raise HTTPException(status_code=403, detail="Token CSRF inválido o ausente.")
