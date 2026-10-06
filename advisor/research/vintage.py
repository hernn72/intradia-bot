"""Congelación reproducible de históricos para investigación.

P2.0 congela el material descargado, no una vista ajustada. El OHLCV se
persiste tal y como lo devuelve yfinance con ``auto_adjust=False`` y
``actions=True``; las vistas de ejecución, señal y hueco para catalizador se
derivan al cargar.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional
from urllib.parse import quote

import pandas as pd

from advisor.data.market_data import MarketDataProvider, validate_exact_range
from advisor.universe.models import Asset, Universe

RAW_COLUMNS = ("Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits")
PRICE_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
ACTION_COLUMNS = ("Dividends", "Stock Splits")
CANONICAL_SERIES_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume", "dividends", "stock_splits")
CANONICAL_ACTION_COLUMNS = ("timestamp", "dividends", "stock_splits")
PROVIDER = "yfinance"
# 17 dígitos significativos es lo que garantiza que un float64 sobreviva al
# ciclo CSV -> pandas sin cambiar. Escritura y hash canónico DEBEN usar la
# misma: con precisiones distintas, una cosecha recién escrita no se puede
# releer porque su hash ya no coincide con el del manifiesto.
FLOAT_PRECISION = 17
ADJUSTMENT_POLICY = {
    "download": "auto_adjust=False, actions=True",
    "execution_prices": "OHLC descargado: ajustado por splits, no por dividendos",
    "signal_prices": "misma escala que execution_prices",
    "gap_for_catalyst": "close_referencia(t)=close(t-1)-dividendo(t)",
    "timestamp_normalization": "UTC ISO-8601 si hay zona; fecha naive YYYY-MM-DD si no la hay",
}


@dataclass(frozen=True)
class VintageViews:
    """Material congelado y vistas derivadas de un símbolo."""

    raw: pd.DataFrame
    execution_prices: pd.DataFrame
    signal_prices: pd.DataFrame
    gap_for_catalyst: pd.DataFrame


@dataclass(frozen=True)
class VintageLoad:
    """Cosecha cargada desde disco y verificada."""

    data_vintage_id: str
    manifest: Dict
    by_symbol: Dict[str, VintageViews]


@dataclass(frozen=True)
class VintageRunResult:
    """Resultado de una campaña de descarga."""

    data_vintage_id: str
    manifest_path: Path
    succeeded: List[str]
    failed: Dict[str, str]


def freeze_vintage(
    symbols: Iterable[str],
    provider: MarketDataProvider,
    *,
    period: Optional[str] = None,
    interval: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    root_dir: str | Path = "data/vintages",
    downloaded_at: Optional[datetime] = None,
    universe_vintage: Optional[str] = None,
    request_context: Optional[Mapping[str, object]] = None,
) -> VintageRunResult:
    """Descarga símbolos, persiste CSV deterministas y escribe el manifiesto.

    ``universe_vintage`` queda dentro del manifiesto para que una cosecha sepa
    con qué universo se congeló. Sin él, la guarda de INV-08 ampliada que
    compara universos en `replay_managed_population` no se dispara nunca,
    porque el campo que consulta no lo escribía nadie.

    La petición es por ``period`` (la de siempre, manifiesto ``schema_version``
    1 sin cambios) o exacta por ``start``/``end`` (``start`` inclusivo, ``end``
    exclusivo, como en yfinance), nunca las dos. La exacta escribe
    ``schema_version`` 2 con la petición completa en ``request`` y rechaza el
    símbolo cuya respuesta traiga alguna barra fuera de ``[start, end)``.
    ``request_context`` (solo en la exacta) queda en ``request.context`` y
    entra en el hash: liga la cosecha al contexto que la pidió.
    """

    exact = validate_exact_range(start, end)
    if exact == (period is not None):
        raise ValueError("freeze_vintage: o period, o start y end; exactamente una de las dos peticiones")
    if request_context is not None and not exact:
        raise ValueError("freeze_vintage: request_context solo existe en la petición exacta")
    timestamp = _downloaded_at(downloaded_at)
    root = Path(root_dir)
    requested = _unique_symbols(symbols)
    prepared: List[tuple[str, str, pd.DataFrame, Dict]] = []
    failed: Dict[str, str] = {}

    for symbol in requested:
        try:
            if exact:
                assert start is not None and end is not None
                history = provider.get_raw_history(symbol, interval=interval, start=start, end=end)
                _require_inside_range(history, start, end)
                request_fields: Dict = {
                    "requested_start": start,
                    "requested_end": end,
                    "end_exclusive": True,
                    "auto_adjust": False,
                    "actions": True,
                }
            else:
                assert period is not None
                history = provider.get_raw_history(symbol, period=period, interval=interval)
                request_fields = {"requested_range": period}
            raw = normalize_raw_history(history)
            series_hash = hash_series(raw)
            actions_hash = hash_actions(raw)
            filename = _filename_for_symbol(symbol)
            prepared.append(
                (
                    symbol,
                    filename,
                    raw,
                    {
                        "symbol": symbol,
                        "filename": filename,
                        "interval": interval,
                        **request_fields,
                        "series_hash": series_hash,
                        "corporate_actions_hash": actions_hash,
                        "provider": PROVIDER,
                        "provider_version": _provider_version(),
                        "adjustment_policy": ADJUSTMENT_POLICY,
                        "downloaded_at": timestamp,
                    },
                )
            )
        except Exception as exc:
            failed[symbol] = str(exc)

    if not prepared:
        raise ValueError("No se pudo congelar ningún símbolo")

    manifest_body: Dict = {
        "schema_version": 2 if exact else 1,
        "created_at": timestamp,
        "assets": [entry for _, _, _, entry in prepared],
        "failed": [{"symbol": symbol, "error": failed[symbol]} for symbol in sorted(failed)],
    }
    if exact:
        manifest_body["request"] = {
            "symbols": requested,
            "symbols_sha256": hash_symbol_list(requested),
            "start": start,
            "end": end,
            "end_exclusive": True,
            "interval": interval,
            "auto_adjust": False,
            "actions": True,
            "provider": PROVIDER,
            "provider_version": _provider_version(),
        }
        if request_context is not None:
            manifest_body["request"]["context"] = dict(request_context)
    # Va dentro del cuerpo que se hashea a propósito: el universo forma parte
    # de la identidad de la cosecha, no es un adorno. Consecuencia asumida: las
    # cosechas congeladas a partir de aquí tienen un `data_vintage_id` distinto
    # del que tendrían con el esquema anterior. La cosecha `071ddb2b…` ya
    # existente no lo lleva y se sigue leyendo igual, porque `load_vintage`
    # recalcula el hash sobre el cuerpo que encuentra.
    if universe_vintage is not None:
        manifest_body["universe_vintage_id"] = universe_vintage
    manifest_hash = hash_manifest(manifest_body)
    data_vintage_id = manifest_hash
    vintage_dir = root / data_vintage_id
    vintage_dir.mkdir(parents=True, exist_ok=True)

    for _, filename, raw, _ in prepared:
        _write_raw_csv(raw, vintage_dir / filename)

    manifest = dict(manifest_body)
    manifest["manifest_hash"] = manifest_hash
    manifest["data_vintage_id"] = data_vintage_id
    manifest_path = vintage_dir / "manifest.json"
    manifest_path.write_text(_canonical_json(manifest) + "\n", encoding="utf-8")

    return VintageRunResult(
        data_vintage_id=data_vintage_id,
        manifest_path=manifest_path,
        succeeded=[symbol for symbol, _, _, _ in prepared],
        failed=failed,
    )


def load_vintage(data_vintage_id: str, *, root_dir: str | Path = "data/vintages") -> VintageLoad:
    """Carga una cosecha desde disco y verifica sus hashes antes de exponerla."""

    vintage_dir = Path(root_dir) / data_vintage_id
    manifest_path = vintage_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No existe el manifiesto de la cosecha: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest_hash = manifest.get("manifest_hash")
    if manifest.get("data_vintage_id") != data_vintage_id:
        raise ValueError("El data_vintage_id del manifiesto no coincide con el directorio solicitado")

    manifest_body = {k: v for k, v in manifest.items() if k not in {"manifest_hash", "data_vintage_id"}}
    actual_manifest_hash = hash_manifest(manifest_body)
    if actual_manifest_hash != expected_manifest_hash or expected_manifest_hash != data_vintage_id:
        raise ValueError("Hash de manifiesto inválido: la cosecha fue editada o está corrupta")

    loaded: Dict[str, VintageViews] = {}
    for asset_entry in manifest["assets"]:
        symbol = asset_entry["symbol"]
        raw = read_raw_csv(vintage_dir / asset_entry["filename"])
        actual_series_hash = hash_series(raw)
        if actual_series_hash != asset_entry["series_hash"]:
            raise ValueError(f"Hash de serie inválido para {symbol}: la cosecha fue editada o está corrupta")
        actual_actions_hash = hash_actions(raw)
        if actual_actions_hash != asset_entry["corporate_actions_hash"]:
            raise ValueError(f"Hash de acciones corporativas inválido para {symbol}")
        loaded[symbol] = build_views(raw)

    return VintageLoad(data_vintage_id=data_vintage_id, manifest=manifest, by_symbol=loaded)


@dataclass(frozen=True)
class VintageStructure:
    """Fechas y acciones corporativas de una cosecha, sin precios.

    ``by_symbol`` tiene, por símbolo, las filas que ``load_vintage`` conservaría (mismo índice que
    ``execution_prices``) con solo ``Dividends`` y ``Stock Splits``, verificadas contra el
    ``corporate_actions_hash`` del manifiesto.
    """

    data_vintage_id: str
    manifest: Dict
    by_symbol: Dict[str, pd.DataFrame]


def _verified_manifest(data_vintage_id: str, root_dir: str | Path) -> tuple[Path, Dict]:
    vintage_dir = Path(root_dir) / data_vintage_id
    manifest_path = vintage_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No existe el manifiesto de la cosecha: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("data_vintage_id") != data_vintage_id:
        raise ValueError("El data_vintage_id del manifiesto no coincide con el directorio solicitado")
    manifest_body = {k: v for k, v in manifest.items() if k not in {"manifest_hash", "data_vintage_id"}}
    expected_manifest_hash = manifest.get("manifest_hash")
    if hash_manifest(manifest_body) != expected_manifest_hash or expected_manifest_hash != data_vintage_id:
        raise ValueError("Hash de manifiesto inválido: la cosecha fue editada o está corrupta")
    return vintage_dir, manifest


def _structural_rows(path: Path) -> pd.DataFrame:
    """Filas de ``read_raw_csv`` con solo las acciones corporativas.

    Las columnas de precio se leen como texto y solo para saber qué filas descarta
    ``normalize_raw_history`` (las que tienen algún precio vacío): ningún precio se convierte a número.
    """

    df = pd.read_csv(path, index_col="timestamp", dtype=str)
    df.index = pd.Index([str(value) for value in df.index], name="timestamp")
    df = df.sort_index()
    df.index = pd.Index([_normalize_timestamp(ts) for ts in df.index], name="timestamp")
    present = [column for column in PRICE_COLUMNS if column in df.columns]
    keep = df[present].notna().all(axis=1) if len(present) == len(PRICE_COLUMNS) else pd.Series(False, index=df.index)
    actions = pd.DataFrame(index=df.index)
    for column in ACTION_COLUMNS:
        actions[column] = df[column].astype(float).fillna(0.0) if column in df.columns else 0.0
    actions = actions.loc[keep.to_numpy()]
    if actions.empty:
        raise ValueError("histórico vacío tras limpiar precios")
    return actions


def load_vintage_structure(data_vintage_id: str, *, root_dir: str | Path = "data/vintages") -> VintageStructure:
    """Carga solo fechas y acciones corporativas, verificadas contra el manifiesto, sin abrir precios."""

    vintage_dir, manifest = _verified_manifest(data_vintage_id, root_dir)
    loaded: Dict[str, pd.DataFrame] = {}
    for asset_entry in manifest["assets"]:
        symbol = asset_entry["symbol"]
        actions = _structural_rows(vintage_dir / asset_entry["filename"])
        if _hash_action_rows(actions) != asset_entry["corporate_actions_hash"]:
            raise ValueError(f"Hash de acciones corporativas inválido para {symbol}")
        loaded[symbol] = actions
    return VintageStructure(data_vintage_id=data_vintage_id, manifest=manifest, by_symbol=loaded)


def load_price_rows(
    data_vintage_id: str,
    symbol: str,
    timestamps: Iterable[str],
    columns: Iterable[str],
    *,
    root_dir: str | Path = "data/vintages",
) -> pd.DataFrame:
    """Lee solo las filas y columnas pedidas de un símbolo, ya normalizadas.

    Sirve para comprobaciones estructurales que necesitan unos pocos precios (p. ej. la coherencia
    dividendo/split en las fechas ex) sin construir las vistas. ``Adj Close`` no entra en
    ``series_hash``; estas filas no se verifican contra el manifiesto, solo el manifiesto en sí.
    """

    vintage_dir, manifest = _verified_manifest(data_vintage_id, root_dir)
    entry = next((asset for asset in manifest["assets"] if asset["symbol"] == symbol), None)
    if entry is None:
        raise KeyError(f"{symbol} no está en la cosecha {data_vintage_id}")
    wanted = set(timestamps)
    cols = list(columns)
    df = pd.read_csv(vintage_dir / entry["filename"], index_col="timestamp", dtype=str)
    df.index = pd.Index([_normalize_timestamp(str(ts)) for ts in df.index], name="timestamp")
    rows = df.loc[df.index.isin(wanted), cols].astype(float)
    missing = wanted - set(rows.index)
    if missing:
        raise KeyError(f"{symbol}: filas ausentes en la cosecha: {sorted(missing)[:3]}")
    return rows.sort_index()


def resolve_vintage_id(value: str, root_dir: str | Path = "data/vintages") -> str:
    """Acepta el identificador entero o un prefijo inequívoco.

    Un `data_vintage_id` son 64 caracteres de hash: escribirlo entero a mano en
    cada comando invita a equivocarse. El prefijo solo vale si identifica una
    sola cosecha; si es ambiguo, se dice cuáles y no se elige por el operador.
    """

    root = Path(root_dir)
    if (root / value / "manifest.json").is_file():
        return value
    matches = [path.name for path in root.iterdir() if path.is_dir() and path.name.startswith(value)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"No existe la cosecha {value!r} en {root_dir}")
    raise ValueError(f"Prefijo de cosecha ambiguo {value!r}: {matches}")


def frozen_close(vintage: VintageLoad, symbol: Optional[str]) -> Optional[pd.Series]:
    """Cierres congelados de un símbolo, o ``None`` si la cosecha no lo tiene."""

    if symbol is None:
        return None
    views = vintage.by_symbol.get(symbol)
    if views is None:
        return None
    return views.signal_prices["Close"]


def build_views(raw: pd.DataFrame) -> VintageViews:
    """Deriva las tres vistas P2.0 a partir del material bruto."""

    normalized = normalize_raw_history(raw)
    execution = normalized.loc[:, PRICE_COLUMNS].copy()
    signal = execution.copy()
    gap = execution.copy()
    gap["Reference Close"] = normalized["Close"].shift(1) - normalized["Dividends"]
    gap["Dividends"] = normalized["Dividends"]
    return VintageViews(raw=normalized, execution_prices=execution, signal_prices=signal, gap_for_catalyst=gap)


def hash_series(raw: pd.DataFrame) -> str:
    """Hash canónico de OHLCV usado y acciones corporativas."""

    normalized = normalize_raw_history(raw)
    rows = _canonical_rows(normalized, CANONICAL_SERIES_COLUMNS)
    return _sha256(_canonical_json({"columns": CANONICAL_SERIES_COLUMNS, "rows": rows}))


def hash_actions(raw: pd.DataFrame) -> str:
    """Hash canónico de dividendos y splits."""

    return _hash_action_rows(normalize_raw_history(raw))


def _hash_action_rows(normalized: pd.DataFrame) -> str:
    rows = _canonical_rows(normalized, CANONICAL_ACTION_COLUMNS)
    return _sha256(_canonical_json({"columns": CANONICAL_ACTION_COLUMNS, "rows": rows}))


def hash_symbol_list(symbols: Iterable[str]) -> str:
    """Hash de una lista de símbolos en su orden: SHA-256 de los símbolos unidos por saltos de línea."""

    return _sha256("\n".join(symbols))


def _require_inside_range(history: pd.DataFrame, start: str, end: str) -> None:
    """Rechaza una respuesta con barras fuera de ``[start, end)``.

    La fecha de cada barra es la de su propia marca temporal, en la zona en que la sirve el proveedor (la
    de la plaza), antes de normalizar a UTC: una sesión asiática a medianoche local cae el día anterior
    en UTC. No se recorta nada: una barra fuera de la petición invalida el símbolo.
    """

    if history is None or history.empty:
        return
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    outside = sorted({pd.Timestamp(ts).date() for ts in history.index if not first <= pd.Timestamp(ts).date() < last})
    if outside:
        raise ValueError(f"barras fuera de la petición [{start}, {end}): {[d.isoformat() for d in outside[:3]]}")


def hash_manifest(manifest_body: Dict) -> str:
    """Hash canónico del manifiesto, sin los campos de identidad derivados."""

    return _sha256(_canonical_json(manifest_body))


def normalize_raw_history(history: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas y orden temporal sin reconstruir ajustes de precio."""

    if history is None or history.empty:
        raise ValueError("histórico vacío")

    normalized = history.copy()
    for column in RAW_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = 0.0 if column in ACTION_COLUMNS else math.nan

    normalized = normalized.loc[:, RAW_COLUMNS].sort_index()
    normalized.index = pd.Index([_normalize_timestamp(ts) for ts in normalized.index], name="timestamp")
    normalized[list(ACTION_COLUMNS)] = normalized.loc[:, list(ACTION_COLUMNS)].fillna(0.0)
    normalized = normalized.dropna(subset=list(PRICE_COLUMNS))
    if normalized.empty:
        raise ValueError("histórico vacío tras limpiar precios")
    return normalized


