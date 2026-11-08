"""Cuentas de usuario: registro (con verificación por email), inicio y cierre
de sesión, y recuperación de contraseña.

La cuenta en `usuarios` no se crea hasta que se confirma el correo (ver
`registros_pendientes` en storage/database.py): así nadie puede ocupar un
nombre de usuario con un correo ajeno que nunca llega a confirmar. Si el SMTP
no está configurado (ver web/mail.py), se cae al comportamiento anterior:
cuenta creada al momento, sin verificación.
"""
from __future__ import annotations

import logging
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from pingunews.web import csrf, mail, passwords
from pingunews.web.deps import get_db, iniciar_sesion, render, render_formulario, usuario_actual
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
EMAIL_MAX = 254
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")
NOMBRES_RESERVADOS = {"admin", "administrador", "root", "system", "soporte", "pingunews", "moderador", "api"}
TOKEN_EXPIRA_REGISTRO_HORAS = 24
TOKEN_EXPIRA_RESET_HORAS = 1
ERROR_DEMASIADOS_INTENTOS = "Demasiados intentos. Espera unos minutos y vuelve a probar."
ERROR_CREDENCIALES = "Usuario o contraseña incorrectos."
MENSAJE_RESET_GENERICO = "Si ese correo está registrado, te hemos enviado un enlace para restablecer la contraseña."

_HASH_FALSO = None  # se calcula en el primer login para igualar tiempos


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def enviar_token_reset(db, usuario: dict, base_url: str) -> None:
    """Genera y envía un enlace de recuperación de contraseña a `usuario`.
    Reutilizado tanto por /olvide-password como por el panel de admin
    (routes/admin.py) para forzar un reset desde ahí."""
    token = secrets.token_urlsafe(32)
    expira_en = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRA_RESET_HORAS)).isoformat()
    db.crear_token_reset(token, usuario["id"], expira_en)
    mail.enviar_reset_password(usuario["email"], usuario["nombre_usuario"], token, base_url)
    logger.info("Reset de contraseña solicitado: usuario_id=%s", usuario["id"])


def validar_email(email: str) -> str | None:
    """Reutilizado también en routes/perfil.py para validar el cambio de correo."""
    if not email or len(email) > EMAIL_MAX or not EMAIL_RE.fullmatch(email):
        return "Introduce un correo electrónico válido."
    return None


def _validar_registro(db, nombre_usuario: str, email: str, password: str, password2: str):
    if len(nombre_usuario) < NOMBRE_USUARIO_MIN:
        return f"El usuario debe tener al menos {NOMBRE_USUARIO_MIN} caracteres."
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", nombre_usuario):
        return "El usuario solo puede tener letras, números, punto, guion y guion bajo (máximo 32)."
    if nombre_usuario.lower() in NOMBRES_RESERVADOS:
        return "Ese nombre de usuario está reservado."
    error_email = validar_email(email)
    if error_email:
        return error_email
    if len(password) < PASSWORD_MIN:
        return f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    if len(password) > PASSWORD_MAX:
        return f"La contraseña no puede superar los {PASSWORD_MAX} caracteres."
    if password != password2:
        return "Las contraseñas no coinciden."
    if db.obtener_usuario_por_nombre(nombre_usuario):
        return "Ese nombre de usuario ya existe."
    if db.obtener_usuario_por_email(email):
        return "Ese correo ya está en uso por otra cuenta."
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
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    csrf.exigir_csrf(request, csrf_token)
    if limite_intentos_superado(f"registro:{ip_cliente(request)}"):
        return render_formulario(request, "registro.html.j2", ERROR_DEMASIADOS_INTENTOS, 429)

    db = get_db(request)
    nombre_usuario = nombre_usuario.strip()
    email = email.strip().lower()
    db.limpiar_registros_pendientes_expirados()

    error = _validar_registro(db, nombre_usuario, email, password, password2)
    if error:
        return render_formulario(request, "registro.html.j2", error, 400)

    salt = passwords.generar_salt()
    pwd_hash = passwords.hash_password(password, salt)

    if not mail.smtp_configurado():
        # Sin SMTP no hay forma de verificar: se crea la cuenta al momento,
        # igual que antes de tener verificación por email.
        usuario_id = db.crear_usuario(nombre_usuario, pwd_hash, salt, email)
        iniciar_sesion(request, db.obtener_usuario_por_id(usuario_id))
        logger.warning("SMTP no configurado — cuenta creada sin verificación: %s", nombre_usuario)
        return RedirectResponse("/", status_code=303)

    conflicto = db.registro_pendiente_en_conflicto(nombre_usuario, email)
    if conflicto and conflicto["nombre_usuario"] == nombre_usuario and conflicto["email"] == email:
        # Mismos datos que un registro ya pendiente: se trata como un
        # reenvío (con token nuevo) en vez de como un error.
        db.eliminar_registro_pendiente(conflicto["token"])
        conflicto = None
    if conflicto:
        return render_formulario(
            request, "registro.html.j2",
            "Ya hay un registro pendiente de verificación con ese usuario o correo. "
            "Revisa tu bandeja de entrada o espera 24h a que caduque.",
            400,
        )

    token = secrets.token_urlsafe(32)
    expira_en = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRA_REGISTRO_HORAS)).isoformat()
    db.crear_registro_pendiente(token, nombre_usuario, email, pwd_hash, salt, expira_en)
    mail.enviar_verificacion_registro(email, nombre_usuario, token, _base_url(request))
    logger.info("Registro pendiente de verificación: %s", nombre_usuario)
    return render(request, "verificar-pendiente.html.j2", {
        "usuario": None, "email": email, "token": token, "csrf_token": csrf.token_csrf(request),
    })


