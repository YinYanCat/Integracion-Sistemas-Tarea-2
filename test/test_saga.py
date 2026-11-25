import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from orquestador.saga import ejecutar_saga, reanudar


PAYLOAD = {
    "id_dispensacion": "TX-1",
    "paciente_id": "PAC-1",
    "codigo_medicamento": "MED-1",
    "cantidad": 2,
}


class FakeRepo:
    def __init__(self):
        self.datos = {}

    def iniciar(self, id_dispensacion, payload):
        if id_dispensacion in self.datos:
            return False
        self.datos[id_dispensacion] = {
            "id_dispensacion": id_dispensacion,
            "estado": "INICIADA",
            "payload": payload,
            "pasos_confirmados": [],
        }
        return True

    def obtener(self, id_dispensacion):
        return self.datos.get(id_dispensacion)

    def actualizar(self, id_dispensacion, estado, pasos_confirmados=None):
        self.datos[id_dispensacion]["estado"] = estado
        if pasos_confirmados is not None:
            self.datos[id_dispensacion]["pasos_confirmados"] = pasos_confirmados


class FakeClientes:
    def __init__(self, receta="ok", despacho_crea=True, despacho_existe=False,
                 stock_exito=True, stock_error=False, liberar_exito=True):
        self.receta = receta
        self.despacho_crea = despacho_crea
        self.despacho_existe = despacho_existe
        self.stock_exito = stock_exito
        self.stock_error = stock_error
        self.liberar_exito = liberar_exito
        self.reservas = 0
        self.liberaciones = 0
        self.despacho_llamadas = 0

    def reservar_stock(self, id_dispensacion, codigo, cantidad):
        self.reservas += 1
        return {
            "exito": self.stock_exito,
            "unidades": 48,
            "mensaje": "ok",
            "error": self.stock_error,
        }

    def liberar_stock(self, id_dispensacion, codigo, cantidad):
        self.liberaciones += 1
        return {"exito": self.liberar_exito, "unidades": 50, "mensaje": "ok"}

    def validar_receta(self, id_dispensacion):
        return self.receta

    def crear_despacho(self, payload):
        self.despacho_llamadas += 1
        return self.despacho_crea

    def estado_despacho(self, id_dispensacion):
        return self.despacho_existe


class TestSaga(unittest.TestCase):
    def test_camino_feliz(self):
        repo, clientes = FakeRepo(), FakeClientes()
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "COMPLETADA")
        self.assertEqual(resultado["pasos_confirmados"], ["stock", "receta", "despacho"])
        self.assertEqual(clientes.reservas, 1)

    def test_receta_timeout_queda_pendiente(self):
        repo, clientes = FakeRepo(), FakeClientes(receta="pendiente")
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "PENDIENTE")
        self.assertEqual(resultado["pasos_confirmados"], ["stock"])
        self.assertEqual(clientes.despacho_llamadas, 0)
        self.assertEqual(clientes.liberaciones, 0)

    def test_fallo_despacho_compensa(self):
        repo, clientes = FakeRepo(), FakeClientes(despacho_crea=False)
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "COMPENSADA")
        self.assertEqual(resultado["pasos_confirmados"], ["stock", "receta"])
        self.assertEqual(clientes.liberaciones, 1)

    def test_timeout_despacho_pero_creado_no_compensa(self):
        repo, clientes = FakeRepo(), FakeClientes()
        clientes.despacho_crea = False
        clientes.despacho_existe = True
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "COMPLETADA")
        self.assertEqual(clientes.liberaciones, 0)
        self.assertIn("despacho", resultado["pasos_confirmados"])

    def test_stock_insuficiente_falla_sin_despacho(self):
        repo, clientes = FakeRepo(), FakeClientes(stock_exito=False)
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "FALLIDA")
        self.assertEqual(resultado["pasos_confirmados"], [])
        self.assertEqual(clientes.despacho_llamadas, 0)
        self.assertEqual(clientes.liberaciones, 0)

    def test_replay_mismo_id_estado_terminal(self):
        repo, clientes = FakeRepo(), FakeClientes()
        primero = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        segundo = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(segundo["estado"], primero["estado"])
        self.assertEqual(clientes.reservas, 1)
        self.assertEqual(clientes.despacho_llamadas, 1)

    def test_reanudar_no_reserva_dos_veces(self):
        repo, clientes = FakeRepo(), FakeClientes(receta="pendiente")
        ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        clientes.receta = "ok"
        resultado = reanudar("TX-1", clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "COMPLETADA")
        self.assertEqual(clientes.reservas, 1)
        self.assertEqual(clientes.despacho_llamadas, 1)

    def test_timeout_despacho_estado_indeterminado_queda_pendiente(self):
        repo, clientes = FakeRepo(), FakeClientes(despacho_crea=False, despacho_existe=None)
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "PENDIENTE")
        self.assertEqual(resultado["pasos_confirmados"], ["stock", "receta"])
        self.assertEqual(clientes.liberaciones, 0)

    def test_fallo_compensacion_queda_pendiente_de_compensacion_y_reanuda(self):
        repo, clientes = FakeRepo(), FakeClientes(despacho_crea=False, liberar_exito=False)
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "COMPENSACION_PENDIENTE")
        self.assertEqual(clientes.liberaciones, 1)

        clientes.liberar_exito = True
        reanudado = reanudar("TX-1", clientes=clientes, repo=repo)
        self.assertEqual(reanudado["estado"], "COMPENSADA")
        self.assertEqual(clientes.liberaciones, 2)

    def test_reserva_error_queda_pendiente_y_reanuda_reservando(self):
        repo, clientes = FakeRepo(), FakeClientes(stock_error=True)
        resultado = ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "PENDIENTE")
        self.assertEqual(resultado["pasos_confirmados"], [])

        clientes.stock_error = False
        reanudado = reanudar("TX-1", clientes=clientes, repo=repo)
        self.assertEqual(reanudado["estado"], "COMPLETADA")
        self.assertEqual(clientes.reservas, 2)

    def test_reanudar_estado_terminal_no_reanuda(self):
        repo, clientes = FakeRepo(), FakeClientes()
        ejecutar_saga(PAYLOAD, clientes=clientes, repo=repo)
        resultado = reanudar("TX-1", clientes=clientes, repo=repo)
        self.assertEqual(resultado["estado"], "NO_REANUDABLE")
        self.assertEqual(clientes.reservas, 1)
        self.assertEqual(clientes.despacho_llamadas, 1)


if __name__ == "__main__":
    unittest.main()
