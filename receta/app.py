import logging
import os
import time
from flask import Flask, jsonify, request
import bd

logger = logging.getLogger("receta_service")

app = Flask(__name__)
NOMBRE = os.getenv("NOMBRE", "receta")
MODO_FALLA = os.environ.get("MODO_FALLA", "normal")


@app.post("/ejecutar")
def ejecutar():
    global MODO_FALLA
    data = request.get_json(silent=True) or {}
    tx = data.get("id_dispensacion", data.get("tx", "DESCONOCIDA"))
    
    logger.info("Recibida solicitud de validación de receta para tx=%s [Modo actual: %s]", tx, MODO_FALLA)

    if MODO_FALLA == "caido":
        logger.warning("Simulación de caída: El servicio de recetas no responde (HTTP 500)")
        return jsonify({
            "servicio": NOMBRE,
            "tx": tx,
            "ok": False,
            "error": "Error interno: El validador externo no está disponible."
        }), 500

    if MODO_FALLA == "lento":
        logger.warning("Simulación de lentitud: sleep de 5 segundos...")
        time.sleep(5.0)

    with bd.get_connection() as conn:
        bd.registrar_validacion(conn, tx)

    logger.info("Receta validada exitosamente y guardada en BD para tx=%s", tx)
    return jsonify({
        "servicio": NOMBRE,
        "tx": tx,
        "ok": True,
        "mensaje": "Receta electrónica validada correctamente."
    }), 200


@app.post("/compensar")
def compensar():
    data = request.get_json(silent=True) or {}
    tx = data.get("id_dispensacion", data.get("tx", "DESCONOCIDA"))
    
    logger.info("Compensando validación de receta para tx=%s", tx)
    
    with bd.get_connection() as conn:
        bd.registrar_compensacion(conn, tx)
    
    return jsonify({
        "servicio": NOMBRE,
        "tx": tx,
        "compenso": "anulacion_validacion_receta",
        "ok": True
    }), 200


@app.route("/admin/modo/<nuevo_modo>", methods=["POST"])
def cambiar_modo_falla(nuevo_modo):
    global MODO_FALLA
    if nuevo_modo not in ["normal", "lento", "caido"]:
        return jsonify({"error": "Modo no válido. Use: normal, lento, caido"}), 400
    
    MODO_FALLA = nuevo_modo
    logger.info("Cambiando modo de falla del servicio de recetas a: %s", MODO_FALLA)
    return jsonify({"resultado": "exito", "modo_actual": MODO_FALLA}), 200


@app.get("/estado")
def estado():
    with bd.get_connection() as conn:
        historial = bd.obtener_historial(conn)
    return jsonify({"servicio": NOMBRE, "modo_actual": MODO_FALLA, "log": historial}), 200


@app.get("/salud")
def salud():
    return jsonify({"servicio": NOMBRE, "modo_actual": MODO_FALLA, "ok": True}), 200


if __name__ == "__main__":
    bd.init_db()
    logger.info("Iniciando Servicio de Recetas (Modo inicial: %s)...", MODO_FALLA)
    app.run(host="0.0.0.0", port=8103)