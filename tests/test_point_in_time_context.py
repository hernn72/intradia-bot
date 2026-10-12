from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import advisor.analysis.analyzer as analyzer_module
import advisor.backtest.runner as backtest_runner
import advisor.report.tracking as tracking_module
import advisor.research.event_study as event_study_module
import advisor.research.execution_filter as execution_filter_module
from advisor.config import AdvisorConfig, DataQualityConfig, MarketContextConfig
from advisor.context.point_in_time import (
    EXCLUDED_ASIA_MISSING,
    EXCLUDED_CRYPTO,
    EXCLUDED_TREND_SMA_HISTORY,
    NO_CALCULABLE_CONTEXT_VIX,
    PRODUCTION_PASS_TIMES,
    analysis_timestamp_for_signal,
    context_mode_for,
    fetch_point_in_time_market_context,
    point_in_time_contexts_for_index,
    production_pass_times_from_timer,
    resolve_context_mode,
    resolve_point_in_time_context,
)
from advisor.data.calendars import expected_sessions
from advisor.data.sessions import session_close_at
from advisor.research.p3_population import P3PopulationControl, census_p3_population
from advisor.research.vintage import VintageLoad, VintageViews
from advisor.universe.models import Asset, Universe
from tests.conftest import FakeProvider


def _series_for_sessions(market: str, sessions: list[date], *, start: float = 100.0) -> pd.Series:
    values = []
    index = []
    for offset, session in enumerate(sessions):
        close = session_close_at(market, session)
        assert close is not None
        index.append(pd.Timestamp(close))
        values.append(start + offset)
    return pd.Series(values, index=pd.DatetimeIndex(index))


