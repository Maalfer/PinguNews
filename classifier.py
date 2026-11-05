"""Clasificación por palabras clave y resumen heurístico (sin LLM)."""
from __future__ import annotations

from typing import Dict, List

from utils import coincide_palabra_completa, normalize, strip_html

CATEGORIA_ORDEN = [
    "ciberseguridad",
    "tendencias_sector",
    "empleo",
    "desarrollo_it",
    "actualidad",
]

CATEGORIA_LABELS = {
    "ciberseguridad": "Ciberseguridad / Hacking",
    "tendencias_sector": "📺 Tendencias del sector (despidos, mercado, crecimiento)",
    "empleo": "Empleo",
    "desarrollo_it": "Desarrollo / IT",
    "actualidad": "Actualidad general del sector",
}


def clasificar(titulo: str, texto: str, keywords: Dict[str, List[str]], categoria_sugerida: str | None = None) -> str:
    """Devuelve la categoría más probable para un ítem.

    Si la fuente ya indica una categoría (p. ej. un feed de empleo), se
    respeta salvo que el contenido matchee claramente con otra categoría
    de palabras clave con más peso.
    """
    base = normalize(f"{titulo} {texto}")
    puntuacion = {cat: 0 for cat in keywords}
    for categoria, palabras in keywords.items():
        for palabra in palabras:
            if coincide_palabra_completa(base, normalize(palabra)):
                puntuacion[categoria] += 1

    mejor_categoria = max(puntuacion, key=puntuacion.get) if puntuacion else None
    mejor_puntuacion = puntuacion.get(mejor_categoria, 0) if mejor_categoria else 0

    if mejor_puntuacion == 0:
        return categoria_sugerida or "actualidad"

    if categoria_sugerida and puntuacion.get(categoria_sugerida, 0) >= mejor_puntuacion:
        return categoria_sugerida

    return mejor_categoria


def resumir(texto_html_o_plano: str, max_chars: int = 280) -> str:
    """Resumen heurístico: limpia HTML y recorta por frase hasta max_chars."""
    texto = strip_html(texto_html_o_plano)
    if len(texto) <= max_chars:
        return texto

    recorte = texto[:max_chars]
    ultimo_punto = recorte.rfind(". ")
    if ultimo_punto > max_chars * 0.4:
        return recorte[: ultimo_punto + 1].strip()
    return recorte.rstrip() + "…"
