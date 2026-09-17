# T-005 — correcciones de la segunda revisión independiente

- Fecha: 2026-09-17 · Rama `refactor/data-quality-codes` · base `main` `c255e0c`
- Revisión: subagente `revisor` con `PROMPT_REVIEW`, veredicto **CORREGIR** con
  4 hallazgos de alcance y 4 observaciones
- Correcciones y verificación: Claude Code
- Suite final: **494 tests**, `ruff` y `mypy` limpios (60 ficheros)

Sustituye a la tabla de impacto de `evidence/2026-09-16-T-005-calidad/`, que
quedó obsoleta con `98039b4`: aquel `despues.txt` es de las 13:21 y el fix de
las 13:45, así que publicaba un reparto —`LOW_SCORE` 51 · `MISSING_RECENT_DATA`
22 · `STALE_DATA` 13 · `PARTIAL_BAR` 3— que el código ya no puede producir.

## Las tres ejecuciones, todas del 2026-09-17

Se declaran por separado porque el mercado se mueve entre pasadas y ya se vio
un activo cambiar de bloque en cuatro minutos (`SOL-EUR`, cripto con barra
parcial en curso).

| Fichero | Código | Comando | Run |
|---|---|---|---|
| `antes.txt` | `main` `c255e0c`, en un worktree | `analizar --horizonte swing --sin-ia --sin-guardar` | `f377f11b` 09:04–09:06 |
| `despues.txt` | `1de524b` + las correcciones | el mismo | `2b69ede7` 09:06–09:08 |
| `codigos-por-activo.csv` | `1de524b` + las correcciones | volcado por `run_analysis`, mismos parámetros | 09:08–09:10 |

El volcado existe porque el informe agrupa el bloque DESCARTADOS por un solo
código y la tabla cruzada no se puede leer de ahí. No reimplementa nada: llama
a `run_analysis` igual que `cmd_analizar`.

## Impacto: ninguna decisión cambia, cambia la atribución

| | Antes (`main`) | Después |
|---|---|---|
| OPERAR | 1: `AMD` | 1: `AMD` |
| RADAR (impresos) | 10 | 10 |
| DESCARTADOS | 91, motivo en texto libre con la calidad pegada | 91, todos `LOW_SCORE` |
| Avisos de precio extendido visibles | 0 | 1 |

**Activos que cambian de bloque: 0.** Comparados los tres conjuntos uno a uno:
ni OPERAR, ni RADAR, ni DESCARTADOS tienen un solo símbolo de diferencia. Era
lo esperado: estas correcciones tocan atribución, visibilidad y persistencia,
no la decisión.

## Los dos ejes, que es lo que la revisión anterior exigía separar

Sobre las 107 filas del volcado:

| `discard_code` | Activos |
|---|---|
| `LOW_SCORE` | 106 |
| ninguno (el único OPERAR) | 1 |

| `execution_code` | Activos |
|---|---|
| `BROKER_UNVERIFIED` | 57 |
| `MISSING_RECENT_DATA` | 28 |
| `STALE_DATA` | 19 |
| `PARTIAL_BAR` | 3 |

| Calidad | Activos |
|---|---|
| `OK` | 60 |
| `INCOMPLETO` | 28 |
| `DEGRADADO` | 19 |

Cruzados, los 107 quedan sin solapamiento ni huecos: `LOW_SCORE` ×
`BROKER_UNVERIFIED` 56, × `MISSING_RECENT_DATA` 28, × `STALE_DATA` 19, ×
`PARTIAL_BAR` 3, más el `OPERAR` sin `discard_code`. Se cumple «cero descartes
sin código» con la atribución correcta.

`BROKER_UNVERIFIED` es mayoritario porque los 107 siguen en
`trade_republic: unknown` (OA-03): no veta, declara que la disponibilidad no
está confirmada. Ver D-04.

## Lo que la pasada real NO ejercita, y conviene decirlo

El aviso de precio extendido aparece **una vez**, en la ficha de `AMD`, que es
`OPERAR`. **Ningún activo del bloque RADAR genera advertencia hoy**, porque los
15 en vigilancia caen por `LOW_SCORE` antes de llegar a la comprobación de
extensión. Es decir: la corrección que imprime advertencias en RADAR no está
ejercitada por esta pasada, y quien la protege es
`test_aviso_de_precio_extendido_llega_al_informe_tambien_en_radar`, que va por
`format_report` y falla si se quita el bucle. Se anota en vez de dejar creer
que la salida real lo cubre.

## Las cuatro correcciones, con su comprobación

1. **Segundo camino de `DataQuality` en `medir_frescura_datos`.** Ya no
   publica calidad de ejecución, y usa las ventanas de configuración en vez de
   los valores por defecto 10/10. Dos tests nuevos en `tests/test_freshness.py`,
   ambos comprobados reintroduciendo el defecto. La decisión de fondo —si
   `frescura-datos` debe recortar la barra no cerrada— queda como **D-22
   (propuesta)** porque cambiaría la serie de retrasos sobre la que se
   sostienen D-21 y OD-10.
2. **Aviso de precio extendido.** Se imprime en RADAR y se persiste en una
   columna `warnings` propia, añadida a la migración v4. Verificado que la v4
   todavía no está aplicada en ninguna base: `intradia.db` local está en v3 y
   los tres backups en v0, v1 y v2, así que no hace falta una v5.
3. **`_skip_code`.** Devuelve `ANALYSIS_ERROR` para el fallo no reconocido
   (INV-16). De paso se retiró la rama `INVALID_INDICATORS` de esa función:
   ninguna excepción del proyecto menciona indicadores, así que estaba muerta.
4. **Tests que faltaban.** Añadido el de severidad `CRITICAL`, comprobando
   antes contra el calendario que es alcanzable —entre el viernes 2026-09-11 y
   el lunes 2026-09-14 XETRA no cierra ninguna sesión intermedia, luego
   `sessions_ago = 0`—, y uno del bloque DESCARTADOS que llega al código por
   `build_opportunity`: el que existía pasaba en verde con el defecto
   reintroducido y el nuevo falla.