def _frame(series: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Close": series, "Open": series, "High": series, "Low": series, "Volume": 1_000_000})


def _context_universe() -> Universe:
    def ctx(symbol: str, name: str, region: str, market: str, timezone: str) -> Asset:
        return Asset(
            symbol=symbol,
            name=name,
            asset_class="index",
            region=region,
            market=market,
            currency="EUR",
            timezone=timezone,
            analizable=False,
        )

    return Universe(
        groups={
            "contexto": [
                ctx("^N225", "Nikkei 225", "ASIA", "JPX", "Asia/Tokyo"),
                ctx("^HSI", "Hang Seng", "ASIA", "HKG", "Asia/Hong_Kong"),
                ctx("^KS11", "KOSPI", "ASIA", "KSC", "Asia/Seoul"),
                ctx("^TWII", "Taiwan Weighted", "ASIA", "TAI", "Asia/Taipei"),
                ctx("510300.SS", "CSI 300 ETF", "ASIA", "SHH", "Asia/Shanghai"),
                ctx("^STOXX50E", "Euro Stoxx 50", "EUROPA", "XETRA", "Europe/Berlin"),
            ]
        }
    )


def _analysis_rows() -> list[tuple[str, date, date]]:
    return [
        ("XETRA", date(2026, 8, 26), date(2026, 8, 27)),
        ("XETRA", date(2025, 3, 12), date(2025, 3, 13)),
        ("NYSE", date(2026, 8, 26), date(2026, 8, 27)),
        ("NYSE", date(2025, 3, 12), date(2025, 3, 13)),
        ("NYSE", date(2025, 10, 29), date(2025, 10, 30)),
        ("JPX", date(2026, 8, 26), date(2026, 8, 27)),
        ("JPX", date(2022, 4, 28), date(2022, 5, 2)),
        ("HKG", date(2022, 4, 14), date(2022, 4, 19)),
    ]


def _parity_config() -> AdvisorConfig:
    return AdvisorConfig(
        base_currency="EUR",
        horizontes={
            "intradia": {"interval": "15m", "period": "60d", "min_bars": 1},
            "swing": {"interval": "1d", "period": "1y", "min_bars": 1},
            "medio": {"interval": "1d", "period": "2y", "min_bars": 1},
        },
    )


def _parity_asset(market: str) -> Asset:
    specs = {
        "XETRA": ("SAP.DE", "SAP", "EUROPA", "EUR", "Europe/Berlin"),
        "NYSE": ("IBM", "IBM", "USA", "USD", "America/New_York"),
        "JPX": ("7203.T", "Toyota", "ASIA", "JPY", "Asia/Tokyo"),
        "HKG": ("0700.HK", "Tencent", "ASIA", "HKD", "Asia/Hong_Kong"),
    }
    symbol, name, region, currency, asset_timezone = specs[market]
    return Asset(
        symbol=symbol,
        name=name,
        asset_class="stock",
        region=region,
        market=market,
        currency=currency,
        timezone=asset_timezone,
        benchmark=None,
    )


def _parity_universe(asset: Asset) -> Universe:
    context = _context_universe().groups["contexto"]
    return Universe(groups={"activos": [asset], "contexto": context})


def _signal_frame(market: str, signal_session: date) -> pd.DataFrame:
    sessions = expected_sessions(
        market,
        signal_session - timedelta(days=30),
        signal_session + timedelta(days=45),
    )
    signal_index = sessions.index(signal_session)
    selected = sessions[signal_index - 1 : signal_index + 10]
    return _frame(_series_for_sessions(market, selected, start=50.0))


def _vintage_for(asset: Asset, signal_frame: pd.DataFrame, closes: dict[str, pd.Series]) -> VintageLoad:
    by_symbol = {
        asset.primary_symbol: VintageViews(
            raw=signal_frame,
            execution_prices=signal_frame,
            signal_prices=signal_frame,
            gap_for_catalyst=signal_frame,
        )
    }
    for symbol, close in closes.items():
        frame = _frame(close)
        by_symbol[symbol] = VintageViews(raw=frame, execution_prices=frame, signal_prices=frame, gap_for_catalyst=frame)
    return VintageLoad(data_vintage_id="test-pit", manifest={}, by_symbol=by_symbol)


def _full_context_closes() -> dict[str, pd.Series]:
    return {
        "^VIX": _series_for_sessions("NYSE", expected_sessions("NYSE", date(2020, 1, 1), date(2026, 8, 27)), start=10.0),
        "^STOXX50E": _series_for_sessions(
            "XETRA", expected_sessions("XETRA", date(2020, 1, 1), date(2026, 8, 27)), start=3000.0
        ),
        "^N225": _series_for_sessions("JPX", expected_sessions("JPX", date(2020, 1, 1), date(2026, 8, 27)), start=100.0),
        "^HSI": _series_for_sessions("HKG", expected_sessions("HKG", date(2020, 1, 1), date(2026, 8, 27)), start=100.0),
        "^KS11": _series_for_sessions("KSC", expected_sessions("KSC", date(2020, 1, 1), date(2026, 8, 27)), start=100.0),
        "^TWII": _series_for_sessions("TAI", expected_sessions("TAI", date(2020, 1, 1), date(2026, 8, 27)), start=100.0),
        "510300.SS": _series_for_sessions("SHH", expected_sessions("SHH", date(2020, 1, 1), date(2026, 8, 27)), start=100.0),
    }


def test_analysis_timestamp_por_plaza() -> None:
    rows = [
        (*row, expected)
        for row, expected in zip(
            _analysis_rows(),
            (
                datetime(2026, 8, 27, 6, 0, tzinfo=timezone.utc),
                datetime(2025, 3, 13, 7, 0, tzinfo=timezone.utc),
                datetime(2026, 8, 27, 7, 30, tzinfo=timezone.utc),
                datetime(2025, 3, 13, 8, 30, tzinfo=timezone.utc),
                datetime(2025, 10, 30, 8, 30, tzinfo=timezone.utc),
                datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
                datetime(2022, 4, 29, 20, 0, tzinfo=timezone.utc),
                datetime(2022, 4, 18, 20, 0, tzinfo=timezone.utc),
            ),
        )
    ]

    for market, signal_session, entry_session, expected in rows:
        assert analysis_timestamp_for_signal(
            market,
            signal_session,
            entry_session,
            settlement_minutes=20,
        ) == expected


def test_timer_coincide_con_pasadas_d50() -> None:
    timer = Path("deploy/systemd/intradia-bot.timer")
    assert timer.is_file()
    text = timer.read_text(encoding="utf-8")

    assert production_pass_times_from_timer(text) == PRODUCTION_PASS_TIMES


def test_vix_tendencia_point_in_time() -> None:
    config = MarketContextConfig()
    vix_sessions = expected_sessions("NYSE", date(2022, 1, 1), date(2026, 8, 27))
    trend_sessions = expected_sessions("XETRA", date(2022, 1, 1), date(2026, 8, 27))
    closes = {
        "^VIX": _series_for_sessions("NYSE", vix_sessions, start=10.0),
        "^STOXX50E": _series_for_sessions("XETRA", trend_sessions, start=3000.0),
    }
    rows = [
        (datetime(2026, 8, 27, 6, 0, tzinfo=timezone.utc), date(2026, 8, 26), date(2026, 8, 26)),
        (datetime(2025, 3, 13, 7, 0, tzinfo=timezone.utc), date(2025, 3, 12), date(2025, 3, 12)),
        (datetime(2026, 8, 27, 7, 30, tzinfo=timezone.utc), date(2026, 8, 26), date(2026, 8, 26)),
        (datetime(2025, 3, 13, 8, 30, tzinfo=timezone.utc), date(2025, 3, 12), date(2025, 3, 12)),
        (datetime(2025, 10, 30, 8, 30, tzinfo=timezone.utc), date(2025, 10, 29), date(2025, 10, 29)),
        (datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc), date(2026, 8, 25), date(2026, 8, 26)),
        (datetime(2022, 4, 29, 20, 0, tzinfo=timezone.utc), date(2022, 4, 28), date(2022, 4, 29)),
        (datetime(2022, 4, 18, 20, 0, tzinfo=timezone.utc), date(2022, 4, 14), date(2022, 4, 14)),
    ]

    for analysis_timestamp, expected_vix, expected_trend in rows:
        resolved = resolve_point_in_time_context(
            analysis_timestamp,
            closes,
            config,
            asia_symbols=(),
            settlement_minutes=20,
        )

        assert resolved.vix_session == expected_vix
        assert resolved.trend_used_session == expected_trend


