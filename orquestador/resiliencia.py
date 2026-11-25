"""Primitivas de resiliencia del orquestador: métricas, bulkhead y circuit breaker."""

import threading
import time


class Metricas:
    """Contadores thread-safe para evidenciar el comportamiento ante fallas."""

    CLAVES = (
        "llamadas",
        "exitos",
        "fallos",
        "timeouts",
        "rechazos_bulkhead",
        "fallbacks",
        "aperturas",
    )

    def __init__(self):
        self._lock = threading.Lock()
        self._valores = {clave: 0 for clave in self.CLAVES}

    def incrementar(self, nombre):
        with self._lock:
            self._valores[nombre] += 1

    def instantanea(self):
        with self._lock:
            return dict(self._valores)

    def reiniciar(self):
        with self._lock:
            self._valores = {clave: 0 for clave in self.CLAVES}


class Bulkhead:
    """Limita la concurrencia sin bloquear: rechaza cuando no hay permiso."""

    def __init__(self, limite=4):
        if limite < 1:
            raise ValueError("limite debe ser >= 1")
        self.limite = limite
        self._en_vuelo = 0
        self._lock = threading.Lock()

    def adquirir(self):
        with self._lock:
            if self._en_vuelo >= self.limite:
                return False
            self._en_vuelo += 1
            return True

    def liberar(self):
        with self._lock:
            if self._en_vuelo > 0:
                self._en_vuelo -= 1

    def instantanea(self):
        with self._lock:
            return {"limite": self.limite, "en_vuelo": self._en_vuelo}

    def reiniciar(self):
        with self._lock:
            self._en_vuelo = 0


class CircuitBreaker:
    """Circuit breaker con reloj inyectable para pruebas deterministas."""

    CERRADO = "CERRADO"
    ABIERTO = "ABIERTO"
    MEDIO_ABIERTO = "MEDIO_ABIERTO"

    def __init__(self, umbral=3, enfriamiento=5.0, reloj=time.monotonic):
        if umbral < 1:
            raise ValueError("umbral debe ser >= 1")
        self.umbral = umbral
        self.enfriamiento = enfriamiento
        self._reloj = reloj
        self._lock = threading.Lock()
        self.reiniciar()

    def reiniciar(self):
        with self._lock:
            self._estado = self.CERRADO
            self._fallos = 0
            self._sonda = False
            self._abierto_en = None

    def _transicionar(self):
        """Debe llamarse con el lock tomado."""
        if (
            self._estado == self.ABIERTO
            and self._abierto_en is not None
            and self._reloj() - self._abierto_en >= self.enfriamiento
        ):
            self._estado = self.MEDIO_ABIERTO
            self._sonda = False
        return self._estado

    def estado(self):
        with self._lock:
            return self._transicionar()

    def permitir(self):
        with self._lock:
            estado = self._transicionar()
            if estado == self.ABIERTO:
                return False
            if estado == self.MEDIO_ABIERTO:
                if self._sonda:
                    return False
                self._sonda = True
            return True

    def cancelar(self):
        """Libera la sonda si el llamador no llegó a ejecutar la operación."""
        with self._lock:
            self._sonda = False

    def exito(self):
        with self._lock:
            self._estado = self.CERRADO
            self._fallos = 0
            self._sonda = False
            self._abierto_en = None

    def fallo(self):
        with self._lock:
            self._sonda = False
            self._fallos += 1
            if self._estado == self.MEDIO_ABIERTO or self._fallos >= self.umbral:
                self._estado = self.ABIERTO
                self._abierto_en = self._reloj()

    def instantanea(self):
        with self._lock:
            estado = self._transicionar()
            abierto_hace = 0.0
            if estado == self.ABIERTO and self._abierto_en is not None:
                abierto_hace = round(self._reloj() - self._abierto_en, 3)
            return {
                "estado": estado,
                "fallos": self._fallos,
                "abierto_hace": abierto_hace,
                "enfriamiento": self.enfriamiento,
            }
