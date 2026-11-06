"""Búsqueda de noticias por palabras (sin distinguir mayúsculas ni acentos)."""
from __future__ import annotations

import unicodedata
from typing import List

BUSQUEDA_MAX_CHARS = 100
BUSQUEDA_MAX_TERMINOS = 8
CAMPOS_BUSCABLES = ("titulo", "resumen", "fuente", "autor")


def limpiar_consulta(q: str) -> str:
    """Colapsa espacios y recorta a la longitud máxima permitida."""
    return " ".join((q or "").split())[:BUSQUEDA_MAX_CHARS]


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para que 'seguridad' encuentre 'Seguridad' y
    'vulnerabilidad' encuentre 'vulnerabilidád'."""
    sin_acentos = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).casefold()


def filtrar(items: List[dict], q: str) -> List[dict]:
    """Se queda con los ítems que contienen TODAS las palabras buscadas (en
    título, resumen, fuente o autor)."""
    terminos = normalizar(q).split()[:BUSQUEDA_MAX_TERMINOS]
    if not terminos:
        return items
    resultado = []
    for it in items:
        pajar = normalizar(" ".join(str(it.get(k) or "") for k in CAMPOS_BUSCABLES))
        if all(t in pajar for t in terminos):
            resultado.append(it)
    return resultado
