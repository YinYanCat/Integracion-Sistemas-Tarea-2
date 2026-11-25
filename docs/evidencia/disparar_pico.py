import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://localhost:8081/v1/dispensaciones"
TOKEN = "token123"


def enviar(id_dispensacion):
    cuerpo = json.dumps({"id_dispensacion": id_dispensacion, "paciente_id": "PAC-E2E", "codigo_medicamento": "MED-1", "cantidad": 1}).encode()
    req = urllib.request.Request(BASE, data=cuerpo, headers={"X-API-Key": TOKEN, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"{id_dispensacion}|HTTP {r.status}|{r.read().decode()}"
    except urllib.error.HTTPError as exc:
        return f"{id_dispensacion}|HTTP {exc.code}|{exc.read().decode()}"
    except Exception as exc:
        return f"{id_dispensacion}|ERROR|{exc}"


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    prefix = sys.argv[2] if len(sys.argv) > 2 else "E2E-BH"
    with ThreadPoolExecutor(max_workers=n) as pool:
        for linea in pool.map(enviar, [f"{prefix}-{i}" for i in range(1, n + 1)]):
            print(linea)
