# Evidencia E2E — Forma J

Fecha: 2026-11-24. Stack levantado con `docker compose up --build`.
El Gateway expone el puerto 8080; en la verificación local se usó un override temporal a 8081.
Token: `token123`. Todas las peticiones públicas usan `X-API-Key: token123`.

## Escenario A — Receta lenta/caída: timeout, Circuit Breaker, Bulkhead y fallback

Objetivo: demostrar que la única llamada a Receta está protegida y que un fallo deja la Saga en
`PENDIENTE` en lugar de propagar un 500.

1. Reinicio de métricas, Receta en modo `lento` y 5 `POST /v1/dispensaciones` simultáneos
   (hilos reales, `disparar_pico.py`). Todas devuelven `201 PENDIENTE` con `pasos_confirmados: ["stock"]`.
   - `disparar_pico.py` — generador de carga concurrente.
   - `A2-respuestas-pico.txt` — respuestas `E2E-BH-1` … `E2E-BH-5`.
   - `A2-metricas-pico.txt` — `llamadas=4`, `timeouts=4`, `rechazos_bulkhead=1`, `fallbacks=5`,
     circuito `ABIERTO`, `aperturas=2`. Es decir: 4 llamadas llegaron a Receta (límite del bulkhead),
     1 fue rechazada sin saturar el servicio y las 5 Sagas quedaron pendientes.
2. Enfriamiento de 5 s, Receta en modo `caido` y 2 peticiones secuenciales.
   - `A3-respuestas-caido.txt` — ambas `201 PENDIENTE`.
   - `A3-metricas-caido.txt` — `llamadas=5` (solo una nueva llamada: la sonda de `MEDIO_ABIERTO`,
     que volvió a abrir el circuito), `fallbacks=7`, `aperturas=3`, circuito `ABIERTO`.
     La segunda petición fue fail-fast: no incrementó `llamadas`.
3. Recuperación: Receta vuelve a `normal`, se espera el enfriamiento y se reanuda `E2E-BH-1`.
   - `A4-reanudar.txt` — `COMPLETADA`, pasos `stock, receta, despacho`.
   - `A4-metricas-recuperadas.txt` — circuito `CERRADO`, `exitos=1`, `fallos=0`.

Archivos del primer intento secuencial (sin simultaneidad real): `A-E2E-R-LENTO-*.txt` y
`A-metricas-pico.txt`. Se conservan para trazabilidad; no muestran rechazo de bulkhead porque
las peticiones no se solaparon.

## Escenario B — Despacho caído: compensación inversa

- Se pone `servicio-despacho` en modo `caido` y se envía `E2E-DESPACHO-CAIDO`.
- `B-respuestas.txt` — Saga `COMPENSADA` con pasos `["stock", "receta"]`. El `GET` agregado
  muestra el medicamento y la receta, y `despacho` con `404`: no se creó el despacho y el stock
  fue devuelto por la compensación.
- `B-metricas.txt` — Receta sigue sana: `exitos=1`, `fallos=0`, circuito `CERRADO`.
- El servicio se devolvió a `normal` al terminar.

## Escenario C — Stock gRPC caído: Saga PENDIENTE y reanudación

- Se detiene `servicio-stock` (`docker compose stop servicio-stock`) y se envía la solicitud
  por la API interna del orquestador (`POST /despachar`) para evitar el timeout de 3 s del Gateway.
- `C-escenario-final.txt` — `POST /despachar` → `PENDIENTE` con `pasos_confirmados: []`;
  `GET /estado/E2E-STOCK-CAIDO-3` confirma el estado persistido; tras reiniciar Stock,
  `POST /reanudar/E2E-STOCK-CAIDO-3` → `COMPLETADA` con los tres pasos; `ps` final muestra los
  6 servicios `healthy`.
- `C-respuestas.txt` — intento público descartado: el Gateway devolvió `503` por su propio
  timeout antes de que el orquestador terminara. Se conserva como evidencia del comportamiento
  del Gateway, no como estado de la Saga.

## Verificación final

- `smoke-final.txt` — después de devolver Receta y Despacho a `normal` y reiniciar Stock, un
  `POST` público nuevo termina `COMPLETADA`, el `GET` agregado trae los cuatro bloques,
  `/salud` responde y los seis contenedores siguen `healthy`.

## Logs

- `logs-finales.txt` — logs de orquestador, Receta, Despacho, Stock y Gateway tras los tres
  escenarios, incluyendo fallbacks, reanudaciones y el estado final de los contenedores.

## Reproducción rápida

```bash
docker compose up --build -d
docker compose exec -T orquestador python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8104/admin/resiliencia/reset', data=b'', method='POST'))"
docker compose exec -T servicio-receta python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8103/admin/modo/lento', data=b'', method='POST'))"
python docs/evidencia/disparar_pico.py 5 E2E-REPRO
```
