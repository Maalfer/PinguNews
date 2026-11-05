#!/usr/bin/env python3
"""Panel web (FastAPI) que muestra el contenido recolectado, leyendo de SQLite.

Ejecutar con:
    ./venv/bin/uvicorn app:app --reload --port 8000

Luego abrir http://127.0.0.1:8000 en el navegador.
"""
from __future__ import annotations

import math
import os
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode, urlparse

import yaml
from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from markupsafe import Markup, escape
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

import auth
from frases import frase_aleatoria
from legal import LEGAL
import csrf
from classifier import CATEGORIA_LABELS, CATEGORIA_ORDEN
from collector import ejecutar_recoleccion
from db import Database
from utils import SEPARADOR_FUENTES, setup_logging

# "produccion" activa cookies de sesión solo-HTTPS y cabecera HSTS. En local
# se deja desactivado para poder probar por http://127.0.0.1 sin HTTPS.
PRODUCCION = os.environ.get("ENTORNO", "local").strip().lower() == "produccion"

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

GENERAL = CONFIG.get("general", {})
DASHBOARD_CFG = CONFIG.get("dashboard", {})

logger = setup_logging(
    str(BASE_DIR / GENERAL.get("log_path", "logs/app.log")),
    GENERAL.get("log_level", "INFO"),
)

DB_PATH = str(BASE_DIR / GENERAL.get("db_path", "data/herramienta.db"))
db = Database(DB_PATH)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
# IMPORTANTE: Jinja2Templates decide si autoescapar HTML mirando la extensión
# del archivo (select_autoescape), y nuestras plantillas se llaman
# "*.html.j2" (no "*.html"), así que NO coincide con su lista y el autoescape
# queda desactivado por defecto. Como los títulos/resúmenes vienen de fuentes
# RSS externas (no confiables) y el nombre de usuario lo elige el propio
# usuario, sin esto cualquier feed o usuario podría inyectar HTML/JS
# (XSS) en cada página del panel. Se fuerza explícitamente a True.
templates.env.autoescape = True
templates.env.globals["frase_aleatoria"] = frase_aleatoria
templates.env.globals["legal"] = LEGAL
templates.env.globals["anio_actual"] = lambda: datetime.now().year

# Los emojis de las etiquetas son decorativos: se ocultan a los lectores de pantalla.
_RE_EMOJI_INICIAL = re.compile(r"^([^\w¿¡(\"“«]+)\s*", re.UNICODE)


def emoji_decorativo(texto):
    t = str(texto)
    m = _RE_EMOJI_INICIAL.match(t)
    if m and m.group(1).strip():
        return Markup('<span aria-hidden="true">%s</span> %s') % (m.group(1).strip(), t[m.end():])
    return escape(t)


# Fuentes cuyo contenido está en inglés (para marcarlo con lang="en").
_FUENTES_EN = ("jobicy", "remoteok", "we work remotely")


def idioma_item(item) -> str:
    fuente = str((item.get("fuente") if hasattr(item, "get") else item["fuente"]) or "").lower()
    return "en" if any(fuente.startswith(f) for f in _FUENTES_EN) else ""


templates.env.filters["emoji_decorativo"] = emoji_decorativo
templates.env.globals["idioma_item"] = idioma_item

app = FastAPI(title="Panel de ciberseguridad e IT")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Clave para firmar la cookie de sesión. En producción debe venir de la
# variable de entorno SESSION_SECRET_KEY (ver .env en el servidor) para que
# no cambie entre despliegues (lo que invalidaría todas las sesiones) y para
# no depender de un fichero en disco. En local, si no se define, se genera
# una vez y se guarda en data/.session_secret (excluido de git).
SECRET_KEY = os.environ.get("SESSION_SECRET_KEY")
if not SECRET_KEY:
    if PRODUCCION:
        raise RuntimeError(
            "Falta la variable de entorno SESSION_SECRET_KEY en producción "
            "(ENTORNO=produccion). No se genera una automáticamente para no "
            "invalidar las sesiones de todo el mundo en cada despliegue."
        )
    secret_key_path = BASE_DIR / "data" / ".session_secret"
    if not secret_key_path.exists():
        secret_key_path.parent.mkdir(parents=True, exist_ok=True)
        secret_key_path.write_text(secrets.token_hex(32), encoding="utf-8")
    SECRET_KEY = secret_key_path.read_text(encoding="utf-8").strip()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=PRODUCCION,
    max_age=14 * 24 * 3600,  # 14 días
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    """Cabeceras de seguridad básicas. nginx añade las suyas en producción
    (ver despliegue), pero se repiten aquí para que la app sea segura por sí
    sola incluso si se accede a ella directamente (p. ej. en local)."""
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if PRODUCCION:
        respuesta.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return respuesta


