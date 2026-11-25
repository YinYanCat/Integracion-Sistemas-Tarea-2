import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from despacho import bd


class TestBdDespacho(unittest.TestCase):
    def setUp(self):
        self.db_path_original = bd.DB_PATH
        self.temporal = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temporal.name, "despacho.db")
        bd.DB_PATH = self.path
        bd.init_db()

    def tearDown(self):
        bd.DB_PATH = self.db_path_original
        self.temporal.cleanup()

    def test_crear_repetido_no_duplica(self):
        with bd.get_connection() as conn:
            bd.crear(conn, "TX-1", "PAC-1", "MED-1", 2)
            bd.crear(conn, "TX-1", "PAC-1", "MED-1", 2)
            filas = conn.execute(
                "SELECT COUNT(*) FROM despachos WHERE id_dispensacion='TX-1'"
            ).fetchone()[0]
        self.assertEqual(filas, 1)

    def test_cancelar_es_idempotente(self):
        with bd.get_connection() as conn:
            bd.crear(conn, "TX-2", "PAC-1", "MED-1", 1)
            self.assertTrue(bd.cancelar(conn, "TX-2"))
            self.assertFalse(bd.cancelar(conn, "TX-2"))
            self.assertEqual(bd.obtener(conn, "TX-2")["estado"], "cancelado")


if __name__ == "__main__":
    unittest.main()
