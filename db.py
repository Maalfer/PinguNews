"""Almacenamiento ligero en SQLite: histórico y deduplicado de ítems."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Set, Tuple

from utils import Item, SEPARADOR_FUENTES

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
"""

# Columnas añadidas después de la primera versión del esquema: se agregan a
# bases de datos ya existentes con ALTER TABLE (SQLite no soporta "ADD COLUMN
# IF NOT EXISTS", así que se comprueba a mano con PRAGMA table_info).
COLUMNAS_MIGRABLES = {
    "cobertura": "INTEGER NOT NULL DEFAULT 1",
    "fuentes_cobertura": "TEXT",
}


class Database:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrar_columnas(conn)

    def _migrar_columnas(self, conn: sqlite3.Connection) -> None:
        columnas_actuales = {fila[1] for fila in conn.execute("PRAGMA table_info(items)")}
        for columna, tipo in COLUMNAS_MIGRABLES.items():
            if columna not in columnas_actuales:
                conn.execute(f"ALTER TABLE items ADD COLUMN {columna} {tipo}")

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
        más recientes primero (ver dedup.py: varias fuentes cubriendo la
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
        para el deduplicado por similitud contra el histórico (ver dedup.py)."""
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

    def crear_usuario(self, nombre_usuario: str, password_hash: str, salt: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO usuarios (nombre_usuario, password_hash, salt, creado_en) VALUES (?, ?, ?, ?)",
                (nombre_usuario, password_hash, salt, datetime.now(timezone.utc).isoformat()),
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

    # ---- Guardados ("ver más tarde") ----

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
