"""Núcleo puro de la evaluación final del contrafactual."""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from superbot.ia.cartera import calcular_tamano_entrada
from superbot.ia.madurez import CORTE
from superbot.ia.medicion import coste_orden_eur

CAPITAL_EUR = 5_000.0
REPLICAS = 10_000
SEMILLA = 20261124
SEMANAS_POR_BLOQUE = 4


@dataclass(frozen=True)
class Caso:
    decision_id: int
    symbol: str
    market: str
    currency: str
    grupo: str
    sesion_entrada: date
    sesion_salida: Optional[date]
    entrada: float
    salida: Optional[float]
    stop: float
    score: float
    target_open: datetime
    estado: str


@dataclass(frozen=True)
class SeriePrecios:
    fechas: Tuple[date, ...]
    aperturas: Tuple[float, ...]
    cierres: Tuple[float, ...]
    splits: Tuple[Tuple[date, float], ...] = ()


@dataclass(frozen=True)
class Observacion:
    sesion: date
    exceso: float
    nocional: float


@dataclass(frozen=True)
class Intervalo:
    bajo: Optional[float]
    alto: Optional[float]
    validas: int
    descartadas: int


@dataclass(frozen=True)
class OperacionCartera:
    decision_id: int
    symbol: str
    entrada: date
    salida: Optional[date]
    estado: str
    pnl_eur: Optional[float]


@dataclass(frozen=True)
class ResultadoCartera:
    exceso_acumulado: float
    patrimonio_final: float
    operaciones: Tuple[OperacionCartera, ...]

    def como_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fx_de(fechas: Sequence[date], valores: Sequence[float], dia: date, currency: str = "USD") -> Optional[float]:
    """EUR por unidad de divisa a partir de un par EUR{divisa}=X."""

    if currency.upper() == "EUR":
        return 1.0
    indice = bisect.bisect_right(fechas, dia) - 1
    limite = dia - timedelta(days=5)
    while indice >= 0 and fechas[indice] >= limite:
        valor = float(valores[indice])
        if math.isfinite(valor) and valor > 0:
            return 1.0 / valor
        indice -= 1
    return None


def exceso_neto(
    caso: Caso, fx_entrada: float, fx_salida: float, serie_ref: SeriePrecios,
) -> Tuple[float, float]:
    if caso.salida is None or caso.sesion_salida is None:
        raise ValueError("el caso abierto no pertenece a la métrica")
    unidades, nocional = calcular_tamano_entrada(CAPITAL_EUR, caso.entrada, caso.stop, fx_entrada)
    if unidades <= 0 or nocional <= 0:
        raise ValueError("tamaño de entrada inválido")
    salida_eur = unidades * caso.salida * fx_salida
    costes = coste_orden_eur(nocional) + coste_orden_eur(salida_eur)
    retorno = (salida_eur - nocional - costes) / nocional
    filas = tuple(zip(serie_ref.fechas, serie_ref.aperturas, serie_ref.cierres))
    aperturas = [(dia, apertura) for dia, apertura, _cierre in filas if dia >= caso.sesion_entrada]
    cierres = [(dia, cierre) for dia, _apertura, cierre in filas if dia <= caso.sesion_salida]
    referencia = 0.0
    if aperturas and cierres and aperturas[0][0] <= cierres[-1][0]:
        apertura, cierre = float(aperturas[0][1]), float(cierres[-1][1])
        if not (math.isfinite(apertura) and apertura > 0 and math.isfinite(cierre) and cierre > 0):
            raise ValueError("referencia no finita")
        referencia = (cierre - apertura - 0.001 * apertura - 0.001 * cierre) / apertura
    return retorno - referencia, nocional


def coste_api_por_aprobado(euros_api: float, aprobados: Sequence[Observacion]) -> float:
    nocional = sum(caso.nocional for caso in aprobados)
    if nocional <= 0:
        raise ValueError("no hay nocional aprobado")
    return euros_api / nocional


def estimador(aprobados: Sequence[Observacion], descartados: Sequence[Observacion], coste_api: float) -> float:
    if not aprobados or not descartados:
        raise ValueError("hacen falta los dos grupos")
    return sum(c.exceso - coste_api for c in aprobados) / len(aprobados) - sum(
        c.exceso for c in descartados
    ) / len(descartados)


def bloque_de(sesion: date) -> int:
    lunes = CORTE.date() - timedelta(days=CORTE.date().weekday())
    distancia = (sesion - lunes).days
    if distancia < 0:
        raise ValueError("sesión anterior al corte")
    return distancia // (7 * SEMANAS_POR_BLOQUE)


