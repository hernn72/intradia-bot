# Evidencia T-007 estado de mercado y broker

- Commit de trabajo: `3e677c3`.
- Instante baseline: `2026-09-18T07:35:23Z`.
- Instante posterior: `2026-09-18T07:51:05Z`.
- Entorno: `.venv`, Python invocado con `source .venv/bin/activate`.

## Comandos

Baseline, guardado en `antes.txt`:

```bash
python -m pytest -q
ruff check .
mypy advisor
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main frescura-datos --grupos europa
```

Verificacion posterior, guardada en `despues.txt`:

```bash
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main frescura-datos --grupos europa
```

Backtest de control, guardado en `backtest.txt`:

```bash
.venv/bin/python -m advisor.main backtest --horizonte swing --period 5y
```

## Resultado

- Baseline: 502 tests pasaban antes de tocar codigo; `ruff` y `mypy` limpios.
- Posterior: 513 tests pasan; `ruff check .` y `mypy advisor` limpios.
- La ficha impresa de `AMD` cambia de `Precio actual` a `Ultimo cierre` porque NASDAQ estaba `PRE_OPEN`.
- `9984.T` pasa de radar con `BROKER_UNAVAILABLE` a descartado por `BROKER_UNAVAILABLE`.
- No hubo `VERIFICAR_BROKER` en la salida real porque los 2 activos `unknown` del universo actual no alcanzaron setup operativo.
- `backtest.txt` confirma que el backtest sigue funcionando; no usa el formatter del informe.

## Comprobacion manual

`AMD` en `antes.txt`: `Precio actual: 545,09 USD`.

`AMD` en `despues.txt`: `Ultimo cierre: 545,09 USD · Sesion: 2026-09-17 · Mercado: PRE_OPEN`.

El numero nativo no cambia: `545,09 - 545,09 = 0,00 USD`. Solo cambia la etiqueta y se anaden sesion y estado de mercado. El equivalente EUR varia por el tipo de cambio descargado en cada pasada.

Reevaluacion numerica cubierta por test:

```text
entry_max = 56,11; stop = 54,71; target2 = 58,20
market_price = 55,95
RR = (58,20 - 55,95) / (55,95 - 54,71) = 2,25 / 1,24 = 1,814516129 >= 1,5
```

## Cierres anticipados

Contados con `exchange_calendars==4.13.2` entre `2025-11-01` y `2026-12-31`:

| Plaza | Cierre regular | Sesiones con cierre anticipado |
|---|---:|---|
| XETRA | 17:30 | 2: 2025-12-30 14:00; 2026-12-30 14:00 |
| NYSE | 16:00 | 4: 2025-11-28 13:00; 2025-12-24 13:00; 2026-11-27 13:00; 2026-12-24 13:00 |
| PAR | 17:30 | 4: 2025-12-24 14:05; 2025-12-31 14:05; 2026-12-24 14:05; 2026-12-31 14:05 |
