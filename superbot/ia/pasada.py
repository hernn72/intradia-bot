"""Una pasada de decisión: del análisis a las decisiones registradas.

Nada de aquí crea órdenes. Cada fallo se resuelve hacia el lado seguro: sin compra
y con la posición mantenida. Sin fila en ``ia_decision`` no hay decisión.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from advisor.config import AdvisorConfig
from advisor.data.calendars import expected_sessions
from advisor.data.market_data import MarketDataProvider
from advisor.universe.models import Asset, Universe
from superbot.ia import comite
from superbot.ia.asesores import (
    ERROR_LLAMADA,
    OK,
    OPORTUNIDAD,
    RIESGO,
    SIN_CLIENTE,
    SIN_PRESUPUESTO,
    ClienteIA,
    cargar_prompt,
    esquema_de,
    validar_dictamen,
    version_prompt,
    voto_de,
)
from superbot.ia.datos import Analisis, Contexto, ProveedorCrudo, analizar, cargar_contexto
from superbot.ia.paquete import (
    COMPRA,
    POSICION,
    EstadoCartera,
    Paquete,
    PaqueteInvalido,
    PosicionIA,
    canonico,
    validar_causal,
)
from superbot.ia.politica import SCHEMA_VERSION, PoliticaIA
from superbot.ia.predicados import DatosPredicado, evaluar, hay_disparador
from superbot.ia.registro import PresupuestoAgotado, RegistroIA, ventana_cache

logger = logging.getLogger(__name__)

BROKER_VERIFICADO = "yes"


@dataclass
class ResultadoPasada:
    pasada_id: int
    status: str
    compras: List[str] = field(default_factory=list)
    ventas: List[str] = field(default_factory=list)
    incidencias: List[str] = field(default_factory=list)


def code_sha(repo: Path = Path(__file__).resolve().parents[2]) -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()

    try:
        sha = git("rev-parse", "HEAD")
        return sha + ("+cambios" if git("status", "--porcelain", "--untracked-files=no") else "")
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def _observaciones(paquete: Paquete) -> str:
    return canonico([
        {
            "fuente": o.fuente, "symbol": o.symbol, "session": o.session, "available_at": o.available_at.isoformat(),
            "observed_at": o.observed_at.isoformat(), "hash": o.hash,
        }
        for o in paquete.observaciones
    ])


def _redondeado(value: Any) -> Any:
    return round(float(value), 4) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def _datos_base(analisis: Analisis, contexto: Contexto, cartera: EstadoCartera, tipo: str) -> Dict[str, Any]:
    op = analisis.oportunidad
    s, n, m, asset = op.snapshot, op.levels, contexto.mercado, analisis.asset
    tecnico = {
        "precio": s.price, "ema_rapida": s.ema_fast, "ema_lenta": s.ema_slow, "sma_larga": s.sma_long, "rsi": s.rsi,
        "atr": s.atr, "macd_hist": s.macd_hist, "volumen_relativo": s.volume_ratio, "hueco_pct": s.gap_pct,
        "retorno_corto_pct": s.return_short, "retorno_medio_pct": s.return_medium, "retorno_largo_pct": s.return_long,
        "volatilidad_pct": s.volatility_pct, "fortaleza_relativa": s.relative_strength, "barras": s.bars,
    }
    return {
        "tipo": tipo,
        # Sin el nombre libre: en el mensaje solo van campos normalizados, nada interpretable como orden.
        "activo": {
            "valor": asset.symbol, "clase": asset.asset_class, "region": asset.region,
            "plaza": analisis.market, "divisa": asset.currency,
        },
        "sesion_senal": analisis.signal_session.isoformat(),
        "tecnico": {k: _redondeado(v) for k, v in tecnico.items()},
        "niveles_referencia": {
            "entrada_maxima": _redondeado(n.entry_max), "objetivo_1": _redondeado(n.target1),
            "objetivo_2": _redondeado(n.target2), "ratio_beneficio_riesgo": _redondeado(n.rr_ratio),
            "invalidacion": _redondeado(n.invalidation_level),
        },
        "score": {
            "valor": round(op.score.value, 2), "modelo": op.score.model_version,
            "dimensiones_sin_datos": list(op.score.missing_dimensions),
        },
        "contexto": {
            "fuente": m.source, "estado": m.label, "motivo": m.reason, "vix": _redondeado(m.vix_value),
            "vix_umbral": _redondeado(m.vix_threshold), "tendencia_alcista": m.trend_up,
            "asia_pct": _redondeado(m.asia_change_pct),
        },
        "cartera": cartera.resumen(),
    }


def _paquete(analisis: Analisis, contexto: Contexto, instante: datetime, tipo: str, datos: Mapping[str, Any]) -> Paquete:
    return Paquete(
        tipo=tipo, symbol=analisis.asset.symbol, market=analisis.market, signal_session=analisis.signal_session,
        target_session=analisis.target_session, target_open=analisis.target_open, decision_ts=instante, datos=datos,
        observaciones=(*analisis.observaciones, *contexto.observaciones),
    )


def motivo_no_elegible(
    analisis: Analisis, cartera: EstadoCartera, politica: PoliticaIA, instante: datetime
) -> Optional[str]:
    op, asset = analisis.oportunidad, analisis.asset
    if instante >= analisis.target_open:
        return "APERTURA_PASADA"
    if op.score.value < politica.score_min:
        return "SCORE_BAJO"
    if asset.trade_republic != BROKER_VERIFICADO:
        return "BROKER_NO_VERIFICADO"
    calidad = op.data_freshness.data_quality if op.data_freshness is not None else None
    if calidad is None or not calidad.execution_readiness or not calidad.indicator_readiness:
        return "CALIDAD_DE_DATO"
    if asset.symbol in {p.symbol for p in cartera.posiciones} or asset.symbol in cartera.ordenes_pendientes:
        return "YA_EN_CARTERA"
    vendida = cartera.ventas_ia.get(asset.symbol)
    if vendida is not None:
        sesiones = expected_sessions(analisis.market, vendida + timedelta(days=1), analisis.signal_session)
        if len(sesiones) < politica.espera_recompra_sesiones:
            return "ESPERA_RECOMPRA"
    return None


def elegir_por_plaza(candidatas: List[Analisis], politica: PoliticaIA) -> List[Analisis]:
    por_plaza: Dict[str, List[Analisis]] = {}
    for analisis in candidatas:
        por_plaza.setdefault(analisis.market, []).append(analisis)
    elegidas: List[Analisis] = []
    for plaza in sorted(por_plaza):
        orden = sorted(
            por_plaza[plaza],
            key=lambda a: (-a.oportunidad.score.value, -(a.oportunidad.levels.rr_ratio or 0.0), a.asset.symbol),
        )
        elegidas.extend(orden[: politica.top_por_plaza])
    return elegidas


class Motor:
    """Estado de una pasada: registro, cliente y reloj inyectados."""

    def __init__(
        self, registro: RegistroIA, cliente: Optional[ClienteIA], politica: PoliticaIA, pasada_id: int, instante: datetime,
        reloj: Callable[[], datetime],
    ) -> None:
        self.registro = registro
        self.cliente = cliente
        self.politica = politica
        self.pasada_id = pasada_id
        self.instante = instante
        self.reloj = reloj

    def _guardar(self, asesor: str, paquete: Paquete, estado: str, **extra: Any) -> None:
        self.registro.guardar_llamada(
            pasada_id=self.pasada_id, asesor=asesor, provider="anthropic", prompt_version=version_prompt(asesor),
            schema_version=SCHEMA_VERSION, input_hash=paquete.input_hash,
            input_source_ids=canonico(paquete.input_source_ids), observaciones=_observaciones(paquete),
            analysis_timestamp=self.instante.isoformat(),
            estado=estado, **extra,
        )

    def dictaminar(self, asesor: str, paquete: Paquete) -> Optional[Mapping[str, Any]]:
        """Dictamen válido o ``None``. Toda vía deja su fila en ``ia_llamada``."""

        version = version_prompt(asesor)
        guardada = self.registro.cache(paquete.input_hash, asesor, version, ventana_cache(self.instante, self.politica))
        if guardada is not None:
            self._guardar(
                asesor, paquete, OK, model=self.politica.modelo, respuesta_cruda=guardada.respuesta_cruda,
                salida_validada=canonico(guardada.salida), desde_cache=1,
            )
            return guardada.salida
        if self.cliente is None:
            self._guardar(asesor, paquete, SIN_CLIENTE)
            return None

        system = cargar_prompt(asesor)
        # Un token ocupa al menos un byte: bytes más margen acotan la entrada, y max_tokens la salida.
        esquema = esquema_de(paquete)
        cota = len((system + paquete.mensaje + canonico(esquema)).encode("utf-8")) + self.politica.margen_tokens_entrada
        reserva = self.politica.coste_maximo_eur(cota)
        mes = self.reloj().strftime("%Y-%m")
        try:
            self.registro.reservar(mes, reserva)
        except PresupuestoAgotado as exc:
            self._guardar(asesor, paquete, SIN_PRESUPUESTO, error=str(exc))
            return None
        inicio = time.monotonic()
        try:
            respuesta = self.cliente.llamar(system, paquete.mensaje, esquema)
        except Exception as exc:
            # Una llamada fallida pudo facturarse: se da por gastado lo reservado.
            self.registro.conciliar(mes, reserva, reserva)
            self._guardar(
                asesor, paquete, ERROR_LLAMADA, error=type(exc).__name__, coste_eur=reserva,
                segundos=round(time.monotonic() - inicio, 2),
            )
            return None

        segundos = round(time.monotonic() - inicio, 2)
        coste = self.politica.coste_eur(respuesta.tokens_entrada, respuesta.tokens_salida)
        self.registro.conciliar(mes, reserva, coste)
        estado, dictamen = validar_dictamen(respuesta.texto, paquete, respuesta.stop_reason)
        self._guardar(
            asesor, paquete, estado, model=respuesta.modelo, model_version=respuesta.modelo,
            respuesta_cruda=respuesta.texto, salida_validada=canonico(dictamen) if dictamen is not None else None,
            stop_reason=respuesta.stop_reason, request_id=respuesta.request_id, tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida, coste_eur=coste, segundos=segundos,
        )
        return dictamen

    def registrar(
        self, paquete: Paquete, analisis: Analisis, votos: Mapping[str, Optional[Mapping[str, Any]]],
        resolucion: comite.Resolucion, predicados: Optional[Mapping[str, Optional[bool]]] = None,
        posicion: Optional[PosicionIA] = None,
    ) -> None:
        op = analisis.oportunidad
        apertura = {} if posicion is None else {
            "invalidacion_apertura": posicion.invalidation_level, "sesion_senal_apertura": posicion.signal_session,
            "decision_apertura": posicion.decision_apertura,
        }
        self.registro.guardar_decision(
            clave=paquete.clave, pasada_id=self.pasada_id, symbol=paquete.symbol, market=paquete.market,
            tipo=paquete.tipo, signal_session=paquete.signal_session.isoformat(),
            target_session=paquete.target_session.isoformat(), target_open=paquete.target_open.isoformat(),
            decision_ts=self.instante.isoformat(), input_hash=paquete.input_hash,
            cuantitativo=canonico({
                "score": op.score.value, "score_modelo": op.score.model_version, "accion_asesor": op.accion,
                "rr": op.levels.rr_ratio, "invalidacion": op.levels.invalidation_level, "cierre": analisis.close,
                "sma": analisis.sma, **apertura,
            }),
            votos=canonico(votos), predicados=canonico(predicados) if predicados is not None else None,
            resolucion=resolucion.decision, motivo=resolucion.motivo, prioridad=resolucion.prioridad,
            causa=resolucion.causa,
        )


def _evaluar_compras(
    motor: Motor, elegidas: List[Analisis], contexto: Contexto, cartera: EstadoCartera, resultado: ResultadoPasada
) -> None:
    aprobadas: List[Tuple[str, comite.Resolucion, float]] = []
    for analisis in elegidas:
        symbol = analisis.asset.symbol
        try:
            datos = _datos_base(analisis, contexto, cartera, COMPRA)
            paquete = _paquete(analisis, contexto, motor.instante, COMPRA, datos)
            if motor.registro.ya_decidida(paquete.clave):
                continue
            validar_causal(paquete)
            motor.registro.guardar_paquete(paquete)
            dictamenes = {asesor: motor.dictaminar(asesor, paquete) for asesor in (OPORTUNIDAD, RIESGO)}
            if any(dictamen is None for dictamen in dictamenes.values()):
                # Sin compra y sin decisión: la clave queda libre para reintentar en la pasada siguiente.
                resultado.incidencias.append(f"{symbol}: falta dictamen válido; sin decisión")
                continue
            resolucion = comite.resolver_compra(
                voto_de(OPORTUNIDAD, dictamenes[OPORTUNIDAD]), voto_de(RIESGO, dictamenes[RIESGO])
            )
            motor.registrar(paquete, analisis, dictamenes, resolucion)
        except Exception as exc:
            # Sin registro completo no hay decisión: la compra simplemente no existe.
            resultado.incidencias.append(f"{symbol}: {type(exc).__name__}: {exc}"[:200])
            continue
        if resolucion.decision == comite.COMPRAR:
            aprobadas.append((symbol, resolucion, analisis.oportunidad.score.value))
    resultado.compras = comite.ordenar_compras(aprobadas)


def _evaluar_posiciones(
    motor: Motor, analizadas: Mapping[str, Analisis], contexto: Contexto, cartera: EstadoCartera,
    resultado: ResultadoPasada,
) -> None:
    pendientes: List[
        Tuple[PosicionIA, Paquete, Analisis, Mapping[str, Any], comite.Resolucion, Mapping[str, Optional[bool]]]
    ] = []
    for posicion in cartera.posiciones:
        analisis = analizadas.get(posicion.symbol)
        if analisis is None:
            resultado.incidencias.append(f"{posicion.symbol}: posición sin análisis; se mantiene")
            continue
        if motor.instante >= analisis.target_open:
            continue
        try:
            predicados = evaluar(
                DatosPredicado(analisis.close, analisis.sma, analisis.oportunidad.score.value, posicion.invalidation_level),
                motor.politica,
            )
            if not hay_disparador(predicados):
                continue
            datos = _datos_base(analisis, contexto, cartera, POSICION)
            datos["posicion"] = {
                "fecha_entrada": posicion.entry_date.isoformat(), "sesion_senal": posicion.signal_session.isoformat(),
                "decision_apertura": posicion.decision_apertura,
                "invalidacion_apertura": _redondeado(posicion.invalidation_level),
                "precio_entrada": _redondeado(posicion.entry_price), "stop": _redondeado(posicion.stop),
                "resultado_pct": round(posicion.pnl_pct, 2), "exposicion_pct": round(posicion.exposicion_pct, 2),
            }
            datos["predicados"] = predicados
            paquete = _paquete(analisis, contexto, motor.instante, POSICION, datos)
            if motor.registro.ya_decidida(paquete.clave):
                continue
            validar_causal(paquete)
            motor.registro.guardar_paquete(paquete)
            dictamen = motor.dictaminar(RIESGO, paquete)
            if dictamen is None:
                resultado.incidencias.append(f"{posicion.symbol}: falta dictamen válido; se mantiene")
                continue
            resolucion = comite.resolver_posicion([voto_de(RIESGO, dictamen)], predicados)
        except Exception as exc:
            resultado.incidencias.append(f"{posicion.symbol}: {type(exc).__name__}: {exc}"[:200])
            continue
        pendientes.append((posicion, paquete, analisis, {RIESGO: dictamen}, resolucion, predicados))

    ventas = {p.symbol: p.pnl_pct for p, _q, _a, _v, r, _d in pendientes if r.decision == comite.VENDER}
    permitidas = comite.limitar_ventas(ventas, motor.politica)
    for posicion, paquete, analisis, votos, resolucion, comprobaciones in pendientes:
        if resolucion.decision == comite.VENDER and not permitidas[posicion.symbol]:
            resolucion = comite.Resolucion(comite.MANTENER, "LIMITE_DE_VENTAS", causa=resolucion.causa)
        try:
            motor.registrar(paquete, analisis, votos, resolucion, comprobaciones, posicion)
        except Exception as exc:
            resultado.incidencias.append(f"{posicion.symbol}: {type(exc).__name__}: {exc}"[:200])
            continue
        if resolucion.decision == comite.VENDER:
            resultado.ventas.append(posicion.symbol)


def ejecutar_pasada(**argumentos: Any) -> ResultadoPasada:
    """Pasada en modo ``registro``, en exclusiva. El modo ``activo`` llega con la Entrega C."""

    registro: RegistroIA = argumentos["registro"]
    with registro.exclusivo() as libre:
        if not libre:
            return ResultadoPasada(0, "ERROR", incidencias=["otra pasada en curso"])
        return _ejecutar(**argumentos)


def _ejecutar(
    *,
    config: AdvisorConfig,
    universe: Universe,
    activos: List[Asset],
    proveedor: MarketDataProvider,
    cliente: Optional[ClienteIA],
    registro: RegistroIA,
    cartera: EstadoCartera,
    instante: datetime,
    reloj: Callable[[], datetime],
    politica: Optional[PoliticaIA] = None,
) -> ResultadoPasada:
    politica = politica or registro.politica
    pasada_id = registro.abrir_pasada(instante, "registro", code_sha())
    resultado = ResultadoPasada(pasada_id, "OK")
    crudo = ProveedorCrudo(proveedor, reloj)
    try:
        contexto = cargar_contexto(crudo, config, universe, instante)
    except Exception as exc:
        resultado.status = "ERROR"
        resultado.incidencias.append(f"contexto: {type(exc).__name__}: {exc}"[:300])
        registro.cerrar_pasada(pasada_id, "ERROR", resultado.incidencias[-1])
        return resultado

    analizadas: Dict[str, Analisis] = {}
    tenidas = {p.symbol for p in cartera.posiciones}
    objetivo = {a.symbol: a for a in activos}
    for symbol in tenidas:
        asset = universe.get(symbol)
        if asset is not None:
            objetivo.setdefault(symbol, asset)
    for symbol in sorted(objetivo):
        try:
            analizadas[symbol] = analizar(objetivo[symbol], config, crudo, contexto, instante, politica)
        except Exception as exc:
            logger.info("%s sin análisis: %s", symbol, exc)
            resultado.incidencias.append(f"{symbol}: {type(exc).__name__}: {exc}"[:200])

    # ``instante`` corta los datos. La decisión se fecha aquí, con todo ya observado y antes de llamar al modelo.
    decision_ts = reloj()
    registro.fechar_decision(pasada_id, decision_ts)
    motor = Motor(registro, cliente, politica, pasada_id, decision_ts, reloj)
    _evaluar_posiciones(motor, analizadas, contexto, cartera, resultado)
    candidatas = [
        a for a in analizadas.values() if motivo_no_elegible(a, cartera, politica, decision_ts) is None
    ]
    _evaluar_compras(motor, elegir_por_plaza(candidatas, politica), contexto, cartera, resultado)
    registro.cerrar_pasada(pasada_id, resultado.status, "; ".join(resultado.incidencias))
    return resultado


__all__ = ["BROKER_VERIFICADO", "PaqueteInvalido", "ResultadoPasada", "ejecutar_pasada"]