@router.get("/verificar-correo", response_class=HTMLResponse)
def verificar_correo(request: Request, token: str = Query(default="")):
    db = get_db(request)
    pendiente = db.obtener_registro_pendiente(token) if token else None
    if pendiente and pendiente["expira_en"] < datetime.now(timezone.utc).isoformat():
        db.eliminar_registro_pendiente(token)
        pendiente = None
    if not pendiente:
        return render_formulario(
            request, "registro.html.j2",
            "Ese enlace de verificación no es válido o ha caducado. Vuelve a registrarte para recibir uno nuevo.",
            400,
        )

    try:
        usuario_id = db.crear_usuario(
            pendiente["nombre_usuario"], pendiente["password_hash"], pendiente["salt"], pendiente["email"]
        )
    except sqlite3.IntegrityError:
        # Alguien se ha quedado ese usuario o correo mientras este registro
        # estaba pendiente (ventana rara, pero posible).
        db.eliminar_registro_pendiente(token)
        return render_formulario(
            request, "registro.html.j2", "Ese usuario o correo ya se ha registrado entre tanto. Elige otros datos.", 400
        )

    db.eliminar_registro_pendiente(token)
    usuario = db.obtener_usuario_por_id(usuario_id)
    iniciar_sesion(request, usuario)
    logger.info("Cuenta verificada y creada: %s", usuario["nombre_usuario"])
    return RedirectResponse("/", status_code=303)


@router.post("/reenviar-verificacion", response_class=HTMLResponse)
def reenviar_verificacion(request: Request, csrf_token: str = Form(...), token: str = Form(...)):
    csrf.exigir_csrf(request, csrf_token)
    db = get_db(request)
    if limite_intentos_superado(f"reenviar:{ip_cliente(request)}"):
        return render_formulario(request, "registro.html.j2", ERROR_DEMASIADOS_INTENTOS, 429)

    pendiente = db.obtener_registro_pendiente(token)
    if not pendiente:
        return render_formulario(
            request, "registro.html.j2",
            "Ese registro pendiente ya no existe (puede haber caducado). Vuelve a registrarte.",
            400,
        )

    db.eliminar_registro_pendiente(token)
    token_nuevo = secrets.token_urlsafe(32)
    expira_en = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRA_REGISTRO_HORAS)).isoformat()
    db.crear_registro_pendiente(
        token_nuevo, pendiente["nombre_usuario"], pendiente["email"],
        pendiente["password_hash"], pendiente["salt"], expira_en,
    )
    mail.enviar_verificacion_registro(pendiente["email"], pendiente["nombre_usuario"], token_nuevo, _base_url(request))
    return render(request, "verificar-pendiente.html.j2", {
        "usuario": None, "email": pendiente["email"], "token": token_nuevo,
        "csrf_token": csrf.token_csrf(request), "reenviado": True,
    })


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, reset: str = Query(default=""), correo: str = Query(default="")):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    mensaje = None
    if reset == "ok":
        mensaje = "Contraseña actualizada. Ya puedes iniciar sesión con tu nueva contraseña."
    elif correo == "ok":
        mensaje = "Correo actualizado correctamente."
    return render(request, "login.html.j2", {
        "usuario": None, "error": None, "mensaje": mensaje, "csrf_token": csrf.token_csrf(request),
    })


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

    db = get_db(request)
    usuario = _verificar_credenciales(db, nombre_usuario, password)
    if not usuario:
        registrar_fallo_usuario(nombre_usuario)
        if db.obtener_registro_pendiente_por_nombre(nombre_usuario):
            return render_formulario(
                request, "login.html.j2",
                "Esa cuenta todavía no está verificada. Revisa el correo que te enviamos al registrarte, "
                "o vuelve a registrarte con los mismos datos para recibir un enlace nuevo.",
                400,
            )
        return render_formulario(request, "login.html.j2", ERROR_CREDENCIALES, 400)

    iniciar_sesion(request, usuario)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    csrf.exigir_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/olvide-password", response_class=HTMLResponse)
