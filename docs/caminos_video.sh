#!/usr/bin/env bash
# Demo en vivo para el video (Forma J - Farmacia).
# Uso:
#   bash docs/caminos_video.sh
#   BASE=http://localhost:8081 bash docs/caminos_video.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BASE="${BASE:-http://localhost:8080}"
TOKEN="${TOKEN:-token123}"
AUTH=(-H "X-API-Key: $TOKEN" -H 'Content-Type: application/json')

sep()  { printf '\n========== %s ==========\n' "$1"; }
pausa(){ printf '(pausa de 11s por el rate limit 5 req / 10 s)\n'; sleep 11; }

post_json() {
  curl -sS -w '\nHTTP %{http_code}\n' -X POST "$1" "${AUTH[@]}" -d "$2" || true
}
get_json() {
  curl -sS -w '\nHTTP %{http_code}\n' "$1" "${AUTH[@]}" || true
}
disp() {
  local id="$1" med="${2:-MED-1}" qty="${3:-1}"
  post_json "$BASE/v1/dispensaciones" \
    "{\"id_dispensacion\":\"$id\",\"paciente_id\":\"PAC-DEMO\",\"codigo_medicamento\":\"$med\",\"cantidad\":$qty}"
}
admin_post() { post_json "$BASE/v1/admin/$1" '{}'; }

reset() {
  docker compose exec -T orquestador python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/admin/resiliencia/reset', data=b'', method='POST'))"
}
metrics() {
  docker compose exec -T orquestador python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8104/admin/resiliencia').read().decode())"
}
reanudar() {
  docker compose exec -T -e TX="$1" orquestador python - <<'PY' || true
import os, urllib.request
u = "http://localhost:8104/reanudar/" + os.environ["TX"]
print(urllib.request.urlopen(urllib.request.Request(u, data=b"", method="POST")).read().decode())
PY
}
disp_interna() {
  docker compose exec -T -e TX="$1" orquestador python - <<'PY' || true
import json, os, urllib.request
body = json.dumps({"id_dispensacion": os.environ["TX"], "paciente_id": "PAC-DEMO",
                   "codigo_medicamento": "MED-1", "cantidad": 1}).encode()
r = urllib.request.Request("http://localhost:8104/despachar", data=body,
                           headers={"Content-Type": "application/json"}, method="POST")
print(urllib.request.urlopen(r).read().decode())
PY
}

# ---------------------------------------------------------------- 0. Arrancar
sep "0. Levantar todo con un solo docker compose"
docker compose -f "$ROOT_DIR/docker-compose.yml" up --build -d || true
for _ in $(seq 1 30); do
  curl -fsS "$BASE/salud" >/dev/null 2>&1 && break
  sleep 1
done

PORT="${BASE##*:}"
if ! curl -fsS "$BASE/salud" >/dev/null 2>&1; then
  if [ "$PORT" = "8080" ]; then
    echo "ERROR: el puerto 8080 está ocupado o el gateway no respondió. Usa: BASE=http://localhost:8081 bash docs/caminos_video.sh"
    exit 1
  fi
  echo "El gateway no responde en $BASE; publicando uno one-off en $PORT"
  docker compose -f "$ROOT_DIR/docker-compose.yml" run -d --no-deps -p "$PORT:8080" gateway
  for _ in $(seq 1 30); do
    curl -fsS "$BASE/salud" >/dev/null 2>&1 && break
    sleep 1
  done
fi
get_json "$BASE/salud"

# ---------------------------------------------------------------- 1. Éxito
sep "1. Camino feliz -> 201 COMPLETADA [stock, receta, despacho]"
disp DEMO-HAPPY-1
get_json "$BASE/v1/dispensaciones/DEMO-HAPPY-1"

# ---------------------------------------------------------------- 2. Sin stock
pausa
sep "2. Sin stock (MED-3 = 0 unidades) -> 409 FALLIDA []"
disp DEMO-SIN-STOCK MED-3 1

# ---------------------------------------------------------------- 3. Validación
sep "3. Sin API key -> 401 | cantidad=0 -> 400"
curl -sS -w '\nHTTP %{http_code}\n' -X POST "$BASE/v1/dispensaciones" \
  -H 'Content-Type: application/json' -d '{}' || true
disp DEMO-CANT-0 MED-1 0

# ---------------------------------------------------------------- 4. Receta lenta
pausa
sep "4. Receta LENTA + 5 concurrentes -> timeout, bulkhead y circuito abierto"
admin_post receta/modo/lento
reset
pausa
for i in 1 2 3 4 5; do disp "DEMO-LENTO-$i" & done
wait
metrics

# ---------------------------------------------------------------- 5. Reanudación
pausa
sep "5. Receta normal + reanudar -> COMPLETADA"
admin_post receta/modo/normal
sleep 6
reset
reanudar DEMO-LENTO-1

# ---------------------------------------------------------------- 6. Receta caída
pausa
sep "6. Receta CAIDA -> 3 fallos abren el circuito"
admin_post receta/modo/caido
reset
for i in 1 2 3; do disp "DEMO-CB-$i"; done
metrics
sep "6b. Cuarta petición con circuito ABIERTO -> fail-fast"
inicio=$(date +%s%N)
disp DEMO-CB-FF
fin=$(date +%s%N)
echo "TIEMPO fail-fast: $(( (fin - inicio) / 1000000 )) ms  (llamadas a Receta NO aumenta)"
metrics
pausa
admin_post receta/modo/normal

# ---------------------------------------------------------------- 7. Despacho caído
pausa
sep "7. Despacho CAIDO -> 201 COMPENSADA [stock, receta]"
admin_post despacho/modo/caido
disp DEMO-DESPACHO-CAIDO
get_json "$BASE/v1/dispensaciones/DEMO-DESPACHO-CAIDO"
pausa
admin_post despacho/modo/normal

# ---------------------------------------------------------------- 8. Stock caído
pausa
sep "8. Stock gRPC caído -> PENDIENTE [] y reanudación -> COMPLETADA"
docker compose -f "$ROOT_DIR/docker-compose.yml" stop servicio-stock
disp_interna DEMO-STOCK-CAIDO
docker compose -f "$ROOT_DIR/docker-compose.yml" start servicio-stock
sleep 5
reanudar DEMO-STOCK-CAIDO

# ---------------------------------------------------------------- 9. Cierre
sep "9. Tests unitarios"
python3 -m unittest discover -s "$ROOT_DIR/test" -v

sep "10. Estado final"
docker compose -f "$ROOT_DIR/docker-compose.yml" ps
metrics