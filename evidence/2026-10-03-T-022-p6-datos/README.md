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

**`P6_DATA_ID = 572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383`**
(`calcular_p6_data_id.py` → `p6-data-id.json`). Es el sha256 del JSON canónico
(`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`) del **payload literal de T-022 §18**:

```json
{"asset_list":"36355796a57e55a68ea16957b7edc6975360fb2085e7fd91841d20e2d7812f50","calendar":{"exchange_calendars":"4.13.2","exchange_overrides_sha256":"87e4aa21def5eaf057745cf4b98711c4df694dae2f6cfbf27245823d946539db","tzdata":"2026.4"},"fx_vintage":"10e832ef38daa5d7e81a444bcd3bc99a5e783a382a14a4a14c68e6736dfeac0b","market_data_vintage":"071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841","sector_map":"24f45421a582cc79ee16f8436e3e008d252ccafc06f34503961d5dfccea662cd","universe_vintage":"237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"}
```

La fuente FX usada (B), el sha256 del sidecar y del YAML sectorial y `zoneinfo.TZPATH` se publican
como **metadatos fuera del hash** (`metadatos_fuera_del_hash`). **Corrección:** la primera versión de
este ID (`8759d6c8…acd3`) añadía campos que T-022 no congeló y cambiaba la estructura; queda
sustituida sin regenerar ni descargar ningún dato (FX y sector intactos).

`SHA256SUMS.txt` cubre todos los ficheros de este directorio. Los scripts se niegan a ejecutarse de
nuevo si su salida ya existe: no se vuelve a descargar nada.
