"""Frase inspiradora para la portada.

Fuente principal: la API pública FraseDelDía (frases en español, sin clave):
    https://frasedeldia.azurewebsites.net/api/phrase

Para no frenar la página ni depender de un servicio externo, las frases se
piden en segundo plano a un hilo que mantiene una pequeña reserva en memoria
(_POOL). Cada visita consume una de la reserva; si la reserva está vacía o la
API no responde, se usa la lista local de respaldo (_LOCAL), así que la
portada nunca espera ni falla por esto.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import urllib.request
from collections import deque
from typing import Deque, Dict, Optional

log = logging.getLogger("pingunews.frases")

API_URL = "https://frasedeldia.azurewebsites.net/api/phrase"
POOL_OBJETIVO = 12          # frases que intentamos tener listas
PAUSA_ENTRE_PETICIONES = 3  # s: cortesía con la API gratuita
TIMEOUT = 4                 # s por petición
MAX_LONGITUD = 180          # descartamos frases muy largas (no caben bien)
ENFRIAMIENTO_TRAS_FALLO = 300  # s sin insistir si la API falla

from frases_locales import FRASES as _LOCAL  # repertorio propio (ver frases_locales.py)

_POOL: Deque[Dict[str, str]] = deque()
_lock = threading.Lock()
_rellenando = False
_no_antes_de = 0.0


def _limpiar(texto: str) -> str:
    return " ".join(texto.replace("\r", " ").replace("\n", " ").split())


def _pedir_una() -> Optional[Dict[str, str]]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "PinguNews/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        d = json.load(r)
    texto = _limpiar(str(d.get("phrase", "")))
    autor = _limpiar(str(d.get("author", "")))
    if not texto or len(texto) > MAX_LONGITUD:
        return None
    return {"texto": texto, "autor": autor}


def _rellenar() -> None:
    """Hilo: pide frases hasta llenar la reserva. Nunca lanza excepciones."""
    global _rellenando, _no_antes_de
    try:
        fallos = 0
        while True:
            with _lock:
                if len(_POOL) >= POOL_OBJETIVO:
                    return
                vistas = {f["texto"] for f in _POOL}
            try:
                f = _pedir_una()
                if f and f["texto"] not in vistas:
                    with _lock:
                        _POOL.append(f)
                fallos = 0
            except Exception as e:  # red caída, API caída, JSON raro...
                fallos += 1
                log.warning("FraseDelDía no disponible: %s", e)
                if fallos >= 2:
                    _no_antes_de = time.time() + ENFRIAMIENTO_TRAS_FALLO
                    return
            time.sleep(PAUSA_ENTRE_PETICIONES)
    finally:
        _rellenando = False


def _asegurar_relleno() -> None:
    global _rellenando
    with _lock:
        if _rellenando or len(_POOL) >= POOL_OBJETIVO or time.time() < _no_antes_de:
            return
        _rellenando = True
    threading.Thread(target=_rellenar, name="frases-refill", daemon=True).start()


def frase_aleatoria() -> Dict[str, str]:
    """{'texto', 'autor'}: de la reserva de la API si hay, si no de la lista local."""
    _asegurar_relleno()
    with _lock:
        if _POOL:
            return _POOL.popleft()
    return random.choice(_LOCAL)
