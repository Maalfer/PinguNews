"""Almacenamiento ligero en SQLite: histórico y deduplicado de ítems."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Set, Tuple

from pingunews.models import SEPARADOR_FUENTES, Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    hash TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    url TEXT NOT NULL,
    fuente TEXT NOT NULL,
    categoria TEXT NOT NULL,
    fecha TEXT NOT NULL,
    resumen TEXT,
    autor TEXT,
    origen_tipo TEXT NOT NULL,
    visto_en TEXT NOT NULL,
    cobertura INTEGER NOT NULL DEFAULT 1,
    fuentes_cobertura TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_fecha ON items (fecha);
CREATE INDEX IF NOT EXISTS idx_items_categoria ON items (categoria);
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    email TEXT,
    -- Se incrementa al cambiar la contraseña: las sesiones (cookie firmada,
    -- ver web/deps.usuario_actual) guardan el valor que tenían al iniciar
    -- sesión, así que subir este número cierra cualquier otra sesión abierta
    -- con la contraseña anterior sin necesidad de un almacén de sesiones.
    version_sesion INTEGER NOT NULL DEFAULT 1,
    -- 'usuario' (por defecto, al registrarse) o 'admin'. Los admin pueden
    -- ver /usuarios-registrados y actuar sobre otras cuentas (ver
    -- routes/admin.py); no hay más roles por ahora.
    rol TEXT NOT NULL DEFAULT 'usuario',
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guardados (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    item_hash TEXT NOT NULL REFERENCES items(hash),
    guardado_en TEXT NOT NULL,
    PRIMARY KEY (usuario_id, item_hash)
);
CREATE TABLE IF NOT EXISTS likes (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    item_hash TEXT NOT NULL REFERENCES items(hash),
    creado_en TEXT NOT NULL,
    PRIMARY KEY (usuario_id, item_hash)
);
CREATE INDEX IF NOT EXISTS idx_guardados_usuario ON guardados (usuario_id);
CREATE INDEX IF NOT EXISTS idx_likes_item ON likes (item_hash);

-- Registro pendiente de verificación: la cuenta en `usuarios` no se crea
-- hasta que se confirma el correo (ver routes/cuentas.py), así que no hace
-- falta un campo "verificado" aparte ni se puede ocupar un nombre de usuario
-- solo con un correo ajeno que nunca se confirma.
CREATE TABLE IF NOT EXISTS registros_pendientes (
    token TEXT PRIMARY KEY,
    nombre_usuario TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    creado_en TEXT NOT NULL,
    expira_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_registros_pendientes_nombre ON registros_pendientes (nombre_usuario);
CREATE INDEX IF NOT EXISTS idx_registros_pendientes_email ON registros_pendientes (email);

-- Recuperación de contraseña: como mucho un enlace válido a la vez por
-- usuario (ver crear_token_reset) y se borra al usarse, así que no hace
-- falta un campo "usado".
CREATE TABLE IF NOT EXISTS tokens_reset_password (
    token TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en TEXT NOT NULL,
    expira_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tokens_reset_usuario ON tokens_reset_password (usuario_id);

-- Cambio de correo pendiente de confirmación: el correo nuevo se guarda aquí,
-- no en usuarios.email, hasta que se confirma con el enlace enviado a esa
-- misma dirección (prueba de que el usuario la controla).
CREATE TABLE IF NOT EXISTS cambios_email_pendientes (
    token TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    email_nuevo TEXT NOT NULL,
    creado_en TEXT NOT NULL,
    expira_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cambios_email_usuario ON cambios_email_pendientes (usuario_id);
"""

# Columnas añadidas después de la primera versión del esquema, por tabla: se
# agregan a bases de datos ya existentes con ALTER TABLE (SQLite no soporta
# "ADD COLUMN IF NOT EXISTS", así que se comprueba a mano con PRAGMA
# table_info).
COLUMNAS_MIGRABLES = {
    "items": {
        "cobertura": "INTEGER NOT NULL DEFAULT 1",
        "fuentes_cobertura": "TEXT",
    },
    "usuarios": {
        "email": "TEXT",
        "version_sesion": "INTEGER NOT NULL DEFAULT 1",
        "rol": "TEXT NOT NULL DEFAULT 'usuario'",
    },
}


