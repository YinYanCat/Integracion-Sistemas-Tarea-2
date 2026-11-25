# Verificación E2E — camino feliz y caminos de fallo

Fecha: 2026-11-24/25 (los logs HTTP registran `Wed, 25 Nov 2026 00:48 GMT`).
Resultado: **16/16 comprobaciones correctas**.

## 1. Entorno

- Docker Engine 29.8.0, `docker compose` (plugin v2).
- Python 3.14.4 en el host; Python 3.12-slim dentro de las imágenes.
- Stack: `gateway`, `bff-web`, `orquestador`, `servicio-stock`, `servicio-receta`,
  `servicio-despacho`.
- Token público: `token123` (header `X-API-Key`).
- El puerto 8080 estaba ocupado por `AgentService` (PID 6444), por lo que el Gateway se
  levantó como contenedor *one-off* publicado en **8081**:

  ```bash
  docker compose run -d --no-deps -p 8081:8080 gateway
  ```

  Verificación: `GET http://localhost:8081/salud` → `200 {"ok":true,"servicio":"gateway"}`.

## 2. Arreglo previo necesario en `docker-compose.yml`

El checkout no era ejecutable tal cual; se aplicaron estos cambios mínimos:

```diff
 bff-web:
   build:
-    context: ./bff_web
+    context: .
+    dockerfile: bff_web/Dockerfile
   expose:
     - "8090"
+  depends_on:
+    - orquestador
+    - servicio-stock
+    - servicio-receta
+    - servicio-despacho

+orquestador:
+  build:
+    context: .
+    dockerfile: orquestador/Dockerfile
+  volumes:
+    - saga_data:/data
+  expose:
+    - "8104"

 volumes:
+  saga_data:
```

Motivo: los Dockerfiles de `bff-web` y `orquestador` generan los stubs gRPC desde
`contratos/stock.proto`, así que necesitan el contexto completo del repositorio. Sin el
servicio `orquestador`, el BFF no podía resolver `http://orquestador:8104/despachar`.

Con esto, `docker compose up --build -d` compila los seis servicios sin errores.

## 3. Resultados

| # | Escenario | Request | Respuesta esperada | Obtenido |
|---|---|---|---|---|
| 1 | Salud del gateway | `GET /salud` | 200 | OK |
| 2 | Camino feliz | `POST /v1/dispensaciones` `MED-1` | `201 COMPLETADA` | OK |
| 3 | Agregación | `GET /v1/dispensaciones/E2E-HAPPY-2` | 200, 4 bloques | OK |
| 4 | Sin stock | `POST ... MED-3` (`0` unidades) | `409 FALLIDA`, `[]` | OK |
| 5 | Sin API key | `POST /v1/dispensaciones` | `401` | OK |
| 6 | Validación | `cantidad: 0` | `400` | OK |
| 7-11 | Receta lenta, 5 concurrentes | `POST ...` ×5 | `201 PENDIENTE`, `["stock"]` | OK ×5 |
| 12 | Reanudación | `POST /reanudar/E2E-LENTO-1` | `COMPLETADA`, 3 pasos | OK |
| 13 | Receta caída | `POST ...` en modo `caido` | `201 PENDIENTE` | OK |
| 14 | Despacho caído | `POST ...` en modo `caido` | `201 COMPENSADA`, `["stock","receta"]` | OK |
| 15 | Stock gRPC caído | `POST http://orquestador:8104/despachar` | `201 PENDIENTE`, `[]` | OK |
| 16 | Reanudación tras stock | `POST /reanudar/E2E-STOCK-CAIDO` | `COMPLETADA`, 3 pasos | OK |

Salida completa: [`evidencia/salida-verificacion.txt`](evidencia/salida-verificacion.txt).
Script: [`evidencia/verificar_e2e.py`](evidencia/verificar_e2e.py).

### Camino feliz

```bash
curl.exe -X POST http://localhost:8081/v1/dispensaciones \
  -H 'X-API-Key: token123' -H 'Content-Type: application/json' \
  -d '{"id_dispensacion":"E2E-HAPPY-2","paciente_id":"PAC-E2E","codigo_medicamento":"MED-1","cantidad":1}'
```

```json
{"estado":"COMPLETADA","id_dispensacion":"E2E-HAPPY-2","pasos_confirmados":["stock","receta","despacho"]}
```

### Camino de fallo: sin stock

`MED-3` nace con 0 unidades. Respuesta:

```json
{"estado":"FALLIDA","id_dispensacion":"E2E-SIN-STOCK","pasos_confirmados":[]}
```

### Camino de fallo: receta lenta (timeout + bulkhead + circuit breaker)

