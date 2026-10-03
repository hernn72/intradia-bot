"""Genera politicas-finales.json con las funciones canónicas de P5, sin abrir desenlaces.

Uso, desde la raíz del repositorio: python evidence/2026-10-03-T-021-p5-cierre/generar_politicas.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from advisor.config import load_config
from advisor.research import p5

OUT = Path(__file__).with_name("politicas-finales.json")
EXPECTED = {
    "B2": (
        "c5d60f44e89a754f34dfc685cda5073af1c0f9dbb04ab3ec14a813d423f81760",
        "d5d6a533fe846a6ebb5d5c8e313c84f2a5b4e04095d08386e5d903dce73101b9",
    ),
    "S2": (
        "8a151b80d91bf73e431ec38e5e21f22268783bbd0a26d5f72e6ef8887aca0dbb",
        "e37ee93363dbbd7c58cae74bba4391ab9ad41dd1f3ed55804a92efb531e44d11",
    ),
}


def main() -> int:
    config = load_config("config.yaml")
    records = []
    for cell in (p5.B2_CELL, p5.S2_CELL):
        payload = p5.policy_payload(config, cell)
        canonical = p5.canonical_json(payload)
        regenerated = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        config_hash = p5.advisor_config_hash(config, cell)
        if regenerated != p5.policy_sha256(config, cell) or (config_hash, regenerated) != EXPECTED[cell.gid]:
            print(f"STOP: {cell.gid} no reproduce sus hashes ({config_hash}, {regenerated})", file=sys.stderr)
            return 2
        records.append(
            {
                "id": cell.gid,
                "advisor_config_hash": config_hash,
                "policy_payload": payload,
                "canonical_json": canonical,
                "policy_sha256": regenerated,
            }
        )
    document = {
        "esquema": "intradia.p5.politicas_finales.v1",
        "p5_prereg_sha": p5.P5_PREREG_SHA,
        "label": p5.UNIVERSE_LABEL,
        "politicas": records,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ok: {[record['id'] for record in records]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
