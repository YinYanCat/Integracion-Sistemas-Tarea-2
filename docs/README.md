# Documentación y evidencia del proyecto

Esta carpeta contiene la evidencia de la verificación integral del stack (Saga orquestada +
Gateway + BFF + Stock gRPC + Receta + Despacho) ejecutada en esta sesión.

## Índice

| Archivo | Contenido |
|---|---|
| [`informe.md`](informe.md) | Informe para la rúbrica: decisiones, diagramas, antes/después e interpretación. |
| [`verificacion-e2e.md`](verificacion-e2e.md) | Entorno, cambios, resultados y métricas de las 16 comprobaciones E2E. |
| [`evidencia/salida-verificacion.txt`](evidencia/salida-verificacion.txt) | Transcripción de la salida de las 16 comprobaciones E2E. |
| [`evidencia/antes-despues.txt`](evidencia/antes-despues.txt) | Métricas antes/después y medición del fail-fast (0.060 s). |
| [`evidencia/verificar_e2e.py`](evidencia/verificar_e2e.py) | Script usado para ejecutar las comprobaciones. |
| [`evidencia/medir_antes_despues.py`](evidencia/medir_antes_despues.py) | Script que genera la evidencia de antes/después. |
| [`tests-unitarios.md`](tests-unitarios.md) | Comando y resultado de la suite unitaria (40 tests). |

## Reproducción rápida

```bash
# desde la raíz del repositorio
docker compose up --build -d
python -m unittest discover -s test -v
python docs/evidencia/verificar_e2e.py
```

El script usa `http://localhost:8081` porque en el entorno de verificación el puerto 8080
estaba ocupado por un proceso del sistema (`AgentService`). Si el Gateway se publica en el
puerto 8080 estándar, cambia `BASE` en el script a `http://localhost:8080`.

## Resultado global

- **E2E:** 16/16 comprobaciones correctas (camino feliz y todos los caminos de fallo).
- **Unitarios:** 40/40 tests OK.
- Detalle y evidencia: [`verificacion-e2e.md`](verificacion-e2e.md).
