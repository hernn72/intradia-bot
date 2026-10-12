# OWNER_DECISION_REQUIRED — después de T-023 (para una D-71 aparte)

> **Exploratorio / post hoc. No cambia D-70, no valida una nueva política y no constituye evidencia
> confirmatoria.** Este documento no decide nada. La decisión es del propietario y, si la toma, se
> registra en una D-71 separada.

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Punto de partida que no cambia

- P6 está cerrado: B2 `NO PASA`, S2 `NO PASA` y salida `[]` (D-70). GATE P6 está cruzado.
- P7 sigue **BLOQUEADO** sin supervivientes, y R-01 y P10 siguen bloqueados detrás de él.
- La cosecha `071ddb2b…` ya está consumida para desarrollo. Ninguna opción puede validarse sobre ella.
- Producción sigue igual: C0, Score v1 y la Pi en v0.4.1.

## Lo que T-023 dejó establecido (resumen de `hallazgos.md`)

- La brecha es **persistente**: negativa en todos los años completos y acumulada sobre todo en
  2023–2025, con el universo subiendo fuerte.
- Los costes, el slippage y el FX son **pequeños** frente a la brecha: cada uno < 12 %.
- El puente de todas las barras, con un 95 % de exposición, también queda por debajo del benchmark.
  La brecha no se debe solo al filtro OPERAR ni solo a la participación.
- En B2 la saturación de cash es estructural. En S2 domina la baja participación y su principal
  rechazo es `ABOVE_MAX_ENTRY`.
- B2 y S2 operaron los activos ganadores del benchmark, pero en tramos de unas 16 sesiones.
- C0, la geometría de producción, también queda por debajo del benchmark todos los años.
- **No identificable** con los artefactos: el desenlace de las señales rechazadas y cualquier
  rendimiento contrafactual.

## Opciones

Ninguna está marcada como recomendada. Cada una enlaza con las hipótesis de
`hipotesis-candidatas.md`, que son post hoc.

| Opción | Qué supondría | Hipótesis | Coste y riesgo principal |
|---|---|---|---|
| **A. No continuar la investigación de B2/S2** | Cerrar la línea de geometría B2/S2 con D-70 como resultado final y no abrir estudios derivados | — | Ninguno metodológico; se renuncia a entender si el problema es de cartera o de señal |
| **B. Estudiar asignación y priorización bajo capital finito** | Ficha y pre-registro nuevos sobre reglas de asignación, con ventana nueva | H23-02 | Necesita los desenlaces de las señales rechazadas (simulación nueva) y tiene alto riesgo de elegir un orden a posteriori |
| **C. Estudiar participación y capital ocioso** | Ficha y pre-registro nuevos sobre el tratamiento del cash ocioso o la tolerancia de entrada | H23-03 | Puede reducir la brecha solo por parecerse al benchmark; hay que separar el exceso de la parte activa |
| **D. Estudiar retención de subidas y reglas de salida** | Ficha y pre-registro nuevos sobre salidas o horizonte | H23-01 | Toca la geometría: el espacio de reglas es grande y el riesgo de sobreajuste a 2023–2024 es alto |
| **E. Medir el edge relativo al drift antes de tocar nada** | Estudio de medición: exceso por operación frente a mantener el mismo activo, en ventana nueva | H23-04 | No cambia ninguna regla; sirve para decidir si el problema es de señal (E) o de cartera (B o C) |
| **F. Abrir una arquitectura de señal nueva** | Nueva línea de investigación desde P2/P3 con otro `score_model_version` | (H23-04 si confirma un problema de señal) | Coste alto; reinicia el camino de gates |
| **G. Congelar la línea cuantitativa y priorizar B-00 / C-04 / C-05 / C-06** | Dedicar el esfuerzo a contrato point-in-time y operación; la línea A queda en pausa con P7 bloqueado | — | Retrasa cualquier mejora del modelo |

Las opciones B a E no son excluyentes entre sí, pero cada una necesita su propia ficha, su
pre-registro y datos que no hayan intervenido en su formulación. H23-05 (FX y región) no aparece como
opción propia porque los datos la muestran como secundaria por magnitud. El propietario puede
incluirla igualmente.

## Lo que D-71 no puede hacer, elija lo que elija

- Cambiar la etiqueta de B2 o S2, ni la salida `[]` de P6.
- Iniciar P7 o declararlo desbloqueado sin una política superviviente de un estudio nuevo.
- Reutilizar la cosecha consumida como validación.
- Activar nada en producción.
