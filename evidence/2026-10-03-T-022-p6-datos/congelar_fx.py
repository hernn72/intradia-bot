"""Congela el sidecar FX de P6 según D-69 y T-022 §11 / §11.1, sin desenlaces.

Fuente A: una sola petición fija a Yahoo/yfinance por par (EURUSD=X, EURJPY=X, EURHKD=X) con
start=2021-08-27, end=2026-08-29, interval=1d, auto_adjust=False, actions=True. Solo se reintenta una
llamada que termina con excepción. La primera llamada sin excepción se congela tal cual y se
comprueba una sola vez: el EURUSD=X congelado tiene que reproducir exactamente las 1.300 marcas de la
cosecha 071ddb2b… con su cadena canónica. Si falla, se aplica la fuente B (tipos de referencia del BCE
para USD, JPY y HKD), sin abrir ninguna decisión nueva.

No lee ningún precio de activo ni calcula ningún desenlace de P6.

Uso, desde la raíz del repositorio:
    python evidence/2026-10-03-T-022-p6-datos/congelar_fx.py
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from advisor.research.vintage import (
    CANONICAL_SERIES_COLUMNS,
    _canonical_rows,
    _write_raw_csv,
    hash_series,
    normalize_raw_history,
    read_raw_csv,
)

OUT = Path(__file__).with_name("fx")
VINTAGE_EURUSD = Path("data/vintages/071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841/EURUSD%3DX.csv")
PAIRS = ("EURUSD=X", "EURJPY=X", "EURHKD=X")
REQUEST = {"start": "2021-08-27", "end": "2026-08-29", "interval": "1d", "auto_adjust": False, "actions": True}
MAX_ATTEMPTS_ON_EXCEPTION = 6
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
ECB_CURRENCIES = {"USD": "EURUSD", "JPY": "EURJPY", "HKD": "EURHKD"}
BERLIN = ZoneInfo("Europe/Berlin")
LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def download_yahoo(pair: str) -> Tuple[pd.DataFrame, List[Dict[str, str]], str]:
    """Una sola petición fija; solo se reintenta si la llamada lanza una excepción."""

    attempts: List[Dict[str, str]] = []
    for attempt in range(1, MAX_ATTEMPTS_ON_EXCEPTION + 1):
        started = utc_now()
        try:
            history = yf.Ticker(pair).history(**REQUEST)
        except Exception as exc:
            attempts.append({"intento": str(attempt), "inicio_utc": started, "excepcion": f"{type(exc).__name__}: {exc}"})
            time.sleep(10 * attempt)
            continue
        attempts.append({"intento": str(attempt), "inicio_utc": started, "excepcion": ""})
        return history, attempts, started
    raise RuntimeError(f"{pair}: todas las llamadas terminaron con excepción; no se congela nada")


def canonical_map(raw: pd.DataFrame) -> Dict[str, List[str]]:
    rows = _canonical_rows(normalize_raw_history(raw), CANONICAL_SERIES_COLUMNS)
    return {row[0]: row[1:] for row in rows}


def integrity_eurusd(frozen_raw: pd.DataFrame) -> Dict[str, Any]:
    vintage = canonical_map(read_raw_csv(VINTAGE_EURUSD))
    marks = sorted(vintage)
    first, last = marks[0], marks[-1]
    try:
        sidecar_all = canonical_map(frozen_raw)
    except ValueError as exc:
        return {"ok": False, "motivo": f"respuesta vacía o sin precios: {exc}", "marcas_cosecha": len(marks)}
    in_range = {ts: row for ts, row in sidecar_all.items() if first <= ts <= last}
    missing = sorted(set(vintage) - set(in_range))
    extra = sorted(set(in_range) - set(vintage))
    different = sorted(ts for ts in set(vintage) & set(in_range) if vintage[ts] != in_range[ts])
    ok = not missing and not extra and not different
    return {
        "ok": ok,
        "marcas_cosecha": len(marks),
        "rango": [first, last],
        "marcas_sidecar_en_rango": len(in_range),
        "faltan": len(missing),
        "sobran": len(extra),
        "distintas": len(different),
        "ejemplos_faltan": missing[:5],
        "ejemplos_sobran": extra[:5],
        "ejemplos_distintas": [
            {"marca": ts, "cosecha": vintage[ts], "sidecar": in_range[ts]} for ts in different[:5]
        ],
    }


def contract_rows_yahoo(pair: str, raw: pd.DataFrame, series_hash: str, downloaded_at: str) -> List[Dict[str, Any]]:
    normalized = normalize_raw_history(raw)
    rows = []
    for stamp, row in normalized.iterrows():
        bar = pd.Timestamp(stamp)
        bar = bar.tz_localize("UTC") if bar.tzinfo is None else bar.tz_convert("UTC")
        rows.append(
            {
                "fx_pair": pair,
                "bar_timestamp": bar.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timestamp_available": (bar + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "rate": repr(float(row["Close"])),
                "series_hash": series_hash,
                "provider": "yfinance",
                "provider_version": yf.__version__,
                "downloaded_at": downloaded_at,
            }
        )
    return rows


def freeze_ecb() -> Dict[str, Any]:
    downloaded_at = utc_now()
    with urlopen(ECB_URL, timeout=60) as response:
        payload = response.read()
    (OUT / "ecb-eurofxref-hist.zip").write_bytes(payload)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = archive.namelist()[0]
        table = pd.read_csv(archive.open(name), dtype=str)
    table = table.rename(columns=lambda column: column.strip())
    table["Date"] = table["Date"].str.strip()
    table = table[(table["Date"] >= REQUEST["start"]) & (table["Date"] < REQUEST["end"])].sort_values("Date")
    rows: List[Dict[str, Any]] = []
    per_pair: Dict[str, Any] = {}
    for currency, pair in ECB_CURRENCIES.items():
        values = [(day, value.strip()) for day, value in zip(table["Date"], table[currency]) if value.strip() not in ("", "N/A")]
        series_hash = sha256_bytes(canonical_json([[day, value] for day, value in values]).encode("utf-8"))
        for day, value in values:
            available = datetime.combine(pd.Timestamp(day).date(), datetime.min.time().replace(hour=17), BERLIN).astimezone(timezone.utc)
            rows.append(
                {
                    "fx_pair": pair,
                    "bar_timestamp": day,
                    "timestamp_available": available.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "rate": value,
                    "series_hash": series_hash,
                    "provider": "ECB",
                    "provider_version": "eurofxref-hist",
                    "downloaded_at": downloaded_at,
                }
            )
        per_pair[pair] = {
            "tipos": len(values),
            "primera_fecha": values[0][0] if values else None,
            "ultima_fecha": values[-1][0] if values else None,
            "series_hash": series_hash,
        }
    return {
        "fuente": "B",
        "provider": "ECB",
        "url": ECB_URL,
        "downloaded_at": downloaded_at,
        "zip_sha256": sha256_bytes(payload),
        "fichero_del_zip": name,
        "timestamp_available": "17:00 Europe/Berlin del día de referencia",
        "series": per_pair,
        "rows": rows,
    }


def write_contract(rows: List[Dict[str, Any]]) -> str:
    frame = pd.DataFrame(rows, columns=[
        "fx_pair", "bar_timestamp", "timestamp_available", "rate", "series_hash",
        "provider", "provider_version", "downloaded_at",
    ])
    path = OUT / "fx-sidecar.csv"
    frame.to_csv(path, index=False)
    return sha256_bytes(path.read_bytes())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "fx-manifest.json").exists():
        raise SystemExit("el sidecar FX ya está congelado; no se vuelve a descargar")
    yahoo: Dict[str, Any] = {}
    frozen: Dict[str, pd.DataFrame] = {}
    for pair in PAIRS:
        history, attempts, downloaded_at = download_yahoo(pair)
        frozen[pair] = history
        raw_path = OUT / f"yahoo-{pair.replace('=', '%3D')}.csv"
        entry: Dict[str, Any] = {"intentos": attempts, "downloaded_at": downloaded_at, "filas_devueltas": len(history)}
        if history is not None and not history.empty:
            _write_raw_csv(normalize_raw_history(history), raw_path)
            entry.update(
                {
                    "fichero": raw_path.name,
                    "file_sha256": sha256_bytes(raw_path.read_bytes()),
                    "series_hash": hash_series(history),
                }
            )
        yahoo[pair] = entry
    integrity = integrity_eurusd(frozen["EURUSD=X"])
    manifest: Dict[str, Any] = {
        "label": LABEL,
        "peticion_fuente_A": {**REQUEST, "provider": "yfinance", "provider_version": yf.__version__},
        "fuente_A_yahoo": yahoo,
        "integridad_EURUSD": integrity,
    }
    if integrity["ok"] and all("series_hash" in yahoo[pair] for pair in PAIRS):
        rows: List[Dict[str, Any]] = []
        for pair in PAIRS:
            rows.extend(contract_rows_yahoo(pair, frozen[pair], yahoo[pair]["series_hash"], yahoo[pair]["downloaded_at"]))
        manifest["fuente_usada"] = "A"
        manifest["series_fx"] = {pair: yahoo[pair]["series_hash"] for pair in PAIRS}
    else:
        ecb = freeze_ecb()
        rows = ecb.pop("rows")
        manifest["fuente_usada"] = "B"
        manifest["motivo_B"] = "falla la comprobación de integridad de EURUSD=X de la fuente A (D-69)"
        manifest["fuente_B_ecb"] = ecb
        manifest["series_fx"] = {pair: ecb["series"][pair]["series_hash"] for pair in ecb["series"]}
    manifest["fx_sidecar_csv_sha256"] = write_contract(rows)
    manifest["fx_rate_to_EUR"] = "1 / rate"
    manifest["fx_vintage_id"] = sha256_bytes(
        canonical_json(
            {
                "fuente_usada": manifest["fuente_usada"],
                "series_fx": manifest["series_fx"],
                "fx_sidecar_csv_sha256": manifest["fx_sidecar_csv_sha256"],
            }
        ).encode("utf-8")
    )
    (OUT / "fx-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("fuente_usada", "integridad_EURUSD", "series_fx", "fx_vintage_id")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
