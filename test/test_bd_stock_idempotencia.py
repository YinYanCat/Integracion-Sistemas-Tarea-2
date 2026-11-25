import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from stock import bd_stock as db


class TestIdempotenciaStock(unittest.TestCase):
    def setUp(self):
        self.db_path_original = db.DB_PATH
        self.temporal = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temporal.name, "stock.db")
        db.DB_PATH = self.path
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.temporal.cleanup()

    def test_reservar_repetido_no_descuenta_dos_veces(self):
        with db.get_connection() as conn:
            ok1, u1, _ = db.reservar_unidades(conn, "MED-1", 2, "TX-1")
            ok2, u2, _ = db.reservar_unidades(conn, "MED-1", 2, "TX-1")
        self.assertTrue(ok1 and ok2)
        self.assertEqual((u1, u2), (48, 48))

    def test_liberar_repetido_no_repone_dos_veces(self):
        with db.get_connection() as conn:
            db.reservar_unidades(conn, "MED-1", 2, "TX-2")
            _, u1, _ = db.liberar_unidades(conn, "MED-1", 2, "TX-2")
            _, u2, _ = db.liberar_unidades(conn, "MED-1", 2, "TX-2")
        self.assertEqual((u1, u2), (50, 50))


if __name__ == "__main__":
    unittest.main()
