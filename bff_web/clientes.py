"""Adaptadores del BFF hacia orquestador, Stock, Despacho y Receta."""


class ClientesBFF:
    def __init__(self):
        # Importaciones diferidas para no exigir grpcio en el host de tests.
        import grpc
        import requests
        import stock_pb2
        import stock_pb2_grpc

        self.requests = requests
        self.pb2 = stock_pb2
        self.channel = grpc.insecure_channel("servicio-stock:8101")
        grpc.channel_ready_future(self.channel).result(timeout=3)
        self.stock = stock_pb2_grpc.StockStub(self.channel)

    def saga(self, id_dispensacion: str) -> dict:
        return self._get(f"http://orquestador:8104/estado/{id_dispensacion}")

    def despacho(self, id_dispensacion: str) -> dict:
        return self._get(f"http://servicio-despacho:8102/estado/{id_dispensacion}")

    def validacion(self, id_dispensacion: str) -> dict:
        historial = self._get("http://servicio-receta:8103/estado")
        registros = historial.get("log", []) if isinstance(historial, dict) else []
        for registro in registros:
            if registro.get("id_dispensacion") == id_dispensacion:
                return registro
        return {"estado": "SIN_REGISTRO"}

    def medicamento(self, codigo: str) -> dict:
        respuesta = self.stock.Consultar(
            self.pb2.ConsultarRequest(codigo_medicamento=codigo), timeout=3
        )
        return {
            "codigo_medicamento": respuesta.codigo_medicamento,
            "nombre": respuesta.nombre,
            "unidades_disponibles": respuesta.unidades_disponibles,
            "disponible": respuesta.disponible,
        }

    def enviar_despacho(self, payload: dict):
        respuesta = self.requests.post(
            "http://orquestador:8104/despachar", json=payload, timeout=3
        )
        return respuesta.status_code, respuesta.json()

    def _get(self, url: str):
        respuesta = self.requests.get(url, timeout=3)
        return respuesta.json()
