"""Núcleo de análisis: foto técnica, niveles, puntuación y clasificación."""

from __future__ import annotations

from typing import ClassVar, List

import pandas as pd
import pytest

from advisor.analysis.levels import compute_levels, rr_at_least
from advisor.analysis.opportunity import (
    ACCION_COMPRAR,
    ACCION_DESCARTAR,
    ACCION_ESPERAR,
    RADAR_DESCARTAR,
    RADAR_OPERAR,
    RADAR_VIGILAR,
    classify,
)
from advisor.analysis.scoring import compute_score, suggest_sizing
from advisor.analysis.snapshot import TechnicalSnapshot, build_snapshot
from advisor.config import IndicatorsConfig, LevelsConfig, RiskConfig, ScoringConfig
from tests.conftest import make_ohlcv


def make_snapshot(**overrides) -> TechnicalSnapshot:
    """Snapshot con valores por defecto sanos, sobrescribibles por test."""

    base = dict(
        symbol="TEST",
        timestamp=pd.Timestamp("2026-08-27", tz="UTC"),
        interval="1d",
        bars=300,
        price=100.0,
        ema_fast=99.0,  # 0,5·ATR por debajo del precio: extensión bajo entry_max_atr, sin chase
        ema_slow=95.0,
        sma_long=90.0,
        rsi=60.0,
        atr=2.0,
        macd=1.0,
        macd_signal=0.5,
        macd_hist=0.5,
        volume=2_000_000.0,
        volume_avg=1_000_000.0,
        volume_ratio=2.0,
        gap_pct=2.5,
        high_lookback=101.0,
        low_lookback=94.0,
        return_short=5.0,
        return_medium=12.0,
        return_long=25.0,
        volatility_pct=18.0,
        relative_strength=3.0,
    )
    base.update(overrides)
    return TechnicalSnapshot(**base)


class TestBuildSnapshot:
    def test_calcula_indicadores_en_serie_alcista(self) -> None:
        df = make_ohlcv(n=300, drift=0.3)
        snapshot = build_snapshot("TEST", df, IndicatorsConfig(), LevelsConfig(), "1d")

        assert snapshot.bars == 300
        assert snapshot.ema_fast > snapshot.ema_slow
        assert snapshot.price > snapshot.sma_long
        assert snapshot.trend_up is True
        assert snapshot.atr > 0
        assert snapshot.macd_hist > 0

    def test_indicadores_sin_historico_quedan_en_none(self) -> None:
        df = make_ohlcv(n=60)
        snapshot = build_snapshot("TEST", df, IndicatorsConfig(), LevelsConfig(), "1d")

        assert snapshot.sma_long is None  # requiere 200 velas
        assert snapshot.ema_slow is not None  # requiere 50
        assert snapshot.trend_up is False  # sin SMA larga no se afirma tendencia de fondo

    def test_volumen_relativo(self) -> None:
        df = make_ohlcv(n=100, volume=1_000_000.0, last_volume=3_000_000.0)
        snapshot = build_snapshot("TEST", df, IndicatorsConfig(), LevelsConfig(), "1d")
        assert snapshot.volume_ratio == pytest.approx(3.0)

    def test_volumen_cero_se_trata_como_sin_dato(self) -> None:
        df = make_ohlcv(n=100, last_volume=0.0)
        snapshot = build_snapshot("TEST", df, IndicatorsConfig(), LevelsConfig(), "1d")
        assert snapshot.volume_ratio is None

    def test_fortaleza_relativa_con_benchmark(self) -> None:
        df = make_ohlcv(n=200, drift=1.0)
        benchmark = make_ohlcv(n=200, drift=0.05)["Close"]
        snapshot = build_snapshot("TEST", df, IndicatorsConfig(), LevelsConfig(), "1d", benchmark)
        assert snapshot.relative_strength > 0

    def test_dataframe_vacio(self) -> None:
        with pytest.raises(ValueError, match="vacío"):
            build_snapshot("TEST", pd.DataFrame(), IndicatorsConfig(), LevelsConfig(), "1d")

    def test_sin_columna_close(self) -> None:
        with pytest.raises(ValueError, match="Close"):
            build_snapshot("TEST", pd.DataFrame({"Open": [1.0]}), IndicatorsConfig(), LevelsConfig(), "1d")

    def test_la_resistencia_incluye_la_vela_actual(self) -> None:
        """`high_lookback` toma el máximo de la ventana CON la vela de hoy.

        No es mirar el futuro (la vela ya ha cerrado), pero explica por qué la
        resistencia está casi siempre justo encima del precio: basta la mecha
        superior de la propia vela que genera la señal. Es la raíz por la que
        se descartó el objetivo 2 estructural (docs/ratio-beneficio-riesgo.md)."""

        df = make_ohlcv(n=100, drift=0.3)
        snapshot = build_snapshot("TEST", df, IndicatorsConfig(), LevelsConfig(), "1d")

        assert snapshot.high_lookback == pytest.approx(float(df["High"].iloc[-1]))
        assert snapshot.high_lookback > snapshot.price

    def test_atr_pct_relativo_al_precio(self) -> None:
        snapshot = make_snapshot(price=100.0, atr=3.0)
        assert snapshot.atr_pct == pytest.approx(3.0)


