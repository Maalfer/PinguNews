"""Panel de administración: listado de usuarios y acciones sobre sus cuentas
(/usuarios-registrados). Solo accesible con rol 'admin' (ver deps.es_admin).

Toda acción exige confirmar la contraseña del propio admin, igual que los
cambios sensibles en el perfil (ver routes/perfil.py): una sesión de admin
robada no basta por sí sola para tocar otras cuentas.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from pingunews.web import csrf, mail, passwords
from pingunews.web.deps import ROL_ADMIN, es_admin, get_db, render, usuario_actual
from pingunews.web.ratelimit import limite_intentos_superado
from pingunews.web.routes.cuentas import PASSWORD_MAX, PASSWORD_MIN, enviar_token_reset

router = APIRouter()
logger = logging.getLogger("herramienta.web.admin")

ERROR_DEMASIADOS_INTENTOS = "Demasiados intentos. Espera unos minutos y vuelve a probar."
ERROR_PASSWORD_ADMIN = "Tu contraseña de administrador no es correcta."


def _admin_actual(request: Request):
    """Devuelve el admin con sesión iniciada, o None si no hay sesión (el
    caller debe redirigir a /login). Si hay sesión pero sin rol admin, 403."""
    usuario = usuario_actual(request)
    if usuario and not es_admin(usuario):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a esta página.")
    return usuario


def _render_usuarios(request: Request, admin: dict, error=None, mensaje=None, status_code: int = 200):
    return render(request, "usuarios-registrados.html.j2", {
        "usuario": admin, "csrf_token": csrf.token_csrf(request),
        "usuarios": get_db(request).listar_usuarios(),
        "error": error, "mensaje": mensaje,
    }, status_code=status_code)


@router.get("/usuarios-registrados", response_class=HTMLResponse)
def usuarios_registrados(request: Request):
    admin = _admin_actual(request)
    if not admin:
        return RedirectResponse("/login", status_code=303)
    return _render_usuarios(request, admin)


@router.post("/usuarios-registrados/{usuario_id}/password", response_class=HTMLResponse)
def admin_cambiar_password(
    request: Request, usuario_id: int, csrf_token: str = Form(...),
    password_nueva: str = Form(...), password_nueva2: str = Form(...), password_admin: str = Form(...),
):
    admin = _admin_actual(request)
    if not admin:
        return RedirectResponse("/login", status_code=303)
    csrf.exigir_csrf(request, csrf_token)
    db = get_db(request)

    if limite_intentos_superado(f"admin:{admin['id']}"):
        return _render_usuarios(request, admin, error=ERROR_DEMASIADOS_INTENTOS, status_code=429)
    if not passwords.verificar_password(password_admin, admin["password_hash"], admin["salt"]):
        return _render_usuarios(request, admin, error=ERROR_PASSWORD_ADMIN, status_code=400)

    objetivo = db.obtener_usuario_por_id(usuario_id)
    if not objetivo:
        return _render_usuarios(request, admin, error="Esa cuenta ya no existe.", status_code=404)

    error = None
    if len(password_nueva) < PASSWORD_MIN:
        error = f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    elif len(password_nueva) > PASSWORD_MAX:
        error = f"La contraseña no puede superar los {PASSWORD_MAX} caracteres."
    elif password_nueva != password_nueva2:
        error = "Las contraseñas no coinciden."
    if error:
        return _render_usuarios(request, admin, error=error, status_code=400)

    salt = passwords.generar_salt()
    db.actualizar_password(objetivo["id"], passwords.hash_password(password_nueva, salt), salt)
    logger.warning("Admin %s cambió la contraseña de %s", admin["nombre_usuario"], objetivo["nombre_usuario"])
    return _render_usuarios(request, admin, mensaje=f"Contraseña de {objetivo['nombre_usuario']} actualizada.")


@router.post("/usuarios-registrados/{usuario_id}/enviar-reset", response_class=HTMLResponse)
def admin_enviar_reset(
    request: Request, usuario_id: int, csrf_token: str = Form(...), password_admin: str = Form(...)
):
    admin = _admin_actual(request)
    if not admin:
        return RedirectResponse("/login", status_code=303)
    csrf.exigir_csrf(request, csrf_token)
    db = get_db(request)

    if limite_intentos_superado(f"admin:{admin['id']}"):
        return _render_usuarios(request, admin, error=ERROR_DEMASIADOS_INTENTOS, status_code=429)
    if not passwords.verificar_password(password_admin, admin["password_hash"], admin["salt"]):
        return _render_usuarios(request, admin, error=ERROR_PASSWORD_ADMIN, status_code=400)

    objetivo = db.obtener_usuario_por_id(usuario_id)
    if not objetivo:
        return _render_usuarios(request, admin, error="Esa cuenta ya no existe.", status_code=404)
    if not objetivo.get("email"):
        return _render_usuarios(
            request, admin, error=f"{objetivo['nombre_usuario']} no tiene correo configurado.", status_code=400
        )
    if not mail.smtp_configurado():
        return _render_usuarios(request, admin, error="El envío de correo no está disponible ahora mismo.", status_code=503)

    enviar_token_reset(db, objetivo, str(request.base_url).rstrip("/"))
    logger.info("Admin %s solicitó reset de contraseña para %s", admin["nombre_usuario"], objetivo["nombre_usuario"])
    return _render_usuarios(request, admin, mensaje=f"Correo de restablecimiento enviado a {objetivo['email']}.")


@router.post("/usuarios-registrados/{usuario_id}/rol", response_class=HTMLResponse)
def admin_cambiar_rol(
    request: Request, usuario_id: int, csrf_token: str = Form(...),
    rol_nuevo: str = Form(...), password_admin: str = Form(...),
):
    admin = _admin_actual(request)
    if not admin:
        return RedirectResponse("/login", status_code=303)
    csrf.exigir_csrf(request, csrf_token)
    db = get_db(request)

    if limite_intentos_superado(f"admin:{admin['id']}"):
        return _render_usuarios(request, admin, error=ERROR_DEMASIADOS_INTENTOS, status_code=429)
    if not passwords.verificar_password(password_admin, admin["password_hash"], admin["salt"]):
        return _render_usuarios(request, admin, error=ERROR_PASSWORD_ADMIN, status_code=400)
    if rol_nuevo not in (ROL_ADMIN, "usuario"):
        return _render_usuarios(request, admin, error="Rol no válido.", status_code=400)

    objetivo = db.obtener_usuario_por_id(usuario_id)
    if not objetivo:
        return _render_usuarios(request, admin, error="Esa cuenta ya no existe.", status_code=404)
    if objetivo["id"] == admin["id"]:
        # Si pudieras cambiarte el rol a ti mismo, el último admin podría
        # quitarse el acceso sin querer y dejar la app sin ningún admin.
        return _render_usuarios(request, admin, error="No puedes cambiar tu propio rol desde aquí.", status_code=400)

    db.actualizar_rol(objetivo["id"], rol_nuevo)
    logger.warning("Admin %s cambió el rol de %s a %s", admin["nombre_usuario"], objetivo["nombre_usuario"], rol_nuevo)
    return _render_usuarios(request, admin, mensaje=f"Rol de {objetivo['nombre_usuario']} actualizado a {rol_nuevo}.")
