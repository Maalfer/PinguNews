"""Límite de intentos de login/registro (mitiga la fuerza bruta).

Simple y en memoria (un solo worker): sin dependencias nuevas.
"""
from __future__ import annotations

import time
from collections import defaultdict

from starlette.requests import Request

INTENTOS_MAX = 8
INTENTOS_VENTANA_SEGUNDOS = 300
FALLOS_USUARIO_MAX = 12
FALLOS_USUARIO_VENTANA = 900
_LIMITE_ENTRADAS = 5000

_INTENTOS_RECIENTES: dict[str, list[float]] = defaultdict(list)
_FALLOS_USUARIO: dict[str, list[float]] = defaultdict(list)


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def fallos_usuario_excedidos(nombre: str) -> bool:
    ahora = time.time()
    lista = _FALLOS_USUARIO[nombre.lower()[:64]]
    lista[:] = [t for t in lista if ahora - t < FALLOS_USUARIO_VENTANA]
    return len(lista) >= FALLOS_USUARIO_MAX


def registrar_fallo_usuario(nombre: str) -> None:
    _FALLOS_USUARIO[nombre.lower()[:64]].append(time.time())


def _limpiar_limites() -> None:
    ahora = time.time()
    for d, v in ((_INTENTOS_RECIENTES, INTENTOS_VENTANA_SEGUNDOS), (_FALLOS_USUARIO, FALLOS_USUARIO_VENTANA)):
        for k in [k for k, lista in d.items() if not lista or ahora - lista[-1] > v]:
            d.pop(k, None)


def limite_intentos_superado(clave: str) -> bool:
    ahora = time.time()
    if len(_INTENTOS_RECIENTES) > _LIMITE_ENTRADAS or len(_FALLOS_USUARIO) > _LIMITE_ENTRADAS:
        _limpiar_limites()
    intentos = _INTENTOS_RECIENTES[clave]
    intentos[:] = [t for t in intentos if ahora - t < INTENTOS_VENTANA_SEGUNDOS]
    if len(intentos) >= INTENTOS_MAX:
        return True
    intentos.append(ahora)
    return False