# ---- Límite de intentos de login/registro (mitiga fuerza bruta) ----

_INTENTOS_RECIENTES: dict[str, list[float]] = defaultdict(list)
INTENTOS_MAX = 8
INTENTOS_VENTANA_SEGUNDOS = 300


def _ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def limite_intentos_superado(clave: str) -> bool:
    ahora = time.time()
    intentos = _INTENTOS_RECIENTES[clave]
    intentos[:] = [t for t in intentos if ahora - t < INTENTOS_VENTANA_SEGUNDOS]
    if len(intentos) >= INTENTOS_MAX:
        return True
    intentos.append(ahora)
    return False

OPCIONES_DIAS = DASHBOARD_CFG.get("opciones_dias", [1, 3, 7, 14, 30])
DIAS_POR_DEFECTO = DASHBOARD_CFG.get("dias_por_defecto", 3)
TODAS_LAS_CATEGORIAS = [cat for cat in CATEGORIA_ORDEN]
DESTACADOS_COBERTURA_MINIMA = DASHBOARD_CFG.get("destacados_cobertura_minima", 2)
DESTACADOS_MAX = DASHBOARD_CFG.get("destacados_max", 8)
ITEMS_POR_PAGINA = DASHBOARD_CFG.get("items_por_pagina", 20)


def usuario_actual(request: Request) -> Optional[dict]:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    return db.obtener_usuario_por_id(usuario_id)


def _agrupar(items: List[dict]) -> dict:
    grupos = defaultdict(list)
    for item in items:
        grupos[item["categoria"]].append(item)
    return grupos


def _enriquecer_items(items: List[dict], usuario: Optional[dict]) -> None:
    """Añade a cada ítem: fecha formateada, lista de fuentes de cobertura,
    nº de likes totales y si el usuario actual le dio like / lo guardó."""
    hashes = [item["hash"] for item in items]
    conteo_likes = db.conteo_likes(hashes)
    guardados_usuario = db.hashes_guardados(usuario["id"], hashes) if usuario else set()
    likes_usuario = db.hashes_con_like(usuario["id"], hashes) if usuario else set()

    for item in items:
        fecha = datetime.fromisoformat(item["fecha"])
        item["fecha_fmt"] = fecha.strftime("%d/%m %H:%M")
        item["fuentes_cobertura_lista"] = (
            item["fuentes_cobertura"].split(SEPARADOR_FUENTES)
            if item.get("fuentes_cobertura")
            else [item["fuente"]]
        )
        item["likes"] = conteo_likes.get(item["hash"], 0)
        item["guardado"] = item["hash"] in guardados_usuario
        item["le_gusta"] = item["hash"] in likes_usuario


def _destino_tras_accion(request: Request, item_hash: str = "") -> str:
    """A dónde volver tras guardar/dar like: la misma página desde la que se
    pulsó el botón. Solo se aceptan rutas de ESTE sitio (el Referer lo manda el
    navegador, pero no se redirige a hosts externos) y se añade un ancla a la
    noticia para no perder la posición de lectura."""
    destino = "/"
    referer = request.headers.get("referer") or ""
    if referer:
        u = urlparse(referer)
        if u.netloc == request.headers.get("host", "") and u.path.startswith("/") and not u.path.startswith("//"):
            destino = u.path + (f"?{u.query}" if u.query else "")
    if item_hash and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", item_hash):
        destino += f"#item-{item_hash}"
    return destino


