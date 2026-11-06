"""Cuentas de usuario: registro, inicio y cierre de sesión."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from pingunews.web import csrf, passwords
from pingunews.web.deps import get_db, render_formulario, usuario_actual
from pingunews.web.ratelimit import (
    fallos_usuario_excedidos,
    ip_cliente,
    limite_intentos_superado,
    registrar_fallo_usuario,
)

router = APIRouter()
logger = logging.getLogger("herramienta.web.cuentas")

NOMBRE_USUARIO_MIN = 3
PASSWORD_MIN = 8
PASSWORD_MAX = 128
ERROR_DEMASIADOS_INTENTOS = "Demasiados intentos. Espera unos minutos y vuelve a probar."
ERROR_CREDENCIALES = "Usuario o contraseña incorrectos."

_HASH_FALSO = None  # se calcula en el primer login para igualar tiempos


def _validar_registro(db, nombre_usuario: str, password: str, password2: str):
    if len(nombre_usuario) < NOMBRE_USUARIO_MIN:
        return f"El usuario debe tener al menos {NOMBRE_USUARIO_MIN} caracteres."
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", nombre_usuario):
        return "El usuario solo puede tener letras, números, punto, guion y guion bajo (máximo 32)."
    if len(password) < PASSWORD_MIN:
        return f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    if len(password) > PASSWORD_MAX:
        return f"La contraseña no puede superar los {PASSWORD_MAX} caracteres."
    if password != password2:
        return "Las contraseñas no coinciden."
    if db.obtener_usuario_por_nombre(nombre_usuario):
        return "Ese nombre de usuario ya existe."
    return None


@router.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    return render_formulario(request, "registro.html.j2")


@router.post("/registro", response_class=HTMLResponse)
def registro_submit(
    request: Request,
    csrf_token: str = Form(...),
    nombre_usuario: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    csrf.exigir_csrf(request, csrf_token)
    if limite_intentos_superado(f"registro:{ip_cliente(request)}"):
        return render_formulario(request, "registro.html.j2", ERROR_DEMASIADOS_INTENTOS, 429)

    db = get_db(request)
    nombre_usuario = nombre_usuario.strip()
    error = _validar_registro(db, nombre_usuario, password, password2)
    if error:
        return render_formulario(request, "registro.html.j2", error, 400)

    salt = passwords.generar_salt()
    usuario_id = db.crear_usuario(nombre_usuario, passwords.hash_password(password, salt), salt)
    request.session.clear()
    request.session["usuario_id"] = usuario_id
    logger.info("Nuevo usuario registrado: %s", nombre_usuario)
    return RedirectResponse("/", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    return render_formulario(request, "login.html.j2")


def _verificar_credenciales(db, nombre_usuario: str, password: str):
    """Devuelve el usuario si las credenciales son válidas, o None. Con usuario
    inexistente se hace igualmente un hash del mismo coste, para que no se pueda
    deducir si existe midiendo el tiempo de respuesta."""
    global _HASH_FALSO
    usuario = db.obtener_usuario_por_nombre(nombre_usuario)
    if usuario:
        valido = passwords.verificar_password(password, usuario["password_hash"], usuario["salt"])
        return usuario if valido else None
    if _HASH_FALSO is None:
        sal = passwords.generar_salt()
        _HASH_FALSO = (passwords.hash_password("x" * 12, sal), sal)
    passwords.verificar_password(password, _HASH_FALSO[0], _HASH_FALSO[1])
    return None


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request, csrf_token: str = Form(...), nombre_usuario: str = Form(...), password: str = Form(...)
):
    csrf.exigir_csrf(request, csrf_token)
    if limite_intentos_superado(f"login:{ip_cliente(request)}"):
        return render_formulario(request, "login.html.j2", ERROR_DEMASIADOS_INTENTOS, 429)

    nombre_usuario = nombre_usuario.strip()
    longitud_valida = len(nombre_usuario) <= 64 and len(password) <= PASSWORD_MAX
    if not longitud_valida:
        return render_formulario(request, "login.html.j2", ERROR_CREDENCIALES, 400)
    if fallos_usuario_excedidos(nombre_usuario):
        return render_formulario(request, "login.html.j2", ERROR_DEMASIADOS_INTENTOS, 429)

    usuario = _verificar_credenciales(get_db(request), nombre_usuario, password)
    if not usuario:
        registrar_fallo_usuario(nombre_usuario)
        return render_formulario(request, "login.html.j2", ERROR_CREDENCIALES, 400)

    request.session.clear()
    request.session["usuario_id"] = usuario["id"]
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    csrf.exigir_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/", status_code=303)
