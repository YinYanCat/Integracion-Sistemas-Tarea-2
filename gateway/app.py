"""API Gateway: autenticación central, rate limiting y enrutamiento."""

import logging
import os

from flask import Flask, Response, jsonify, request
from requests import request as http_request

from limitador import Limitador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gateway")

app = Flask(__name__)
PUERTO = int(os.getenv("PORT", "8080"))
TOKEN = os.getenv("TOKEN", "token123")
LIMITE = Limitador(int(os.getenv("RATE_LIMIT", "5")), int(os.getenv("RATE_WINDOW", "10")))

DESTINOS = {
    "dispensaciones": ("http://bff-web:8090", True),
    "admin/receta": ("http://servicio-receta:8103", False),
    "admin/despacho": ("http://servicio-despacho:8102", False),
}


def error(status: int, title: str, detail: str):
    return jsonify({
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }), status


@app.before_request
def puerta_de_entrada():
    if request.path == "/salud":
        return None
    if request.headers.get("X-API-Key") != TOKEN:
        return error(401, "No autenticado", "Falta o es inválido el header X-API-Key")
    if not LIMITE.permitir(request.remote_addr or "desconocido"):
        return error(429, "Demasiadas peticiones", "Se superó el límite de peticiones")
    return None


@app.route("/v1/<path:ruta>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def enrutar(ruta):
    for prefijo, (base, conservar_prefijo) in DESTINOS.items():
        if ruta == prefijo or ruta.startswith(prefijo + "/"):
            if conservar_prefijo:
                destino = f"{base}/{ruta}"
            else:
                sufijo = ruta[len(prefijo):].lstrip("/")
                destino = f"{base}/admin/{sufijo}"
            break
    else:
        return error(404, "No encontrado", f"no existe la ruta /v1/{ruta}")

    kwargs = {"timeout": 3, "params": request.args}
    if request.is_json:
        kwargs["json"] = request.get_json(silent=True)
    elif request.get_data():
        kwargs["data"] = request.get_data()

    try:
        respuesta = http_request(request.method, destino, **kwargs)
    except Exception as exc:
        logger.error("No se pudo enrutar %s → %s: %s", request.method, destino, exc)
        return error(503, "Servicio no disponible", str(exc))

    return Response(respuesta.content, status=respuesta.status_code, content_type=respuesta.headers.get("Content-Type", "application/json"))


@app.get("/salud")
def salud():
    return jsonify({"servicio": "gateway", "ok": True}), 200


if __name__ == "__main__":
    logger.info("Iniciando Gateway en el puerto %s", PUERTO)
    app.run(host="0.0.0.0", port=PUERTO)
