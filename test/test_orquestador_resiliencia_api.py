import os
import sys
import types
import unittest

RAIZ = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "orquestador"))


class RespuestaFalsa:
    def __init__(self, datos, status_code):
        self._datos = datos
        self.status_code = status_code

    def get_json(self):
        return self._datos


class ClienteFalso:
    def __init__(self, rutas):
        self._rutas = rutas

    def get(self, ruta):
        return self._llamar("GET", ruta)

    def post(self, ruta):
        return self._llamar("POST", ruta)

    def _llamar(self, metodo, ruta):
        funcion = self._rutas.get((metodo, ruta))
        if funcion is None:
            return RespuestaFalsa({"detail": "not found"}, 404)
        valor = funcion()
        if isinstance(valor, tuple):
            datos, status = valor
        else:
            datos, status = valor, 200
        if isinstance(datos, dict) and set(datos) == {"__json__"}:
            datos = datos["__json__"]
        return RespuestaFalsa(datos, status)


class FlaskFalso:
    def __init__(self, *args, **kwargs):
        self._rutas = {}

    def _registrar(self, metodo, ruta):
        def decorador(funcion):
            self._rutas[(metodo, ruta)] = funcion
            return funcion
        return decorador

    def get(self, ruta):
        return self._registrar("GET", ruta)

    def post(self, ruta):
        return self._registrar("POST", ruta)

    def test_client(self):
        return ClienteFalso(self._rutas)


def jsonify(datos=None, **kwargs):
    return {"__json__": datos if datos is not None else kwargs}


# El host de tests no instala Flask; se inyecta el doble solo durante el import.
_guardado_flask = sys.modules.get("flask")
_modulo_flask = types.ModuleType("flask")
_modulo_flask.Flask = FlaskFalso
_modulo_flask.jsonify = jsonify
_modulo_flask.request = types.SimpleNamespace(path="")
sys.modules["flask"] = _modulo_flask
try:
    import app as modulo_app  # noqa: E402
finally:
    if _guardado_flask is None:
        sys.modules.pop("flask", None)
    else:
        sys.modules["flask"] = _guardado_flask


CLAVES_METRICAS = {
    "llamadas",
    "exitos",
    "fallos",
    "timeouts",
    "rechazos_bulkhead",
    "fallbacks",
    "aperturas",
}


class FakeClientesResiliencia:
    def __init__(self):
        self.reinicios = 0

    def instantanea_resiliencia(self):
        return {
            "receta": {
                "circuito": {"estado": "CERRADO", "fallos": 0},
                "bulkhead": {"limite": 4, "en_vuelo": 0},
                "metricas": {clave: 0 for clave in CLAVES_METRICAS},
            }
        }

    def reiniciar_resiliencia(self):
        self.reinicios += 1


class TestOrquestadorResilienciaApi(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClientesResiliencia()
        self.guardado = modulo_app._clientes
        modulo_app._clientes = self.fake
        self.cliente = modulo_app.app.test_client()

    def tearDown(self):
        modulo_app._clientes = self.guardado

    def test_get_admin_resiliencia_devuelve_estado_y_contadores(self):
        respuesta = self.cliente.get("/admin/resiliencia")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos["receta"]["circuito"]["estado"], "CERRADO")
        self.assertEqual(datos["receta"]["bulkhead"]["limite"], 4)
        self.assertEqual(set(datos["receta"]["metricas"]), CLAVES_METRICAS)

    def test_post_reset_reinicia_la_resiliencia(self):
        respuesta = self.cliente.post("/admin/resiliencia/reset")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.get_json()["ok"])
        self.assertEqual(self.fake.reinicios, 1)

    def test_salud_no_cambia(self):
        respuesta = self.cliente.get("/salud")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json(), {"servicio": "orquestador", "ok": True})


if __name__ == "__main__":
    unittest.main()
