"""Congela el mapa sectorial de P6 según D-69 (OD-P6-18/19) y T-022 §12, sin desenlaces.

- Acciones: sector de una fuente externa verificable (Yahoo Finance, campo ``sector`` del perfil del
  emisor vía ``yfinance.Ticker(symbol).info``), como foto congelada con ``observed_at``. No es point-in-time.
- ETF/ETC: categoría estructural por tipo de activo, sin look-through (``equity_etf`` → ``EQUITY_ETF``,
  ``bond_etf`` → ``BOND_ETF``).
- Lo que no se pueda clasificar queda ``UNKNOWN``, dentro del denominador.

El sector es solo descriptivo en P6: nunca decide una entrada, un veto ni la supervivencia.
No lee ningún precio ni calcula ningún desenlace.

Uso, desde la raíz del repositorio:
    python evidence/2026-10-03-T-022-p6-datos/congelar_sector.py
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml
import yfinance as yf

from advisor.config import load_config
from advisor.universe.loader import load_universe

HERE = Path(__file__).parent
OUT_YAML = HERE / "p6-sector-map.yaml"
OUT_JSON = HERE / "p6-sector-map.json"
CENSUS = Path("evidence/2026-10-03-T-022-p6-diseno/censo-p6.json")
STRUCTURAL = {"equity_etf": "EQUITY_ETF", "bond_etf": "BOND_ETF", "etc": "ETC", "commodity_etc": "ETC"}
STOCK_TAXONOMY = "Yahoo Finance sector (perfil del emisor)"
STOCK_SOURCE = f"yfinance {yf.__version__} Ticker.info['sector']"
MAX_ATTEMPTS_ON_EXCEPTION = 6
LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stock_sector(symbol: str) -> tuple[str, str, List[str]]:
    errors: List[str] = []
    for attempt in range(1, MAX_ATTEMPTS_ON_EXCEPTION + 1):
        observed_at = utc_now()
        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:
            errors.append(f"{attempt}: {type(exc).__name__}: {exc}")
            time.sleep(5 * attempt)
            continue
        sector = info.get("sector") if isinstance(info, dict) else None
        return (str(sector).strip() if sector else "UNKNOWN"), observed_at, errors
    return "UNKNOWN", utc_now(), errors


def main() -> int:
    if OUT_YAML.exists():
        raise SystemExit("el mapa sectorial ya está congelado; no se vuelve a consultar")
    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    assets = {asset.symbol: asset for group in universe.groups.values() for asset in group}
    symbols = [row["asset"] for row in json.loads(CENSUS.read_text(encoding="utf-8"))["activos"]]
    entries: List[Dict[str, Any]] = []
    for symbol in symbols:
        asset = assets[symbol]
        if asset.asset_class == "stock":
            sector, observed_at, errors = stock_sector(symbol)
            entry = {
                "instrument_id": asset.instrument_id,
                "asset": symbol,
                "asset_class": asset.asset_class,
                "sector": sector,
                "taxonomy": STOCK_TAXONOMY,
                "source": f"{STOCK_SOURCE} para {symbol}",
                "observed_at": observed_at,
            }
            if errors:
                entry["errores_de_red"] = errors
        else:
            entry = {
                "instrument_id": asset.instrument_id,
                "asset": symbol,
                "asset_class": asset.asset_class,
                "sector": STRUCTURAL.get(asset.asset_class, "UNKNOWN"),
                "taxonomy": "categoría estructural por tipo de activo, sin look-through",
                "source": "universe.yaml asset_class",
                "observed_at": utc_now(),
            }
        entries.append(entry)
    entries.sort(key=lambda item: item["instrument_id"])
    document = {"label": LABEL, "solo_descriptivo": True, "instrumentos": entries}
    OUT_YAML.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    OUT_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage: Dict[str, int] = {}
    for entry in entries:
        coverage[entry["sector"]] = coverage.get(entry["sector"], 0) + 1
    summary = {
        "instrumentos": len(entries),
        "por_sector": dict(sorted(coverage.items())),
        "unknown": [entry["asset"] for entry in entries if entry["sector"] == "UNKNOWN"],
        "sector_map_yaml_sha256": hashlib.sha256(OUT_YAML.read_bytes()).hexdigest(),
        "sector_map_canonical_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }
    (HERE / "p6-sector-map-resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
