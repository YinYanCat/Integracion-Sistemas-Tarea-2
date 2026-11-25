"""Máquina de estados de la Saga de despacho de receta."""

import logging

logger = logging.getLogger("saga")


def _resultado(repo, id_dispensacion: str) -> dict:
    fila = repo.obtener(id_dispensacion)
    return {
        "id_dispensacion": id_dispensacion,
        "estado": fila["estado"],
        "pasos_confirmados": fila["pasos_confirmados"],
    }


def _compensar(id_dispensacion, payload, pasos, clientes, repo):
    liberacion = clientes.liberar_stock(
        id_dispensacion,
        payload["codigo_medicamento"],
        payload["cantidad"],
    )
    estado = "COMPENSADA" if liberacion.get("exito") else "COMPENSACION_PENDIENTE"
    repo.actualizar(id_dispensacion, estado, pasos)
    logger.info(
        "Saga tx=%s: compensación %s (liberación exito=%s)",
        id_dispensacion, estado, liberacion.get("exito"),
    )
    return _resultado(repo, id_dispensacion)


def _finalizar_despacho(id_dispensacion, payload, pasos, clientes, repo):
    creado = clientes.crear_despacho(payload)
    if not creado:
        estado = clientes.estado_despacho(id_dispensacion)
        if estado is True:
            # La respuesta se perdió, pero el despacho sí se creó.
            creado = True
        elif estado is None:
            # No se puede afirmar si se creó: se conserva la reserva y se reanuda.
            repo.actualizar(id_dispensacion, "PENDIENTE", pasos)
            return _resultado(repo, id_dispensacion)

    if creado:
        pasos.append("despacho")
        repo.actualizar(id_dispensacion, "COMPLETADA", pasos)
        logger.info("Saga tx=%s: despacho confirmado", id_dispensacion)
        return _resultado(repo, id_dispensacion)

    return _compensar(id_dispensacion, payload, pasos, clientes, repo)


def ejecutar_saga(payload: dict, *, clientes, repo) -> dict:
    id_dispensacion = payload["id_dispensacion"]
    if not repo.iniciar(id_dispensacion, payload):
        return _resultado(repo, id_dispensacion)

    reserva = clientes.reservar_stock(
        id_dispensacion,
        payload["codigo_medicamento"],
        payload["cantidad"],
    )
    if reserva.get("error") or not reserva.get("exito"):
        # Un error de transporte no es stock insuficiente: se puede reanudar.
        estado = "PENDIENTE" if reserva.get("error") else "FALLIDA"
        repo.actualizar(id_dispensacion, estado, [])
        return _resultado(repo, id_dispensacion)

    logger.info("Saga tx=%s: stock reservado", id_dispensacion)
    pasos = ["stock"]
    if clientes.validar_receta(id_dispensacion) != "ok":
        repo.actualizar(id_dispensacion, "PENDIENTE", pasos)
        return _resultado(repo, id_dispensacion)

    logger.info("Saga tx=%s: receta validada", id_dispensacion)
    pasos.append("receta")
    return _finalizar_despacho(id_dispensacion, payload, pasos, clientes, repo)


def reanudar(id_dispensacion: str, *, clientes, repo) -> dict:
    fila = repo.obtener(id_dispensacion)
    if fila is None:
        return {
            "id_dispensacion": id_dispensacion,
            "estado": "NO_ENCONTRADO",
            "pasos_confirmados": [],
        }

    estado = fila["estado"]
    pasos = list(fila["pasos_confirmados"])
    payload = fila["payload"]

    if estado == "COMPENSACION_PENDIENTE":
        return _compensar(id_dispensacion, payload, pasos, clientes, repo)

    if estado != "PENDIENTE":
        return {
            "id_dispensacion": id_dispensacion,
            "estado": "NO_REANUDABLE",
            "pasos_confirmados": pasos,
        }

    if "stock" not in pasos:
        reserva = clientes.reservar_stock(
            id_dispensacion,
            payload["codigo_medicamento"],
            payload["cantidad"],
        )
        if reserva.get("error") or not reserva.get("exito"):
            nuevo_estado = "PENDIENTE" if reserva.get("error") else "FALLIDA"
            repo.actualizar(id_dispensacion, nuevo_estado, [])
            return _resultado(repo, id_dispensacion)
        pasos.append("stock")
        repo.actualizar(id_dispensacion, "PENDIENTE", pasos)

    if "receta" in pasos:
        return _finalizar_despacho(id_dispensacion, payload, pasos, clientes, repo)

    if clientes.validar_receta(id_dispensacion) != "ok":
        return _resultado(repo, id_dispensacion)

    pasos.append("receta")
    return _finalizar_despacho(id_dispensacion, payload, pasos, clientes, repo)
