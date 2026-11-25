import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from orquestador import clientes as modulo_clientes
from orquestador.resiliencia import Bulkhead, CircuitBreaker, Metricas


class Req:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeRpcError(Exception):
    pass


class FakeStub:
    def __init__(self, channel):
        self.channel = channel

    def Reservar(self, request, timeout):
        raise FakeRpcError("stock caído")

    def Liberar(self, request, timeout):
        raise FakeRpcError("stock caído")


class FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeRequests:
    class RequestException(Exception):
        pass

    @staticmethod
    def post(url, json=None, timeout=None):
        return FakeResp(503)

    @staticmethod
    def get(url, timeout=None):
        if url.endswith("/err"):
            raise FakeRequests.RequestException("timeout")
        if url.endswith("/no"):
            return FakeResp(404)
        if url.endswith("/can"):
            return FakeResp(200, {"estado": "cancelado"})
        return FakeResp(200, {"estado": "creado"})


class TestRealClientes(unittest.TestCase):
    def setUp(self):
        self.nombres = ["grpc", "requests", "stock_pb2", "stock_pb2_grpc"]
        self.guardados = {nombre: sys.modules.get(nombre) for nombre in self.nombres}

        grpc = types.ModuleType("grpc")
        grpc.RpcError = FakeRpcError
        grpc.FutureTimeoutError = type("FutureTimeoutError", (Exception,), {})
        grpc.insecure_channel = lambda destino: object()
        grpc.channel_ready_future = lambda canal: types.SimpleNamespace(result=lambda timeout: True)

        pb2 = types.ModuleType("stock_pb2")
        pb2.ReservarRequest = Req
        pb2.LiberarRequest = Req
        pb2.ConsultarRequest = Req

        pb2_grpc = types.ModuleType("stock_pb2_grpc")
        pb2_grpc.StockStub = FakeStub

        sys.modules["grpc"] = grpc
        sys.modules["requests"] = FakeRequests
        sys.modules["stock_pb2"] = pb2
        sys.modules["stock_pb2_grpc"] = pb2_grpc

    def tearDown(self):
        for nombre in self.nombres:
            if self.guardados[nombre] is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = self.guardados[nombre]

    def test_reserva_con_rpc_error_marca_error_y_no_exito(self):
        cliente = modulo_clientes.RealClientes()
        resultado = cliente.reservar_stock("TX-1", "MED-1", 2)
        self.assertFalse(resultado["exito"])
        self.assertTrue(resultado["error"])

    def test_estado_despacho_distingue_no_existe_cancelado_y_indeterminado(self):
        cliente = modulo_clientes.RealClientes()
        self.assertIs(cliente.estado_despacho("no"), False)
        self.assertIs(cliente.estado_despacho("can"), False)
        self.assertTrue(cliente.estado_despacho("ok"))
        self.assertIsNone(cliente.estado_despacho("err"))


class FakeRequestsResiliencia:
    """Requests configurable para probar CB, bulkhead y timeouts sin red."""

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    def __init__(self):
        self.llamadas = 0
        self.respuestas = []
        self.excepciones = []

    def post(self, url, json=None, timeout=None):
        self.llamadas += 1
        if self.excepciones:
            raise self.excepciones.pop(0)
        if self.respuestas:
            estado, payload = self.respuestas.pop(0)
            return FakeResp(estado, payload)
        return FakeResp(200, {"ok": True})


