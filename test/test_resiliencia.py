import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from orquestador.resiliencia import Bulkhead, CircuitBreaker, Metricas


CLAVES_METRICAS = {
    "llamadas",
    "exitos",
    "fallos",
    "timeouts",
    "rechazos_bulkhead",
    "fallbacks",
    "aperturas",
}


class RelojFalso:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class TestMetricas(unittest.TestCase):
    def test_contadores_empiezan_en_cero_y_devuelven_copia(self):
        metricas = Metricas()
        self.assertEqual(set(metricas.instantanea()), CLAVES_METRICAS)
        self.assertTrue(all(valor == 0 for valor in metricas.instantanea().values()))

        metricas.incrementar("llamadas")
        instantanea = metricas.instantanea()
        instantanea["llamadas"] = 99
        self.assertEqual(metricas.instantanea()["llamadas"], 1)

        metricas.reiniciar()
        self.assertTrue(all(valor == 0 for valor in metricas.instantanea().values()))


class TestBulkhead(unittest.TestCase):
    def test_limita_concurrencia_y_libera_permiso(self):
        bulkhead = Bulkhead(limite=2)
        self.assertTrue(bulkhead.adquirir())
        self.assertTrue(bulkhead.adquirir())
        self.assertFalse(bulkhead.adquirir())
        self.assertEqual(bulkhead.instantanea(), {"limite": 2, "en_vuelo": 2})

        bulkhead.liberar()
        self.assertTrue(bulkhead.adquirir())
        self.assertEqual(bulkhead.instantanea()["en_vuelo"], 2)

    def test_reiniciar_y_liberar_no_bajan_de_cero(self):
        bulkhead = Bulkhead(limite=1)
        bulkhead.adquirir()
        bulkhead.reiniciar()
        self.assertEqual(bulkhead.instantanea()["en_vuelo"], 0)
        bulkhead.liberar()
        self.assertEqual(bulkhead.instantanea()["en_vuelo"], 0)


class TestCircuitBreaker(unittest.TestCase):
    def test_se_abre_tras_tres_fallos_y_bloquea_nuevas_llamadas(self):
        reloj = RelojFalso()
        circuito = CircuitBreaker(umbral=3, enfriamiento=5.0, reloj=reloj)

        circuito.fallo()
        circuito.fallo()
        self.assertEqual(circuito.estado(), "CERRADO")
        circuito.fallo()
        self.assertEqual(circuito.estado(), "ABIERTO")
        self.assertFalse(circuito.permitir())

        instantanea = circuito.instantanea()
        self.assertEqual(instantanea["estado"], "ABIERTO")
        self.assertEqual(instantanea["fallos"], 3)
        self.assertEqual(instantanea["enfriamiento"], 5.0)
        self.assertGreaterEqual(instantanea["abierto_hace"], 0.0)

    def test_medio_abierto_solo_permite_una_sonda_y_exito_cierra(self):
        reloj = RelojFalso()
        circuito = CircuitBreaker(umbral=3, enfriamiento=5.0, reloj=reloj)
        for _ in range(3):
            circuito.fallo()

        reloj.t += 5.1
        self.assertEqual(circuito.estado(), "MEDIO_ABIERTO")
        self.assertTrue(circuito.permitir())
        self.assertFalse(circuito.permitir())

        circuito.exito()
        self.assertEqual(circuito.estado(), "CERRADO")
        self.assertEqual(circuito.instantanea()["fallos"], 0)

    def test_fallo_en_medio_abierto_reabre_y_cancelar_libera_la_sonda(self):
        reloj = RelojFalso()
        circuito = CircuitBreaker(umbral=3, enfriamiento=5.0, reloj=reloj)
        for _ in range(3):
            circuito.fallo()

        reloj.t += 5.1
        self.assertEqual(circuito.estado(), "MEDIO_ABIERTO")
        self.assertTrue(circuito.permitir())
        circuito.cancelar()
        self.assertTrue(circuito.permitir())
        circuito.fallo()
        self.assertEqual(circuito.estado(), "ABIERTO")

    def test_reiniciar_vuelve_a_cerrado(self):
        circuito = CircuitBreaker(umbral=1)
        circuito.fallo()
        self.assertEqual(circuito.estado(), "ABIERTO")
        circuito.reiniciar()
        self.assertEqual(circuito.estado(), "CERRADO")
        self.assertEqual(circuito.instantanea()["fallos"], 0)


if __name__ == "__main__":
    unittest.main()
