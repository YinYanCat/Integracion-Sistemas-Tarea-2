import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("RECETA_DB_PATH", "/data/receta.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS recetas_validadas (
    id_dispensacion TEXT PRIMARY KEY,
    estado TEXT NOT NULL CHECK (estado IN ('VALIDADA', 'COMPENSADA')),
    fecha TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

def _ensure_dir():
    dir = os.path.dirname(DB_PATH)
    if dir and not os.path.exists(dir):
        os.makedirs(dir, exist_ok=True)

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

def registrar_validacion(conn, id_dispensacion: str):
    conn.execute(
        "INSERT OR REPLACE INTO recetas_validadas (id_dispensacion, estado) VALUES (?, 'VALIDADA')",
        (id_dispensacion,),
    )
    conn.commit()

def registrar_compensacion(conn, id_dispensacion: str):
    conn.execute(
        "UPDATE recetas_validadas SET estado = 'COMPENSADA' WHERE id_dispensacion = ?",
        (id_dispensacion,),
    )
    conn.commit()

def obtener_historial(conn):
    cur = conn.execute("SELECT id_dispensacion, estado, fecha FROM recetas_validadas ORDER BY fecha DESC")
    return [dict(row) for row in cur.fetchall()]