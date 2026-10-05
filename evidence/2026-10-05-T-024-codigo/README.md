# T-024 — Código de captura ciega, reconfirmación, métricas y miradas (sin datos forward)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Identidad

| | |
|---|---|
| Base (`main`) | `b5b98526362db1bb39cc693e8e4a799f9df3449d` (merge del PR #44) |
| `T024_PREREG_SHA` | `dfcca0ef3428df916089480a0ca574f47e550c24` (vinculante, con D-71 y D-72) |
| **`T024_CODE_SHA`** | **`ddcdb8de7e8781f87fa860db4c0ef0b0675f8356`**: el último commit que toca el ejecutor y la captura. Está fijado en el sidecar `evidence/2026-10-05-T-024-code-lock/T024_CODE_SHA.txt`, fuera de los `EXECUTOR_PATHS` |

Commits de código, todos nuevos y sin amend: `3da05e7` → `e19e398` → `12420f8` → `65eb32f` → `70ffdf7` → `789e4c1` →
`ddcdb8d`. `70ffdf7` dejó de ser candidato: con `T024_CODE_SHA` como constante dentro de `advisor/`, fijarlo
cambiaba el ejecutor tras ese SHA (BLOCKER detectado por el propietario). `789e4c1` lo sustituye por el
sidecar versionado y `ddcdb8d` ancla la identidad al repositorio del código importado.

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
- `tests/test_t024.py`: 88 tests (`tests-t024.md`), incluidos los del lock real en un repositorio git temporal, sin monkeypatch del SHA:
  - el lock correcto pasa;
  - deniega con ejecutor cambiado, con el SHA dentro de `advisor/` (la circularidad), y con el sidecar ausente, sin commitear, modificado, inválido o no ancestro.

  En CI, sin los CSV de `data/vintages` (están en `.gitignore`), los dos de desarrollo se omiten, como en `tests/test_p6.py`.

No modifica P6, B2, S2, C0, el score, `config.yaml`, `universe.yaml`, producción ni la Pi.

## Verificación

`verificacion.txt`:
- 88 tests de T-024 en verde, dos veces y con el mismo resultado;
- suite completa: 1191 passed;
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
| 8 | Focalizada en el arreglo | `70ffdf7` | 0 · 0 · 0 | — |
| 9 | Identidad | `789e4c1` | 0 · **1 IMPORTANTE** | La ruta pública valida `REPO_ROOT`, sin `repo` |
| 10 | API y guardas | `789e4c1` | **1 BLOCKER** · 1 IMPORTANTE | El mismo `repo`; el otro hallazgo era el sidecar aún inexistente, por diseño |
| 11 | **Identidad (final)** | `ddcdb8d` | **0 BLOCKER · 0 IMPORTANTE** | — |
| 12 | **API y guardas (final)** | `ddcdb8d` | **0 BLOCKER · 0 IMPORTANTE · 0 MENOR** | — |

La revisión de look-ahead final sigue siendo la 7. Según la 12, el diff `70ffdf7..ddcdb8d` solo toca
identidad, no las rutas de captura ni de decisión. Las revisiones de las 20:41 fallaron por límite de uso de
Codex, sin veredicto, y se relanzaron sin cambios (`revisiones/00-nota-limite-de-uso.md`).

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

- Revisión y fusión del PR #45.
- Con autorización aparte: el registro forward y el primer checkpoint mensual (solo conteos).
