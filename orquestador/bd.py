import json
import os
import sqlite3
from contextlib import contextmanager


class SqliteRepo:
    """Persistencia del estado de la Saga. Una instancia por proceso."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get("SAGA_DB_PATH", "/data/saga.db")
        directorio = os.path.dirname(self.db_path)
        if directorio and not os.path.exists(directorio):
            os.makedirs(directorio, exist_ok=True)
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sagas (
                    id_dispensacion TEXT PRIMARY KEY,
                    estado TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    pasos_confirmados TEXT NOT NULL DEFAULT '[]',
                    fecha TEXT NOT NULL DEFAULT (datetime('now')),
                    actualizado TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def iniciar(self, id_dispensacion: str, payload: dict) -> bool:
        with self.get_connection() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sagas (id_dispensacion, estado, payload) "
                "VALUES (?, 'INICIADA', ?)",
                (id_dispensacion, json.dumps(payload)),
            )
            conn.commit()
            return cur.rowcount == 1

    def obtener(self, id_dispensacion: str):
        with self.get_connection() as conn:
            fila = conn.execute(
                "SELECT id_dispensacion, estado, payload, pasos_confirmados, fecha, actualizado "
                "FROM sagas WHERE id_dispensacion = ?",
                (id_dispensacion,),
            ).fetchone()
        if fila is None:
            return None
        datos = dict(fila)
        datos["payload"] = json.loads(datos["payload"] or "{}")
        datos["pasos_confirmados"] = json.loads(datos["pasos_confirmados"] or "[]")
        return datos

    def actualizar(self, id_dispensacion: str, estado: str, pasos_confirmados: list = None) -> None:
        with self.get_connection() as conn:
            if pasos_confirmados is None:
                conn.execute(
                    "UPDATE sagas SET estado = ?, actualizado = datetime('now') "
                    "WHERE id_dispensacion = ?",
                    (estado, id_dispensacion),
                )
            else:
                conn.execute(
                    "UPDATE sagas SET estado = ?, pasos_confirmados = ?, "
                    "actualizado = datetime('now') WHERE id_dispensacion = ?",
                    (estado, json.dumps(pasos_confirmados), id_dispensacion),
                )
            conn.commit()
