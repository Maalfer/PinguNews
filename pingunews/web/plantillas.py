"""Motor de plantillas Jinja2: filtros y funciones globales."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from pingunews.collector.classifier import CATEGORIA_LABELS
from pingunews.content.frases import frase_aleatoria
from pingunews.content.legal import LEGAL
from pingunews.web.estaticos import css_en_linea, css_texto, static_v

DIR_PLANTILLAS = Path(__file__).resolve().parent / "templates"

# Los emojis de las etiquetas son decorativos: se ocultan a los lectores de pantalla.
_RE_EMOJI_INICIAL = re.compile(r"^([^\w¿¡(\"“«]+)\s*", re.UNICODE)

# Fuentes cuyo contenido está en inglés (para marcarlo con lang="en").
_FUENTES_EN = ("jobicy", "remoteok", "we work remotely")

# Autores de las fuentes: "noreply@blogger.com (SeguInfo)" -> "SeguInfo"
_RE_AUTOR_EMAIL = re.compile(r"^\S+@\S+\s*\((.+)\)\s*$")
_RE_SOLO_EMAIL = re.compile(r"^\S+@\S+$")


def emoji_decorativo(texto):
    t = str(texto)
    m = _RE_EMOJI_INICIAL.match(t)
    if m and m.group(1).strip():
        return Markup('<span aria-hidden="true">%s</span> %s') % (m.group(1).strip(), t[m.end():])
    return escape(t)


def idioma_item(item) -> str:
    fuente = str((item.get("fuente") if hasattr(item, "get") else item["fuente"]) or "").lower()
    return "en" if any(fuente.startswith(f) for f in _FUENTES_EN) else ""


def autor_limpio(autor) -> str:
    a = str(autor or "").strip()
    m = _RE_AUTOR_EMAIL.match(a)
    if m:
        return m.group(1).strip()
    return "" if _RE_SOLO_EMAIL.match(a) else a


def url_segura(u) -> str:
    return u if isinstance(u, str) and re.match(r"https?://", u.strip(), re.I) else "#"


def etiqueta_categoria(cat: str) -> str:
    return CATEGORIA_LABELS.get(cat, cat).split(" (")[0]


def crear_plantillas() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(DIR_PLANTILLAS))
    # IMPORTANTE: Jinja2Templates decide si autoescapar HTML mirando la extensión
    # del archivo (select_autoescape), y nuestras plantillas se llaman
    # "*.html.j2" (no "*.html"), así que NO coincide con su lista y el autoescape
    # queda desactivado por defecto. Como los títulos/resúmenes vienen de fuentes
    # RSS externas (no confiables) y el nombre de usuario lo elige el propio
    # usuario, sin esto cualquier feed o usuario podría inyectar HTML/JS
    # (XSS) en cada página del panel. Se fuerza explícitamente a True.
    templates.env.autoescape = True

    g = templates.env.globals
    g["frase_aleatoria"] = frase_aleatoria
    g["legal"] = LEGAL
    g["anio_actual"] = lambda: datetime.now().year
    g["static_v"] = static_v
    g["etiqueta_categoria"] = etiqueta_categoria
    g["css_texto"] = css_texto
    g["css_en_linea"] = css_en_linea
    g["idioma_item"] = idioma_item

    f = templates.env.filters
    f["emoji_decorativo"] = emoji_decorativo
    f["url_segura"] = url_segura
    f["autor_limpio"] = autor_limpio
    return templates