def test_sma200_sin_historia_excluye() -> None:
    config = MarketContextConfig()
    sessions = expected_sessions("XETRA", date(2026, 1, 1), date(2026, 12, 31))
    vix_sessions = expected_sessions("NYSE", date(2026, 1, 1), date(2026, 12, 31))
    reference = datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)

    with_199 = resolve_point_in_time_context(
        reference,
        {
            "^STOXX50E": _series_for_sessions("XETRA", sessions[-199:]),
            "^VIX": _series_for_sessions("NYSE", vix_sessions),
        },
        config,
        asia_symbols=(),
        settlement_minutes=20,
    )
    with_200 = resolve_point_in_time_context(
        reference,
        {
            "^STOXX50E": _series_for_sessions("XETRA", sessions[-200:]),
            "^VIX": _series_for_sessions("NYSE", vix_sessions),
        },
        config,
        asia_symbols=(),
        settlement_minutes=20,
    )

    assert EXCLUDED_TREND_SMA_HISTORY in with_199.exclusions
    assert EXCLUDED_TREND_SMA_HISTORY not in with_200.exclusions


def test_hueco_stoxx_usa_ultimo_cierre_causal() -> None:
    config = MarketContextConfig()
    sessions = expected_sessions("XETRA", date(2025, 1, 1), date(2026, 8, 26))
    vix_sessions = expected_sessions("NYSE", date(2025, 1, 1), date(2026, 8, 26))
    reference = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    closes = {
        "^STOXX50E": _series_for_sessions("XETRA", sessions[-220:-1]),
        "^VIX": _series_for_sessions("NYSE", vix_sessions),
    }

    resolved = resolve_point_in_time_context(
        reference,
        closes,
        config,
        asia_symbols=(),
        settlement_minutes=20,
    )

    assert resolved.trend_expected_session == date(2026, 8, 26)
    assert resolved.trend_used_session == sessions[-2]
    assert resolved.stoxx_age_days == (date(2026, 8, 26) - sessions[-2]).days
    assert EXCLUDED_TREND_SMA_HISTORY not in resolved.exclusions


