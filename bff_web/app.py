"""BFF web: punto de agregación por cliente (landing en construcción)."""

import os

from flask import Flask, jsonify

app = Flask(__name__)
PUERTO = int(os.getenv("BFF_PORT", "8090"))


@app.get("/salud")
def salud():
    return jsonify({"servicio": "bff-web", "ok": True}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PUERTO)
