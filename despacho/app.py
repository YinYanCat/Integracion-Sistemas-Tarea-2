"""Servicio de Despacho: crea y cancela entregas (landing en construcción)."""

import os

from flask import Flask, jsonify

app = Flask(__name__)
PUERTO = int(os.getenv("DESPACHO_PORT", "8102"))


@app.get("/salud")
def salud():
    return jsonify({"servicio": "despacho", "ok": True}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PUERTO)
