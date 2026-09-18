# T-012 — Interpretar el histórico de frescura de la Pi (A-01)

Estado: PENDIENTE
Agente: Opus (ficha y lectura) → Codex (agregación) → propietario (OD-02, OD-09, OD-10)
Línea / fase: Línea A, A-01
Gate al que contribuye: ninguno directamente; **produce la cifra con la que se
deciden OD-02, OD-09 y OD-10**

## Objetivo
Convertir las pasadas guardadas en la Pi en tres números que hoy no existen:
cada cuánto falta el dato, **a qué hora** y **a qué activos**. Con ellos, el
propietario decide si paga una segunda fuente para Europa (OD-02), si mueve el
horario de las pasadas (OD-09) y qué hace con cripto (OD-10).

## Por qué existe
Las tres decisiones abiertas se están tomando con intuición y con muestras
pequeñas medidas de pasada:

- OD-02 fija un umbral —«> 2 sesiones perdidas por mes en más de 10 activos»—
  **que nadie ha medido todavía**.
- OD-09 se apoya en 21 pasadas medidas el 2026-09-16 (96–100 % de retraso
  europeo a las 06:02 y 07:32 UTC, 38 % a las 13:32, 0 % a las 20:02). Es la
  dirección correcta, pero son 21 pasadas y dos semanas.
- OD-10 se apoya en el razonamiento de que la sesión 24/7 solo cierra a las
  00:00 UTC, no en el recuento de cuántas veces la barra de cripto llegó
  parcial y a qué hora.

La Pi acumula histórico persistido de frescura **desde el 2026-09-02**
(`frescura-historico`). Esta ficha lo lee y lo publica.

## Pregunta, métrica y criterio — PRE-REGISTRO
Se escribe antes de mirar los datos. Lo que se decida después de verlos se
etiqueta `exploratorio`.

- **Pregunta primaria:** ¿con qué frecuencia el dato que ve el asesor está
  retrasado o ausente, desglosado por plaza y por hora de pasada?
- **Métrica primaria:** para cada par (plaza, hora de pasada), el **porcentaje
  de mediciones con retraso ≥ 1 sesión**, con su intervalo de confianza y su
  denominador. El denominador se publica siempre: un 100 % sobre 4 mediciones
  no es lo mismo que sobre 400.
- **Métricas secundarias:** sesiones ausentes por activo y por mes (la cifra
  del umbral de OD-02); racha máxima de sesiones consecutivas ausentes por
  activo; porcentaje de barras parciales por activo (la cifra de OD-10);
  distribución por día de la semana (la sospecha del lunes); y cuántas
  ausencias coinciden con un `exchange_overrides.yaml` ya registrado —esas no
  son huecos, son cierres reales.
- **Población:** todas las mediciones persistidas en la Pi desde el
  2026-09-02 hasta la fecha de ejecución, los 107 analizables. Se declara el
  número exacto de pasadas y de mediciones.
- **Criterio de decisión de OD-02, fijado antes de medir:** el umbral ya
  propuesto —más de 2 sesiones perdidas por mes en más de 10 activos— se
  evalúa tal cual. Si sale por encima, OD-02 se reabre con la cifra; si sale
  por debajo, se cierra como «no procede por ahora» con la cifra. **Este
  informe no decide**: prepara la decisión.
- **Tratamiento de la incertidumbre:** intervalo binomial por celda. Una
  celda con menos de 30 mediciones se publica como insuficiente y **no** se
  agrega con otra para alcanzar el mínimo.
- **Sesgo conocido que hay que declarar:** el histórico empieza el
  2026-09-02, cubre pocas semanas y **no** incluye ningún periodo de
  vacaciones ni cierres largos. Cualquier tasa mensual extrapolada de aquí es
  provisional y se etiqueta como tal.

## Dependencias previas
Acceso a la Pi (`ssh -i ~/.ssh/id_ed25519_rpi_bot fer@192.168.1.113`). No
depende de GATE L0. Sí conviene hacerla **después** de T-007, porque el
estado de plaza permite separar «no hay barra porque la plaza está cerrada»
de «no hay barra y debería haberla».

## Archivos probables
- `advisor/main.py` — `cmd_frescura_historico`, ya existe: se **amplía** con
  la agregación, no se escribe un comando paralelo.
- `advisor/storage/` — la tabla que persiste las mediciones; leer su esquema
  real antes de escribir nada (`sqlite3 intradia.db ".schema"`).
- `advisor/data/` — `calcular_frescura_dato` y la clasificación de calidad.
- `exchange_overrides.yaml` — los cierres reales ya registrados, que hay que
  descontar de las ausencias.

