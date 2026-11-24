"""BFF web: agrega datos de la Saga, Stock, Despacho y Receta."""

import logging
import os

from flask import Flask, jsonify, request

from agregacion import armar_respuesta
from clientes import ClientesBFF

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bff_web")

app = Flask(__name__)
PUERTO = int(os.getenv("BFF_PORT", "8090"))
_clientes = None


def clientes():
    global _clientes
    if _clientes is None:
        _clientes = ClientesBFF()
    return _clientes


def error(status: int, title: str, detail: str):
    return jsonify({
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }), status


@app.post("/dispensaciones")
def crear_dispensacion():
    payload = request.get_json(silent=True) or {}
    if not payload:
        return error(400, "Solicitud inválida", "se espera un cuerpo JSON")
    try:
        estado, respuesta = clientes().enviar_despacho(payload)
    except Exception as exc:
        logger.error("Error al llamar al orquestador: %s", exc)
        return error(503, "Orquestador no disponible", str(exc))
    return jsonify(respuesta), estado


@app.get("/dispensaciones/<id_dispensacion>")
def obtener_dispensacion(id_dispensacion):
    respuesta = armar_respuesta(id_dispensacion, clientes=clientes())
    if isinstance(respuesta["saga"], dict) and respuesta["saga"].get("status") == 404:
        return error(404, "No encontrado", f"no existe la Saga {id_dispensacion}")
    return jsonify(respuesta), 200


@app.get("/salud")
def salud():
    return jsonify({"servicio": "bff-web", "ok": True}), 200


if __name__ == "__main__":
    logger.info("Iniciando BFF web en el puerto %s", PUERTO)
    app.run(host="0.0.0.0", port=PUERTO)