Se puso Receta en `lento` (duerme 5 s; el orquestador tiene timeout de 2 s), se reiniciaron
las métricas y se enviaron 5 peticiones simultáneas. Las 5 devolvieron `201 PENDIENTE` con
`pasos_confirmados: ["stock"]`. Instantánea de resiliencia:

```json
{"receta":{"bulkhead":{"en_vuelo":0,"limite":4},"circuito":{"abierto_hace":0.384,"enfriamiento":5.0,"estado":"ABIERTO","fallos":4},"metricas":{"aperturas":2,"exitos":0,"fallbacks":5,"fallos":4,"llamadas":4,"rechazos_bulkhead":1,"timeouts":4}}}
```

Lectura: solo 4 llamadas llegaron a Receta (límite del bulkhead), 1 fue rechazada sin
saturar el servicio, hubo 4 timeouts, 5 fallbacks y el circuito abrió 2 veces.

Tras volver Receta a `normal`, esperar 6 s el enfriamiento y reanudar:

```json
{"estado":"COMPLETADA","id_dispensacion":"E2E-LENTO-1","pasos_confirmados":["stock","receta","despacho"]}
```

### Camino de fallo: receta caída

Con `POST /v1/admin/receta/modo/caido`, la validación devuelve 500 y la Saga queda
`PENDIENTE` con `["stock"]`:

```json
{"receta":{"bulkhead":{"en_vuelo":0,"limite":4},"circuito":{"abierto_hace":0.0,"enfriamiento":5.0,"estado":"CERRADO","fallos":1},"metricas":{"aperturas":0,"exitos":1,"fallbacks":1,"fallos":1,"llamadas":2,"rechazos_bulkhead":0,"timeouts":0}}}
```

### Camino de fallo: despacho caído (compensación inversa)

```json
{"estado":"COMPENSADA","id_dispensacion":"E2E-DESPACHO-CAIDO","pasos_confirmados":["stock","receta"]}
```

El `GET` agregado confirma que no se creó el despacho (`404`) y que el stock fue devuelto
por la compensación (`MED-1` con 42 unidades disponibles):

```json
{
  "despacho": {"status": 404, "title": "No encontrado", "detail": "no existe el despacho E2E-DESPACHO-CAIDO"},
  "medicamento": {"codigo_medicamento": "MED-1", "nombre": "Paracetamol 500mg", "unidades_disponibles": 42, "disponible": true},
  "saga": {"estado": "COMPENSADA", "pasos_confirmados": ["stock", "receta"]},
  "validacion_receta": {"estado": "VALIDADA", "id_dispensacion": "E2E-DESPACHO-CAIDO"}
}
```

### Camino de fallo: stock gRPC caído

Se detuvo `servicio-stock` y se usó la API interna del orquestador para evitar el timeout
de 3 s del Gateway:

```bash
docker compose stop servicio-stock
docker compose exec -T orquestador python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://localhost:8104/despachar', data=b'{\"id_dispensacion\":\"E2E-STOCK-CAIDO\",\"paciente_id\":\"PAC-E2E\",\"codigo_medicamento\":\"MED-1\",\"cantidad\":1}', headers={'Content-Type':'application/json'}, method='POST')).read().decode())"
# {"estado":"PENDIENTE","id_dispensacion":"E2E-STOCK-CAIDO","pasos_confirmados":[]}

docker compose start servicio-stock
docker compose exec -T orquestador python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/reanudar/E2E-STOCK-CAIDO', data=b'', method='POST'))"
# {"estado":"COMPLETADA",...,"pasos_confirmados":["stock","receta","despacho"]}
```

## 4. Notas de ejecución

- En PowerShell, `curl` es un alias de `Invoke-WebRequest`: usar `curl.exe` o el script Python.
  Con `curl` sin `.exe`, el cuerpo JSON no llegaba al BFF (`400 se espera un cuerpo JSON`).
- El Gateway aplica rate limit de 5 peticiones / 10 s por IP. El script espera 11 s y reintenta
  cuando recibe `429`, por lo que la corrida completa tarda alrededor de 2 minutos.
- Al finalizar, Receta y Despacho quedaron en modo `normal` y los seis contenedores `Up`.

## 5. Conclusión

El sistema satisface los comportamientos esperados: la Saga completa el camino feliz,
falla sin compensación cuando no hay stock, deja Sagas `PENDIENTE` ante fallos transitorios
de Receta o Stock (reanudables sin reservar dos veces), compensa en orden inverso cuando
falla el Despacho, y protege la llamada a Receta con timeout, bulkhead y circuit breaker.
La suite unitaria también pasa íntegramente (ver [`tests-unitarios.md`](tests-unitarios.md)).
