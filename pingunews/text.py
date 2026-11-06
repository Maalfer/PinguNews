"""Utilidades de texto: normalización y limpieza."""
from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Minúsculas y sin acentos, para comparación de palabras clave."""
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def coincide_palabra_completa(texto_normalizado: str, palabra_normalizada: str) -> bool:
    """Compara por palabra completa, no por subcadena.

    Imprescindible para palabras cortas: "ere" (de "ERE") aparece como
    subcadena dentro de montones de palabras españolas normales
    ("dif**ere**ntes", "qu**ere**r"...), igual que "soc" dentro de "social"
    o "apt" dentro de "adaptar".
    """
    return re.search(rf"\b{re.escape(palabra_normalizada)}\b", texto_normalizado) is not None


def strip_html(html: str) -> str:
    """Elimina etiquetas HTML de un texto, dejando solo el contenido legible."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