class TestComputeLevels:
    def test_stop_por_volatilidad_cuando_no_hay_soporte_cercano(self) -> None:
        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0)
        levels = compute_levels(snapshot, LevelsConfig(atr_stop_multiple=2.0))

        assert levels.stop == pytest.approx(96.0)
        assert "ATR" in levels.stop_basis

    def test_stop_se_apoya_en_el_soporte_si_esta_mas_cerca(self) -> None:
        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=97.0)
        levels = compute_levels(snapshot, LevelsConfig(atr_stop_multiple=2.0))

        assert levels.stop == pytest.approx(97.0 - 0.25 * 2.0)
        assert "soporte" in levels.stop_basis

    def test_objetivo1_se_ancla_en_la_resistencia_mas_cercana(self) -> None:
        snapshot = make_snapshot(price=100.0, atr=2.0, high_lookback=102.0)
        levels = compute_levels(snapshot, LevelsConfig(target_atr_multiples=[1.5, 3.0, 5.0]))

        assert levels.target1 == pytest.approx(102.0)  # 100 + 1,5·2 = 103 > resistencia
        assert levels.target2 == pytest.approx(106.0)
        assert levels.target3 == pytest.approx(110.0)

    def test_objetivo2_estructural_cede_ante_la_resistencia(self) -> None:
        """Con ``target2_structural`` el objetivo que forma el ratio también
        se detiene en el primer obstáculo real, y el ratio deja de ser el
        múltiplo fijo del ATR (ver docs/ratio-beneficio-riesgo.md)."""

        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0, high_lookback=104.0)

        sin_d = compute_levels(snapshot, LevelsConfig(target2_structural=False))
        assert sin_d.target2 == pytest.approx(106.0)
        assert sin_d.rr_ratio == pytest.approx(1.5)

        con_d = compute_levels(snapshot, LevelsConfig(target2_structural=True))
        assert con_d.target2 == pytest.approx(104.0)
        assert con_d.rr_ratio == pytest.approx(1.0)
        # El objetivo 3 es el escenario de ruptura: no cede ante la resistencia.
        assert con_d.target3 == pytest.approx(110.0)

    def test_objetivo2_estructural_no_toca_nada_sin_resistencia_por_delante(self) -> None:
        # Resistencia por debajo del precio: no hay obstáculo delante.
        atras = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0, high_lookback=99.0)
        levels = compute_levels(atras, LevelsConfig(target2_structural=True))
        assert levels.target2 == pytest.approx(106.0)
        assert levels.rr_ratio == pytest.approx(1.5)

        # Resistencia MÁS LEJOS que el objetivo 2: tampoco lo recorta.
        lejos = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0, high_lookback=112.0)
        levels = compute_levels(lejos, LevelsConfig(target2_structural=True))
        assert levels.target2 == pytest.approx(106.0)
        assert levels.rr_ratio == pytest.approx(1.5)

    def test_objetivo2_estructural_puede_coincidir_con_el_objetivo1(self) -> None:
        """Con la resistencia por debajo del objetivo 1, ambos objetivos se
        anclan en el mismo obstáculo. Es degenerado a propósito: si el primer
        techo real está tan cerca, no hay dos niveles distintos que ofrecer."""

        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0, high_lookback=102.0)
        levels = compute_levels(snapshot, LevelsConfig(target2_structural=True))

        assert levels.target1 == pytest.approx(102.0)
        assert levels.target2 == pytest.approx(102.0)
        assert levels.rr_ratio == pytest.approx(0.5)

    def test_ratio_se_calcula_sobre_el_objetivo2(self) -> None:
        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0)
        levels = compute_levels(snapshot, LevelsConfig(atr_stop_multiple=2.0))

        assert levels.risk_pct == pytest.approx(4.0)
        assert levels.reward_pct == pytest.approx(6.0)
        assert levels.rr_ratio == pytest.approx(1.5)

    def test_detecta_precio_extendido(self) -> None:
        extendido = make_snapshot(price=100.0, ema_fast=90.0, atr=2.0)
        assert compute_levels(extendido, LevelsConfig(entry_max_atr=0.75)).chase is True

        normal = make_snapshot(price=100.0, ema_fast=99.0, atr=2.0)
        assert compute_levels(normal, LevelsConfig(entry_max_atr=0.75)).chase is False

    def test_el_soporte_nunca_aleja_el_stop(self) -> None:
        """Un soporte pegado al stop por volatilidad no debe empeorarlo.

        Con soporte en 96,1 y stop por volatilidad en 96,0, la holgura de
        0,25·ATR dejaría el stop en 95,6: MÁS lejos que el de volatilidad,
        al revés de lo que justifica apoyarse en la estructura.
        """

        config = LevelsConfig(atr_stop_multiple=2.0)
        pegado = make_snapshot(price=100.0, atr=2.0, low_lookback=96.1)
        levels = compute_levels(pegado, config)
        assert levels.stop == pytest.approx(96.0)
        assert "ATR" in levels.stop_basis

        # Cuando el soporte sí acerca el stop, sigue mandando el soporte.
        lejos_del_stop = make_snapshot(price=100.0, atr=2.0, low_lookback=97.0)
        levels = compute_levels(lejos_del_stop, config)
        assert levels.stop == pytest.approx(96.5)
        assert "soporte" in levels.stop_basis

    def test_sin_atr_no_hay_niveles(self) -> None:
        assert compute_levels(make_snapshot(atr=None), LevelsConfig()) is None

    def test_invalidacion_usa_la_ema_lenta_cuando_el_precio_la_supera(self) -> None:
        levels = compute_levels(make_snapshot(price=100.0, ema_slow=95.0), LevelsConfig())
        assert levels.invalidation_level == pytest.approx(95.0)
        assert "EMA lenta" in levels.invalidation_reason

    def test_invalidacion_cae_a_la_sma_larga(self) -> None:
        snapshot = make_snapshot(price=100.0, ema_slow=105.0, sma_long=90.0)
        levels = compute_levels(snapshot, LevelsConfig())
        assert levels.invalidation_level == pytest.approx(90.0)

    def test_el_ratio_en_el_minimo_no_se_pierde_por_redondeo(self) -> None:
        """Stop 2·ATR y objetivo 2 a 3·ATR dan exactamente 1,5:1.

        En coma flotante ese cociente cae en 1,49999… para la mayoría de los
        precios reales, así que la comparación debe tolerarlo: si no, el
        activo se descarta por un bit de redondeo.
        """

        config = LevelsConfig(atr_stop_multiple=2.0, target_atr_multiples=[1.5, 3.0, 5.0])
        crudos = 0
        for price in (10.0, 37.13, 100.0, 183.46, 240.5, 1234.56, 66131.98):
            for atr_pct in (0.3, 0.5, 1.0, 1.7, 2.5, 4.0):
                atr = price * atr_pct / 100
                snapshot = make_snapshot(
                    price=price, atr=atr, ema_fast=price - 0.5 * atr, ema_slow=price - atr,
                    sma_long=price * 0.9, low_lookback=price * 0.01, high_lookback=price * 10,
                )
                levels = compute_levels(snapshot, config)
                assert levels.rr_ratio == pytest.approx(1.5)
                assert rr_at_least(levels.rr_ratio, 1.5), f"{price} / {atr_pct}%"
                if levels.rr_ratio < 1.5:
                    crudos += 1

        # Si esto fuese 0, el test no estaría probando nada: significaría que
        # la comparación cruda ya bastaba.
        assert crudos > 0

    def test_stop_incoherente_devuelve_none(self) -> None:
        """Un ATR mayor que el precio situaría el stop en negativo."""
        snapshot = make_snapshot(price=10.0, atr=20.0, low_lookback=1.0)
        assert compute_levels(snapshot, LevelsConfig(atr_stop_multiple=2.0)) is None


