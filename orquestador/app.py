"""API del Orquestador de la Saga."""

import logging
import os
import uuid

from flask import Flask, jsonify, request

from bd import SqliteRepo
from clientes import RealClientes
from saga import ejecutar_saga, reanudar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("orquestador")

app = Flask(__name__)
PUERTO = int(os.getenv("ORQUESTADOR_PORT", "8104"))

_repo = None
_clientes = None


def repo():
    global _repo
    if _repo is None:
        _repo = SqliteRepo()
    return _repo


def clientes():
    global _clientes
    if _clientes is None:
        _clientes = RealClientes()
    return _clientes


def error(status: int, title: str, detail: str):
    return jsonify({
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }), status


@app.post("/despachar")
def despachar():
    data = request.get_json(silent=True) or {}
    for campo in ("paciente_id", "codigo_medicamento", "cantidad"):
        if campo not in data:
            return error(400, "Solicitud inválida", f"falta el campo {campo}")
    try:
        cantidad = int(data["cantidad"])
        if cantidad < 1:
            raise ValueError
    except (TypeError, ValueError):
        return error(400, "Solicitud inválida", "cantidad debe ser un entero >= 1")

    payload = {
        "id_dispensacion": data.get("id_dispensacion") or str(uuid.uuid4()),
        "paciente_id": data["paciente_id"],
        "codigo_medicamento": data["codigo_medicamento"],
        "cantidad": cantidad,
    }
    logger.info("Iniciando Saga tx=%s", payload["id_dispensacion"])
    try:
        resultado = ejecutar_saga(payload, clientes=clientes(), repo=repo())
    except Exception as exc:
        logger.error("No se pudo ejecutar la Saga tx=%s: %s", payload["id_dispensacion"], exc)
        return error(503, "Dependencia no disponible", str(exc))
    logger.info("Saga tx=%s terminó en %s", payload["id_dispensacion"], resultado["estado"])
    status = 409 if resultado["estado"] == "FALLIDA" else 201
    return jsonify(resultado), status


@app.get("/estado/<id_dispensacion>")
def estado(id_dispensacion):
    fila = repo().obtener(id_dispensacion)
    if fila is None:
        return error(404, "No encontrado", f"no existe la Saga {id_dispensacion}")
    return jsonify({
        "id_dispensacion": fila["id_dispensacion"],
        "estado": fila["estado"],
        "pasos_confirmados": fila["pasos_confirmados"],
        "payload": fila["payload"],
    }), 200


@app.post("/reanudar/<id_dispensacion>")
def reanudar_endpoint(id_dispensacion):
    fila = repo().obtener(id_dispensacion)
    if fila is None:
        return error(404, "No encontrado", f"no existe la Saga {id_dispensacion}")
    try:
        resultado = reanudar(id_dispensacion, clientes=clientes(), repo=repo())
    except Exception as exc:
        logger.error("No se pudo reanudar la Saga tx=%s: %s", id_dispensacion, exc)
        return error(503, "Dependencia no disponible", str(exc))
    if resultado["estado"] == "NO_REANUDABLE":
        return error(409, "Conflicto", f"la Saga {id_dispensacion} no está en estado reanudable")
    return jsonify(resultado), 200


@app.get("/salud")
def salud():
    return jsonify({"servicio": "orquestador", "ok": True}), 200


@app.get("/admin/resiliencia")
def admin_resiliencia():
    return jsonify(clientes().instantanea_resiliencia()), 200


@app.post("/admin/resiliencia/reset")
def admin_resiliencia_reset():
    clientes().reiniciar_resiliencia()
    logger.info("Contadores y circuito de resiliencia reiniciados")
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    repo()
    logger.info("Iniciando Orquestador en el puerto %s", PUERTO)
    app.run(host="0.0.0.0", port=PUERTO)
