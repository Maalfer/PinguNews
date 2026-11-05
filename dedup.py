"""Deduplicado por similitud de título — y conteo de cobertura.

El deduplicado por hash (ver db.py) solo detecta ítems con la misma URL+título
exactos. Pero si Hispasec y MuySeguridad cubren el mismo CVE, cada uno con su
propio titular, tienen hashes distintos y aparecerían como dos noticias
diferentes. Esto compara por solapamiento de palabras significativas del
título para detectar esos casos — y de paso usa ese mismo dato para calcular
una señal gratuita de relevancia: cuántas fuentes distintas cubren la misma
noticia (ver Item.cobertura). Si 3 medios independientes cubren lo mismo,
probablemente sea más interesante para comentar que algo que solo cubrió uno.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

from utils import Item, normalize

# Palabras demasiado comunes en titulares en español como para aportar señal
# de que dos noticias tratan lo mismo.
STOPWORDS_GENERALES = {
    "de", "la", "el", "en", "por", "para", "con", "una", "uno", "unos", "unas",
    "los", "las", "su", "sus", "se", "que", "mas", "nuevo", "nueva", "nuevos",
    "nuevas", "como", "del", "al", "lo", "ya", "tras", "sobre", "entre", "este",
    "esta", "estos", "estas", "un", "y", "o", "a", "es", "ser", "hay", "sin",
    "qué", "más",
}

# Vocabulario genérico muy repetido en titulares de ciberseguridad/IT. Sin
# esto, dos CVEs totalmente distintos (p. ej. uno de Apache y otro de Nginx)
# salen más "parecidos" entre sí que dos titulares que sí son la misma
# noticia, porque comparten frases hechas como "vulnerabilidad crítica
# permite ejecución remota de código" y solo difieren en el nombre propio.
STOPWORDS_SECTOR = {
    "vulnerabilidad", "vulnerabilidades", "critica", "criticas", "grave",
    "graves", "permite", "permiten", "podria", "podrian", "ejecucion",
    "remota", "remoto", "codigo", "ataque", "ataques", "ciberataque",
    "ciberataques", "fallo", "fallos", "seguridad", "descubre", "descubren",
    "investigadores", "informan", "informa", "advierte", "advierten",
    "afecta", "afectados", "afectadas", "detectan", "detecta", "revela",
    "revelan", "segun", "millones", "usuarios", "usuario", "empresa",
    "empresas", "compania", "companias", "dispositivos", "dispositivo",
    "sistema", "sistemas", "datos", "importante", "explotar", "explotada",
    "explotan", "parche", "parches", "actualizacion", "actualizaciones",
}

STOPWORDS = STOPWORDS_GENERALES | STOPWORDS_SECTOR

UMBRAL_POR_DEFECTO = 0.55

# (hash_existente, titulo_existente, fuentes_que_ya_la_cubrian)
ExistenteConCobertura = Tuple[str, str, List[str]]
# (hash_existente, fuentes_nuevas_a_sumar)
IncrementoCobertura = Tuple[str, List[str]]


def _tokens(titulo: str) -> set[str]:
    # \w incluye "_", que no aparece en titulares; re.findall con [a-z0-9]
    # separa correctamente "fabricante," o "Google:" en su palabra limpia,
    # sin lo cual esa puntuación pegada generaba un token distinto que no
    # coincidía con la misma palabra sin puntuación en otro titular.
    palabras = re.findall(r"[a-z0-9]+", normalize(titulo))
    return {p for p in palabras if len(p) >= 4 and p not in STOPWORDS}


def _similitud(a: set[str], b: set[str]) -> float:
    """Jaccard sobre las palabras significativas: intersección / unión."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def agrupar_por_titulo(items: Sequence[Item], umbral: float = UMBRAL_POR_DEFECTO) -> List[Item]:
    """Dentro de una misma tanda, colapsa ítems cuyo título es casi la misma
    noticia. El ítem superviviente (el primero del grupo) se queda con
    `cobertura` = nº de fuentes distintas que la cubrieron y
    `fuentes_cobertura` con sus nombres."""
    grupos: List[Tuple[set[str], Item]] = []
    for item in items:
        tokens = _tokens(item.titulo)
        representante = None
        for tokens_grupo, candidato in grupos:
            if _similitud(tokens, tokens_grupo) >= umbral:
                representante = candidato
                break
        if representante is None:
            item.fuentes_cobertura = [item.fuente]
            item.cobertura = 1
            grupos.append((tokens, item))
        elif item.fuente not in representante.fuentes_cobertura:
            representante.fuentes_cobertura.append(item.fuente)
            representante.cobertura += 1
    return [representante for _, representante in grupos]


def separar_duplicados_de_historico(
    items: Sequence[Item],
    existentes: Iterable[ExistenteConCobertura],
    umbral: float = UMBRAL_POR_DEFECTO,
) -> Tuple[List[Item], List[IncrementoCobertura]]:
    """Separa los ítems casi idénticos (por título) a algo ya guardado en el
    histórico, aunque la URL (y por tanto el hash) sea distinta.

    Devuelve (items_realmente_nuevos, incrementos): cada incremento dice qué
    fila existente de la base de datos debe sumar qué fuentes nuevas a su
    cobertura, en vez de guardarse como una fila duplicada.
    """
    existentes_tokens = [(h, _tokens(t), fuentes) for h, t, fuentes in existentes]
    nuevos: List[Item] = []
    incrementos: List[IncrementoCobertura] = []
    for item in items:
        tokens = _tokens(item.titulo)
        coincidencia = next(
            (
                (h, fuentes)
                for h, tokens_existente, fuentes in existentes_tokens
                if _similitud(tokens, tokens_existente) >= umbral
            ),
            None,
        )
        if coincidencia is None:
            nuevos.append(item)
            continue

        hash_existente, fuentes_existentes = coincidencia
        fuentes_nuevas = [f for f in (item.fuentes_cobertura or [item.fuente]) if f not in fuentes_existentes]
        if fuentes_nuevas:
            incrementos.append((hash_existente, fuentes_nuevas))

    return nuevos, incrementos
