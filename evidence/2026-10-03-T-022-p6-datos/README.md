# T-022 / A-06 — Datos auxiliares congelados de P6: sidecar FX, mapa sectorial y `P6_DATA_ID`

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- Base: `main = 03f04a42ea9d2be893e7c4cc09de76bd1c55778b` = **`P6_PREREG_SHA`** (D-69 y T-022 congelados).
- **Sin desenlaces.** No se ha leído ningún precio de activo, ni contado señales OPERAR, ni construido
  ninguna equity o benchmark, ni calculado ninguna métrica de P6. P6 no está implementado.

## FX (D-69, OD-P6-15/16; T-022 §11 y §11.1)

- **Fuente A** (`congelar_fx.py`):
  - una sola petición fija a Yahoo/yfinance 1.7.0 por par, con `start = 2021-08-27`,
    `end = 2026-08-29`, `interval = 1d`, `auto_adjust = False` y `actions = True`;
  - las tres llamadas terminaron sin excepción al primer intento (1.301 barras cada una), y las
    respuestas están congeladas tal cual en `fx/yahoo-*.csv`.
- **Comprobación única de integridad de `EURUSD=X` contra la cosecha: FALLA.**
  - Las 1.300 marcas coinciden: 0 faltan y 0 sobran.
  - **1 barra distinta:** la última, `2026-08-27T23:00:00Z`. El cierre es 1,1587486 en la cosecha y
    1,1656370 en la descarga nueva; probablemente la cosecha (descargada el 2026-08-30) congeló esa
    barra todavía sin cerrar.
  - Detalle en `fx/fx-manifest.json` → `integridad_EURUSD`.
- **Por la regla ratificada se aplica automáticamente la fuente B**, sin abrir ninguna decisión:
  - tipos de referencia del BCE (`eurofxref-hist.zip`, sha256 `9465dd5c…45f3`, descargado el
    2026-10-03 13:57:42Z) para USD, JPY y HKD;
  - 1.282 tipos por par, del 2021-08-27 al 2026-08-28;
  - `timestamp_available = 17:00 Europe/Berlin` del día de referencia;
  - `fx_rate_to_EUR = 1 / rate`.
- Contrato del sidecar: `fx/fx-sidecar.csv` (`fx_pair, bar_timestamp, timestamp_available, rate,
  series_hash, provider, provider_version, downloaded_at`), sha256 `222e94e7…fddf`.

| Par | `series_hash` (BCE) |
|---|---|
| EURUSD | `b59ebb02bf400a9dd5966f8b5ec4acda0b1983839b6e0cfd46f320af8a037b7c` |
| EURJPY | `e5a6c648c4c68c85109b7b2d7b6b6676e12a87ddcc3cde2fed9886aa2da60950` |
| EURHKD | `d86adb766c476d2c8eedc50d9a6fb7ecd51a54264874a1d2427a961886f21cc7` |

`fx_vintage_id = 10e832ef38daa5d7e81a444bcd3bc99a5e783a382a14a4a14c68e6736dfeac0b`.

Las descargas de Yahoo se conservan solo como evidencia del intento A fallido; **no se usan**.

## Sector (D-69, OD-P6-18/19; T-022 §12)

- `congelar_sector.py` → `p6-sector-map.yaml`, `p6-sector-map.json` y `p6-sector-map-resumen.json`.
- Acciones (74): sector del perfil del emisor en Yahoo Finance (`yfinance` `Ticker.info['sector']`),
  como foto con `observed_at` del 2026-10-03; **no es point-in-time**.
- ETF (16): categoría estructural por tipo, sin look-through: 15 `EQUITY_ETF` y 1 `BOND_ETF`.
- **Cobertura 90/90, 0 `UNKNOWN`.** Por categoría: Technology 29, EQUITY_ETF 15, Industrials 11,
  Financial Services 9, Consumer Cyclical 8, Communication Services 6, Energy 5, Healthcare 4,
  BOND_ETF 1, Consumer Defensive 1, Utilities 1.
- Hashes: YAML `220b21ed2ce74c60c0c1988e36e3eaf12f5c7357ae53e620005762e379f0e93c`; canónico
  `24f45421a582cc79ee16f8436e3e008d252ccafc06f34503961d5dfccea662cd`.
- El sector es **solo descriptivo**: nunca decide una entrada, un veto ni la supervivencia.

## `P6_DATA_ID` (T-022 §18)

**`P6_DATA_ID = 8759d6c876ce513d6a0d63d4ddb3d43508349ec60f56408b913cb6993756acd3`**
(`calcular_p6_data_id.py` → `p6-data-id.json`). Es el sha256 del JSON canónico de:
- la cosecha `071ddb2b…` y el universo `237b0056…`;
- la lista de activos `36355796…`;
- el FX (fuente B, `fx_vintage_id` y sha256 del sidecar);
- el mapa sectorial (canónico y YAML);
- el calendario: `exchange_calendars` 4.13.2, `exchange_overrides.yaml` `87e4aa21…`, `tzdata` 2026.4 y
  `zoneinfo.TZPATH`.

`SHA256SUMS.txt` cubre todos los ficheros de este directorio. Los scripts se niegan a ejecutarse de
nuevo si su salida ya existe: no se vuelve a descargar nada.
