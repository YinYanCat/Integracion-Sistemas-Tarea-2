import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from gateway.limitador import Limitador


class TestLimitador(unittest.TestCase):
    def test_limitador_bloquea_exceso(self):
        limite = Limitador(limite=2, ventana=10)
        self.assertTrue(limite.permitir("IP-1", ahora=0))
        self.assertTrue(limite.permitir("IP-1", ahora=1))
        self.assertFalse(limite.permitir("IP-1", ahora=2))
        self.assertTrue(limite.permitir("IP-1", ahora=11))

    def test_limitador_es_por_cliente(self):
        limite = Limitador(limite=1, ventana=10)
        self.assertTrue(limite.permitir("IP-1", ahora=0))
        self.assertTrue(limite.permitir("IP-2", ahora=0))
        self.assertFalse(limite.permitir("IP-1", ahora=1))

    def test_limitador_concurrente_no_supera_el_limite(self):
        limite = Limitador(limite=5, ventana=10)
        permitidos = []
        cerrojo = threading.Lock()

        def intentar():
            if limite.permitir("IP-1"):
                with cerrojo:
                    permitidos.append(1)

        hilos = [threading.Thread(target=intentar) for _ in range(20)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(len(permitidos), 5)


if __name__ == "__main__":
    unittest.main()
