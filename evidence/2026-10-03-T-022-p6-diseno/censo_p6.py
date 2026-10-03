"""Censo estructural de P6 (T-022), sin desenlaces.

Lee el universo vigente, la cosecha congelada 071ddb2b… y la lista de los 90 activos de P4/P5.
Solo publica metadatos, recuentos de acciones corporativas, fechas de primera y última sesión y
disponibilidad de FX/sector. No calcula retornos, `net_R`, ni nada de ninguna política.

Uso, desde la raíz del repositorio:
    python evidence/2026-10-03-T-022-p6-diseno/censo_p6.py
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import pandas as pd

from advisor.config import load_config
from advisor.data.calendars import EXCHANGE_OVERRIDES_PATH, calendar_mic, exchange_calendar, load_exchange_overrides
from advisor.data.sessions import MARKET_SESSIONS
from advisor.research.vintage import read_raw_csv
from advisor.universe.loader import load_universe

DATA_VINTAGE_ID = "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841"
VINTAGE_DIR = Path("data/vintages") / DATA_VINTAGE_ID
P4_PREFLIGHT = Path("evidence/2026-10-01-T-020-p4/preflight/p4-preflight.json")
OUT = Path(__file__).with_name("censo-p6.json")
WARMUP_BARS = 120  # min_bars del horizonte swing (config.yaml)
LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"


def population_assets() -> List[str]:
    data = json.loads(P4_PREFLIGHT.read_text(encoding="utf-8"))
    return sorted(data["estratos"]["B2"]["activos"])


def manifest_by_symbol() -> Dict[str, Dict[str, Any]]:
    manifest = json.loads((VINTAGE_DIR / "manifest.json").read_text(encoding="utf-8"))
    return {entry["symbol"]: entry for entry in manifest["assets"]}


def fx_structure(manifest: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for symbol, entry in sorted(manifest.items()):
        if not symbol.endswith("=X"):
            continue
        stamps = pd.DatetimeIndex(read_raw_csv(VINTAGE_DIR / entry["filename"]).index)
        out[symbol] = {
            "barras": len(stamps),
            "primera_marca_utc": str(stamps[0]),
            "ultima_marca_utc": str(stamps[-1]),
            "horas_utc_de_la_marca": sorted(set(stamps.strftime("%H:%M"))),
            "series_hash": entry["series_hash"],
        }
    return out


def trend_structure(manifest: Dict[str, Dict[str, Any]], config: Any) -> Dict[str, Any]:
    """Fecha local de la barra que completa la SMA de tendencia (D-55); sin precios ni retornos."""

    symbol = config.market_context.trend_symbol
    sma = config.market_context.trend_sma
    stamps = pd.DatetimeIndex(read_raw_csv(VINTAGE_DIR / manifest[symbol]["filename"]).index)
    local = [stamp.date() for stamp in stamps.tz_convert(ZoneInfo("Europe/Berlin"))]
    return {
        "simbolo": symbol,
        "sma": sma,
        "primera_sesion": str(local[0]),
        "sesion_que_completa_la_sma": str(local[sma - 1]),
        "nota": "con contexto point-in-time, la primera señal OPERAR posible es al cierre de esa sesión",
    }


def calendar_structure(rows: List[Dict[str, Any]], assets: Dict[str, Any], manifest: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Sesiones del calendario efectivo (exchange_calendars + exchange_overrides.yaml) frente a las barras."""

    overrides = load_exchange_overrides()
    missing: Dict[str, List[str]] = {}
    outside: Dict[str, List[str]] = {}
    for row in rows:
        asset = assets[row["asset"]]
        stamps = pd.DatetimeIndex(read_raw_csv(VINTAGE_DIR / manifest[row["asset"]]["filename"]).index)
        bars = {stamp.date() for stamp in stamps.tz_convert(ZoneInfo(asset.timezone))}
        calendar = exchange_calendar(asset.market)
        sessions = {pd.Timestamp(day).date() for day in calendar.sessions_in_range(min(bars), max(bars))}
        override = overrides.get(calendar_mic(asset.market))
        if override is not None:
            sessions -= {entry.fecha for entry in override.cierres_adicionales}
            sessions |= {entry.fecha for entry in override.aperturas_forzadas if min(bars) <= entry.fecha <= max(bars)}
        if sessions - bars:
            missing[row["asset"]] = sorted(str(day) for day in sessions - bars)
        if bars - sessions:
            outside[row["asset"]] = sorted(str(day) for day in bars - sessions)
    return {
        "fuente": "exchange_calendars + exchange_overrides.yaml",
        "exchange_overrides_sha256": hashlib.sha256(Path(EXCHANGE_OVERRIDES_PATH).read_bytes()).hexdigest(),
        "sesiones_sin_barra": sum(len(days) for days in missing.values()),
        "sesiones_sin_barra_por_activo": missing,
        "barras_fuera_de_calendario": sum(len(days) for days in outside.values()),
        "barras_fuera_de_calendario_por_activo": outside,
    }


