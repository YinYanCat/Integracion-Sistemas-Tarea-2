import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bff_web.agregacion import armar_respuesta


class FakeClientesBFF:
    def saga(self, id_dispensacion):
        return {"estado": "COMPLETADA", "pasos_confirmados": ["stock", "receta", "despacho"]}

    def medicamento(self, codigo):
        return {"codigo_medicamento": codigo, "unidades_disponibles": 48}

    def despacho(self, id_dispensacion):
        return {"estado": "creado", "codigo_medicamento": "MED-1"}

    def validacion(self, id_dispensacion):
        return {"estado": "VALIDADA"}


class TestAgregacion(unittest.TestCase):
    def test_armar_respuesta_agrega_cuatro_servicios(self):
        respuesta = armar_respuesta("TX-1", clientes=FakeClientesBFF())
        self.assertEqual(
            set(respuesta),
            {"saga", "medicamento", "despacho", "validacion_receta"},
        )
        self.assertEqual(respuesta["saga"]["estado"], "COMPLETADA")
        self.assertEqual(respuesta["medicamento"]["unidades_disponibles"], 48)
        self.assertEqual(respuesta["despacho"]["estado"], "creado")
        self.assertEqual(respuesta["validacion_receta"]["estado"], "VALIDADA")

    def test_fallo_de_una_dependencia_no_tumba_la_respuesta(self):
        class Parcial(FakeClientesBFF):
            def despacho(self, id_dispensacion):
                raise RuntimeError("despacho caído")

        respuesta = armar_respuesta("TX-1", clientes=Parcial())
        self.assertIn("error", respuesta["despacho"])
        self.assertEqual(respuesta["saga"]["estado"], "COMPLETADA")

    def test_pendiente_usa_payload_de_la_saga_sin_despacho(self):
        class Pendiente(FakeClientesBFF):
            codigo_visto = None

            def saga(self, id_dispensacion):
                return {
                    "estado": "PENDIENTE",
                    "pasos_confirmados": ["stock"],
                    "payload": {"codigo_medicamento": "MED-2"},
                }

            def despacho(self, id_dispensacion):
                return {"status": 404}

            def medicamento(self, codigo):
                self.codigo_visto = codigo
                return {"codigo_medicamento": codigo, "unidades_disponibles": 10}

        clientes = Pendiente()
        respuesta = armar_respuesta("TX-1", clientes=clientes)
        self.assertEqual(clientes.codigo_visto, "MED-2")
        self.assertEqual(respuesta["medicamento"]["codigo_medicamento"], "MED-2")


if __name__ == "__main__":
    unittest.main()
