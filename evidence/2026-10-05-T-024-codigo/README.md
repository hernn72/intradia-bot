# T-024 — Código de captura ciega, reconfirmación, métricas y miradas (sin datos forward)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Identidad

| | |
|---|---|
| Base (`main`) | `b5b98526362db1bb39cc693e8e4a799f9df3449d` (merge del PR #44) |
| `T024_PREREG_SHA` | `dfcca0ef3428df916089480a0ca574f47e550c24` (vinculante, con D-71 y D-72) |
| **Candidato a `T024_CODE_SHA`** | **`70ffdf7557981b846c6ed9e6cd5c3390933e321e`**: el último commit que toca el ejecutor y la captura. **No está fijado**: `T024_CODE_SHA = None` en el código, de modo que la decisión se niega |

Commits de código, todos nuevos y sin amend: `3da05e7` → `e19e398` → `12420f8` → `65eb32f` → `70ffdf7`.

## Qué contiene

- `advisor/research/t024_comun.py`: identidad, constantes de D-72, tipos y fechas locales idénticas a
  P6.
- `advisor/research/t024_captura.py`: camino ciego. Genera señales OPERAR replicando P6 sin su token;
  la apertura de `e_i` solo pasa por `VistaCiega`; calcula ejecutabilidad, `Q_p`, `W_p`, calidad y
  reconfirmación; tiene un modo de desarrollo rotulado.
- `advisor/research/t024_decision.py`:
  - ventanas con el contrato de salidas y ejecutabilidad de P6 y no solapamiento por activo;
  - D1 (comprobación), D2 (primaria), D2o, D2c, D3, D4, la convención (b), el coste prorrateado y EUR;
  - φ por política y activo, y las exclusiones de §5.3;
  - el bootstrap de 10 semanas y el criterio;
  - registro forward, calendario de miradas, marca exclusiva y `TokenMirada`.
- `tests/test_t024.py`: 70 tests (`tests-t024.md`).

No modifica P6, B2, S2, C0, el score, `config.yaml`, `universe.yaml`, producción ni la Pi.

## Verificación

`verificacion.txt`:
- 70 tests de T-024 en verde, dos veces y con el mismo resultado;
- suite completa: 1173 passed;
- `ruff check .` y `mypy advisor` limpios;
- el diff frente a `main` son solo los cuatro ficheros;
- el `run/` de P6 sigue intacto (30/30);
- en `data/vintages` solo está la cosecha consumida.

## Revisiones independientes (Codex, solo lectura)

| # | Tipo | Commit | Resultado | Corrección |
|---|---|---|---|---|
| 1 | Look-ahead | `3da05e7` | 0 BLOCKER · **1 IMPORTANTE** | Las ventanas aplican la ejecutabilidad de P6 |
| 2 | API y guardas | `3da05e7` | **1 BLOCKER** · 2 MENOR | `TokenMirada` en `construir_resultado` y `barras_decision`; test AST; tests de identidad |
| 3 | Look-ahead | `e19e398` | 0 · 0 · 1 MENOR | D3 con todos los analizables |
| 4 | API y guardas | `e19e398` | **1 BLOCKER** · **1 IMPORTANTE** | Cosecha atada por `data_vintage_id`; capacidad por política en la final |
| 5 | API y guardas | `12420f8` | **1 BLOCKER** | Las funciones de desenlace exigen el token con barras de cosecha (`origen`) |
| 6 | **API y guardas (final)** | `65eb32f` | **0 BLOCKER · 0 IMPORTANTE** | — |
| 7 | **Look-ahead (final)** | `65eb32f` | **0 BLOCKER · 0 IMPORTANTE** · 1 MENOR | `truncada_t1` solo para la regla final |
| 8 | **Focalizada en el arreglo** | `70ffdf7` | **0 · 0 · 0** | — |

Informes literales en `revisiones/`. Modelo de amenaza y guardas en `guardas-modelo-amenaza.md`.

Además de lo que encontraron las revisiones, la revisión propia de Claude de las rondas de Codex corrigió:
- la guarda ciega, que no era física;
- φ y D2o por ventana;
- el truncado en `T1`;
- D3 alineado por posición;
- miradas sin limitar y una puerta trasera `verificar=False`;
- dos tests omitidos incondicionalmente;
- el modo de desarrollo sin efecto;
- `c_e` y la cosecha decisiva sin atar al calendario;
- la lectura de la marca histórica de P6 en un test.

## Datos

No se descargó nada ni se leyó ningún dato posterior al 2026-08-27. No se leyó
`data/frescura-snapshot.db`. Sobre la cosecha consumida `071ddb2b…` solo se generaron **señales y
conteos de desarrollo**: el smoke de `capturar` y la equivalencia de señales con P6, sin salidas ni
métricas. No se calculó ninguna D2 real. No se ha congelado ninguna cosecha forward ni se ha consumido
ninguna mirada.

## Siguiente (solo con el propietario)

1. Fijar `T024_CODE_SHA` (candidato `70ffdf7`) en un commit aparte, que no toque el ejecutor.
2. Con autorización aparte: el registro forward y el primer checkpoint mensual (solo conteos).
