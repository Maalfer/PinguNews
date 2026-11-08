"""Fábrica de la aplicación web (FastAPI).

Ejecutar en desarrollo:
    uvicorn pingunews.web.app:app --reload --port 8000

y abrir http://127.0.0.1:8000
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from pingunews.config import PRODUCCION, cargar_config, ruta_db, ruta_log
from pingunews.logging_setup import setup_logging
from pingunews.storage import Database
from pingunews.web.ajustes import AjustesPanel
from pingunews.web.estaticos import DIR_ESTATICOS, EstaticosConCache
from pingunews.web.plantillas import crear_plantillas
from pingunews.web.routes import cuentas, feed, guardados, paginas, panel
from pingunews.web.seguridad import cabeceras_seguridad, obtener_secret_key

SESION_MAX_AGE = 14 * 24 * 3600  # 14 días


async def error_http(request: Request, exc: StarletteHTTPException):
    """404 amigable en HTML; el resto de errores siguen devolviendo JSON."""
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return request.app.state.templates.TemplateResponse(
            request, "error.html.j2", {"titulo": "Página no encontrada"}, status_code=404
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


def create_app(config: Optional[dict] = None) -> FastAPI:
    config = config if config is not None else cargar_config()
    general = config.get("general", {})
    setup_logging(ruta_log(config), general.get("log_level", "INFO"))

    app = FastAPI(title="Panel de ciberseguridad e IT", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.ajustes = AjustesPanel.desde_config(config)
    app.state.db = Database(ruta_db(config))
    app.state.templates = crear_plantillas()

    app.mount("/static", EstaticosConCache(directory=str(DIR_ESTATICOS)), name="static")
    app.add_middleware(
        SessionMiddleware,
        secret_key=obtener_secret_key(),
        same_site="lax",
        https_only=PRODUCCION,
        max_age=SESION_MAX_AGE,
    )
    app.add_middleware(BaseHTTPMiddleware, dispatch=cabeceras_seguridad)
    app.add_exception_handler(StarletteHTTPException, error_http)

    for modulo in (panel, cuentas, guardados, paginas, feed):
        app.include_router(modulo.router)
    return app


app = create_app()