def olvide_password_form(request: Request):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    return render_formulario(request, "olvide-password.html.j2")


@router.post("/olvide-password", response_class=HTMLResponse)
def olvide_password_submit(request: Request, csrf_token: str = Form(...), email: str = Form(...)):
    csrf.exigir_csrf(request, csrf_token)
    if limite_intentos_superado(f"olvide:{ip_cliente(request)}"):
        return render_formulario(request, "olvide-password.html.j2", ERROR_DEMASIADOS_INTENTOS, 429)
    if not mail.smtp_configurado():
        return render_formulario(
            request, "olvide-password.html.j2", "El envío de correo no está disponible ahora mismo.", 503
        )

    db = get_db(request)
    email = email.strip().lower()
    usuario = db.obtener_usuario_por_email(email) if EMAIL_RE.fullmatch(email or "") else None
    if usuario:
        enviar_token_reset(db, usuario, _base_url(request))
    # Mismo mensaje exista o no la cuenta: evita que este formulario se use
    # para averiguar qué correos están registrados.
    return render(request, "olvide-password.html.j2", {
        "usuario": None, "csrf_token": csrf.token_csrf(request), "mensaje": MENSAJE_RESET_GENERICO,
    })


def _token_reset_valido(db, token: str):
    t = db.obtener_token_reset(token) if token else None
    if t and t["expira_en"] < datetime.now(timezone.utc).isoformat():
        db.eliminar_token_reset(token)
        t = None
    return t


@router.get("/restablecer-password", response_class=HTMLResponse)
def restablecer_password_form(request: Request, token: str = Query(default="")):
    db = get_db(request)
    if not _token_reset_valido(db, token):
        return render_formulario(
            request, "olvide-password.html.j2",
            "Ese enlace para restablecer la contraseña no es válido o ha caducado. Pide uno nuevo.",
            400,
        )
    return render(request, "restablecer-password.html.j2", {
        "usuario": None, "error": None, "token": token, "csrf_token": csrf.token_csrf(request),
    })


@router.post("/restablecer-password", response_class=HTMLResponse)
def restablecer_password_submit(
    request: Request, csrf_token: str = Form(...), token: str = Form(...),
    password: str = Form(...), password2: str = Form(...),
):
    csrf.exigir_csrf(request, csrf_token)
    db = get_db(request)
    t = _token_reset_valido(db, token)
    if not t:
        return render_formulario(
            request, "olvide-password.html.j2",
            "Ese enlace para restablecer la contraseña no es válido o ha caducado. Pide uno nuevo.",
            400,
        )

    error = None
    if len(password) < PASSWORD_MIN:
        error = f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    elif len(password) > PASSWORD_MAX:
        error = f"La contraseña no puede superar los {PASSWORD_MAX} caracteres."
    elif password != password2:
        error = "Las contraseñas no coinciden."
    if error:
        return render(request, "restablecer-password.html.j2", {
            "usuario": None, "error": error, "token": token, "csrf_token": csrf.token_csrf(request),
        }, status_code=400)

    salt = passwords.generar_salt()
    db.actualizar_password(t["usuario_id"], passwords.hash_password(password, salt), salt)
    db.eliminar_token_reset(token)
    request.session.clear()
    logger.info("Contraseña restablecida: usuario_id=%s", t["usuario_id"])
    return RedirectResponse("/login?reset=ok", status_code=303)