def test_vix_ausente_pit_no_usa_regla_legacy() -> None:
    config = MarketContextConfig()
    sessions = expected_sessions("XETRA", date(2025, 1, 1), date(2026, 8, 26))
    asia_closes = {
        symbol: series
        for symbol, series in _full_context_closes().items()
        if symbol in {"^N225", "^HSI", "^KS11", "^TWII", "510300.SS"}
    }

    resolved = resolve_point_in_time_context(
        datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
        {"^STOXX50E": _series_for_sessions("XETRA", sessions[-220:]), **asia_closes},
        config,
        asia_symbols=("^N225", "^HSI", "^KS11", "^TWII", "510300.SS"),
        settlement_minutes=20,
    )

    assert resolved.context is None
    assert not resolved.calculable
    assert resolved.exclusions == ()
    assert resolved.no_calculable_codes == (NO_CALCULABLE_CONTEXT_VIX,)


def test_asia_vacia_pit_no_es_calculable() -> None:
    config = MarketContextConfig()
    closes = _full_context_closes()
    resolved = resolve_point_in_time_context(
        datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc),
        closes,
        config,
        asia_symbols=(),
        settlement_minutes=20,
    )

    assert resolved.context is None
    assert not resolved.calculable
    assert resolved.exclusions == (EXCLUDED_ASIA_MISSING,)
    assert resolved.asia_missing[0].missing == "sin series asiáticas en el universo"


def test_censo_p3_falla_si_vix_pit_no_calculable(monkeypatch: pytest.MonkeyPatch) -> None:
    advisor_config = _parity_config()
    asset = _parity_asset("XETRA")
    signal_session = date(2026, 8, 26)
    signal_frame = _signal_frame("XETRA", signal_session)
    trend_sessions = expected_sessions("XETRA", date(2025, 1, 1), date(2026, 8, 26))
    closes = {
        "^STOXX50E": _series_for_sessions("XETRA", trend_sessions[-220:]),
        **{
            symbol: series
            for symbol, series in _full_context_closes().items()
            if symbol not in {"^VIX", "^STOXX50E"}
        },
    }
    vintage = _vintage_for(asset, signal_frame, closes)
    observation = SimpleNamespace(asset=asset.symbol, signal_idx=1)
    fake_result = SimpleNamespace(
        signals=[SimpleNamespace(observation=observation)],
        skipped=[],
    )

    monkeypatch.setattr(event_study_module, "run_event_study_on_vintage", lambda *args, **kwargs: fake_result)

    with pytest.raises(RuntimeError, match=NO_CALCULABLE_CONTEXT_VIX):
        census_p3_population(
            advisor_config,
            _parity_universe(asset),
            vintage,
            horizonte="swing",
        )


def test_exclusiones_p3_union_sin_doble_conteo() -> None:
    config = MarketContextConfig()
    reference = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    trend_sessions = expected_sessions("XETRA", date(2026, 1, 1), date(2026, 8, 26))[-199:]
    vix_sessions = expected_sessions("NYSE", date(2026, 1, 1), date(2026, 8, 26))
    asia_sessions = expected_sessions("JPX", date(2026, 8, 1), date(2026, 8, 26))
    closes = {
        "^STOXX50E": _series_for_sessions("XETRA", trend_sessions),
        "^N225": _series_for_sessions("JPX", asia_sessions[:-1]),
        "^VIX": _series_for_sessions("NYSE", vix_sessions),
    }

    resolved = resolve_point_in_time_context(
        reference,
        closes,
        config,
        asia_symbols=("^N225",),
        settlement_minutes=20,
    )

    assert set(resolved.exclusions) == {EXCLUDED_ASIA_MISSING, EXCLUDED_TREND_SMA_HISTORY}
    assert len(set(resolved.exclusions)) == 2
    assert analysis_timestamp_for_signal(
        "CRYPTO",
        date(2026, 8, 26),
        date(2026, 8, 27),
        settlement_minutes=20,
    ) is None
    assert EXCLUDED_CRYPTO == "excluded_crypto"

    control = P3PopulationControl(
        horizonte="swing",
        a02_population=3,
        rows_by_reason={
            EXCLUDED_ASIA_MISSING: (("AAA", date(2026, 8, 26)),),
            EXCLUDED_TREND_SMA_HISTORY: (("AAA", date(2026, 8, 26)),),
            EXCLUDED_CRYPTO: (("BTC-EUR", date(2026, 8, 26)),),
        },
        final_population=(("BBB", date(2026, 8, 26)),),
        stoxx_gap_rows=(),
        blocks_with_signals=1,
    )

    assert control.union_excluded == 2
    assert ("AAA", date(2026, 8, 26)) in control.rows_by_reason[EXCLUDED_ASIA_MISSING]
    assert ("AAA", date(2026, 8, 26)) in control.rows_by_reason[EXCLUDED_TREND_SMA_HISTORY]


