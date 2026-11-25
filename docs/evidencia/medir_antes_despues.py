"""Captura métricas antes/después de inducir falla en Receta."""
import json
import subprocess
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8081"
TOKEN = "token123"
SALIDA = []


def escribir(linea):
    print(linea)
    SALIDA.append(linea)


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "X-API-Key": TOKEN}
    for intento in range(4):
        r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 3:
                time.sleep(11)
                continue
            return e.code, json.loads(e.read().decode())


def docker(*args):
    out = subprocess.run(["docker", "compose", *args], capture_output=True, text=True, timeout=120)
    return (out.stdout or out.stderr).strip()


def reset():
    docker("exec", "-T", "orquestador", "python", "-c",
           "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/admin/resiliencia/reset', data=b'', method='POST'))")


def metricas():
    return docker("exec", "-T", "orquestador", "python", "-c",
                  "import urllib.request; print(urllib.request.urlopen('http://localhost:8104/admin/resiliencia').read().decode())")


def post(tx):
    return req("POST", "/v1/dispensaciones", {
        "id_dispensacion": tx, "paciente_id": "PAC-E2E",
        "codigo_medicamento": "MED-1", "cantidad": 1,
    })


escribir("== ANTES: resiliencia reiniciada, Receta en modo normal ==")
req("POST", "/v1/admin/receta/modo/normal")
reset()
escribir(metricas())

escribir("\n== ANTES: una dispensación sana ==")
escribir(str(post("E2E-ANTES-1")))
escribir(metricas())

escribir("\n== INDUCCIÓN: Receta en modo caído + 3 peticiones ==")
req("POST", "/v1/admin/receta/modo/caido")
for i in range(1, 4):
    escribir(f"  petición {i}: {post(f'E2E-CB-{i}')}")
escribir("DESPUÉS (circuito abierto):")
escribir(metricas())

escribir("\n== DESPUÉS: cuarta petición con circuito ABIERTO (fail-fast) ==")
inicio = time.monotonic()
code, cuerpo = post("E2E-CB-FAILFAST")
elapsed = time.monotonic() - inicio
escribir(f"  HTTP {code} en {elapsed:.3f}s -> {json.dumps(cuerpo, ensure_ascii=False)}")
escribir(metricas())

escribir("\n== RESTAURACIÓN ==")
req("POST", "/v1/admin/receta/modo/normal")
time.sleep(6)
reset()
escribir(metricas())

with open(r"C:\Users\matia\AppData\Local\Temp\opencode\antes_después.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(SALIDA) + "\n")
