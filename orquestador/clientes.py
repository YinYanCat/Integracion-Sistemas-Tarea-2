"""Adaptadores reales del orquestador hacia Stock, Receta y Despacho."""

import logging

try:  # importado como paquete desde los tests
    from .resiliencia import Bulkhead, CircuitBreaker, Metricas
except ImportError:  # importado como módulo top-level dentro del contenedor
    from resiliencia import Bulkhead, CircuitBreaker, Metricas

logger = logging.getLogger("resiliencia")


class RealClientes:
    def __init__(self, *, circuito=None, bulkhead=None, metricas=None):
        self.metricas = metricas or Metricas()
        self.circuito = circuito or CircuitBreaker()
        self.bulkhead = bulkhead or Bulkhead()
        # Importaciones diferidas: el host de tests no tiene grpcio ni los stubs generados.
        import grpc
        import requests
        import stock_pb2
        import stock_pb2_grpc

        self.grpc = grpc
        self.requests = requests
        self.pb2 = stock_pb2
        self.channel = grpc.insecure_channel("servicio-stock:8101")
        try:
            grpc.channel_ready_future(self.channel).result(timeout=3)
        except grpc.FutureTimeoutError as exc:
            raise RuntimeError("Stock gRPC no disponible en 3s") from exc
        self.stub = stock_pb2_grpc.StockStub(self.channel)

    def reservar_stock(self, id_dispensacion: str, codigo: str, cantidad: int) -> dict:
        return self._movimiento_stock(
            "Reservar", "reserva", id_dispensacion, codigo, cantidad
        )

    def liberar_stock(self, id_dispensacion: str, codigo: str, cantidad: int) -> dict:
        return self._movimiento_stock(
            "Liberar", "liberacion", id_dispensacion, codigo, cantidad
        )

    def _movimiento_stock(self, rpc: str, tipo: str, id_dispensacion: str,
                          codigo: str, cantidad: int) -> dict:
        request_cls = (
            self.pb2.ReservarRequest if rpc == "Reservar" else self.pb2.LiberarRequest
        )
        try:
            respuesta = getattr(self.stub, rpc)(
                request_cls(
                    codigo_medicamento=codigo,
                    cantidad=cantidad,
                    id_dispensacion=id_dispensacion,
                ),
                timeout=3,
            )
            return {
                "exito": respuesta.exito,
                "unidades": respuesta.unidades_resultantes,
                "mensaje": respuesta.mensaje,
            }
        except self.grpc.RpcError as exc:
            return {
                "exito": False,
                "unidades": 0,
                "mensaje": str(exc),
                "error": True,
            }

    def _registrar_fallo(self, tx, motivo, estado_antes, es_timeout=False):
        if es_timeout:
            self.metricas.incrementar("timeouts")
        self.metricas.incrementar("fallos")
        self.metricas.incrementar("fallbacks")
        self.circuito.fallo()
        if estado_antes != "ABIERTO" and self.circuito.estado() == "ABIERTO":
            self.metricas.incrementar("aperturas")
        logger.warning(
            "Resiliencia tx=%s: fallback (%s), circuito=%s",
            tx, motivo, self.circuito.estado(),
        )
        return "pendiente"

    def validar_receta(self, id_dispensacion: str) -> str:
        estado_antes = self.circuito.estado()
        if not self.circuito.permitir():
            motivo = (
                "circuito_abierto"
                if self.circuito.estado() == "ABIERTO"
                else "sonda_en_vuelo"
            )
            self.metricas.incrementar("fallbacks")
            logger.warning(
                "Resiliencia tx=%s: fallback (%s), circuito=%s",
                id_dispensacion, motivo, self.circuito.estado(),
            )
            return "pendiente"

        if not self.bulkhead.adquirir():
            self.circuito.cancelar()
            self.metricas.incrementar("rechazos_bulkhead")
            self.metricas.incrementar("fallbacks")
            logger.warning(
                "Resiliencia tx=%s: fallback (bulkhead lleno), circuito=%s, en_vuelo=%s",
                id_dispensacion,
                self.circuito.estado(),
                self.bulkhead.instantanea()["en_vuelo"],
            )
            return "pendiente"

        self.metricas.incrementar("llamadas")
        try:
            try:
                respuesta = self.requests.post(
                    "http://servicio-receta:8103/ejecutar",
                    json={"id_dispensacion": id_dispensacion},
                    timeout=2,
                )
            except self.requests.RequestException as exc:
                timeout_cls = getattr(self.requests, "Timeout", ())
                return self._registrar_fallo(
                    id_dispensacion,
                    str(exc),
                    estado_antes,
                    es_timeout=isinstance(exc, timeout_cls),
                )

            try:
                valida = (
                    respuesta.status_code == 200
                    and respuesta.json().get("ok") is True
                )
            except (ValueError, AttributeError):
                valida = False

            if valida:
                self.metricas.incrementar("exitos")
                self.circuito.exito()
                logger.info(
                    "Resiliencia tx=%s: receta validada, circuito=%s",
                    id_dispensacion, self.circuito.estado(),
                )
                return "ok"

            return self._registrar_fallo(
                id_dispensacion,
                f"respuesta inválida status={respuesta.status_code}",
                estado_antes,
            )
        finally:
            self.bulkhead.liberar()

    def instantanea_resiliencia(self) -> dict:
        return {
            "receta": {
                "circuito": self.circuito.instantanea(),
                "bulkhead": self.bulkhead.instantanea(),
                "metricas": self.metricas.instantanea(),
            }
        }

    def reiniciar_resiliencia(self) -> None:
        self.circuito.reiniciar()
        self.bulkhead.reiniciar()
        self.metricas.reiniciar()

    def crear_despacho(self, payload: dict) -> bool:
        try:
            respuesta = self.requests.post(
                "http://servicio-despacho:8102/crear",
                json={
                    "id_dispensacion": payload["id_dispensacion"],
                    "paciente_id": payload["paciente_id"],
                    "codigo_medicamento": payload["codigo_medicamento"],
                    "cantidad": payload["cantidad"],
                },
                timeout=2,
            )
            return respuesta.status_code in (200, 201)
        except self.requests.RequestException:
            return False

    def estado_despacho(self, id_dispensacion: str):
        try:
            respuesta = self.requests.get(
                f"http://servicio-despacho:8102/estado/{id_dispensacion}",
                timeout=2,
            )
        except self.requests.RequestException:
            return None
        if respuesta.status_code == 404:
            return False
        if respuesta.status_code != 200:
            return None
        return respuesta.json().get("estado") != "cancelado"
