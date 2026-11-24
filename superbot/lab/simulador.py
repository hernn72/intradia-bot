"""Cartera simulada con las reglas de Superbot IA y variantes de entrada y salida (D-84 §5).

Puro: recibe series y fichas ya calculadas y no lee bases, red ni reloj. No usa ningún resultado del
contrafactual. El gate, el stop y el tamaño son los del motor real; las variantes están en
``docs/superbot-ia/SIMULACIONES-REGLAS.md``.
"""

from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from superbot.ia.cartera import calcular_tamano_entrada, evaluar_gate_apertura, evaluar_stop
from superbot.ia.medicion import coste_orden_eur

CAPITAL_EUR = 5_000.0
ESPERA_RECOMPRA = 5
TOP_POR_PLAZA = 5
SMA_HOLGURA = 0.02

ENTRADA_APERTURA = "APERTURA"
ENTRADA_LIMITE = "LIMITE"


@dataclass(frozen=True)
class Regla:
    nombre: str
    entrada: str = ENTRADA_APERTURA
    # Margen sobre el precio máximo actual, en ATR. Cero es la regla actual. Siempre hay un tope.
    margen_atr: float = 0.0
    score_compra: float = 60.0
    score_venta: float = 60.0
    objetivo: bool = False
    stop_movil_atr: Optional[float] = None
    max_sesiones: Optional[int] = None


BASE = Regla("BASE")
VARIANTES: Tuple[Regla, ...] = (
    Regla("E1_MARGEN_025", margen_atr=0.25),
    Regla("E2_MARGEN_050", margen_atr=0.50),
    Regla("E3_LIMITE_DIA", entrada=ENTRADA_LIMITE),
    Regla("H1_60_55", score_venta=55.0),
    Regla("H2_65_60", score_compra=65.0),
    Regla("H3_65_55", score_compra=65.0, score_venta=55.0),
    Regla("X1_OBJETIVO", objetivo=True),
    Regla("X2_STOP_MOVIL", stop_movil_atr=2.0),
    Regla("X3_20_SESIONES", max_sesiones=20),
)


@dataclass(frozen=True)
class Serie:
    symbol: str
    market: str
    currency: str
    sesiones: Tuple[date, ...]
    apertura: Tuple[float, ...]
    maximo: Tuple[float, ...]
    minimo: Tuple[float, ...]
    cierre: Tuple[float, ...]
    # Minuto UTC de apertura de su plaza: el efectivo se reparte en ese orden, como en producción.
    minuto_apertura: int = 0


@dataclass(frozen=True)
class Ficha:
    """Lo que se sabe de un valor al cierre de una sesión."""

    score: float
    cierre: float
    stop: float
    target2: float
    entry_max: float
    min_rr: float
    rr: float
    atr: float
    invalidacion: Optional[float]
    sma: Optional[float]


@dataclass
class Posicion:
    symbol: str
    unidades: float
    coste_eur: float
    entrada: float
    sesion: date
    stop: float
    stop_inicial: float
    target2: float
    atr: float
    invalidacion: Optional[float]
    maximo_cierre: float
    sesiones: int = 0
    salida_pendiente: Optional[str] = None


@dataclass(frozen=True)
class Operacion:
    symbol: str
    entrada: date
    salida: date
    motivo: str
    pnl_eur: float


@dataclass
class Resultado:
    regla: str
    dias: List[date] = field(default_factory=list)
    equity: List[float] = field(default_factory=list)
    exposicion: List[float] = field(default_factory=list)
    exceso: List[float] = field(default_factory=list)
    operaciones: List[Operacion] = field(default_factory=list)
    candidatas: int = 0
    rechazadas: Dict[str, int] = field(default_factory=dict)
    costes_eur: float = 0.0
    abiertas: int = 0

    def caida_maxima(self) -> float:
        maximo, peor = CAPITAL_EUR, 0.0
        for valor in self.equity:
            maximo = max(maximo, valor)
            peor = min(peor, valor / maximo - 1.0)
        return peor


def _ultimo(fechas: Sequence[date], valores: Sequence[float], dia: date) -> Optional[float]:
    i = bisect.bisect_right(fechas, dia) - 1
    return None if i < 0 else valores[i]


def precio_entrada(regla: Regla, ficha: Ficha, apertura: float, minimo: float) -> Tuple[Optional[float], str]:
    """Precio al que entra, o ``None`` y el motivo. Nunca por encima del tope de la regla."""

    if regla.entrada == ENTRADA_LIMITE:
        # Orden limitada al precio máximo actual, viva solo durante la sesión objetivo.
        if minimo > ficha.entry_max:
            return None, "LIMITE_NO_TOCADO"
        precio = min(apertura, ficha.entry_max)
        gate = evaluar_gate_apertura(precio, ficha.stop, ficha.target2, ficha.entry_max, ficha.min_rr)
    elif regla.margen_atr > 0:
        tope = ficha.entry_max + regla.margen_atr * ficha.atr
        # Con el objetivo fijo, pagar más baja el ratio: se exige el que queda justo en el tope.
        minimo_rr = None if tope >= ficha.target2 else min(ficha.min_rr, (ficha.target2 - tope) / (tope - ficha.stop))
        gate = evaluar_gate_apertura(apertura, ficha.stop, ficha.target2, tope, minimo_rr)
    else:
        gate = evaluar_gate_apertura(apertura, ficha.stop, ficha.target2, ficha.entry_max, ficha.min_rr)
    return (gate.eff, "") if gate.aprobado and gate.eff is not None else (None, str(gate.motivo))


