"""Ficheros estáticos: caché larga con versionado por hash y CSS incrustado."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.staticfiles import StaticFiles

DIR_ESTATICOS = Path(__file__).resolve().parent / "static"

_VERSIONES: dict[str, str] = {}
_CSS_TEXTO: dict[str, str] = {}


class EstaticosConCache(StaticFiles):
    """/static con caché larga: un año e inmutable si la URL lleva ?v=<hash>
    (la versión cambia sola al cambiar el fichero); un día en el resto."""

    async def get_response(self, path, scope):
        respuesta = await super().get_response(path, scope)
        if respuesta.status_code in (200, 304):
            versionado = b"v=" in scope.get("query_string", b"")
            respuesta.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if versionado else "public, max-age=86400"
            )
        return respuesta


def static_v(nombre: str) -> str:
    """Huella corta del contenido de un fichero de /static: si cambia, cambia la URL
    (?v=...) y el navegador descarga la versión nueva; si no, la reutiliza un año."""
    v = _VERSIONES.get(nombre)
    if v is None:
        try:
            v = hashlib.md5((DIR_ESTATICOS / nombre).read_bytes(), usedforsecurity=False).hexdigest()[:10]
        except OSError:
            v = "0"
        _VERSIONES[nombre] = v
    return v


def css_texto() -> str:
    """Contenido de estilos.css (se lee una vez y se guarda en memoria)."""
    if "v" not in _CSS_TEXTO:
        _CSS_TEXTO["v"] = (DIR_ESTATICOS / "estilos.css").read_text(encoding="utf-8")
    return _CSS_TEXTO["v"]


def css_en_linea(request) -> bool:
    """Primera visita (o hoja de estilos nueva): el CSS va incrustado para que la
    primera pintura no espere a una petición extra, y se descarga el fichero
    cacheable en segundo plano. Después: se usa ese fichero, ya en caché, y no se
    reenvían 50 KB de CSS en cada página. La marca se guarda en la cookie de sesión."""
    version = static_v("estilos.css")
    try:
        if request.session.get("css_v") == version:
            return False
        request.session["css_v"] = version
    except Exception:
        return False
    return True