class TestScoring:
    def test_el_objetivo2_estructural_arrastra_la_nota_no_solo_el_veto(self, benign_context) -> None:
        """Recortar el objetivo 2 no solo dispara el veto de ratio: se lleva
        por delante puntos de la nota, que no se recuperan bajando
        `min_rr_ratio`. Es el motivo medido por el que la opción A no rescata
        a la D (docs/ratio-beneficio-riesgo.md)."""

        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0, high_lookback=104.0)
        control = compute_levels(snapshot, LevelsConfig(target2_structural=False))
        con_d = compute_levels(snapshot, LevelsConfig(target2_structural=True))

        puntos = {
            etiqueta: next(d for d in compute_score(snapshot, niveles, benign_context, ScoringConfig(), 250).dimensions
                           if d.name == "beneficio_riesgo").points
            for etiqueta, niveles in (("control", control), ("D", con_d))
        }
        assert puntos["D"] < puntos["control"]

    def test_fundamental_se_excluye_y_la_nota_se_normaliza(self, benign_context) -> None:
        snapshot = make_snapshot()
        levels = compute_levels(snapshot, LevelsConfig())
        score = compute_score(snapshot, levels, benign_context, ScoringConfig(), 250)

        assert "fundamental" in score.missing_dimensions
        assert score.evaluable_max == pytest.approx(80.0)
        # La nota se calcula sobre 80, no sobre 100.
        assert score.value == pytest.approx(round(100 * score.points / 80, 1))

    def test_una_dimension_excluida_no_penaliza_la_nota(self, benign_context) -> None:
        """Sin normalizar, ningún activo llegaría nunca al umbral de operar."""
        snapshot = make_snapshot()
        levels = compute_levels(snapshot, LevelsConfig())
        score = compute_score(snapshot, levels, benign_context, ScoringConfig(), 250)

        sin_normalizar = score.points  # sobre 100
        assert score.value > sin_normalizar

    def test_activo_fuerte_puntua_mas_que_uno_debil(self, benign_context) -> None:
        fuerte = make_snapshot()
        debil = make_snapshot(
            ema_fast=90.0, ema_slow=95.0, sma_long=110.0, rsi=30.0,
            macd_hist=-0.5, volume_ratio=0.8, gap_pct=-3.0, relative_strength=-5.0,
            high_lookback=130.0,
        )

        score_fuerte = compute_score(fuerte, compute_levels(fuerte, LevelsConfig()), benign_context, ScoringConfig(), 250)
        score_debil = compute_score(debil, compute_levels(debil, LevelsConfig()), benign_context, ScoringConfig(), 250)

        assert score_fuerte.value > score_debil.value

    def test_el_tramo_del_ratio_no_se_pierde_por_redondeo(self, benign_context) -> None:
        """Un ratio de exactamente 1,5:1 debe puntuar como "aceptable" (10/20).

        Con la comparación cruda cae al tramo "insuficiente" (5/20) y pierde
        más de seis puntos de nota, suficientes para cambiar el veredicto.
        """

        price, atr = 183.46, 183.46 * 0.017
        snapshot = make_snapshot(
            price=price, atr=atr, ema_fast=price - 0.5 * atr, ema_slow=price - atr,
            sma_long=price * 0.9, low_lookback=price * 0.01, high_lookback=price * 10,
        )
        levels = compute_levels(snapshot, LevelsConfig())
        assert levels.rr_ratio < 1.5  # el cociente crudo está por debajo

        score = compute_score(snapshot, levels, benign_context, ScoringConfig(), 250)
        ratio_dim = next(d for d in score.dimensions if d.name == "beneficio_riesgo")
        assert ratio_dim.points == pytest.approx(10.0)
        assert "aceptable" in ratio_dim.components[0].detail

    def test_contexto_hostil_baja_la_nota(self, benign_context, hostile_context) -> None:
        snapshot = make_snapshot()
        levels = compute_levels(snapshot, LevelsConfig())

        bueno = compute_score(snapshot, levels, benign_context, ScoringConfig(), 250)
        malo = compute_score(snapshot, levels, hostile_context, ScoringConfig(), 250)

        assert malo.value < bueno.value

    def test_historico_corto_reduce_la_conviccion(self, benign_context) -> None:
        completo = make_snapshot(bars=300)
        corto = make_snapshot(bars=100)
        levels = compute_levels(completo, LevelsConfig())

        c1 = compute_score(completo, levels, benign_context, ScoringConfig(), 250)
        c2 = compute_score(corto, levels, benign_context, ScoringConfig(), 250)

        conviccion1 = next(d for d in c1.dimensions if d.name == "conviccion")
        conviccion2 = next(d for d in c2.dimensions if d.name == "conviccion")
        assert conviccion1.points > conviccion2.points

    def test_grado_segun_la_nota(self, benign_context) -> None:
        snapshot = make_snapshot()
        levels = compute_levels(snapshot, LevelsConfig())
        score = compute_score(snapshot, levels, benign_context, ScoringConfig(), 250)
        assert score.grade in {"Excepcional", "Muy atractiva", "Interesante", "Vigilancia", "No operar"}

    def test_volatilidad_alta_rebaja_el_dimensionamiento(self, benign_context) -> None:
        snapshot = make_snapshot()
        levels = compute_levels(snapshot, LevelsConfig())
        score = compute_score(snapshot, levels, benign_context, ScoringConfig(), 250)

        _, _, normal_max = suggest_sizing(score, levels, atr_pct=2.0)
        etiqueta, _, volatil_max = suggest_sizing(score, levels, atr_pct=9.0)

        assert volatil_max <= normal_max
        assert "volatilidad" in etiqueta or volatil_max <= 5.0