def simular(
    series: Mapping[str, Serie], fichas: Mapping[str, Mapping[date, Ficha]],
    fx: Mapping[str, Tuple[Sequence[date], Sequence[float]]], referencia: Tuple[Sequence[date], Sequence[float]],
    regla: Regla, inicio: date, fin: date,
) -> Resultado:
    """Recorre las sesiones en orden. ``fx`` es EUR por unidad de divisa; ``EUR`` no hace falta.

    Dentro de un día, el orden del motor real: entradas con el efectivo de antes, stops y ventas
    pendientes a la apertura. Las decisiones se toman al cierre y se ejecutan en la sesión siguiente.
    """

    salida = Resultado(regla.nombre)
    indice = {s: {d: i for i, d in enumerate(serie.sesiones)} for s, serie in series.items()}
    dias = sorted({d for serie in series.values() for d in serie.sesiones if inicio <= d <= fin})
    cash, posiciones = CAPITAL_EUR, {}  # type: float, Dict[str, Posicion]
    pendientes: Dict[str, Tuple[date, Ficha]] = {}
    vendidas: Dict[str, int] = {}
    equity_previa, exposicion_previa = CAPITAL_EUR, 0.0
    ref_previa = _ultimo(referencia[0], referencia[1], inicio)

    def tasa(currency: str, dia: date) -> Optional[float]:
        return 1.0 if currency == "EUR" else _ultimo(*fx[currency], dia)

    def vender(posicion: Posicion, precio: float, dia: date, motivo: str) -> None:
        nonlocal cash
        importe = posicion.unidades * precio * (tasa(series[posicion.symbol].currency, dia) or 0.0)
        coste = coste_orden_eur(importe)
        cash += importe - coste
        salida.costes_eur += coste
        salida.operaciones.append(
            Operacion(posicion.symbol, posicion.sesion, dia, motivo, importe - coste - posicion.coste_eur)
        )
        del posiciones[posicion.symbol]
        # La espera de recompra cuenta desde cualquier cierre, también un stop (``_ventas_ia_recientes``).
        vendidas[posicion.symbol] = indice[posicion.symbol][dia]

    for dia in dias:
        # 1. Entradas pendientes de hoy, por apertura y símbolo, con el efectivo de antes de cualquier venta.
        for symbol, (sesion, ficha) in sorted(pendientes.items(), key=lambda x: (series[x[0]].minuto_apertura, x[0])):
            if sesion != dia:
                continue
            del pendientes[symbol]
            serie, i = series[symbol], indice[symbol][dia]
            precio, motivo = precio_entrada(regla, ficha, serie.apertura[i], serie.minimo[i])
            cambio = tasa(serie.currency, dia)
            if precio is None or cambio is None:
                salida.rechazadas[motivo or "SIN_FX"] = salida.rechazadas.get(motivo or "SIN_FX", 0) + 1
                continue
            unidades, nocional = calcular_tamano_entrada(equity_previa, precio, ficha.stop, cambio)
            coste = coste_orden_eur(nocional)
            if unidades <= 0 or nocional + coste > cash:
                salida.rechazadas["SIN_EFECTIVO"] = salida.rechazadas.get("SIN_EFECTIVO", 0) + 1
                continue
            cash -= nocional + coste
            salida.costes_eur += coste
            posiciones[symbol] = Posicion(
                symbol, unidades, nocional + coste, precio, dia, ficha.stop, ficha.stop, ficha.target2, ficha.atr,
                ficha.invalidacion, serie.cierre[i],
            )
        # 2. Stops, 3. ventas pendientes a la apertura y 4. objetivo. El stop manda si el día toca ambos.
        for symbol in sorted(posiciones):
            posicion = posiciones[symbol]
            i_hoy = indice[symbol].get(dia)
            if i_hoy is None:
                continue
            serie = series[symbol]
            posicion.sesiones += 1
            stop = evaluar_stop(posicion.stop, serie.apertura[i_hoy], serie.minimo[i_hoy])
            if stop.disparado and stop.precio_fill is not None:
                # En la sesión de entrada la apertura puede ser anterior a la compra (orden limitada).
                vender(posicion, min(stop.precio_fill, posicion.entrada) if posicion.sesion == dia else stop.precio_fill,
                       dia, "STOP")
            elif posicion.salida_pendiente is not None:
                vender(posicion, serie.apertura[i_hoy], dia, posicion.salida_pendiente)
            elif regla.objetivo and posicion.sesion != dia and serie.maximo[i_hoy] >= posicion.target2:
                vender(posicion, max(serie.apertura[i_hoy], posicion.target2), dia, "OBJETIVO")
        # 5. Cierre: lo que se decide hoy para la sesión siguiente.
        for symbol, posicion in posiciones.items():
            i_hoy = indice[symbol].get(dia)
            if i_hoy is None:
                continue
            cierre, ficha_hoy = series[symbol].cierre[i_hoy], fichas.get(symbol, {}).get(dia)
            posicion.maximo_cierre = max(posicion.maximo_cierre, cierre)
            if regla.stop_movil_atr is not None:
                posicion.stop = max(posicion.stop, posicion.maximo_cierre - regla.stop_movil_atr * posicion.atr)
            if ficha_hoy is not None and ficha_hoy.score < regla.score_venta:
                posicion.salida_pendiente = "PREDICADO_SCORE"
            elif posicion.invalidacion is not None and cierre < posicion.invalidacion:
                posicion.salida_pendiente = "PREDICADO_INVALIDACION"
            elif ficha_hoy is not None and ficha_hoy.sma is not None and cierre < ficha_hoy.sma * (1 - SMA_HOLGURA):
                posicion.salida_pendiente = "PREDICADO_SMA"
            elif regla.max_sesiones is not None and posicion.sesiones >= regla.max_sesiones:
                posicion.salida_pendiente = "TIEMPO"
        por_plaza: Dict[str, List[Tuple[str, Ficha, date]]] = {}
        for symbol, serie in series.items():
            i_hoy = indice[symbol].get(dia)
            candidata = fichas.get(symbol, {}).get(dia)
            if i_hoy is None or candidata is None or candidata.score < regla.score_compra:
                continue
            if symbol in posiciones or symbol in pendientes or i_hoy + 1 >= len(serie.sesiones):
                continue
            if symbol in vendidas and i_hoy - vendidas[symbol] < ESPERA_RECOMPRA:
                continue
            if serie.sesiones[i_hoy + 1] <= fin:
                por_plaza.setdefault(serie.market, []).append((symbol, candidata, serie.sesiones[i_hoy + 1]))
        for lista in por_plaza.values():
            for symbol, candidata, siguiente in sorted(lista, key=lambda x: (-x[1].score, -x[1].rr, x[0]))[:TOP_POR_PLAZA]:
                pendientes[symbol] = (siguiente, candidata)
                salida.candidatas += 1
        # 6. Valor a mercado y exceso sobre la referencia con la exposición del cierre anterior.
        exposicion = 0.0
        for posicion in posiciones.values():
            serie = series[posicion.symbol]
            precio_hoy = _ultimo(serie.sesiones, serie.cierre, dia)
            exposicion += posicion.unidades * (precio_hoy or 0.0) * (tasa(serie.currency, dia) or 0.0)
        equity = cash + exposicion
        ref = _ultimo(referencia[0], referencia[1], dia)
        rendimiento = 0.0 if ref is None or ref_previa is None else ref / ref_previa - 1.0
        salida.dias.append(dia)
        salida.equity.append(equity)
        salida.exposicion.append(exposicion)
        salida.exceso.append(equity - equity_previa - exposicion_previa * rendimiento)
        equity_previa, exposicion_previa = equity, exposicion
        ref_previa = ref if ref is not None else ref_previa
    salida.abiertas = len(posiciones)
    return salida