def test_backtest_pit_usa_settlement_de_config(monkeypatch: pytest.MonkeyPatch) -> None:
    advisor_config = _parity_config().model_copy(
        update={"data_quality": DataQualityConfig(settlement_minutes=45)}
    )
    asset = _parity_asset("XETRA")
    signal_session = date(2026, 8, 26)
    signal_frame = _signal_frame("XETRA", signal_session)
    provider = FakeProvider(
        {
            **{symbol: _frame(series) for symbol, series in _full_context_closes().items()},
            asset.primary_symbol: signal_frame,
        }
    )
    seen_settlement = []
    real_resolver = backtest_runner.PointInTimeContextResolver

    class CapturingResolver(real_resolver):
        def __init__(self, *args, settlement_minutes: int, **kwargs) -> None:
            seen_settlement.append(settlement_minutes)
            super().__init__(*args, settlement_minutes=settlement_minutes, **kwargs)

    monkeypatch.setattr(backtest_runner, "PointInTimeContextResolver", CapturingResolver)
    monkeypatch.setattr(backtest_runner, "simulate_asset", lambda *args, **kwargs: [])

    backtest_runner.run_backtest(
        advisor_config,
        _parity_universe(asset),
        provider,
        horizonte="swing",
        period="1y",
        settlement_minutes=20,
        context_mode="point_in_time",
    )

    assert seen_settlement == [45]


def test_backtest_legacy_no_descarga_series_asia(monkeypatch: pytest.MonkeyPatch) -> None:
    advisor_config = _parity_config()
    asset = _parity_asset("XETRA")
    provider = FakeProvider(
        {
            "^VIX": _frame(_full_context_closes()["^VIX"]),
            "^STOXX50E": _frame(_full_context_closes()["^STOXX50E"]),
            asset.primary_symbol: _signal_frame("XETRA", date(2026, 8, 26)),
        }
    )

    monkeypatch.setattr(backtest_runner, "simulate_asset", lambda *args, **kwargs: [])

    backtest_runner.run_backtest(
        advisor_config,
        _parity_universe(asset),
        provider,
        horizonte="swing",
        period="1y",
        context_mode="legacy_v1",
    )

    assert "^N225" not in provider.calls
    assert "^HSI" not in provider.calls
    assert "^KS11" not in provider.calls
    assert "^TWII" not in provider.calls
    assert "510300.SS" not in provider.calls


def test_context_mode_deriva_de_version_y_legacy_v2_falla() -> None:
    assert context_mode_for("1.0") == "legacy_v1"
    assert context_mode_for("2.0") == "point_in_time"
    assert resolve_context_mode("1.0", None) == "legacy_v1"
    assert resolve_context_mode("1.0", "point_in_time") == "point_in_time"

    with pytest.raises(ValueError, match="legacy_v1 solo"):
        resolve_context_mode("2.0", "legacy_v1")