def read_raw_csv(path: str | Path) -> pd.DataFrame:
    """Lee un CSV congelado con índice temporal estable."""

    df = pd.read_csv(path, index_col="timestamp", float_precision="round_trip")
    df.index = pd.Index([str(value) for value in df.index], name="timestamp")
    return normalize_raw_history(df)


def select_symbols(universe: Universe, *, groups: Optional[List[str]] = None, symbols: Optional[List[str]] = None) -> List[str]:
    """Selecciona símbolos del universo para una campaña."""

    if symbols:
        selected = []
        for symbol in symbols:
            asset = universe.get(symbol)
            if asset is None:
                raise ValueError(f"'{symbol}' no está en el universo")
            selected.append(asset.symbol)
        return _unique_symbols(selected)

    assets: List[Asset]
    if groups is None:
        assets = universe.all_assets()
    else:
        unknown = [group for group in groups if group not in universe.groups]
        if unknown:
            raise ValueError(f"grupos desconocidos: {unknown}. Disponibles: {sorted(universe.groups)}")
        assets = [asset for group in groups for asset in universe.groups[group]]
    return _unique_symbols(asset.symbol for asset in assets)


def _write_raw_csv(raw: pd.DataFrame, path: Path) -> None:
    raw.to_csv(path, index_label="timestamp", float_format=f"%.{FLOAT_PRECISION}g", lineterminator="\n")


