import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DESPACHO_DB_PATH", "/data/despacho.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS despachos (
    id_dispensacion TEXT PRIMARY KEY,
    paciente_id TEXT NOT NULL,
    codigo_medicamento TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('creado', 'cancelado')),
    fecha TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _ensure_dir():
    directorio = os.path.dirname(DB_PATH)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio, exist_ok=True)


def init_db():
    _ensure_dir()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def crear(conn, id_dispensacion: str, paciente_id: str, codigo: str, cantidad: int) -> dict:
    conn.execute(
        "INSERT OR IGNORE INTO despachos "
        "(id_dispensacion, paciente_id, codigo_medicamento, cantidad, estado) "
        "VALUES (?, ?, ?, ?, 'creado')",
        (id_dispensacion, paciente_id, codigo, cantidad),
    )
    conn.commit()
    return obtener(conn, id_dispensacion)


def cancelar(conn, id_dispensacion: str) -> bool:
    cur = conn.execute(
        "UPDATE despachos SET estado = 'cancelado' "
        "WHERE id_dispensacion = ? AND estado = 'creado'",
        (id_dispensacion,),
    )
    conn.commit()
    return cur.rowcount > 0


def obtener(conn, id_dispensacion: str):
    cur = conn.execute(
        "SELECT id_dispensacion, paciente_id, codigo_medicamento, cantidad, estado, fecha "
        "FROM despachos WHERE id_dispensacion = ?",
        (id_dispensacion,),
    )
    fila = cur.fetchone()
    return dict(fila) if fila is not None else None