class Database:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrar_columnas(conn)
            # El índice único de email se crea aparte (no en SCHEMA): en una
            # base de datos ya existente la columna no existe todavía cuando
            # se ejecuta SCHEMA, solo después de _migrar_columnas.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email) WHERE email IS NOT NULL"
            )

    def _migrar_columnas(self, conn: sqlite3.Connection) -> None:
        for tabla, columnas in COLUMNAS_MIGRABLES.items():
            columnas_actuales = {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})")}
            for columna, tipo in columnas.items():
                if columna not in columnas_actuales:
                    conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def existe(self, item_hash: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("SELECT 1 FROM items WHERE hash = ?", (item_hash,))
            return cur.fetchone() is not None

    def filtrar_nuevos(self, items: Iterable[Item]) -> List[Item]:
        """Devuelve solo los ítems cuyo hash no está ya en la base de datos."""
        nuevos = []
        with self._connect() as conn:
            for item in items:
                cur = conn.execute("SELECT 1 FROM items WHERE hash = ?", (item.hash,))
                if cur.fetchone() is None:
                    nuevos.append(item)
        return nuevos

    def guardar(self, items: Iterable[Item]) -> int:
        ahora = datetime.now().isoformat()
        filas = [
            (
                item.hash,
                item.titulo,
                item.url,
                item.fuente,
                item.categoria,
                item.fecha_iso(),
                item.resumen,
                item.autor,
                item.origen_tipo,
                ahora,
                item.cobertura,
                item.fuentes_cobertura_texto(),
            )
            for item in items
        ]
        if not filas:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO items
                (hash, titulo, url, fuente, categoria, fecha, resumen, autor, origen_tipo,
                 visto_en, cobertura, fuentes_cobertura)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                filas,
            )
        return len(filas)

    def incrementar_cobertura(self, item_hash: str, fuentes_nuevas: List[str]) -> None:
        """Suma fuentes nuevas a la cobertura de un ítem ya guardado, en vez de
        insertarlo de nuevo como si fuera una noticia distinta."""
        if not fuentes_nuevas:
            return
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT cobertura, fuentes_cobertura FROM items WHERE hash = ?", (item_hash,)
            )
            fila = cur.fetchone()
            if fila is None:
                return
            cobertura_actual, fuentes_texto = fila
            fuentes_actuales = fuentes_texto.split(SEPARADOR_FUENTES) if fuentes_texto else []
            for fuente in fuentes_nuevas:
                if fuente not in fuentes_actuales:
                    fuentes_actuales.append(fuente)
            conn.execute(
                "UPDATE items SET cobertura = ?, fuentes_cobertura = ? WHERE hash = ?",
                (len(fuentes_actuales), SEPARADOR_FUENTES.join(fuentes_actuales), item_hash),
            )

    def items_recientes(self, dias: int, categorias: Optional[List[str]] = None) -> List[dict]:
        """Ítems guardados en los últimos `dias` días, los de más cobertura y
        más recientes primero (ver collector/dedup.py: varias fuentes cubriendo la
        misma noticia es la señal de qué es más relevante)."""
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        query = "SELECT * FROM items WHERE fecha >= ?"
        params: list = [desde]
        if categorias:
            placeholders = ",".join("?" for _ in categorias)
            query += f" AND categoria IN ({placeholders})"
            params.extend(categorias)
        query += " ORDER BY cobertura DESC, fecha DESC"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def existentes_para_dedup(self, dias: int) -> List[Tuple[str, str, List[str]]]:
        """(hash, título, fuentes que ya la cubrían) de los últimos `dias` días,
        para el deduplicado por similitud contra el histórico (ver collector/dedup.py)."""
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT hash, titulo, fuentes_cobertura FROM items WHERE fecha >= ?", (desde,)
            )
            return [
                (h, t, (f.split(SEPARADOR_FUENTES) if f else []))
                for h, t, f in cur.fetchall()
            ]

    # ---- Usuarios ----

    def crear_usuario(self, nombre_usuario: str, password_hash: str, salt: str, email: Optional[str] = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO usuarios (nombre_usuario, password_hash, salt, email, creado_en) VALUES (?, ?, ?, ?, ?)",
                (nombre_usuario, password_hash, salt, email.lower() if email else None, datetime.now(timezone.utc).isoformat()),
            )
            return cur.lastrowid

    def obtener_usuario_por_nombre(self, nombre_usuario: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM usuarios WHERE nombre_usuario = ?", (nombre_usuario,))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def obtener_usuario_por_id(self, usuario_id: int) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def obtener_usuario_por_email(self, email: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email.lower(),))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def listar_usuarios(self) -> List[dict]:
        """Todas las cuentas, las más recientes primero (ver routes/admin.py)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM usuarios ORDER BY creado_en DESC")
            return [dict(row) for row in cur.fetchall()]

    def actualizar_rol(self, usuario_id: int, rol: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, usuario_id))

    def actualizar_nombre_usuario(self, usuario_id: int, nombre_usuario: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE usuarios SET nombre_usuario = ? WHERE id = ?", (nombre_usuario, usuario_id))

    def actualizar_email(self, usuario_id: int, email: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE usuarios SET email = ? WHERE id = ?", (email.lower(), usuario_id))

    def actualizar_password(self, usuario_id: int, password_hash: str, salt: str) -> int:
        """Cambia la contraseña y sube version_sesion (ver comentario en SCHEMA):
        invalida cualquier otra sesión abierta con la contraseña anterior.
        Devuelve la nueva version_sesion para que la sesión actual se
        actualice y no se cierre a sí misma (ver routes/cuentas.py y
        routes/perfil.py)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE usuarios SET password_hash = ?, salt = ?, version_sesion = version_sesion + 1 WHERE id = ?",
                (password_hash, salt, usuario_id),
            )
            return conn.execute(
                "SELECT version_sesion FROM usuarios WHERE id = ?", (usuario_id,)
            ).fetchone()[0]

    # ---- Registro pendiente de verificación por email ----

    def crear_registro_pendiente(
        self, token: str, nombre_usuario: str, email: str, password_hash: str, salt: str, expira_en: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO registros_pendientes "
                "(token, nombre_usuario, email, password_hash, salt, creado_en, expira_en) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (token, nombre_usuario, email.lower(), password_hash, salt,
                 datetime.now(timezone.utc).isoformat(), expira_en),
            )

    def obtener_registro_pendiente(self, token: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM registros_pendientes WHERE token = ?", (token,))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def obtener_registro_pendiente_por_nombre(self, nombre_usuario: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM registros_pendientes WHERE nombre_usuario = ?", (nombre_usuario,))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def registro_pendiente_en_conflicto(self, nombre_usuario: str, email: str) -> Optional[dict]:
        """Registro pendiente que ya usa ese nombre de usuario o ese correo
        (para avisar o reenviar el correo al registrarse otra vez, ver
        routes/cuentas.py)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM registros_pendientes WHERE nombre_usuario = ? OR email = ?",
                (nombre_usuario, email.lower()),
            )
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def eliminar_registro_pendiente(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM registros_pendientes WHERE token = ?", (token,))

    def limpiar_registros_pendientes_expirados(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM registros_pendientes WHERE expira_en < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )

    # ---- Recuperación de contraseña ----

    def crear_token_reset(self, token: str, usuario_id: int, expira_en: str) -> None:
        with self._connect() as conn:
            # Como mucho un enlace válido a la vez por usuario: evita
            # confusión sobre cuál es "el" enlace si se pide varias veces.
            conn.execute("DELETE FROM tokens_reset_password WHERE usuario_id = ?", (usuario_id,))
            conn.execute(
                "INSERT INTO tokens_reset_password (token, usuario_id, creado_en, expira_en) VALUES (?, ?, ?, ?)",
                (token, usuario_id, datetime.now(timezone.utc).isoformat(), expira_en),
            )

    def obtener_token_reset(self, token: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM tokens_reset_password WHERE token = ?", (token,))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def eliminar_token_reset(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM tokens_reset_password WHERE token = ?", (token,))

    # ---- Cambio de correo pendiente de confirmación ----

    def crear_cambio_email(self, token: str, usuario_id: int, email_nuevo: str, expira_en: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cambios_email_pendientes WHERE usuario_id = ?", (usuario_id,))
            conn.execute(
                "INSERT INTO cambios_email_pendientes (token, usuario_id, email_nuevo, creado_en, expira_en) "
                "VALUES (?, ?, ?, ?, ?)",
                (token, usuario_id, email_nuevo.lower(), datetime.now(timezone.utc).isoformat(), expira_en),
            )

    def obtener_cambio_email(self, token: str) -> Optional[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM cambios_email_pendientes WHERE token = ?", (token,))
            fila = cur.fetchone()
            return dict(fila) if fila else None

    def eliminar_cambio_email(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cambios_email_pendientes WHERE token = ?", (token,))

    # ---- Guardados ("ver más tarde") ----

    def existe_item(self, item_hash: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM items WHERE hash = ?", (item_hash,)).fetchone() is not None

    def alternar_guardado(self, usuario_id: int, item_hash: str) -> bool:
        """Guarda o quita de guardados. Devuelve True si ha quedado guardado."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM guardados WHERE usuario_id = ? AND item_hash = ?",
                (usuario_id, item_hash),
            )
            if cur.fetchone():
                conn.execute(
                    "DELETE FROM guardados WHERE usuario_id = ? AND item_hash = ?",
                    (usuario_id, item_hash),
                )
                return False
            conn.execute(
                "INSERT INTO guardados (usuario_id, item_hash, guardado_en) VALUES (?, ?, ?)",
                (usuario_id, item_hash, datetime.now(timezone.utc).isoformat()),
            )
            return True

    def hashes_guardados(self, usuario_id: int, hashes: List[str]) -> Set[str]:
        """De esta lista de hashes, cuáles tiene guardados este usuario."""
        if not hashes:
            return set()
        placeholders = ",".join("?" for _ in hashes)
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT item_hash FROM guardados WHERE usuario_id = ? AND item_hash IN ({placeholders})",
                [usuario_id, *hashes],
            )
            return {row[0] for row in cur.fetchall()}

    def items_guardados(self, usuario_id: int) -> List[dict]:
        """Ítems guardados por este usuario, los guardados más recientemente primero."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT items.*, guardados.guardado_en AS guardado_en
                FROM guardados JOIN items ON guardados.item_hash = items.hash
                WHERE guardados.usuario_id = ?
                ORDER BY guardados.guardado_en DESC
                """,
                (usuario_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    # ---- Likes ----

    def alternar_like(self, usuario_id: int, item_hash: str) -> bool:
        """Da o quita el like. Devuelve True si ha quedado con like."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM likes WHERE usuario_id = ? AND item_hash = ?",
                (usuario_id, item_hash),
            )
            if cur.fetchone():
                conn.execute(
                    "DELETE FROM likes WHERE usuario_id = ? AND item_hash = ?",
                    (usuario_id, item_hash),
                )
                return False
            conn.execute(
                "INSERT INTO likes (usuario_id, item_hash, creado_en) VALUES (?, ?, ?)",
                (usuario_id, item_hash, datetime.now(timezone.utc).isoformat()),
            )
            return True

    def hashes_con_like(self, usuario_id: int, hashes: List[str]) -> Set[str]:
        """De esta lista de hashes, a cuáles les ha dado like este usuario."""
        if not hashes:
            return set()
        placeholders = ",".join("?" for _ in hashes)
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT item_hash FROM likes WHERE usuario_id = ? AND item_hash IN ({placeholders})",
                [usuario_id, *hashes],
            )
            return {row[0] for row in cur.fetchall()}

    def conteo_likes(self, hashes: List[str]) -> dict:
        """Nº total de likes (de todos los usuarios) por cada hash de esta lista."""
        if not hashes:
            return {}
        placeholders = ",".join("?" for _ in hashes)
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                SELECT item_hash, COUNT(*) FROM likes
                WHERE item_hash IN ({placeholders})
                GROUP BY item_hash
                """,
                hashes,
            )
            return dict(cur.fetchall())

    def set_meta(self, clave: str, valor: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )

    def get_meta(self, clave: str) -> Optional[str]:
        with self._connect() as conn:
            cur = conn.execute("SELECT valor FROM meta WHERE clave = ?", (clave,))
            row = cur.fetchone()
            return row[0] if row else None
