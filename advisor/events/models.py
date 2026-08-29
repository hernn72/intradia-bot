"""Un evento de mercado con fecha conocida de antemano.

El asesor distingue dos cosas que hasta ahora confundía en una sola: la
*huella* de un catalizador en el precio (volumen anormal, hueco, ruptura),
que ya detecta, y el *catalizador* en sí, que hasta ahora no conocía. Este
módulo cubre lo segundo, pero solo para lo que es previsible con fecha:
resultados empresariales y decisiones de banco central.

Deliberadamente NO cubre noticias: una noticia no tiene fecha futura y su
relevancia no es verificable con una regla, así que entra por otro camino.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# Un evento de banco central afecta a todo el universo; unos resultados,
# solo al activo que los publica.
ALCANCE_GLOBAL = "global"
ALCANCE_ACTIVO = "activo"

TIPO_RESULTADOS = "resultados"
TIPO_BANCO_CENTRAL = "banco_central"


@dataclass(frozen=True)
class MarketEvent:
    """Un evento con fecha, su alcance y de dónde salió la fecha."""

    fecha: date
    tipo: str
    alcance: str
    titulo: str
    fuente: str
    simbolo: Optional[str] = None
    detalle: Optional[str] = None
    # Una fecha estimada por el proveedor de datos no vale lo mismo que una
    # publicada por el banco central: el informe debe poder decirlo.
    confirmada: bool = True

    def dias_hasta(self, desde: date) -> int:
        """Días naturales hasta el evento. Negativo si ya ocurrió."""
        return (self.fecha - desde).days

    @property
    def etiqueta_fuente(self) -> str:
        return self.fuente if self.confirmada else f"{self.fuente} (fecha estimada)"
