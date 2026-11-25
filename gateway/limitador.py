"""Rate limiting deslizante en memoria, por cliente."""

import threading
import time


class Limitador:
    def __init__(self, limite: int, ventana: int):
        self.limite = limite
        self.ventana = ventana
        self._eventos = {}
        self._cerrojo = threading.Lock()

    def permitir(self, cliente: str, ahora: float = None) -> bool:
        ahora = time.time() if ahora is None else ahora
        with self._cerrojo:
            eventos = [
                instante for instante in self._eventos.get(cliente, [])
                if ahora - instante < self.ventana
            ]
            if len(eventos) >= self.limite:
                self._eventos[cliente] = eventos
                return False
            eventos.append(ahora)
            self._eventos[cliente] = eventos
            return True
