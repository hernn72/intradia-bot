"""Censo de la población de P4 (D-63, OD-P4-2 = C): A-02 swing sin cripto, sin leer desenlaces.

Solo recorre la cosecha para enumerar señales y sus primitivas del instante de señal. Los
evaluadores de desenlace se sustituyen por funciones que devuelven `None` (el camino del preflight
de P3), y se comprueba que ninguna señal trae desenlace: este script no puede producir ningún
`net_R`. El score de cada observación se calcula porque el event study lo hace,
pero no se lee.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import advisor.research.event_study as event_study  # noqa: E402
from advisor.analysis.overview import context_assets_of  # noqa: E402
from advisor.config import load_config  # noqa: E402
from advisor.context.point_in_time import PointInTimeContextResolver, analysis_timestamp_for_signal  # noqa: E402
from advisor.data.freshness import mercado_para_simbolo  # noqa: E402
from advisor.data.sessions import session_date_of  # noqa: E402
from advisor.research.capacity import _temporal_block_lookup  # noqa: E402
from advisor.research.event_study import EventStudyResult  # noqa: E402
from advisor.research.vintage import frozen_close, load_vintage  # noqa: E402
from advisor.universe.loader import load_universe  # noqa: E402
from advisor.universe.vintage import universe_vintage_id  # noqa: E402

VID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
EXPECTED_A02 = 106_363
EXPECTED_CRYPTO = 5_112
EXPECTED_P4 = 101_251
EXPECTED_ASSETS = 90
MAX_HOLD = 40
BLOCK_LENGTHS = (40, 60, 80, 120)
OUT = Path(__file__).resolve().parent
LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"


def _stop(message: str) -> None:
    raise SystemExit(f"STOP: {message}")


def main() -> None:
    cfg = load_config("config.yaml")
    universe = load_universe(cfg.universe_path)
    vintage = load_vintage(VID)
    # A-02 enumeró con el selector de v1 ("1.0" → legacy_v1). El modo de contexto solo cambia el
    # score, que P4 no lee; en legacy ninguna señal se descarta por contexto.
    with (
        patch.object(event_study, "evaluate_managed_event", lambda *a, **k: None),
        patch.object(event_study, "evaluate_potential_event", lambda *a, **k: None),
    ):
        result = event_study.run_event_study_on_vintage(
            cfg, universe, vintage, horizonte="swing", cost_pct=0.2, score_model_version="1.0"
        )
    if len(result.signals) != EXPECTED_A02:
        _stop(f"A-02 swing {len(result.signals)} ≠ {EXPECTED_A02}")
    if any(signal.managed is not None or signal.potential is not None for signal in result.signals):
        _stop("alguna señal trae desenlace")

    crypto = {symbol for symbol in result.evaluated_assets if universe.get(symbol).asset_class == "crypto"}
    kept = [signal for signal in result.signals if signal.observation.asset not in crypto]
    n_crypto = len(result.signals) - len(kept)
    if n_crypto != EXPECTED_CRYPTO or len(kept) != EXPECTED_P4:
        _stop(f"cripto {n_crypto} (esperado {EXPECTED_CRYPTO}); P4 {len(kept)} (esperado {EXPECTED_P4})")
    assets = sorted({signal.observation.asset for signal in kept})
    if len(assets) != EXPECTED_ASSETS:
        _stop(f"activos {len(assets)} ≠ {EXPECTED_ASSETS}")

    p4 = EventStudyResult(
        data_vintage_id=result.data_vintage_id,
        horizonte=result.horizonte,
        cost_pct=result.cost_pct,
        warmup_bars=result.warmup_bars,
        max_hold_bars=result.max_hold_bars,
        universe_vintage_id=result.universe_vintage_id,
        population_name="P4_A02_sin_cripto",
        signals=kept,
        evaluated_assets=[symbol for symbol in result.evaluated_assets if symbol not in crypto],
        asset_bar_counts={k: v for k, v in result.asset_bar_counts.items() if k not in crypto},
        session_dates_by_asset={k: v for k, v in result.session_dates_by_asset.items() if k not in crypto},
    )

    # Identidad canónica, con la misma forma que la de P3 (activo y sesión de plaza), y una segunda
    # sobre los signal_id literales.
    keys = []
    for signal in kept:
        asset = universe.get(signal.observation.asset)
        views = vintage.by_symbol[asset.primary_symbol]
        session = session_date_of(
            views.signal_prices.index[signal.observation.signal_idx], mercado_para_simbolo(asset, asset.primary_symbol)
        )
        if session is None:
            _stop(f"{asset.symbol}: señal sin sesión de plaza")
        keys.append((asset.symbol, session))
    if len(set(keys)) != len(keys):
        _stop("pares (activo, sesión) duplicados")
    population_sha256 = hashlib.sha256("\n".join(sorted(f"{s}\t{d}" for s, d in keys)).encode()).hexdigest()
    signal_ids_sha256 = hashlib.sha256(
        "\n".join(sorted(signal.observation.signal_id for signal in kept)).encode()
    ).hexdigest()

    blocks = {}
    for length in BLOCK_LENGTHS:
        lookup = _temporal_block_lookup(p4, length, universe)
        occupied = Counter(lookup.block_for(signal) for signal in kept)
        sizes = {block: lookup.sessions_in_block(block) for block in occupied}
        shortest = min(sizes.values())
        blocks[length] = {
            "espina_sesiones": len(lookup.session_spine),
            "bloques_espina": len(set(lookup.session_to_block.values())),
            "bloques_ocupados": len(occupied),
            "primer_y_ultimo_ocupado": [min(occupied), max(occupied)],
            "bloque_ocupado_mas_corto": shortest,
            "valida_P2_5": shortest > MAX_HOLD,
            "senales_min_por_bloque": min(occupied.values()),
        }

    regions = Counter(universe.get(signal.observation.asset).region for signal in kept)

    # Régimen PIT por señal, solo para estratificar: lo no calculable NO sale de P4 (OD-P4-11).
    asia_symbols = tuple(sorted(a.primary_symbol for a in context_assets_of(universe) if a.region == "ASIA"))
    symbols = (cfg.market_context.vix_symbol, cfg.market_context.trend_symbol, *asia_symbols)
    closes = {s: c for s in symbols if (c := frozen_close(vintage, s)) is not None}
    resolver = PointInTimeContextResolver(
        closes, cfg.market_context, asia_symbols=asia_symbols, settlement_minutes=cfg.data_quality.settlement_minutes
    )
    regime: Counter[str] = Counter()
    no_calc: Counter[str] = Counter()
    for signal in kept:
        obs = signal.observation
        asset = universe.get(obs.asset)
        views = vintage.by_symbol[asset.primary_symbol]
        market = mercado_para_simbolo(asset, asset.primary_symbol)
        session = session_date_of(views.signal_prices.index[obs.signal_idx], market)
        entry = session_date_of(views.signal_prices.index[obs.signal_idx + 1], market)
        ts = analysis_timestamp_for_signal(market, session, entry, settlement_minutes=cfg.data_quality.settlement_minutes)
        if ts is None:
            regime["NO_CALCULABLE_CONTEXT"] += 1
            no_calc["SIN_ANALYSIS_TIMESTAMP"] += 1
            continue
        resolved = resolver.resolve(ts)
        if resolved.calculable:
            regime[resolved.context.label] += 1
        else:
            regime["NO_CALCULABLE_CONTEXT"] += 1
            for code in resolved.exclusions or resolved.no_calculable_codes or ("SIN_CODIGO",):
                no_calc[code] += 1

    output = {
        "label": LABEL,
        "data_vintage_id": VID,
        "universe_vintage_id": universe_vintage_id(universe),
        "config_score_model_version": cfg.scoring.score_model_version,
        "enumeracion": "run_event_study_on_vintage(swing, score_model_version='1.0'), desenlaces parcheados a None",
        "a02_swing": len(result.signals),
        "cripto_excluido": n_crypto,
        "cripto_activos": sorted(crypto),
        "p4_swing": len(kept),
        "activos": len(assets),
        "population_sha256_activo_sesion": population_sha256,
        "signal_ids_sha256": signal_ids_sha256,
        "regiones": dict(sorted(regions.items())),
        "bloques": {str(k): v for k, v in blocks.items()},
        "regimen_pit": dict(sorted(regime.items())),
        "no_calculable_por_codigo": dict(sorted(no_calc.items())),
    }
    (OUT / "censo-p4.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
