"""Perfil del usuario: cambiar nombre de usuario, correo o contraseña.

Las tres acciones exigen confirmar la contraseña actual (igual que cambiar el
correo en muchos servicios): una sesión robada por sí sola no basta para
tomar la cuenta. El cambio de correo, además, no se aplica hasta que se
confirma desde la dirección nueva (ver cambios_email_pendientes en
storage/database.py), igual que en el registro.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from pingunews.web import csrf, mail, passwords
from pingunews.web.deps import get_db, render, usuario_actual
from pingunews.web.ratelimit import limite_intentos_superado
from pingunews.web.routes.cuentas import (
    NOMBRE_USUARIO_MIN,
    NOMBRES_RESERVADOS,
    PASSWORD_MAX,
    PASSWORD_MIN,
    validar_email,
)

router = APIRouter()
logger = logging.getLogger("herramienta.web.perfil")

TOKEN_EXPIRA_CAMBIO_EMAIL_HORAS = 1
ERROR_DEMASIADOS_INTENTOS = "Demasiados intentos. Espera unos minutos y vuelve a probar."
ERROR_PASSWORD_ACTUAL = "La contraseña actual no es correcta."


def _exigir_login(request: Request):
    usuario = usuario_actual(request)
    if not usuario:
        return None
    return usuario


def _render_perfil(request: Request, usuario: dict, error=None, mensaje=None, seccion=None, status_code=200):
    return render(request, "perfil.html.j2", {
        "usuario": usuario, "csrf_token": csrf.token_csrf(request),
        "error": error, "mensaje": mensaje, "seccion": seccion,
    }, status_code=status_code)


@router.get("/perfil", response_class=HTMLResponse)
def perfil_form(request: Request):
    usuario = _exigir_login(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    return _render_perfil(request, usuario)


@router.post("/perfil/usuario", response_class=HTMLResponse)
def cambiar_usuario(
    request: Request, csrf_token: str = Form(...), nombre_usuario_nuevo: str = Form(...), password_actual: str = Form(...)
):
    csrf.exigir_csrf(request, csrf_token)
    usuario = _exigir_login(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)

    db = get_db(request)
    if limite_intentos_superado(f"perfil:{usuario['id']}"):
        return _render_perfil(request, usuario, error=ERROR_DEMASIADOS_INTENTOS, seccion="usuario", status_code=429)
    if not passwords.verificar_password(password_actual, usuario["password_hash"], usuario["salt"]):
        return _render_perfil(request, usuario, error=ERROR_PASSWORD_ACTUAL, seccion="usuario", status_code=400)

    nombre_nuevo = nombre_usuario_nuevo.strip()
    error = None
    if len(nombre_nuevo) < NOMBRE_USUARIO_MIN or not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", nombre_nuevo):
        error = "El usuario solo puede tener letras, números, punto, guion y guion bajo (3-32 caracteres)."
    elif nombre_nuevo.lower() in NOMBRES_RESERVADOS:
        error = "Ese nombre de usuario está reservado."
    elif nombre_nuevo != usuario["nombre_usuario"] and db.obtener_usuario_por_nombre(nombre_nuevo):
        error = "Ese nombre de usuario ya existe."
    if error:
        return _render_perfil(request, usuario, error=error, seccion="usuario", status_code=400)

    if nombre_nuevo != usuario["nombre_usuario"]:
        db.actualizar_nombre_usuario(usuario["id"], nombre_nuevo)
        logger.info("Usuario %s renombrado a %s", usuario["id"], nombre_nuevo)
    usuario = db.obtener_usuario_por_id(usuario["id"])
    return _render_perfil(request, usuario, mensaje="Nombre de usuario actualizado.", seccion="usuario")


@router.post("/perfil/email", response_class=HTMLResponse)
def cambiar_email(
    request: Request, csrf_token: str = Form(...), email_nuevo: str = Form(...), password_actual: str = Form(...)
):
    csrf.exigir_csrf(request, csrf_token)
    usuario = _exigir_login(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)

    db = get_db(request)
    if limite_intentos_superado(f"perfil:{usuario['id']}"):
        return _render_perfil(request, usuario, error=ERROR_DEMASIADOS_INTENTOS, seccion="email", status_code=429)
    if not mail.smtp_configurado():
        return _render_perfil(
            request, usuario, error="El envío de correo no está disponible ahora mismo.", seccion="email", status_code=503
        )
    if not passwords.verificar_password(password_actual, usuario["password_hash"], usuario["salt"]):
        return _render_perfil(request, usuario, error=ERROR_PASSWORD_ACTUAL, seccion="email", status_code=400)

    email_nuevo = email_nuevo.strip().lower()
    error = validar_email(email_nuevo)
    if not error and usuario.get("email") == email_nuevo:
        error = "Ese ya es tu correo actual."
    elif not error and db.obtener_usuario_por_email(email_nuevo):
        error = "Ese correo ya está en uso por otra cuenta."
    if error:
        return _render_perfil(request, usuario, error=error, seccion="email", status_code=400)

    token = secrets.token_urlsafe(32)
    expira_en = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRA_CAMBIO_EMAIL_HORAS)).isoformat()
    db.crear_cambio_email(token, usuario["id"], email_nuevo, expira_en)
    base_url = str(request.base_url).rstrip("/")
    mail.enviar_confirmacion_cambio_email(email_nuevo, usuario["nombre_usuario"], token, base_url)
    if usuario.get("email"):
        mail.enviar_aviso_cambio_email(usuario["email"], usuario["nombre_usuario"], email_nuevo)
    logger.info("Cambio de correo solicitado: usuario_id=%s", usuario["id"])
    return _render_perfil(
        request, usuario, mensaje=f"Te hemos enviado un enlace de confirmación a {email_nuevo}.", seccion="email"
    )


@router.get("/confirmar-cambio-correo", response_class=HTMLResponse)
def confirmar_cambio_correo(request: Request, token: str = Query(default="")):
    db = get_db(request)
    cambio = db.obtener_cambio_email(token) if token else None
    if cambio and cambio["expira_en"] < datetime.now(timezone.utc).isoformat():
        db.eliminar_cambio_email(token)
        cambio = None
    if not cambio:
        usuario = usuario_actual(request)
        if usuario:
            return _render_perfil(
                request, usuario, error="Ese enlace de confirmación no es válido o ha caducado.", seccion="email", status_code=400
            )
        return RedirectResponse("/login", status_code=303)

    if db.obtener_usuario_por_email(cambio["email_nuevo"]):
        db.eliminar_cambio_email(token)
        usuario = usuario_actual(request)
        if usuario:
            return _render_perfil(
                request, usuario, error="Ese correo se ha quedado en uso por otra cuenta mientras tanto.",
                seccion="email", status_code=400,
            )
        return RedirectResponse("/login", status_code=303)

    db.actualizar_email(cambio["usuario_id"], cambio["email_nuevo"])
    db.eliminar_cambio_email(token)
    logger.info("Correo confirmado y actualizado: usuario_id=%s", cambio["usuario_id"])

    usuario = usuario_actual(request)
    if usuario and usuario["id"] == cambio["usuario_id"]:
        return _render_perfil(request, usuario, mensaje="Correo actualizado correctamente.", seccion="email")
    return RedirectResponse("/login?correo=ok", status_code=303)


@router.post("/perfil/password", response_class=HTMLResponse)
def cambiar_password(
    request: Request, csrf_token: str = Form(...), password_actual: str = Form(...),
    password_nueva: str = Form(...), password_nueva2: str = Form(...),
):
    csrf.exigir_csrf(request, csrf_token)
    usuario = _exigir_login(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)

    db = get_db(request)
    if limite_intentos_superado(f"perfil:{usuario['id']}"):
        return _render_perfil(request, usuario, error=ERROR_DEMASIADOS_INTENTOS, seccion="password", status_code=429)
    if not passwords.verificar_password(password_actual, usuario["password_hash"], usuario["salt"]):
        return _render_perfil(request, usuario, error=ERROR_PASSWORD_ACTUAL, seccion="password", status_code=400)

    error = None
    if len(password_nueva) < PASSWORD_MIN:
        error = f"La contraseña nueva debe tener al menos {PASSWORD_MIN} caracteres."
    elif len(password_nueva) > PASSWORD_MAX:
        error = f"La contraseña nueva no puede superar los {PASSWORD_MAX} caracteres."
    elif password_nueva != password_nueva2:
        error = "Las contraseñas nuevas no coinciden."
    if error:
        return _render_perfil(request, usuario, error=error, seccion="password", status_code=400)

    salt = passwords.generar_salt()
    version_nueva = db.actualizar_password(usuario["id"], passwords.hash_password(password_nueva, salt), salt)
    # Se actualiza la sesión actual con la version_sesion nueva para no
    # cerrarla a ella misma (ver deps.usuario_actual): solo se invalidan las
    # DEMÁS sesiones que hubiera abiertas con la contraseña anterior.
    request.session["version_sesion"] = version_nueva
    logger.info("Contraseña cambiada desde el perfil: usuario_id=%s", usuario["id"])
    usuario = db.obtener_usuario_por_id(usuario["id"])
    return _render_perfil(request, usuario, mensaje="Contraseña actualizada correctamente.", seccion="password")
