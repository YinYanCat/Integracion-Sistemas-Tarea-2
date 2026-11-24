"""Composición de la respuesta del BFF a partir de varios servicios."""


def _seguro(funcion, *args):
    try:
        return funcion(*args)
    except Exception as exc:
        return {"error": str(exc)}


def armar_respuesta(id_dispensacion: str, *, clientes) -> dict:
    saga = _seguro(clientes.saga, id_dispensacion)
    despacho = _seguro(clientes.despacho, id_dispensacion)

    codigo = None
    if isinstance(saga, dict):
        codigo = saga.get("payload", {}).get("codigo_medicamento")
    if codigo is None and isinstance(despacho, dict):
        codigo = despacho.get("codigo_medicamento")

    medicamento = (
        _seguro(clientes.medicamento, codigo)
        if codigo
        else {"error": "sin código de medicamento en la Saga"}
    )

    return {
        "saga": saga,
        "medicamento": medicamento,
        "despacho": despacho,
        "validacion_receta": _seguro(clientes.validacion, id_dispensacion),
    }