class TestResilienciaEnClientes(unittest.TestCase):
    def setUp(self):
        self.nombres = ["grpc", "requests", "stock_pb2", "stock_pb2_grpc"]
        self.guardados = {nombre: sys.modules.get(nombre) for nombre in self.nombres}

        grpc = types.ModuleType("grpc")
        grpc.RpcError = FakeRpcError
        grpc.FutureTimeoutError = type("FutureTimeoutError", (Exception,), {})
        grpc.insecure_channel = lambda destino: object()
        grpc.channel_ready_future = lambda canal: types.SimpleNamespace(result=lambda timeout: True)

        pb2 = types.ModuleType("stock_pb2")
        pb2.ReservarRequest = Req
        pb2.LiberarRequest = Req
        pb2.ConsultarRequest = Req

        pb2_grpc = types.ModuleType("stock_pb2_grpc")
        pb2_grpc.StockStub = FakeStub

        self.fake_requests = FakeRequestsResiliencia()
        sys.modules["grpc"] = grpc
        sys.modules["requests"] = self.fake_requests
        sys.modules["stock_pb2"] = pb2
        sys.modules["stock_pb2_grpc"] = pb2_grpc

    def tearDown(self):
        for nombre in self.nombres:
            if self.guardados[nombre] is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = self.guardados[nombre]

    def test_validar_receta_ok_contabiliza_llamada_y_exito(self):
        self.fake_requests.respuestas.append((200, {"ok": True}))
        cliente = modulo_clientes.RealClientes()

        self.assertEqual(cliente.validar_receta("TX-OK"), "ok")
        self.assertEqual(self.fake_requests.llamadas, 1)
        metricas = cliente.instantanea_resiliencia()["receta"]["metricas"]
        self.assertEqual(metricas["llamadas"], 1)
        self.assertEqual(metricas["exitos"], 1)

    def test_tres_fallos_abren_circuito_y_evitan_nuevas_llamadas(self):
        self.fake_requests.respuestas.extend([(500, {}), (500, {}), (500, {})])
        cliente = modulo_clientes.RealClientes()

        for _ in range(3):
            self.assertEqual(cliente.validar_receta("TX-CB"), "pendiente")
        self.assertEqual(cliente.circuito.estado(), "ABIERTO")
        self.assertEqual(self.fake_requests.llamadas, 3)

        self.assertEqual(cliente.validar_receta("TX-CB-2"), "pendiente")
        self.assertEqual(self.fake_requests.llamadas, 3)

        metricas = cliente.instantanea_resiliencia()["receta"]["metricas"]
        self.assertEqual(metricas["aperturas"], 1)
        self.assertGreaterEqual(metricas["fallbacks"], 4)
        self.assertEqual(metricas["timeouts"], 0)

    def test_bulkhead_lleno_hace_fallback_sin_llamar_a_receta(self):
        bulkhead = Bulkhead(limite=1)
        bulkhead.adquirir()
        metricas = Metricas()
        cliente = modulo_clientes.RealClientes(
            circuito=CircuitBreaker(), bulkhead=bulkhead, metricas=metricas
        )

        self.assertEqual(cliente.validar_receta("TX-BH"), "pendiente")
        self.assertEqual(self.fake_requests.llamadas, 0)
        self.assertEqual(metricas.instantanea()["rechazos_bulkhead"], 1)
        self.assertEqual(metricas.instantanea()["fallbacks"], 1)
        self.assertEqual(cliente.circuito.estado(), "CERRADO")

    def test_timeout_de_receta_se_contabiliza_y_degrada(self):
        self.fake_requests.excepciones.append(self.fake_requests.Timeout("lento"))
        cliente = modulo_clientes.RealClientes()

        self.assertEqual(cliente.validar_receta("TX-TO"), "pendiente")
        metricas = cliente.instantanea_resiliencia()["receta"]["metricas"]
        self.assertEqual(metricas["timeouts"], 1)
        self.assertEqual(metricas["fallos"], 1)
        self.assertEqual(metricas["fallbacks"], 1)

    def test_instantanea_y_reinicio_del_circuito(self):
        cliente = modulo_clientes.RealClientes()
        self.assertEqual(
            set(cliente.instantanea_resiliencia()),
            {"receta"},
        )
        cliente.metricas.incrementar("llamadas")
        cliente.circuito.fallo()

        cliente.reiniciar_resiliencia()
        snapshot = cliente.instantanea_resiliencia()["receta"]
        self.assertEqual(snapshot["circuito"]["estado"], "CERRADO")
        self.assertTrue(all(v == 0 for v in snapshot["metricas"].values()))
        self.assertEqual(snapshot["bulkhead"]["en_vuelo"], 0)


if __name__ == "__main__":
    unittest.main()
