# Sondeo del plan gratuito de EODHD — OD-01 (D-39)

Ejecutado el **2026-09-20** con la clave gratuita del propietario. Salida literal
en `resultado.md`; el recorte publicable del JSON, en `extracto-AAPL-US.json`.

## Las dos respuestas, que no son la misma

**1. El plan gratuito NO sirve para fundamentales.** Ni europeos ni de EE. UU.:

    fundamentals SAP.XETRA   →  HTTP 403  "Only EOD data allowed for free users"
    fundamentals ASML.AS     →  HTTP 403  "Only EOD data allowed for free users"
    fundamentals AAPL.US     →  HTTP 403  "Only EOD data allowed for free users"
    eod SAP.XETRA            →  HTTP 200, 656 bytes

La cuarta línea es la que da sentido a las tres primeras: **la clave es válida y
el acceso funciona**; lo que no incluye el plan es el producto de fundamentales,
y no tiene nada que ver con la plaza. Es exactamente la distinción que D-39
exigía separar: **«este plan no lo da», no «el proveedor no lo da»**.

**2. La forma del JSON sí se pudo ver, con el token público `demo`.** EODHD
publica un token de demostración que sirve fundamentales de `AAPL.US` —y solo de
unos pocos símbolos: con `SAP.XETRA` devuelve 403—. Sobre ese JSON real, 1.005 KB:

| Campo | Resultado |
|---|---|
| **`filing_date`** | **PRESENTE, 594 apariciones**, una por línea de cada estado financiero: `Financials.Balance_Sheet.quarterly.2026-06-30.filing_date` = `2026-07-31` para un periodo cerrado el `2026-06-30` |
| `ISIN` | presente en `General.ISIN` (`US0378331005`) |
| Balance, resultados y flujo de caja | los tres, en `Financials`, con 164 periodos trimestrales y 41 anuales (hasta 1985) |
| EPS | dos formas: `Highlights.EarningsShare` (instantánea, **sin** fecha) y `Earnings.History.<periodo>.epsActual` con `reportDate` al lado, que sí es utilizable point-in-time |
| Deuda | **no hay `totalDebt`**; hay `netDebt`, `shortTermDebt`, `shortLongTermDebt`, `shortLongTermDebtTotal` y `longTermDebt`. Se deriva en Python, que es lo que el roadmap ya exige para los ratios |
| Flujo de caja libre | `Cash_Flow.<periodicidad>.<periodo>.freeCashFlow`, con su `filing_date` |

## Qué decide esto para OD-01

**El esquema de EODHD sí es point-in-time.** `filing_date` viene por línea y
separado del cierre del periodo, que es justo lo que hace falta para que los
fundamentales puedan entrar en un backtest sin look-ahead. Eso mueve a EODHD a
la alternativa **(a)** de OD-01 en cuanto a forma del dato, y quita de en medio
la objeción que tenía a `yfinance`.

**Lo que este sondeo NO demuestra, y no se debe dar por supuesto:**

- **Cobertura europea.** Todo lo verificado es `AAPL.US`. Que el esquema traiga
  `filing_date` para una empresa de EE. UU. **no prueba** que lo traiga relleno
  para `SAP.XETRA`, `ASML.AS` o el resto del universo. Es la pregunta que queda
  abierta y la única que justifica pagar un mes para comprobarla.
- **Calidad del relleno.** Hay campos a `null` incluso en el ejemplo de demo
  (`longTermDebtTotal`, `earningAssets`). Cuántos van vacíos en un europeo es
  parte de la misma comprobación.
- **Revisiones.** No se ha visto si una magnitud republicada conserva la fecha
  original o se sobrescribe, que es lo que distingue un point-in-time de verdad
  de una foto fechada.

## Lo que hace falta para cerrar OD-01

Un mes del plan de pago más barato que incluya fundamentales, con dos o tres
europeos del universo, comprobando: `filing_date` relleno en los tres estados,
porcentaje de campos nulos, y qué pasa con una magnitud revisada. Decisión del
propietario: es gasto.

## Cómo se reproduce

    .venv/bin/python evidence/2026-09-20-OD-01-eodhd-free/sondeo_eodhd.py

Los pasos con el token `demo` corren sin clave ninguna. Los tres primeros
necesitan `EODHD_API_KEY` en `.env`, que **no** está en el repositorio; el
sondeo registra las URL con la clave recortada y nunca la escribe en la
evidencia. El JSON completo no se commitea —pasa del megabyte— y se regenera
ejecutando el script.

## Lo que este sondeo no toca

No entra en `advisor/`. B-00 (GATE B0) exige la ficha de proveedor antes de que
ninguna fuente externa forme parte del sistema, y esto es el material con el que
se escribe esa ficha.