def _render_dashboard(
    request: Request, dias: int, categorias_activas: List[str], pagina: int
) -> HTMLResponse:
    dias = dias if dias in OPCIONES_DIAS else DIAS_POR_DEFECTO
    categorias_activas = [c for c in categorias_activas if c in TODAS_LAS_CATEGORIAS] or TODAS_LAS_CATEGORIAS
    usuario = usuario_actual(request)

    # Ya vienen ordenados por cobertura (nº de fuentes que cubren la misma
    # noticia) y luego por fecha, ver db.items_recientes: lo más relevante
    # siempre queda primero, también después de paginar.
    items = db.items_recientes(dias, categorias_activas)
    _enriquecer_items(items, usuario)

    # Lo más comentado: cubierto por varias fuentes independientes, buena
    # señal gratuita de qué es relevante de verdad (útil para un directo).
    # Solo se muestra en la primera página: es un destacado, no tiene sentido
    # repetirlo en cada página.
    destacados = (
        [i for i in items if i["cobertura"] >= DESTACADOS_COBERTURA_MINIMA][:DESTACADOS_MAX]
        if pagina == 1
        else []
    )

    grupos_completos = _agrupar(items)
    conteo_por_categoria = {cat: len(lista) for cat, lista in grupos_completos.items()}
    categorias_disponibles = [(cat, CATEGORIA_LABELS[cat]) for cat in CATEGORIA_ORDEN]

    # Paginación: cada sección de categoría se pagina con el mismo número de
    # página, cortando su propia lista (que ya viene ordenada por relevancia).
    total_paginas = max(
        1, math.ceil(max(conteo_por_categoria.values(), default=1) / ITEMS_POR_PAGINA)
    )
    pagina = min(max(pagina, 1), total_paginas)
    inicio = (pagina - 1) * ITEMS_POR_PAGINA
    fin = inicio + ITEMS_POR_PAGINA
    grupos = {cat: lista[inicio:fin] for cat, lista in grupos_completos.items()}

    categorias_qs = ""
    if set(categorias_activas) != set(TODAS_LAS_CATEGORIAS):
        categorias_qs = "&" + urlencode({"categorias": categorias_activas}, doseq=True)

    ultima_recoleccion_raw = db.get_meta("ultima_recoleccion")
    ultima_recoleccion = None
    if ultima_recoleccion_raw:
        ultima_recoleccion = datetime.fromisoformat(ultima_recoleccion_raw).strftime("%d/%m/%Y %H:%M UTC")

    return templates.TemplateResponse(
        request,
        "dashboard.html.j2",
        {
            "usuario": usuario,
            "csrf_token": csrf.token_csrf(request),
            "dias": dias,
            "opciones_dias": OPCIONES_DIAS,
            "categorias_disponibles": categorias_disponibles,
            "categorias_activas": categorias_activas,
            "categorias_qs": categorias_qs,
            "grupos": grupos,
            "destacados": destacados,
            "destacados_cobertura_minima": DESTACADOS_COBERTURA_MINIMA,
            "conteo_por_categoria": conteo_por_categoria,
            "total_items": len(items),
            "pagina": pagina,
            "total_paginas": total_paginas,
            "ultima_recoleccion": ultima_recoleccion,
            "twitter_activo": CONFIG.get("twitter", {}).get("enabled", False),
        },
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    dias: int = DIAS_POR_DEFECTO,
    categorias: Optional[List[str]] = Query(default=None),
    pagina: int = Query(default=1, ge=1),
):
    return _render_dashboard(request, dias, categorias or TODAS_LAS_CATEGORIAS, pagina)


@app.post("/actualizar")
def actualizar(
    request: Request,
    csrf_token: str = Form(...),
    dias: int = DIAS_POR_DEFECTO,
    categorias: Optional[List[str]] = Query(default=None),
):
    """Lanza una recolección nueva (bloqueante) y vuelve al panel."""
    csrf.exigir_csrf(request, csrf_token)
    logger.info("Recolección manual solicitada desde el panel web")
    ejecutar_recoleccion(CONFIG, db)

    query = {"dias": dias}
    if categorias:
        query["categorias"] = categorias
    return RedirectResponse(url=f"/?{urlencode(query, doseq=True)}", status_code=303)


# ---- Autenticación ----

NOMBRE_USUARIO_MIN = 3
PASSWORD_MIN = 8


ERROR_DEMASIADOS_INTENTOS = "Demasiados intentos. Espera unos minutos y vuelve a probar."


@app.get("/registro", response_class=HTMLResponse)
def registro_form(request: Request):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "registro.html.j2", {"error": None, "usuario": None, "csrf_token": csrf.token_csrf(request)}
    )