def test_d59_v1_legacy_permitido_v2_pit_automatico_y_v2_legacy_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    advisor_config = _parity_config()
    asset = _parity_asset("XETRA")
    universe = _parity_universe(asset)
    provider = FakeProvider({})
    seen: list[tuple[str, str | None]] = []

    monkeypatch.setattr(analyzer_module, "fetch_overview", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(analyzer_module, "fetch_market_context", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("legacy")))
    monkeypatch.setattr(
        analyzer_module,
        "fetch_point_in_time_market_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("pit")),
    )
    with pytest.raises(RuntimeError, match="pit"):
        analyzer_module.run_analysis(
            advisor_config,
            universe,
            provider,
            horizonte="swing",
            score_model_version="2.0",
        )
    with pytest.raises(RuntimeError, match="legacy"):
        analyzer_module.run_analysis(advisor_config, universe, provider, horizonte="swing", score_model_version="1.0")

    def spy(score_model_version: str, explicit: str | None) -> str:
        mode = resolve_context_mode(score_model_version, explicit)
        seen.append((score_model_version, explicit))
        raise RuntimeError(f"resolved {mode}")

    for module, call in (
        (
            backtest_runner,
            lambda: backtest_runner.run_backtest(
                advisor_config,
                universe,
                provider,
                horizonte="swing",
                score_model_version="2.0",
            ),
        ),
        (
            event_study_module,
            lambda: event_study_module.run_event_study_on_vintage(
                advisor_config,
                universe,
                VintageLoad(data_vintage_id="test", manifest={}, by_symbol={}),
                horizonte="swing",
                score_model_version="2.0",
            ),
        ),
    ):
        monkeypatch.setattr(module, "resolve_context_mode", spy)
        with pytest.raises(RuntimeError, match="resolved point_in_time"):
            call()

    with pytest.raises(ValueError, match="score_model_version 1\\.0"):
        execution_filter_module.run_execution_filter_study(
            advisor_config,
            universe,
            "missing",
            horizonte="swing",
            root_dir="/private/tmp/no-vintage",
            score_model_version="2.0",
        )

    assert ("2.0", None) in seen
    assert resolve_context_mode("1.0", None) == "legacy_v1"
    assert resolve_context_mode("2.0", None) == "point_in_time"
    with pytest.raises(ValueError, match="legacy_v1 solo"):
        resolve_context_mode("2.0", "legacy_v1")


def test_produccion_v2_ignora_barra_diaria_aun_no_disponible() -> None:
    config = MarketContextConfig()
    closes = _full_context_closes()
    intraday_vix = pd.Series(
        [99.0],
        index=pd.DatetimeIndex([pd.Timestamp(session_close_at("NYSE", date(2026, 8, 27)))]),
    )
    closes["^VIX"] = pd.concat([closes["^VIX"], intraday_vix])
    provider = FakeProvider({symbol: _frame(series) for symbol, series in closes.items()})

    context = fetch_point_in_time_market_context(
        provider,
        config,
        _context_universe(),
        datetime(2026, 8, 27, 7, 30, tzinfo=timezone.utc),
        settlement_minutes=20,
    )
    direct = resolve_point_in_time_context(
        datetime(2026, 8, 27, 7, 30, tzinfo=timezone.utc),
        closes,
        config,
        asia_symbols=("^N225", "^HSI", "^KS11", "^TWII", "510300.SS"),
        settlement_minutes=20,
    )

    assert direct.vix_session == date(2026, 8, 26)
    assert context == direct.context


