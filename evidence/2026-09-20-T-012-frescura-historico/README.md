# T-012 — el histórico de frescura de la Pi, interpretado

- Commit base: `e19daa5`. Instante de cierre: `2026-09-20T17:05Z`.
- Base leída: `data/frescura-snapshot.db`, 3.321.856 bytes, SHA-256
  `9cc5309e255279038a8dd178d96b9a431368ffa2a4743cf8d8f42a03b191fca7`, copiada de
  la Pi con el API de backup de SQLite el `2026-09-20T16:36:39Z`. **No se escribió
  nada en la base de producción.**
- Comando: `.venv/bin/python -m advisor.main frescura-historico --resumen --db data/frescura-snapshot.db`
- Histórico: **4.143 mediciones, 39 pasadas, 107 símbolos**, del
  `2026-09-02T17:24:51Z` al `2026-09-20T16:11:02Z`.

## La cifra que contesta a OD-02: el retraso es europeo y solo europeo

En las cuatro pasadas programadas, mediciones con retraso ≥ 1 sesión:

| Hora UTC | Europa | resto del mundo |
|---|---|---|
| 06 | **278/329 = 84,5 %** | **0/399 = 0,0 %** |
| 07 | **277/328 = 84,5 %** | **0/399 = 0,0 %** |
| 13 | **135/327 = 41,3 %** | **0/397 = 0,0 %** |
| 20 | **0/327 = 0,0 %** | **0/397 = 0,0 %** |

«Resto del mundo» son NASDAQ, NYSE, JPX, HKG y KSC. **Ni una sola medición
retrasada fuera de Europa en las 39 pasadas.**

**Cómo NO leer estos porcentajes** (D-41): las mediciones de una misma pasada no
son independientes. Cada una de esas franjas sale de **7 pasadas**, y un fallo
del proveedor afecta a la vez a decenas de símbolos, así que 329 filas son ~7
eventos matinales, no 329 experimentos. Los intervalos binomiales que publica la
tabla son por eso demasiado estrechos, y van marcados como tales. La dirección
del hallazgo aguanta —el patrón se repite en cuatro días distintos—; la precisión
no. Confirma la medición de 21
pasadas del 2026-09-16 con una muestra quince veces mayor, y la afina: la de las
20:02 UTC no tiene retraso ninguno.

## Y la que la complica: «sesión perdida» admite tres definiciones

El pre-registro fijó el umbral de OD-02 —más de 2 sesiones perdidas por mes en
más de 10 activos— pero **no definió qué es una sesión perdida**. Las tres
lecturas posibles dan respuestas opuestas:

| Lectura | Activos por encima del umbral | ¿Se alcanza el umbral de 10? |
|---|---:|---|
| **(a)** el hueco **sigue ausente** en la última pasada que vio al activo | **0** (9 tienen algún hueco, ninguno más de dos) | **NO** |
| **(b)** la sesión faltó del histórico en alguna pasada, aunque llegara después | 18 | sí |
| **(c)** lo anterior más las sesiones que solo llegaban con retraso | 47 | sí |

**La diferencia entre (a) y (c) es la conclusión entera:** casi todo lo que
parece un agujero es un retraso que acaba llegando. Al final de la ventana solo
quedan **9 activos con un hueco cada uno**, casi todos del 2026-09-17, tres días
antes de la copia y todavía capaces de llegar.

**Elegir la lectura es decisión del propietario**, y el informe no la toma. Lo
que sí dice con cualquiera de las tres: el problema es de Europa, no del
proveedor en general, así que una segunda fuente para todo el universo no está
justificada por estos datos; la pregunta útil es si hace falta para las plazas
europeas, que es justo la alternativa parcial que el propietario pidió medir.

## Dos avisos que hay que leer antes de usar estas tablas

