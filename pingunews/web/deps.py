"""Dependencias compartidas por las rutas (acceso al estado de la app)."""
from __future__ import annotations

from typing import Optional

from fastapi.responses import HTMLResponse
from starlette.requests import Request

from pingunews.storage import Database
from pingunews.web import csrf
from pingunews.web.ajustes import AjustesPanel


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_ajustes(request: Request) -> AjustesPanel:
    return request.app.state.ajustes


def usuario_actual(request: Request) -> Optional[dict]:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    usuario = get_db(request).obtener_usuario_por_id(usuario_id)
    if not usuario:
        return None
    version_sesion = request.session.get("version_sesion")
    # Si la sesión no lleva version_sesion es que se abrió antes de que este
    # campo existiera: se acepta tal cual para no cerrar de golpe sesiones ya
    # abiertas al desplegar esto. Solo se exige que coincida cuando la sesión
    # SÍ la lleva y no coincide con la actual (se cambió la contraseña en
    # otro sitio, ver Database.actualizar_password).
    if version_sesion is not None and version_sesion != usuario["version_sesion"]:
        request.session.clear()
        return None
    return usuario


def iniciar_sesion(request: Request, usuario: dict) -> None:
    """Crea la sesión de este usuario (login o verificación de registro).
    session.clear() evita session fixation: cualquier dato de la sesión
    anónima anterior (csrf_token incluido) se descarta y se genera de cero."""
    request.session.clear()
    request.session["usuario_id"] = usuario["id"]
    request.session["version_sesion"] = usuario["version_sesion"]


def render(request: Request, plantilla: str, contexto: dict, status_code: int = 200) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, plantilla, contexto, status_code=status_code)


def render_formulario(request: Request, plantilla: str, error: Optional[str] = None, status_code: int = 200):
    """Render de login/registro: siempre sin usuario y con token CSRF."""
    return render(
        request, plantilla,
        {"error": error, "usuario": None, "csrf_token": csrf.token_csrf(request)},
        status_code=status_code,
    )