def intervalo_bloques(
    aprobados: Sequence[Observacion], descartados: Sequence[Observacion], coste_api: float, *,
    replicas: int = REPLICAS, semilla: int = SEMILLA,
) -> Intervalo:
    por_bloque_a: Dict[int, list[Observacion]] = {}
    por_bloque_d: Dict[int, list[Observacion]] = {}
    for destino, casos in ((por_bloque_a, aprobados), (por_bloque_d, descartados)):
        for caso in casos:
            bloque = bloque_de(caso.sesion)
            destino.setdefault(bloque, []).append(caso)
    bloques = sorted(set(por_bloque_a) | set(por_bloque_d))
    if not bloques:
        return Intervalo(None, None, 0, replicas)
    azar = random.Random(semilla)
    valores: list[float] = []
    descartadas_n = 0
    for _ in range(replicas):
        elegidos = [bloques[azar.randrange(len(bloques))] for _ in bloques]
        muestra_a = [caso for bloque in elegidos for caso in por_bloque_a.get(bloque, ())]
        muestra_d = [caso for bloque in elegidos for caso in por_bloque_d.get(bloque, ())]
        if not muestra_a or not muestra_d:
            descartadas_n += 1
        else:
            valores.append(estimador(muestra_a, muestra_d, coste_api))
    if descartadas_n > replicas * 0.05 or not valores:
        return Intervalo(None, None, len(valores), descartadas_n)
    valores.sort()
    n = len(valores)
    return Intervalo(valores[math.floor(0.025 * n)], valores[math.ceil(0.975 * n) - 1], n, descartadas_n)


def veredicto(ic: Intervalo | Tuple[float, float] | None) -> str:
    if ic is None:
        return "INCONCLUSO"
    bajo, alto = (ic.bajo, ic.alto) if isinstance(ic, Intervalo) else ic
    if bajo is None or alto is None:
        return "INCONCLUSO"
    if bajo > 0:
        return "LA IA APORTA"
    if alto <= 0:
        return "LA IA NO APORTA"
    return "INCONCLUSO"


@dataclass(frozen=True)
class _Posicion:
    caso: Caso
    unidades: float
    nocional: float
    coste_entrada: float


def _precio_original(serie: SeriePrecios, dia: date) -> Optional[float]:
    indice = bisect.bisect_right(serie.fechas, dia) - 1
    while indice >= 0:
        fecha = serie.fechas[indice]
        precio = float(serie.cierres[indice])
        if math.isfinite(precio) and precio > 0:
            for fecha_split, ratio in serie.splits:
                if fecha_split > fecha:
                    precio *= ratio
            return precio
        indice -= 1
    return None


def _ultimo_cierre(serie: SeriePrecios, dia: date) -> Optional[float]:
    indice = bisect.bisect_right(serie.fechas, dia) - 1
    while indice >= 0:
        precio = float(serie.cierres[indice])
        if math.isfinite(precio) and precio > 0:
            return precio
        indice -= 1
    return None


def carteras(
    casos: Sequence[Caso], series: Mapping[str, SeriePrecios],
    fx: Mapping[str, Tuple[Sequence[date], Sequence[float]]], referencia: SeriePrecios,
    api_por_dia: Mapping[date, float], fin: date,
) -> Dict[str, ResultadoCartera]:
    return {
        "sin_ia": _cartera(casos, series, fx, referencia, {}, fin, solo_aprobadas=False),
        "con_ia": _cartera(casos, series, fx, referencia, api_por_dia, fin, solo_aprobadas=True),
    }


