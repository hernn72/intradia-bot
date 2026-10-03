"""Calcula P6_DATA_ID (T-022 §18, D-69) a partir de identidades ya congeladas, sin desenlaces.

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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    census = json.loads(CENSUS.read_text(encoding="utf-8"))["resumen"]
    fx = json.loads((HERE / "fx" / "fx-manifest.json").read_text(encoding="utf-8"))
    sector = json.loads((HERE / "p6-sector-map-resumen.json").read_text(encoding="utf-8"))
    components = {
        "market_data_vintage": census["data_vintage_id"],
        "universe_vintage": "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19",
        "asset_list_sha256": census["asset_list_sha256"],
        "fx": {
            "fuente_usada": fx["fuente_usada"],
            "fx_vintage_id": fx["fx_vintage_id"],
            "fx_sidecar_csv_sha256": fx["fx_sidecar_csv_sha256"],
        },
        "sector_map": {
            "canonical_sha256": sector["sector_map_canonical_sha256"],
            "yaml_sha256": sector["sector_map_yaml_sha256"],
        },
        "calendar": {
            "exchange_calendars": importlib.metadata.version("exchange_calendars"),
            "exchange_overrides_sha256": sha256_file(Path("exchange_overrides.yaml")),
            "tzdata": importlib.metadata.version("tzdata"),
            "zoneinfo_tzpath": list(zoneinfo.TZPATH),
        },
    }
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result = {
        "esquema": "intradia.p6.data_id.v1",
        "componentes": components,
        "canonical_json": canonical,
        "P6_DATA_ID": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }
    (HERE / "p6-data-id.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"P6_DATA_ID": result["P6_DATA_ID"], **components}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