def intervalo_diferencia(
    variante: Sequence[float], base: Sequence[float], *, nivel: float, bloque: int = 20, replicas: int = 10_000,
    semilla: int = 20261124,
) -> Tuple[float, float, float]:
    """Diferencia acumulada de exceso (EUR) e intervalo por bloques móviles circulares de los mismos días."""

    if len(variante) != len(base) or not base:
        raise ValueError("las dos series tienen que cubrir los mismos días")
    dif = [v - b for v, b in zip(variante, base)]
    n, azar = len(dif), random.Random(semilla)
    doble = dif + dif
    acumulada = [0.0]
    for valor in doble:
        acumulada.append(acumulada[-1] + valor)
    sumas = []
    for _ in range(replicas):
        total, quedan = 0.0, n
        while quedan > 0:
            largo, desde = min(bloque, quedan, n), azar.randrange(n)
            total += acumulada[desde + largo] - acumulada[desde]
            quedan -= largo
        sumas.append(total)
    sumas.sort()
    cola = (1.0 - nivel) / 2.0
    return sum(dif), sumas[int(cola * replicas)], sumas[min(replicas - 1, int((1.0 - cola) * replicas))]


__all__ = [
    "BASE", "CAPITAL_EUR", "ENTRADA_APERTURA", "ENTRADA_LIMITE", "VARIANTES", "Ficha", "Operacion", "Regla", "Resultado",
    "Serie", "intervalo_diferencia", "precio_entrada", "simular",
]
