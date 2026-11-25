"""Verificación E2E del stack en localhost:8081."""
import json
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://localhost:8081"
TOKEN = "token123"


def req(method, path, body=None, token=TOKEN):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-Key"] = token
    for intento in range(4):
        r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 3:
                print("    (rate limit: esperando 11s)")
                time.sleep(11)
                continue
            return e.code, json.loads(e.read().decode())
    raise RuntimeError("reintentos agotados")


def docker(*args):
    out = subprocess.run(["docker", "compose", *args], capture_output=True, text=True, timeout=120)
    return (out.stdout or out.stderr).strip()


def post_dispensacion(tx, med="MED-1", cantidad=1):
    return req("POST", "/v1/dispensaciones", {
        "id_dispensacion": tx, "paciente_id": "PAC-E2E",
        "codigo_medicamento": med, "cantidad": cantidad,
    })


def mostrar(nombre, resultado, esperado=None):
    estado, cuerpo = resultado
    resumen = {k: cuerpo.get(k) for k in ("estado", "id_dispensacion", "pasos_confirmados") if isinstance(cuerpo, dict)}
    ok = esperado is None or (resumen.get("estado") == esperado)
    print(f"[{'OK ' if ok else 'FALLO'}] {nombre}: HTTP {estado} {json.dumps(resumen or cuerpo, ensure_ascii=False)}")
    return ok


resultados = []

print("== 0. salud ==")
resultados.append(mostrar("gateway /salud", req("GET", "/salud")))

print("\n== 1. camino feliz ==")
resultados.append(mostrar("POST MED-1", post_dispensacion("E2E-HAPPY-2"), "COMPLETADA"))
resultados.append(mostrar("GET agregado", req("GET", "/v1/dispensaciones/E2E-HAPPY-2")))

print("\n== 2. sin stock (MED-3, 0 unidades) ==")
resultados.append(mostrar("POST MED-3", post_dispensacion("E2E-SIN-STOCK", "MED-3"), "FALLIDA"))

print("\n== 3. validaciones ==")
code, body = req("POST", "/v1/dispensaciones", {}, token=None)
resultados.append(code == 401)
print(f"[{'OK ' if code == 401 else 'FALLO'}] sin API key: HTTP {code}")
resultados.append(mostrar("cantidad=0", post_dispensacion("E2E-CANT-0", "MED-1", 0)))

print("\n== 4. receta lenta: 5 concurrentes, timeout + bulkhead + circuit breaker ==")
req("POST", "/v1/admin/receta/modo/lento")
docker("exec", "-T", "orquestador", "python", "-c",
       "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/admin/resiliencia/reset', data=b'', method='POST'))")
with ThreadPoolExecutor(max_workers=5) as pool:
    respuestas = list(pool.map(lambda i: post_dispensacion(f"E2E-LENTO-{i}"), range(1, 6)))
for i, r in enumerate(respuestas, 1):
    resultados.append(mostrar(f"E2E-LENTO-{i}", r, "PENDIENTE"))
print("  resiliencia:", docker("exec", "-T", "orquestador", "python", "-c",
      "import urllib.request; print(urllib.request.urlopen('http://localhost:8104/admin/resiliencia').read().decode())"))

print("\n== 5. recuperación y reanudación ==")
req("POST", "/v1/admin/receta/modo/normal")
time.sleep(6)
docker("exec", "-T", "orquestador", "python", "-c",
       "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/admin/resiliencia/reset', data=b'', method='POST'))")
out = docker("exec", "-T", "orquestador", "python", "-c",
             "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8104/reanudar/E2E-LENTO-1', data=b'', method='POST')).read().decode())")
try:
    resultados.append(mostrar("reanudar E2E-LENTO-1", (200, json.loads(out)), "COMPLETADA"))
except Exception:
    print("[FALLO] reanudar:", out)
    resultados.append(False)

print("\n== 6. receta caída ==")
req("POST", "/v1/admin/receta/modo/caido")
resultados.append(mostrar("POST con receta caída", post_dispensacion("E2E-RECETA-CAIDO"), "PENDIENTE"))
print("  resiliencia:", docker("exec", "-T", "orquestador", "python", "-c",
      "import urllib.request; print(urllib.request.urlopen('http://localhost:8104/admin/resiliencia').read().decode())"))
req("POST", "/v1/admin/receta/modo/normal")

print("\n== 7. despacho caído -> compensación ==")
req("POST", "/v1/admin/despacho/modo/caido")
resultados.append(mostrar("POST con despacho caído", post_dispensacion("E2E-DESPACHO-CAIDO"), "COMPENSADA"))
print("  GET agregado:", req("GET", "/v1/dispensaciones/E2E-DESPACHO-CAIDO")[1])
req("POST", "/v1/admin/despacho/modo/normal")

print("\n== 8. stock gRPC caído -> PENDIENTE y reanudación ==")
docker("stop", "servicio-stock")
out = docker("exec", "-T", "orquestador", "python", "-c",
             "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8104/despachar', "
             "data=b'{\"id_dispensacion\":\"E2E-STOCK-CAIDO\",\"paciente_id\":\"PAC-E2E\",\"codigo_medicamento\":\"MED-1\",\"cantidad\":1}', "
             "headers={'Content-Type':'application/json'}, method='POST')).read().decode())")
try:
    resultados.append(mostrar("POST interno con stock caído", (201, json.loads(out)), "PENDIENTE"))
except Exception:
    print("[FALLO] POST interno:", out)
    resultados.append(False)
docker("start", "servicio-stock")
time.sleep(5)
out = docker("exec", "-T", "orquestador", "python", "-c",
             "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8104/reanudar/E2E-STOCK-CAIDO', data=b'', method='POST')).read().decode())")
try:
    resultados.append(mostrar("reanudar E2E-STOCK-CAIDO", (200, json.loads(out)), "COMPLETADA"))
except Exception:
    print("[FALLO] reanudar stock:", out)
    resultados.append(False)

print(f"\nRESULTADO: {sum(resultados)}/{len(resultados)} comprobaciones correctas")
