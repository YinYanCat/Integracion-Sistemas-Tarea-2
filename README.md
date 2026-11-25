# Farmacia — despacho de receta (Unidad 3, Forma J)

Sistema distribuido resiliente: API Gateway + BFF + Saga orquestada + Circuit Breaker y
Bulkhead sobre la dependencia frágil (Receta).

## Levantar todo

```bash
docker compose up --build -d
docker compose ps
```

Servicios: `gateway` (puerto/host 8080), `bff-web` (8090), `orquestador` (8104),
`servicio-stock` (8101, gRPC), `servicio-receta` (8103), `servicio-despacho` (8102).
Solo el Gateway se publica al exterior; el resto usa `expose`.

- Token: `token123` → header `X-API-Key: token123`.
- Salud: `GET http://localhost:8080/salud`.
- Rate limit del gateway: 5 peticiones / 10 s por cliente (`RATE_LIMIT`, `RATE_WINDOW`).

> En el entorno donde se verificó, el puerto 8080 estaba ocupado por un proceso del sistema,
> así que el Gateway se publicó en 8081 con:
> `docker compose run -d --no-deps -p 8081:8080 gateway`. Los scripts de `docs/evidencia/`
> usan 8081; cambia `BASE` a 8080 si usas el puerto estándar.

En PowerShell usa `curl.exe` (no `curl`, que es alias de `Invoke-WebRequest`) o los scripts
Python de `docs/evidencia/`.

## Operación central

```bash
curl.exe -X POST http://localhost:8080/v1/dispensaciones \
  -H 'X-API-Key: token123' -H 'Content-Type: application/json' \
  -d '{"id_dispensacion":"DEMO-1","paciente_id":"PAC-1","codigo_medicamento":"MED-1","cantidad":1}'
# 201 {"estado":"COMPLETADA","pasos_confirmados":["stock","receta","despacho"]}

curl.exe http://localhost:8080/v1/dispensaciones/DEMO-1 -H 'X-API-Key: token123'
```

## Cómo provocar los escenarios de falla

### 1. Éxito (camino feliz)

`MED-1` (50 unidades) → `COMPLETADA` con los tres pasos. Ver comando arriba.

### 2. Fallo con compensación (último paso)

```bash
curl.exe -X POST http://localhost:8080/v1/admin/despacho/modo/caido -H 'X-API-Key: token123'
curl.exe -X POST http://localhost:8080/v1/dispensaciones \
  -H 'X-API-Key: token123' -H 'Content-Type: application/json' \
  -d '{"id_dispensacion":"DEMO-DESPACHO-CAIDO","paciente_id":"PAC-1","codigo_medicamento":"MED-1","cantidad":1}'
# 201 {"estado":"COMPENSADA","pasos_confirmados":["stock","receta"]}
curl.exe -X POST http://localhost:8080/v1/admin/despacho/modo/normal -H 'X-API-Key: token123'
```

El `GET` agregado muestra `despacho: 404` y el stock devuelto.

También hay fallo sin compensación por regla de negocio: `MED-3` nace con 0 unidades →
`409 FALLIDA`, pasos `[]`.

### 3. Falla en cascada contenida (Receta lenta y caída)

```bash
# lentitud: sleep de 5s en Receta vs timeout de 2s en el orquestador
curl.exe -X POST http://localhost:8080/v1/admin/receta/modo/lento -H 'X-API-Key: token123'
python docs/evidencia/verificar_e2e.py   # incluye 5 peticiones concurrentes

# caída: HTTP 500 en Receta
curl.exe -X POST http://localhost:8080/v1/admin/receta/modo/caido -H 'X-API-Key: token123'
python docs/evidencia/medir_antes_despues.py  # antes/después + fail-fast

curl.exe -X POST http://localhost:8080/v1/admin/receta/modo/normal -H 'X-API-Key: token123'
docker compose exec -T orquestador python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/admin/resiliencia/reset', data=b'', method='POST'))"
```

Resultados: Sagas `PENDIENTE` con `["stock"]`, circuito `ABIERTO`, rechazos del bulkhead y
respuesta fail-fast en ~0.06 s. Métricas:

```bash
docker compose exec -T orquestador python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8104/admin/resiliencia').read().decode())"
```

### 4. Stock gRPC caído y reanudación

```bash
docker compose stop servicio-stock
docker compose exec -T orquestador python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8104/despachar', data=b'{\"id_dispensacion\":\"DEMO-STOCK\",\"paciente_id\":\"PAC-1\",\"codigo_medicamento\":\"MED-1\",\"cantidad\":1}', headers={'Content-Type':'application/json'}, method='POST')).read().decode())"
# PENDIENTE, pasos []
docker compose start servicio-stock
docker compose exec -T orquestador python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/reanudar/DEMO-STOCK', data=b'', method='POST'))"
# COMPLETADA, pasos [stock, receta, despacho]
```

## Pruebas y documentación

```bash
python -m unittest discover -s test -v     # 40 tests OK
```

- [`docs/informe.md`](docs/informe.md) — informe con decisiones, diagramas y evidencia.
- [`docs/verificacion-e2e.md`](docs/verificacion-e2e.md) — 16 comprobaciones E2E.
- [`docs/evidencia/`](docs/evidencia/) — salidas y scripts reproducibles.
- [`ADR/ADR-001.md`](ADR/ADR-001.md) — por qué Saga y no 2PC.