1. **La ventana cruza 14 versiones de código**, y 1.177 mediciones (11 pasadas)
   son anteriores al manifiesto, así que ni siquiera se sabe con qué código se
   tomaron. **Solo 93 mediciones —una pasada— usan la regla vigente**, la de
   D-36 y D-37 desplegada hoy como `v0.3.0`. Las tasas de arriba describen
   mayoritariamente la regla anterior. La tabla `tabla-versiones-codigo.md` lo
   publica entero.
2. **Ventana corta:** 18 días, sin vacaciones ni cierres largos. Cualquier tasa
   mensual es una extrapolación y va etiquetada como provisional.

## Otros números

- **Barras parciales:** solo las tres criptos, 18 de 39 pasadas cada una
  (46,2 %). Con D-37 desplegado hoy, la última pasada las da en 0.
- **Día de la semana:** el viernes es el peor (35,6 % de mediciones con retraso)
  y el lunes el mejor (0 % sobre n=535). La sospecha del lunes no se confirma.
- **Causas, en ausencias distintas (activo, fecha):** plaza cerrada 88,
  proveedor con plaza abierta 182, barra parcial 42. Contadas por aparición en
  cada pasada serían 1.682 / 2.446 / 42, que es lo que no hay que hacer.
- **Huecos históricos heredados:** los reporta `absent_reference_sessions`
  porque mira 200 sesiones atrás, y no son sesiones perdidas de esta ventana.
  Van en su propia tabla.

## Cómo se trabajó, y el defecto que se corrigió

La implementación la hizo Codex con el `PROMPT_CODEX_TASK` del repo y llegó con
**600 tests en verde, ruff y mypy limpios**. Tenía un defecto que ninguna de las
dos cosas veía, y estaba justo en la única línea que el propietario iba a leer:

> **No deduplicaba las ausencias.** `absent_reference_sessions` lista los huecos
> del histórico de 200 sesiones del activo, así que **la misma sesión ausente
> reaparece en las 39 pasadas**. Al sumarla una vez por pasada, un hueco contaba
> 39 veces, y además se extrapolaba a «por mes» una fecha de marzo vista desde
> septiembre. Su respuesta a OD-02 era «50 activos superan el umbral».

Corregido por el supervisor: las ausencias se acumulan como conjuntos de fechas,
cada una se atribuye al mes **de su sesión** y no al de la pasada que la vio, las
anteriores a la ventana se publican aparte, y se separan las tres lecturas. El
test `test_una_ausencia_repetida_en_varias_pasadas_cuenta_una_vez` falla contra
el código sin corregir.

La segmentación por versión de código tampoco estaba en la ficha: la añadió el
supervisor al ver que la ventana cruzaba el cambio de regla de D-36 y D-37.

## Ficheros

| Fichero | Qué contiene |
|---|---|
| `antes.txt` | línea base antes de tocar código |
| `despues.txt` | salida completa del resumen corregido |
| `validacion.txt` | `pytest`, `ruff` y `mypy` finales: **604 pasan** |
| `tabla-plaza-hora.md`, `tabla-activo-mes.md`, `tabla-barras-parciales.md`, `tabla-dia-semana.md` | las cuatro tablas que pide la ficha |
| `tabla-huecos-historicos.md`, `tabla-versiones-codigo.md` | las dos que añade el supervisor |
| `comprobacion-manual.sql`, `comprobacion-manual-resultado.txt` | SQL directo, sin usar el código del resumen |
| `pre-registro.md` | pre-registro copiado de la ficha |

## Comprobación manual, sin usar el código del resumen

XETRA a las 06 UTC: el SQL directo da **186 retrasadas / 217 mediciones**, y la
tabla dice lo mismo. Las tres lecturas de OD-02 (0, 18 y 47) se recalcularon
también por separado antes de escribir una línea de código, y coinciden.

## Lo que este informe NO hace

No decide OD-02 ni OD-01. No se ejecutó en la Pi: `--resumen` es un comando de
investigación, la Pi corre el tag `v0.3.0` y los timers no lo ejecutan; estará
allí con el próximo release. Los datos son los suyos, copiados en solo lectura.