def _canonical_rows(df: pd.DataFrame, columns: tuple[str, ...]) -> List[List[str]]:
    rows: List[List[str]] = []
    for timestamp, row in df.iterrows():
        values = [_canonical_timestamp(timestamp)]
        if columns == CANONICAL_SERIES_COLUMNS:
            values.extend(_canonical_float(row[column]) for column in PRICE_COLUMNS)
            values.extend(_canonical_float(row[column]) for column in ACTION_COLUMNS)
        else:
            values.extend(_canonical_float(row[column]) for column in ACTION_COLUMNS)
        rows.append(values)
    return rows


def _canonical_float(value: object) -> str:
    number = float(value) if isinstance(value, (int, float)) else float(str(value))
    if math.isnan(number):
        return "NaN"
    if math.isinf(number):
        return "Infinity" if number > 0 else "-Infinity"
    if number == 0:
        number = 0.0
    return format(number, f".{FLOAT_PRECISION}g")


def _normalize_timestamp(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(timezone.utc)
        return timestamp.isoformat().replace("+00:00", "Z")
    if timestamp.time() == datetime.min.time():
        return timestamp.date().isoformat()
    return timestamp.isoformat()


def _canonical_timestamp(value: object) -> str:
    return _normalize_timestamp(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _provider_version() -> str:
    try:
        return metadata.version("yfinance")
    except metadata.PackageNotFoundError:  # pragma: no cover - yfinance es dependencia del proyecto
        return "unknown"


def _downloaded_at(value: Optional[datetime]) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _filename_for_symbol(symbol: str) -> str:
    return f"{quote(symbol.upper(), safe='')}.csv"


def _unique_symbols(symbols: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for symbol in symbols:
        cleaned = symbol.strip().upper()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result
