# T-003 — correcciones tras la revisión independiente

- Fecha: 2026-09-16
- Rama: `fix/exchange-calendars`
- Entrega revisada: `5fb3394` (base `1c76add`)
- Revisor: subagente `revisor` con `PROMPT_REVIEW`, veredicto **CORREGIR**
- Python local: 3.12.13 (`.venv`), `exchange_calendars==4.13.2`

La revisión encontró un BLOCKER y tres defectos de alcance. Los cuatro están
corregidos; cada uno con su test de regresión, comprobado además contra el
código sin corregir para asegurar que el test falla de verdad.

## 1. BLOCKER — `frescura-datos` rompía el comando entero

`python -m advisor.main frescura-datos` sin `--grupos` mide los 126 activos del
universo, no los 107 analizables. Once activos de contexto tienen plazas sin
calendario declarado (`CBOE`, `SNP`, `WCB`, `ZRH`×2, `OSA`, `CCY`, `NYB`,
`CGI`, `NYM`, `CMX`). Desde T-003 la frescura pide el MIC de la plaza, así que
el primero de ellos lanzaba `ValueError` y, al estar la llamada **fuera** del
`try`, tumbaba la medición completa con código 1 y cero filas.

No se detectó porque la evidencia del 14 solo contiene la salida de `analizar`,
que recorre los 107 analizables; la ficha sí pedía ejecutar los dos comandos.

Corregido en `advisor/main.py`: la resolución de plaza y el cálculo de frescura
entran en el `try`, de modo que una plaza sin calendario degrada **su fila**
—declarada por su nombre— y nunca la medición. Se rechaza la alternativa de
declarar MIC para índices, divisas y futuros: es alcance nuevo y un calendario
mal asignado reintroduciría huecos falsos, justo lo que T-003 elimina.

Verificado contra datos reales hoy: `frescura-datos` termina con `exit=0`, 126
filas, y las once plazas sin calendario aparecen una a una bajo «Símbolos sin
datos». Salida completa en `frescura-datos.txt`.

## 2. El requisito 5 de la ficha no llegaba a producción

`_may_be_partial_current_session` implementa bien el cierre lógico de cripto
(UTC 00:00 + `settlement_minutes`), pero `advisor/analysis/analyzer.py` lo
pisaba a `False` cuando `trim.status == "sin sesión de cierre"`, que ocurre
exactamente —y solo— en `CRYPTO`, la única plaza sin `close_time`. Resultado:
el informe **nunca** declaraba la barra parcial de cripto, mientras
`frescura-datos` sí la declaraba. La línea venía de `465b4c8`, anterior a
T-003, pero anula un requisito que esta ficha sí exige.

Corregido: la condición conserva los dos casos legítimos (`removed_last_bar` y
«última barra cerrada») y deja decidir a la frescura en cripto.

No cambia ninguna clasificación: `classify_data_quality` no lee ese campo, de
modo que calidad, veto, nota y señal quedan intactos (INV-03). Verificado en la
pasada real de hoy: el informe declara «⚠️ Barra potencialmente parcial», y
`BTC-EUR`/`ETH-EUR`/`SOL-EUR` conservan la calidad que tenían.

## 3. El manifiesto no registraba la versión de `exchange_calendars`

Desde T-003, los festivos de esa librería deciden calidad, veto y etiquetas de
los 107 activos. Una versión distinta cambia el resultado de una pasada
guardada sin que `analysis_run` lo refleje (INV-18). Añadida a
`provider_versions` en `advisor/run/manifest.py`.

## 4. Valor por defecto silencioso de plaza

`calcular_frescura_dato(..., market="XETRA")` daba calendario alemán a
cualquier llamante que omitiera la plaza. El criterio de rechazo de la ficha
prohíbe el fallback silencioso, y el resto del módulo ya falla ruidosamente.
`market` pasa a ser obligatorio; los cuatro tests que lo omitían declaran
`"XETRA"` de forma explícita.

## Evidencia de la instalación en Python 3.13

El criterio de aceptación pedía instalación verificada en 3.13 y el fichero que
la acompañaba (`pip-install-exchange-calendars.txt`, renombrado ahora a
`pip-install-fallido-por-dns.txt`) era el log del intento **fallido**.
Verificado hoy en la Pi por SSH, sobre su propio intérprete: Python 3.13.5
aarch64, `exchange_calendars` 4.13.2, las 14 plazas cargan y devuelven sesiones.
Salida en `pi-python313-exchange-calendars.txt`.

## Comprobaciones

| Comprobación | Resultado |
|---|---|
| `python -m pytest -q` | 435 pasan (431 antes + 4 de regresión) |
| `ruff check .` | limpio |
| `mypy advisor` | limpio, 58 ficheros |
| `python -m advisor.main frescura-datos` | `exit=0`, 126 filas, 11 declaradas sin calendario |
| `python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar` | `exit=0`, 107 activos, barra parcial de cripto declarada |
| Tests nuevos contra el código sin corregir | los 3 fallan (`ValueError: plaza 'CBOE' sin calendario declarado` y `assert False is True`) |

## Activos que cambian de radar o de acción entre la línea base y T-003: 0

Recalculado aquí, no heredado: OPERAR idéntico, RADAR idéntico (10 símbolos con
las mismas notas) y los 90 descartados son **el mismo conjunto** de símbolos.
Lo único que cambia es el motivo: `AZN` y `TSM` dejan de llevar «calidad
INCOMPLETO». Es lo esperado de una entrega que no toca el score.

## Hallazgo abierto que hereda T-004 — las dos ausencias coreanas

`005930.KS` y `000660.KS` son los dos únicos valores coreanos del universo y a
**ambos** les faltan exactamente `2026-06-03` y `2026-07-17`. Que coincidan
apunta a cierre de plaza, no a un fallo de descarga por ticker.

Medido sobre `exchange_calendars==4.13.2`: todos los días electorales coreanos
pasados son no-sesión (2020-04-15, 2022-03-09, 2022-06-01, 2024-04-10,
2025-06-03), pero **2026-06-03 figura como sesión**, y el 3 de junio de 2026 es
la fecha de las elecciones locales. Los calendarios públicos de KRX para 2026
listan exactamente los mismos 15 cierres que la librería y ninguno incluye
días electorales: Corea los declara como festivo temporal, no programado.

`2026-07-17` no tiene explicación candidata todavía.

**No está probado**, y por eso no se cierra aquí: si son festivos de su propia
plaza, dos activos quedan `DEGRADADO` por un hueco que no existe, que es
justo lo que el criterio de aceptación de T-003 y la métrica de GATE L0
prohíben. T-004 debe resolverlo contra fuente oficial antes de dar por buena
su población.
