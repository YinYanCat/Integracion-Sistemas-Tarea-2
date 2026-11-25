import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from orquestador.bd import SqliteRepo


class TestSqliteRepo(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temporal.name, "saga.db")
        self.repo = SqliteRepo(self.path)

    def tearDown(self):
        self.temporal.cleanup()

    def test_iniciar_es_idempotente_y_guarda_payload(self):
        payload = {"paciente_id": "PAC-1", "cantidad": 2}
        self.assertTrue(self.repo.iniciar("TX-1", payload))
        self.assertFalse(self.repo.iniciar("TX-1", payload))
        fila = self.repo.obtener("TX-1")
        self.assertEqual(fila["estado"], "INICIADA")
        self.assertEqual(fila["payload"], payload)

    def test_actualizar_cambia_estado_y_pasos(self):
        self.repo.iniciar("TX-2", {"cantidad": 1})
        self.repo.actualizar("TX-2", "COMPLETADA", ["stock", "receta"])
        fila = self.repo.obtener("TX-2")
        self.assertEqual(fila["estado"], "COMPLETADA")
        self.assertEqual(fila["pasos_confirmados"], ["stock", "receta"])


if __name__ == "__main__":
    unittest.main()