## Invariantes que no pueden romperse
INV-05 (la plaza sale de `primary_market`), INV-16 (una celda sin datos se
declara vacía, nunca 0 %), INV-06 (la clasificación de frescura es la misma
que usa producción; no se reimplementa para el informe).

## Implementación requerida

1. **Traer el histórico de la Pi al portátil sin tocar la base de la Pi.**
   Copia de solo lectura (`scp` del fichero de base o export a CSV desde la
   Pi), registrada en la evidencia con su instante y su tamaño. **No** se
   ejecuta nada que escriba en la base de producción.

2. **Agregación**, como subcomando o argumento de `frescura-historico`:
   `frescura-historico --resumen` que publique, en tablas:
   - (plaza × hora de pasada): mediciones, % con retraso ≥ 1 sesión, IC;
   - (activo × mes): sesiones ausentes, descontando las de
     `exchange_overrides.yaml`, y racha máxima;
   - (activo): % de barras parciales;
   - (día de la semana): % con retraso.

   Todo con denominador visible. Nada de porcentajes sin `n`.

3. **Responder al umbral de OD-02 con una sola línea**, calculada por el
   código y no a ojo: «N activos superan las 2 sesiones perdidas por mes;
   el umbral es 10». Esa línea es el entregable que el propietario lee.

4. **Separar las tres causas**, que hoy se confunden: plaza cerrada (cierre
   real, con override o con calendario) · proveedor que no entregó con la
   plaza abierta · barra parcial por sesión aún en curso. Cada ausencia cae
   en una y solo una.

## Qué NO debe modificarse
Nada de producción: esta ficha **lee**. Si al leer aparece un defecto en cómo
se persiste la frescura, se clasifica (BLOCKER / FOLLOW_UP) y se decide
aparte; no se arregla dentro de una tarea de medición.

## Tests unitarios
- `test_resumen_no_agrega_celdas_con_muestra_insuficiente`.
- `test_ausencia_con_override_no_cuenta_como_hueco`: fecha de KRX del
  2026-06-03, ya registrada como cierre real → no suma al recuento.
- `test_celda_sin_mediciones_se_declara_vacia_y_no_cero` (INV-16).
- `test_porcentaje_siempre_va_con_denominador`.
- `test_las_tres_causas_son_excluyentes`: una ausencia no puede contarse dos
  veces.

## Verificación contra datos reales
```bash
# en la Pi, solo lectura
ssh -i ~/.ssh/id_ed25519_rpi_bot fer@192.168.1.113 \
  "cd ~/intradia-bot && python -m advisor.main frescura-historico --resumen"
# y en el portátil, sobre la copia
.venv/bin/python -m advisor.main frescura-historico --resumen
```
Comprobar a mano: elegir **un** activo europeo y **una** hora de pasada,
contar sus mediciones retrasadas en la base con una consulta SQL directa y
comprobar que coincide con la celda de la tabla, denominador incluido.

## Medición del impacto
Ninguno sobre el comportamiento del bot. El impacto es informativo y se mide
así: las tres decisiones abiertas (OD-02, OD-09, OD-10) pasan de no tener
cifra a tenerla, y se dice cuál.

## Criterio de aceptación
- Las cuatro tablas publicadas, con denominadores e intervalos.
- La línea de respuesta al umbral de OD-02, calculada por el código.
- Las tres causas separadas y excluyentes.
- El sesgo de ventana corta declarado en el informe, no solo en la ficha.
- `pytest`, `ruff`, `mypy` limpios.

## Criterio de rechazo
- Un porcentaje sin denominador.
- Agregar celdas pequeñas para alcanzar una muestra.
- Extrapolar una tasa mensual desde tres semanas sin etiquetarla provisional.
- Escribir en la base de la Pi.
- Tomar por el propietario cualquiera de las tres decisiones.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-012-frescura-historico/` con README.md, el pre-registro
copiado, el instante y tamaño de la copia traída de la Pi, las cuatro tablas,
la consulta SQL de la comprobación manual y su resultado.

## Commit esperado
Rama `feat/freshness-history-summary`. Mensaje:
`feat(frescura): resumen del historico persistido con denominadores y causas separadas`

## Actualización documental requerida
`docs/roadmap.md`: fila A-01 a EN_REVISION y luego ACEPTADA.
`docs/decision-log.md`: OD-02, OD-09 y OD-10 actualizadas **con la cifra**, y
marcadas explícitamente como «listas para decidir, pendientes del
propietario». Ninguna se cierra aquí.

## Handoff al siguiente agente
Pendiente de escribir al terminar.