def _cartera(
    casos: Sequence[Caso], series: Mapping[str, SeriePrecios],
    fx: Mapping[str, Tuple[Sequence[date], Sequence[float]]], referencia: SeriePrecios,
    api_por_dia: Mapping[date, float], fin: date, *, solo_aprobadas: bool,
) -> ResultadoCartera:
    candidatas = [c for c in casos if c.sesion_entrada <= fin and (not solo_aprobadas or c.grupo == "COMPRAR")]
    dias = sorted(
        {d for c in candidatas for d in (c.sesion_entrada, c.sesion_salida) if d is not None and d <= fin}
        | set(referencia.fechas) | set(api_por_dia) | {d for serie in series.values() for d in serie.fechas}
    )
    dias = [d for d in dias if CORTE.date() <= d <= fin]
    entradas: Dict[date, list[Caso]] = {}
    for caso in candidatas:
        entradas.setdefault(caso.sesion_entrada, []).append(caso)
    cash, pendientes, posiciones = CAPITAL_EUR, {}, {}  # type: float, Dict[date, float], Dict[str, _Posicion]
    operaciones: list[OperacionCartera] = []
    patrimonio_previo, exposicion_previa, exceso = CAPITAL_EUR, 0.0, 0.0
    cierre_ref_previo: Optional[float] = None

    def cambio(caso: Caso, dia: date) -> Optional[float]:
        if caso.currency == "EUR":
            return 1.0
        fechas, valores = fx[caso.currency]
        return fx_de(fechas, valores, dia, caso.currency)

    for dia in dias:
        cash += pendientes.pop(dia, 0.0)
        cash -= api_por_dia.get(dia, 0.0)
        for caso in sorted(entradas.get(dia, ()), key=lambda c: (c.target_open, -c.score, c.symbol)):
            if caso.symbol in posiciones:
                continue
            tasa = cambio(caso, dia)
            if tasa is None:
                raise ValueError(f"falta FX de {caso.currency} para {dia}")
            unidades, nocional = calcular_tamano_entrada(CAPITAL_EUR, caso.entrada, caso.stop, tasa)
            coste = coste_orden_eur(nocional)
            if unidades <= 0 or nocional + coste > cash:
                continue
            cash -= nocional + coste
            posiciones[caso.symbol] = _Posicion(caso, unidades, nocional, coste)
        for symbol, posicion in list(posiciones.items()):
            caso = posicion.caso
            if caso.sesion_salida is None or caso.salida is None or caso.sesion_salida != dia:
                continue
            tasa = cambio(caso, dia)
            if tasa is None:
                raise ValueError(f"falta FX de {caso.currency} para {dia}")
            importe = posicion.unidades * caso.salida * tasa
            coste = coste_orden_eur(importe)
            siguiente = next((d for d in dias if d > dia), None)
            disponibilidad = siguiente if siguiente is not None else fin + timedelta(days=1)
            pendientes[disponibilidad] = pendientes.get(disponibilidad, 0.0) + importe - coste
            operaciones.append(OperacionCartera(
                caso.decision_id, symbol, caso.sesion_entrada, dia, caso.estado,
                importe - coste - posicion.nocional - posicion.coste_entrada,
            ))
            del posiciones[symbol]
        exposicion = 0.0
        for posicion in posiciones.values():
            caso = posicion.caso
            precio = _precio_original(series[caso.symbol], dia)
            tasa = cambio(caso, dia)
            if precio is None or tasa is None:
                raise ValueError(f"falta valoración de {caso.symbol} para {dia}")
            exposicion += posicion.unidades * precio * tasa
        patrimonio = cash + sum(pendientes.values()) + exposicion
        cierre_ref = _ultimo_cierre(referencia, dia)
        rendimiento_ref = 0.0
        if cierre_ref is not None and cierre_ref_previo is not None:
            rendimiento_ref = cierre_ref / cierre_ref_previo - 1.0
        exceso += patrimonio - patrimonio_previo - exposicion_previa * rendimiento_ref
        patrimonio_previo, exposicion_previa = patrimonio, exposicion
        if cierre_ref is not None:
            cierre_ref_previo = cierre_ref
    for posicion in posiciones.values():
        operaciones.append(OperacionCartera(
            posicion.caso.decision_id, posicion.caso.symbol, posicion.caso.sesion_entrada, None, "ABIERTA", None,
        ))
    return ResultadoCartera(exceso, patrimonio_previo, tuple(operaciones))


def secundario(casos: Sequence[Caso], retornos_r: Mapping[int, float], no_ejecutables: Mapping[str, int]) -> Dict[str, Any]:
    salida: Dict[str, Any] = {}
    for grupo in ("COMPRAR", "DESCARTAR"):
        valores = [retornos_r[c.decision_id] for c in casos if c.grupo == grupo and c.decision_id in retornos_r]
        salida[grupo] = {
            "media_r": None if not valores else sum(valores) / len(valores),
            "proporcion_positiva": None if not valores else sum(v > 0 for v in valores) / len(valores),
            "stops": sum(c.estado == "STOP" for c in casos if c.grupo == grupo),
            "no_ejecutables": no_ejecutables.get(grupo, 0),
        }
    return salida


__all__ = [
    "CAPITAL_EUR", "REPLICAS", "SEMILLA", "Caso", "Intervalo", "Observacion", "OperacionCartera",
    "ResultadoCartera", "SeriePrecios", "bloque_de", "carteras", "coste_api_por_aprobado", "estimador",
    "exceso_neto", "fx_de", "intervalo_bloques", "secundario", "veredicto",
]
