"""Calcula P6_DATA_ID con el payload literal de T-022 §18 y D-69, a partir de identidades ya congeladas.

El payload canónico contiene exactamente:
market_data_vintage, universe_vintage, fx_vintage, sector_map,
calendar {exchange_calendars, exchange_overrides_sha256, tzdata} y asset_list.
Lo demás (fuente FX usada, sha256 del sidecar y del YAML, zoneinfo.TZPATH…) se publica como
metadatos y **no** entra en el hash. No descarga nada ni calcula ningún desenlace.

Uso, desde la raíz del repositorio:
    python evidence/2026-10-03-T-022-p6-datos/calcular_p6_data_id.py
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import zoneinfo
from pathlib import Path

HERE = Path(__file__).parent
CENSUS = Path("evidence/2026-10-03-T-022-p6-diseno/censo-p6.json")
UNIVERSE_VINTAGE = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    census = json.loads(CENSUS.read_text(encoding="utf-8"))["resumen"]
    fx = json.loads((HERE / "fx" / "fx-manifest.json").read_text(encoding="utf-8"))
    sector = json.loads((HERE / "p6-sector-map-resumen.json").read_text(encoding="utf-8"))
    payload = {
        "market_data_vintage": census["data_vintage_id"],
        "universe_vintage": UNIVERSE_VINTAGE,
        "fx_vintage": fx["fx_vintage_id"],
        "sector_map": sector["sector_map_canonical_sha256"],
        "calendar": {
            "exchange_calendars": importlib.metadata.version("exchange_calendars"),
            "exchange_overrides_sha256": sha256_file(Path("exchange_overrides.yaml")),
            "tzdata": importlib.metadata.version("tzdata"),
        },
        "asset_list": census["asset_list_sha256"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result = {
        "esquema": "intradia.p6.data_id.v1",
        "payload": payload,
        "canonical_json": canonical,
        "P6_DATA_ID": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "metadatos_fuera_del_hash": {
            "fx_fuente_usada": fx["fuente_usada"],
            "fx_sidecar_csv_sha256": fx["fx_sidecar_csv_sha256"],
            "sector_map_yaml_sha256": sector["sector_map_yaml_sha256"],
            "zoneinfo_tzpath": list(zoneinfo.TZPATH),
        },
    }
    (HERE / "p6-data-id.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"P6_DATA_ID": result["P6_DATA_ID"], "canonical_json": canonical}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