class TestClassify:
    def _score_con_valor(self, valor: float):
        """Score mínimo con un valor conocido, sin depender del cálculo real."""

        class _Score:
            value = valor
            missing_dimensions: ClassVar[List] = []
            dimensions: ClassVar[List] = []
            evaluable_max = 80.0

        return _Score()

    def test_descarta_por_nota_baja(self, asset_eur, benign_context) -> None:
        levels = compute_levels(make_snapshot(), LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(40.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_DESCARTAR, ACCION_DESCARTAR)
        assert "por debajo del mínimo" in motivos[0]

    def test_descarta_por_ratio_insuficiente(self, asset_eur, benign_context) -> None:
        # Stop muy lejano y objetivos cortos: ratio por debajo de 1,5.
        snapshot = make_snapshot(price=100.0, atr=2.0, low_lookback=50.0)
        levels = compute_levels(snapshot, LevelsConfig(atr_stop_multiple=4.0, target_atr_multiples=[1.0, 2.0, 3.0]))
        radar, accion, motivos = classify(
            self._score_con_valor(85.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_DESCARTAR, ACCION_DESCARTAR)
        assert "beneficio/riesgo" in motivos[0]

    def test_el_ratio_justo_en_el_minimo_no_descarta(self, asset_eur, benign_context) -> None:
        """El caso por defecto (stop 2·ATR, objetivo 2 a 3·ATR) da 1,5:1 exacto."""

        price, atr = 183.46, 183.46 * 0.017
        snapshot = make_snapshot(
            price=price, atr=atr, ema_fast=price - 0.5 * atr, ema_slow=price - atr,
            sma_long=price * 0.9, low_lookback=price * 0.01, high_lookback=price * 10,
        )
        levels = compute_levels(snapshot, LevelsConfig())
        assert levels.rr_ratio < 1.5  # el cociente crudo está por debajo

        radar, accion, _ = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_OPERAR, ACCION_COMPRAR)

    def test_horizonte_medio_exige_superar_la_alternativa_sin_riesgo(self, asset_eur, benign_context) -> None:
        """Meses inmovilizado por un 3% de potencial no compensa frente al 2,25% anual."""

        poco_potencial = make_snapshot(price=100.0, atr=1.0, ema_fast=99.5)  # objetivo 2 = +3%
        levels = compute_levels(poco_potencial, LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(),
            asset_eur, horizonte="medio",
        )
        assert (radar, accion) == (RADAR_VIGILAR, ACCION_ESPERAR)
        assert "sin riesgo" in motivos[0]

        # El mismo potencial en swing no se veta: el capital no queda meses inmovilizado.
        radar, accion, _ = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(),
            asset_eur, horizonte="swing",
        )
        assert (radar, accion) == (RADAR_OPERAR, ACCION_COMPRAR)

    def test_vigila_cuando_la_nota_no_llega_a_operar(self, asset_eur, benign_context) -> None:
        levels = compute_levels(make_snapshot(), LevelsConfig())
        radar, accion, _ = classify(
            self._score_con_valor(65.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_VIGILAR, ACCION_ESPERAR)

    def test_precio_extendido_advierte_pero_no_veta(self, asset_eur, benign_context) -> None:
        """Medido en backtest (europa 2y/5y): como veto dejaba al asesor sin
        operar y las señales bloqueadas eran las más rentables. La advertencia
        se conserva para que el humano priorice la zona de entrada ideal."""

        snapshot = make_snapshot(price=100.0, ema_fast=90.0, atr=2.0)
        levels = compute_levels(snapshot, LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_OPERAR, ACCION_COMPRAR)
        assert any("extendido" in m for m in motivos)
        assert any("no persigas" in m for m in motivos)

    def test_contexto_hostil_frena_la_compra(self, asset_eur, hostile_context) -> None:
        levels = compute_levels(make_snapshot(), LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(90.0), levels, hostile_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_VIGILAR, ACCION_ESPERAR)
        assert "adverso" in motivos[0]

    def test_activo_no_disponible_en_trade_republic_se_descarta(self, asset_eur, benign_context) -> None:
        no_disponible = asset_eur.model_copy(update={"trade_republic": "no"})
        levels = compute_levels(make_snapshot(), LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(), no_disponible
        )
        assert (radar, accion) == (RADAR_DESCARTAR, ACCION_DESCARTAR)
        assert "Trade Republic" in motivos[0]

    def test_disponibilidad_sin_verificar_avisa_pero_no_bloquea(self, asset_usd, benign_context) -> None:
        levels = compute_levels(make_snapshot(), LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_usd
        )
        assert (radar, accion) == (RADAR_OPERAR, ACCION_COMPRAR)
        assert any("sin verificar" in m for m in motivos)

    def test_compra_limpia_no_genera_advertencias(self, asset_eur, benign_context) -> None:
        levels = compute_levels(make_snapshot(), LevelsConfig())
        radar, accion, motivos = classify(
            self._score_con_valor(90.0), levels, benign_context, ScoringConfig(), RiskConfig(), asset_eur
        )
        assert (radar, accion) == (RADAR_OPERAR, ACCION_COMPRAR)
        assert motivos == []
