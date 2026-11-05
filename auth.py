"""Autenticación: hash de contraseñas con PBKDF2-HMAC-SHA256 y salt aleatorio
por usuario (sin dependencias externas de cifrado). Pensado para una
herramienta de uso personal/local, no para un servicio expuesto a internet
con miles de usuarios — para eso haría falta bcrypt/argon2 y más medidas
(rate limiting, verificación de email, etc.).
"""
from __future__ import annotations

import hashlib
import secrets

ITERACIONES_PBKDF2 = 600_000  # recomendación actual de OWASP para PBKDF2-SHA256


def generar_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERACIONES_PBKDF2
    ).hex()


def verificar_password(password: str, password_hash: str, salt: str) -> bool:
    calculado = hash_password(password, salt)
    # compare_digest evita timing attacks (comparar con == filtra por tiempo
    # cuánto del hash coincide, letra a letra)
    return secrets.compare_digest(calculado, password_hash)
