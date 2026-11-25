"""Servicio de Despacho: crea y cancela entregas, con fallo inducible."""

import logging
import os

from flask import Flask, jsonify, request

import bd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("despacho_service")

app = Flask(__name__)
PUERTO = int(os.getenv("DESPACHO_PORT", "8102"))
MODO_FALLA = os.environ.get("MODO_FALLA", "normal")


def error(status: int, title: str, detail: str):
    return jsonify({
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }), status


@app.post("/crear")
def crear():
    global MODO_FALLA
    data = request.get_json(silent=True) or {}
    for campo in ("id_dispensacion", "paciente_id", "codigo_medicamento", "cantidad"):
        if campo not in data:
            return error(400, "Solicitud inválida", f"falta el campo {campo}")

    id_dispensacion = data["id_dispensacion"]
    logger.info("Crear despacho tx=%s [Modo actual: %s]", id_dispensacion, MODO_FALLA)

    if MODO_FALLA == "caido":
        logger.warning("Simulación de caída: no se crea el despacho de %s", id_dispensacion)
        return error(503, "Despacho no disponible", "El servicio de despacho no está disponible")

    with bd.get_connection() as conn:
        resultado = bd.crear(
            conn,
            id_dispensacion,
            data["paciente_id"],
            data["codigo_medicamento"],
            int(data["cantidad"]),
        )
    return jsonify(resultado), 201


@app.post("/cancelar")
def cancelar():
    data = request.get_json(silent=True) or {}
    id_dispensacion = data.get("id_dispensacion")
    if not id_dispensacion:
        return error(400, "Solicitud inválida", "falta id_dispensacion")

    with bd.get_connection() as conn:
        cambiado = bd.cancelar(conn, id_dispensacion)
        resultado = bd.obtener(conn, id_dispensacion)

    if resultado is None:
        return error(404, "No encontrado", f"no existe el despacho {id_dispensacion}")
    logger.info("Cancelar despacho tx=%s cambiado=%s", id_dispensacion, cambiado)
    return jsonify(resultado), 200


@app.get("/estado/<id_dispensacion>")
def estado(id_dispensacion):
    with bd.get_connection() as conn:
        resultado = bd.obtener(conn, id_dispensacion)
    if resultado is None:
        return error(404, "No encontrado", f"no existe el despacho {id_dispensacion}")
    return jsonify(resultado), 200


@app.post("/admin/modo/<nuevo_modo>")
def cambiar_modo(nuevo_modo):
    global MODO_FALLA
    if nuevo_modo not in ("normal", "caido"):
        return error(400, "Modo no válido", "Use: normal, caido")
    MODO_FALLA = nuevo_modo
    logger.info("Modo de falla del despacho cambiado a %s", MODO_FALLA)
    return jsonify({"resultado": "exito", "modo_actual": MODO_FALLA}), 200


@app.get("/salud")
def salud():
    return jsonify({"servicio": "despacho", "modo_actual": MODO_FALLA, "ok": True}), 200


if __name__ == "__main__":
    bd.init_db()
    logger.info("Iniciando Servicio de Despacho en el puerto %s", PUERTO)
    app.run(host="0.0.0.0", port=PUERTO)