@app.post("/registro", response_class=HTMLResponse)
def registro_submit(
    request: Request,
    csrf_token: str = Form(...),
    nombre_usuario: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    csrf.exigir_csrf(request, csrf_token)
    if limite_intentos_superado(f"registro:{_ip_cliente(request)}"):
        return templates.TemplateResponse(
            request,
            "registro.html.j2",
            {"error": ERROR_DEMASIADOS_INTENTOS, "usuario": None, "csrf_token": csrf.token_csrf(request)},
            status_code=429,
        )

    nombre_usuario = nombre_usuario.strip()
    error = None
    if len(nombre_usuario) < NOMBRE_USUARIO_MIN:
        error = f"El usuario debe tener al menos {NOMBRE_USUARIO_MIN} caracteres."
    elif len(password) < PASSWORD_MIN:
        error = f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    elif password != password2:
        error = "Las contraseñas no coinciden."
    elif db.obtener_usuario_por_nombre(nombre_usuario):
        error = "Ese nombre de usuario ya existe."

    if error:
        return templates.TemplateResponse(
            request,
            "registro.html.j2",
            {"error": error, "usuario": None, "csrf_token": csrf.token_csrf(request)},
            status_code=400,
        )

    salt = auth.generar_salt()
    password_hash = auth.hash_password(password, salt)
    usuario_id = db.crear_usuario(nombre_usuario, password_hash, salt)
    request.session.clear()
    request.session["usuario_id"] = usuario_id
    logger.info("Nuevo usuario registrado: %s", nombre_usuario)
    return RedirectResponse("/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if usuario_actual(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html.j2", {"error": None, "usuario": None, "csrf_token": csrf.token_csrf(request)}
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request, csrf_token: str = Form(...), nombre_usuario: str = Form(...), password: str = Form(...)
):
    csrf.exigir_csrf(request, csrf_token)
    if limite_intentos_superado(f"login:{_ip_cliente(request)}"):
        return templates.TemplateResponse(
            request,
            "login.html.j2",
            {"error": ERROR_DEMASIADOS_INTENTOS, "usuario": None, "csrf_token": csrf.token_csrf(request)},
            status_code=429,
        )

    usuario = db.obtener_usuario_por_nombre(nombre_usuario.strip())
    credenciales_validas = usuario and auth.verificar_password(
        password, usuario["password_hash"], usuario["salt"]
    )
    if not credenciales_validas:
        return templates.TemplateResponse(
            request,
            "login.html.j2",
            {
                "error": "Usuario o contraseña incorrectos.",
                "usuario": None,
                "csrf_token": csrf.token_csrf(request),
            },
            status_code=400,
        )

    request.session.clear()
    request.session["usuario_id"] = usuario["id"]
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    csrf.exigir_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ---- Página de error 404 amigable (el resto de errores siguen devolviendo JSON) ----


@app.exception_handler(StarletteHTTPException)
async def error_http(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(request, "error.html.j2", {"titulo": "Página no encontrada"}, status_code=404)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


# ---- Páginas legales ----

_PAGINAS_LEGALES = {
    "aviso-legal": "Aviso legal",
    "privacidad": "Política de privacidad",
    "cookies": "Política de cookies",
}


def _pagina_legal(request: Request, clave: str):
    return templates.TemplateResponse(
        request, "legal.html.j2", {"titulo": _PAGINAS_LEGALES[clave], "pagina": clave}
    )


@app.get("/aviso-legal", response_class=HTMLResponse)
def aviso_legal(request: Request):
    return _pagina_legal(request, "aviso-legal")


@app.get("/privacidad", response_class=HTMLResponse)
def privacidad(request: Request):
    return _pagina_legal(request, "privacidad")


@app.get("/cookies", response_class=HTMLResponse)
def cookies(request: Request):
    return _pagina_legal(request, "cookies")


# ---- Otra frase motivadora (la pide el botón del bocadillo) ----


@app.get("/frase")
def otra_frase(actual: str = Query("", max_length=400)):
    """Devuelve una frase distinta de la que el usuario ya está viendo.
    Solo lee de la reserva en memoria / lista local: no hace llamadas externas."""
    f = frase_aleatoria()
    for _ in range(8):
        if f["texto"] != actual:
            break
        f = frase_aleatoria()
    return JSONResponse({"texto": f["texto"], "autor": f.get("autor", "")}, headers={"Cache-Control": "no-store"})


# ---- Guardar para más tarde / likes ----


@app.post("/guardar/{item_hash}")
def alternar_guardado(request: Request, item_hash: str, csrf_token: str = Form(...)):
    usuario = usuario_actual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    csrf.exigir_csrf(request, csrf_token)
    db.alternar_guardado(usuario["id"], item_hash)
    return RedirectResponse(_destino_tras_accion(request, item_hash), status_code=303)


@app.post("/like/{item_hash}")
def alternar_like(request: Request, item_hash: str, csrf_token: str = Form(...)):
    usuario = usuario_actual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)
    csrf.exigir_csrf(request, csrf_token)
    db.alternar_like(usuario["id"], item_hash)
    return RedirectResponse(_destino_tras_accion(request, item_hash), status_code=303)


@app.get("/guardados", response_class=HTMLResponse)
def ver_guardados(request: Request):
    usuario = usuario_actual(request)
    if not usuario:
        return RedirectResponse("/login", status_code=303)

    items = db.items_guardados(usuario["id"])
    _enriquecer_items(items, usuario)

    return templates.TemplateResponse(
        request,
        "guardados.html.j2",
        {
            "usuario": usuario,
            "items": items,
            "csrf_token": csrf.token_csrf(request),
            "twitter_activo": CONFIG.get("twitter", {}).get("enabled", False),
        },
    )
