"""API Gateway: único punto de entrada (landing en construcción)."""

import os

from flask import Flask, jsonify

app = Flask(__name__)
PUERTO = int(os.getenv("PORT", "8080"))


@app.get("/salud")
def salud():
    return jsonify({"servicio": "gateway", "ok": True}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PUERTO)