def main() -> int:
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    assets = {asset.symbol: asset for group in universe.groups.values() for asset in group}
    manifest = manifest_by_symbol()
    symbols = population_assets()
    fx_symbols = sorted(symbol for symbol in manifest if symbol.endswith("=X"))
    rows: List[Dict[str, Any]] = []
    for symbol in symbols:
        asset = assets[symbol]
        entry = manifest[symbol]
        raw = read_raw_csv(VINTAGE_DIR / entry["filename"])
        dividends = raw["Dividends"].astype(float)
        splits = raw["Stock Splits"].astype(float)
        currency = asset.primary_currency if asset.primary_currency else asset.currency
        stamps = pd.DatetimeIndex(raw.index)
        local_dates = [stamp.date() for stamp in stamps.tz_convert(ZoneInfo(asset.timezone))]
        rows.append(
            {
                "asset": symbol,
                "instrument_id": asset.instrument_id,
                "region": asset.region,
                "asset_class": asset.asset_class,
                "market": asset.market,
                "session_defined": asset.market in MARKET_SESSIONS,
                "timezone": asset.timezone,
                "currency": asset.currency,
                "primary_currency": asset.primary_currency,
                "economic_currency": asset.economic_currency,
                "fx_needed": currency != config.base_currency,
                "fx_pair_needed": None if currency == config.base_currency else f"EUR{currency}=X",
                "fx_in_vintage": currency == config.base_currency or f"EUR{currency}=X" in fx_symbols,
                "sector_available": hasattr(asset, "sector"),
                "dividend_column": "Dividends" in raw.columns,
                "dividend_events": int((dividends > 0).sum()),
                "split_events": int((splits > 0).sum()),
                "bars": len(raw),
                "first_bar_timestamp_utc": str(stamps[0]),
                "last_bar_timestamp_utc": str(stamps[-1]),
                "first_valid_session": str(local_dates[0]),
                "last_valid_session": str(local_dates[-1]),
                "warmup_complete_session": str(local_dates[WARMUP_BARS]) if len(local_dates) > WARMUP_BARS else None,
                "series_hash": entry["series_hash"],
                "corporate_actions_hash": entry["corporate_actions_hash"],
            }
        )

    def count(key: str) -> Dict[str, int]:
        return dict(sorted(Counter(str(row[key]) for row in rows).items()))

    first_sessions = Counter(row["first_valid_session"] for row in rows)
    last_sessions = Counter(row["last_valid_session"] for row in rows)
    summary = {
        "label": LABEL,
        "data_vintage_id": DATA_VINTAGE_ID,
        "activos": len(rows),
        "asset_list_sha256": hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest(),
        "base_currency": config.base_currency,
        "por_region": count("region"),
        "por_asset_class": count("asset_class"),
        "por_market": count("market"),
        "por_session_defined": count("session_defined"),
        "por_timezone": count("timezone"),
        "por_currency": count("currency"),
        "por_primary_currency": count("primary_currency"),
        "por_economic_currency": count("economic_currency"),
        "fx_en_cosecha": fx_symbols,
        "pares_fx_necesarios": sorted({row["fx_pair_needed"] for row in rows if row["fx_pair_needed"]}),
        "activos_que_necesitan_fx": sum(1 for row in rows if row["fx_needed"]),
        "activos_sin_fx_en_cosecha": sorted(row["asset"] for row in rows if not row["fx_in_vintage"]),
        "sector_disponible": sum(1 for row in rows if row["sector_available"]),
        "activos_con_dividendos": sum(1 for row in rows if row["dividend_events"] > 0),
        "eventos_de_dividendo": sum(row["dividend_events"] for row in rows),
        "activos_con_splits": sorted(row["asset"] for row in rows if row["split_events"] > 0),
        "eventos_de_split": sum(row["split_events"] for row in rows),
        "primera_sesion": dict(sorted(first_sessions.items())),
        "ultima_sesion": dict(sorted(last_sessions.items())),
        "fechas": "fecha de sesión local de la plaza (zona del activo); la marca UTC de la barra va aparte",
        "calentamiento_completo": dict(sorted(Counter(str(row["warmup_complete_session"]) for row in rows).items())),
        "columnas_de_la_cosecha": list(read_raw_csv(VINTAGE_DIR / manifest[symbols[0]]["filename"]).columns),
        "fecha_de_pago_de_dividendos": "no disponible: la cosecha solo trae la columna Dividends en la fecha ex",
        "aperturas_en_sessions_py": "no: MarketSession solo define zona y cierre regular",
        "mercados_de_sesion_definidos": sorted(MARKET_SESSIONS),
    }
    summary["fx_series"] = fx_structure(manifest)
    summary["contexto_tendencia"] = trend_structure(manifest, config)
    summary["calendario_efectivo"] = calendar_structure(rows, assets, manifest)
    OUT.write_text(json.dumps({"resumen": summary, "activos": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