def test_paridad_r_ctx_cuatro_caminos_pit(monkeypatch: pytest.MonkeyPatch) -> None:
    config = MarketContextConfig()
    advisor_config = _parity_config()
    closes = _full_context_closes()
    asia_symbols = ("^N225", "^HSI", "^KS11", "^TWII", "510300.SS")

    for market, signal_session, entry_session in _analysis_rows():
        asset = _parity_asset(market)
        universe = _parity_universe(asset)
        signal_frame = _signal_frame(market, signal_session)
        provider = FakeProvider(
            {
                **{symbol: _frame(series) for symbol, series in closes.items()},
                asset.primary_symbol: signal_frame,
            },
            closes={asset.primary_symbol: 55.0},
        )
        analysis_timestamp = analysis_timestamp_for_signal(
            market,
            signal_session,
            entry_session,
            settlement_minutes=20,
        )
        assert analysis_timestamp is not None
        expected = resolve_point_in_time_context(
            analysis_timestamp,
            closes,
            config,
            asia_symbols=asia_symbols,
            settlement_minutes=20,
        ).context
        index = pd.DatetimeIndex(
            [
                pd.Timestamp(session_close_at(market, signal_session)),
                pd.Timestamp(session_close_at(market, entry_session)),
            ]
        )
        by_bar = point_in_time_contexts_for_index(
            index,
            signal_market=market,
            closes=closes,
            config=config,
            asia_symbols=asia_symbols,
            settlement_minutes=20,
        )[0]
        assert by_bar is not None
        assert expected is not None

        production_seen = []

        def production_analyze(*args, seen=production_seen, **kwargs):
            seen.append(args[3])
            raise RuntimeError("capturado")

        # Score v2 aún no está registrado en la config; el test fuerza solo el
        # selector de rama para verificar la llamada real de producción v2.
        monkeypatch.setattr(analyzer_module, "context_mode_for", lambda _version: "point_in_time")
        monkeypatch.setattr(analyzer_module, "analyze_asset", production_analyze)
        analysis_result = analyzer_module.run_analysis(
            advisor_config,
            universe,
            provider,
            horizonte="swing",
            now=analysis_timestamp,
        )

        backtest_seen = []

        def backtest_simulate(*args, seen=backtest_seen, **kwargs):
            market_context_at = kwargs["market_context_at"]
            seen.append(market_context_at[1])
            return []

        monkeypatch.setattr(backtest_runner, "simulate_asset", backtest_simulate)
        backtest_runner.run_backtest(
            advisor_config,
            universe,
            provider,
            horizonte="swing",
            period="1y",
            context_mode="point_in_time",
        )

        event_seen = []
        vintage = _vintage_for(asset, signal_frame, closes)

        def event_signal(*args, seen=event_seen, **kwargs):
            j = args[2]
            market_context_at = args[9]
            seen.append(market_context_at[j])
            return None

        monkeypatch.setattr(event_study_module, "_build_event_signal", event_signal)
        event_study_module.run_event_study_on_vintage(
            advisor_config,
            universe,
            vintage,
            horizonte="swing",
            context_mode="point_in_time",
        )

        tracking_seen = []

        def tracking_analyze(*args, seen=tracking_seen, **kwargs):
            seen.append(args[3])
            return SimpleNamespace(score=SimpleNamespace(value=75.0), snapshot=SimpleNamespace(price=110.0))

        position_row = {
            "id": 1,
            "symbol": asset.symbol,
            "name": asset.name,
            "currency": asset.currency,
            "opened_at": "2026-01-01T00:00:00Z",
            "entry_price": 100.0,
            "quantity": 1.0,
            "stop": 90.0,
            "target": 150.0,
            "horizonte": "swing",
            "thesis": "test",
        }

        class FakeDB:
            def list_open_positions(self, row=position_row):
                return [row]

            def insert_review(self, **kwargs):
                return None

        monkeypatch.setattr(tracking_module, "context_mode_for", lambda _version: "point_in_time")
        monkeypatch.setattr(tracking_module, "analyze_asset", tracking_analyze)
        tracking_module.review_positions(
            advisor_config,
            universe,
            FakeDB(),
            provider,
            "run-paridad",
            now=analysis_timestamp,
        )

        assert by_bar.context == expected
        assert analysis_result.context == expected
        assert production_seen == [expected]
        assert backtest_seen[:1] == [expected]
        assert event_seen[:1] == [expected]
        assert tracking_seen == [expected]
        for context in (
            by_bar.context,
            analysis_result.context,
            production_seen[0],
            backtest_seen[0],
            event_seen[0],
            tracking_seen[0],
        ):
            assert context.points == expected.points


def test_d54_cierres_extraordinarios_y_huecos_no_forzados() -> None:
    assert date(2023, 9, 1) not in expected_sessions("HKG", date(2023, 9, 1), date(2023, 9, 1))
    assert date(2023, 9, 8) not in expected_sessions("HKG", date(2023, 9, 8), date(2023, 9, 8))
    assert date(2023, 1, 18) not in expected_sessions("TAI", date(2023, 1, 18), date(2023, 1, 18))
    assert date(2024, 10, 31) not in expected_sessions("TAI", date(2024, 10, 31), date(2024, 10, 31))
    assert date(2026, 7, 10) not in expected_sessions("TAI", date(2026, 7, 10), date(2026, 7, 10))

    assert date(2022, 5, 9) in expected_sessions("KSC", date(2022, 5, 9), date(2022, 5, 9))
    assert date(2025, 10, 24) in expected_sessions("SHH", date(2025, 10, 24), date(2025, 10, 24))
    assert date(2026, 8, 28) in expected_sessions("SHH", date(2026, 8, 28), date(2026, 8, 28))
