# Sondeo del plan gratuito de EODHD — OD-01 / D-39

Salida literal de `sondeo_eodhd.py`. Se comprueba contra el JSON crudo.

## Qué responde cada petición

### fundamentales de SAP.XETRA con la clave del propietario

`https://eodhd.com/api/fundamentals/SAP.XETRA?api_token=6ab0…30&fmt=json`

- **sin datos** — HTTP 403 — prohibido: el plan no incluye este producto, o el token no cubre ese símbolo: Only EOD data allowed for free users. Please, contact our support team: support@eodhistoricaldata.com

### fundamentales de ASML.AS con la clave del propietario

`https://eodhd.com/api/fundamentals/ASML.AS?api_token=6ab0…30&fmt=json`

- **sin datos** — HTTP 403 — prohibido: el plan no incluye este producto, o el token no cubre ese símbolo: Only EOD data allowed for free users. Please, contact our support team: support@eodhistoricaldata.com

### fundamentales de AAPL.US con la clave del propietario (¿es la plaza o el plan?)

`https://eodhd.com/api/fundamentals/AAPL.US?api_token=6ab0…30&fmt=json`

- **sin datos** — HTTP 403 — prohibido: el plan no incluye este producto, o el token no cubre ese símbolo: Only EOD data allowed for free users. Please, contact our support team: support@eodhistoricaldata.com

### EOD de SAP.XETRA con la clave del propietario (¿la clave vale?)

`https://eodhd.com/api/eod/SAP.XETRA?api_token=6ab0…30&fmt=json&from=2026-09-14`

- **respuesta OK**, 656 bytes de JSON.

### fundamentales de AAPL.US con el token público `demo`

`https://eodhd.com/api/fundamentals/AAPL.US?api_token=demo&fmt=json`

- **respuesta OK**, 1005 KB de JSON.

### fundamentales de SAP.XETRA con el token público `demo`

`https://eodhd.com/api/fundamentals/SAP.XETRA?api_token=demo&fmt=json`

- **sin datos** — HTTP 403 — prohibido: el plan no incluye este producto, o el token no cubre ese símbolo: Forbidden. Please contact support@eodhistoricaldata.com

## Inventario de campos sobre ese JSON

Fuente: `AAPL.US` con el token `demo`. Extracto publicable en `extracto-AAPL-US.json`;
el JSON completo (1005 KB) se regenera ejecutando este script.

- **filing_date**: PRESENTE, 594 apariciones — `Financials.Balance_Sheet.quarterly.2026-06-30.filing_date` (+592 más) · fecha de publicación por línea — sin esto no hay point-in-time
- **ISIN**: PRESENTE, 1 apariciones — `General.ISIN` · identidad del instrumento, para cruzar con universe.yaml
- **Balance_Sheet**: PRESENTE, 1 apariciones — `Financials.Balance_Sheet` · estados financieros: balance
- **Income_Statement**: PRESENTE, 1 apariciones — `Financials.Income_Statement` · estados financieros: cuenta de resultados
- **Cash_Flow**: PRESENTE, 1 apariciones — `Financials.Cash_Flow` · estados financieros: flujo de caja
- **EarningsShare**: PRESENTE, 1 apariciones — `Highlights.EarningsShare` · EPS (instantánea, sin fecha de publicación)
- **epsActual**: PRESENTE, 165 apariciones — `Earnings.History.2026-09-30.epsActual` (+163 más) · EPS publicado, con `reportDate` al lado
- **netDebt**: PRESENTE, 205 apariciones — `Financials.Balance_Sheet.quarterly.2026-06-30.netDebt` (+203 más) · deuda neta
- **longTermDebt**: PRESENTE, 205 apariciones — `Financials.Balance_Sheet.quarterly.2026-06-30.longTermDebt` (+203 más) · deuda a largo plazo
- **shortTermDebt**: PRESENTE, 205 apariciones — `Financials.Balance_Sheet.quarterly.2026-06-30.shortTermDebt` (+203 más) · deuda a corto plazo
- **freeCashFlow**: PRESENTE, 184 apariciones — `Financials.Cash_Flow.quarterly.2026-06-30.freeCashFlow` (+182 más) · flujo de caja libre
- **totalDebt**: AUSENTE · deuda total en una sola línea (se espera ausente: se deriva)

