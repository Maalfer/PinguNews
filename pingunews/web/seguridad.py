"""Seguridad HTTP: clave de sesión y cabeceras (CSP con nonce, etc.)."""
from __future__ import annotations

import os
import secrets

from starlette.requests import Request

from pingunews.config import BASE_DIR, PRODUCCION


def obtener_secret_key() -> str:
    """Clave para firmar la cookie de sesión.

    En producción debe venir de la variable de entorno SESSION_SECRET_KEY (ver
    `.env` en el servidor) para que no cambie entre despliegues (lo que
    invalidaría todas las sesiones). En local, si no se define, se genera una
    vez y se guarda en data/.session_secret (excluido de git).
    """
    clave = os.environ.get("SESSION_SECRET_KEY")
    if clave:
        return clave
    if PRODUCCION:
        raise RuntimeError(
            "Falta la variable de entorno SESSION_SECRET_KEY en producción "
            "(ENTORNO=produccion). No se genera una automáticamente para no "
            "invalidar las sesiones de todo el mundo en cada despliegue."
        )
    ruta = BASE_DIR / "data" / ".session_secret"
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(secrets.token_hex(32), encoding="utf-8")
    return ruta.read_text(encoding="utf-8").strip()


async def cabeceras_seguridad(request: Request, call_next):
    """Cabeceras de seguridad (CSP con nonce por petición, etc.). HSTS lo añade
    nginx. Las páginas dinámicas no se guardan en cachés compartidas."""
    request.state.csp_nonce = secrets.token_urlsafe(16)
    respuesta = await call_next(request)
    h = respuesta.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    h["Cross-Origin-Resource-Policy"] = "same-origin"
    if not request.url.path.startswith("/static/"):
        h["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'nonce-%s'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'" % request.state.csp_nonce
        )
        if "cache-control" not in h:
            h["Cache-Control"] = "private, no-cache"
    return respuesta
