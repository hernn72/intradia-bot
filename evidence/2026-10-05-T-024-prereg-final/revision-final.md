# T-024 — Revisión final del pre-registro (solo lectura)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Historial de revisiones

| Ronda | Objeto | Resultado | Correcciones |
|---|---|---|---|
| 1 | Ficha de diseño (`77739a1`, antes del commit) | 2 BLOCKER · 4 IMPORTANTE · 1 MENOR | D1 con dividendos; captura ciega sin no solapamiento; `T1` fijado; excepción a INV-14; base temporal; datos insuficientes (el IMPORTANTE sobre los ritmos se retiró en la ronda 2) |
| 2 | Ficha reescrita | 0 BLOCKER · 1 IMPORTANTE | Warm-up en la tabla de §7 |
| 3 | Arreglo, D-71 y sesgo de `μ_a` | 0 BLOCKER · 0 IMPORTANTE · 1 MENOR | Remisión de D-71 al §4 |
| **Final** | **Pre-registro completo tras D-72 (`90475f0`)** | **0 BLOCKER · 0 IMPORTANTE · 1 MENOR · 2 OBSERVACIONES** | Nota en D-71 de que su interpretación la sustituye D-72; los detalles del bootstrap se rotulan como precisión técnica |

El detalle de las rondas 1 a 3 está al final de la ficha.

## Informe de la revisión final (Codex, literal)

**Resumen**
0 BLOCKER, 0 IMPORTANTE. Encontré 1 MENOR y 2 OBSERVACIÓN. Con el criterio dado, el pre-registro es **CONGELABLE**.

**MENOR**
`docs/decision-log.md:1906-1908`

Explicación: D-71 conserva la interpretación histórica "el timing de la señal aporta valor". D-72 corrige explícitamente esa lectura y es la fuente de verdad (`docs/decision-log.md:1963-1979`), y la ficha ya está alineada (`docs/tareas/T-024-edge-relativo-al-drift.md:37-45`, `375-383`). No contamina la ficha congelable, pero deja una frase antigua susceptible de cita fuera de contexto.

Corrección propuesta: añadir en D-71 una nota breve tipo "Interpretación sustituida por la precisión obligatoria de D-72".

**OBSERVACIÓN**
`docs/tareas/T-024-edge-relativo-al-drift.md:327-340`

Explicación: el contrato bootstrap está completo: semanas ISO consecutivas incluyendo vacías, `K − 9` bloques no circulares, `⌈K/10⌉`, truncado a `K`, ventanas juntas con repeticiones, réplica vacía sustituida, `B = 10 000`, `default_rng(20261005)`, percentiles `0,00625/0,99375` con `method="linear"`. D-72 solo fija el cambio propietario de bloque de 10 semanas, B, semilla y esquema común (`docs/decision-log.md:1935-1943`); Codex infiere que los detalles adicionales son desarrollos operativos fieles, no nuevas decisiones propietarias.

Corrección propuesta: ninguna obligatoria. Si se quiere blindaje máximo, rotular esos detalles como "precisión técnica del pre-registro, no nueva OD".

**OBSERVACIÓN**
`docs/tareas/T-024-edge-relativo-al-drift.md:282-311`

Explicación: no veo hueco accionable en re-propuestas ni miradas extra. La mirada 1 solo se propone por conteos, la reconfirmación fallida no abre desenlaces ni crea/consume marca, y vuelve a acumular; la mirada final queda fijada por `2027-08-27`. Al no abrir desenlaces, esas re-propuestas no añaden miradas para Bonferroni. El IC fijo 98,75 % incluso con una sola mirada está explícito en `docs/tareas/T-024-edge-relativo-al-drift.md:357-358` y coincide con D-72 (`docs/decision-log.md:1954-1955`).

Corrección propuesta: ninguna.

**Comprobaciones clave**
La ficha no presenta D2/D2o/D2c/D3/D4 como "timing puro"; al contrario, lo niega y prohíbe atribución causal solo al score/señal (`docs/tareas/T-024-edge-relativo-al-drift.md:37-45`, `137-138`, `383`). La captura y reconfirmación son ciegas a salidas/desenlaces (`docs/tareas/T-024-edge-relativo-al-drift.md:207-222`, `289-296`, `393-401`). Separación desarrollo/forward y warm-up están claros (`docs/tareas/T-024-edge-relativo-al-drift.md:201-204`, `224-229`). P6/P7/producción quedan sin cambios (`docs/tareas/T-024-edge-relativo-al-drift.md:20-23`, `386`, `434-435`; `docs/gates.md:312-321`; `docs/tareas/T-022-p6-sistema-completo.md:2027-2037`).

**Veredicto**
**CONGELABLE**: 0 BLOCKER y 0 IMPORTANTE.

**Comandos ejecutados**
```bash
git status --short --branch && git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD && git merge-base HEAD main && rg ...
rg -n ... advisor/research/p6_sim.py advisor/research/p6.py advisor/research/vintage.py
rg --files evidence/2026-10-05-T-023-diagnostico-post-p6 docs advisor/research | sort
sed -n '1,220p' docs/tareas/T-024-edge-relativo-al-drift.md
sed -n '220,520p' docs/tareas/T-024-edge-relativo-al-drift.md
sed -n '1868,1990p' docs/decision-log.md
rg -n 'timing|score|señal|...' docs/tareas/T-024-edge-relativo-al-drift.md docs/decision-log.md
nl -ba docs/tareas/T-024-edge-relativo-al-drift.md | sed -n ...
nl -ba docs/decision-log.md | sed -n ...
nl -ba docs/gates.md | sed -n '270,330p' && nl -ba docs/protocolo-investigacion.md | sed -n '480,545p'
nl -ba docs/tareas/T-022-p6-sistema-completo.md | sed -n '640,680p;2020,2040p'
rg ...  # una consulta ruidosa por backticks de shell, repetida después de forma segura
git diff --stat main...HEAD && git diff --name-only main...HEAD
rg -n 'T-024|T024|edge relativo|...' ...
rg -n 'ceil|⌈|K − 9|default_rng|linear|...' docs/tareas/T-024-edge-relativo-al-drift.md docs/decision-log.md
```

## Correcciones aplicadas antes de congelar

- **MENOR:** en D-71 se añade la nota «sustituida por la precisión obligatoria de D-72»; se conserva el
  texto original.
- **OBSERVACIÓN 1:** en §10 de la ficha, los detalles del bootstrap quedan rotulados como «precisión
  técnica del pre-registro, no una OD nueva».
- **OBSERVACIÓN 2:** sin acción.

Ambas correcciones son de redacción: no cambian ninguna regla, definición, umbral ni criterio.

## Confirmación

No se ha calculado ningún desenlace ni ninguna métrica de T-024. No se ha leído ni descargado ningún
dato posterior al 2026-08-27 para este trabajo. Tampoco se ha calculado nada sobre la cosecha
consumida. No existe código de T-024.
