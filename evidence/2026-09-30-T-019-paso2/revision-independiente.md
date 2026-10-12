# Revisión independiente del paso 2 de T-019 (2026-09-30)

- **Revisor:** agente `revisor` (Claude), independiente de quien programó (Codex) y del
  supervisor.
- **Modo:** solo lectura, sobre el árbol sin commitear tras la tercera vuelta de Codex.
- **Mandato:** intentar demostrar que la implementación es incorrecta.
- **Foco:**
  - v1 idéntico;
  - RR y convicción fuera de v2;
  - confianza fuera del score;
  - D-59 imposible de violar;
  - v2 sin cortes ni presentación de v1;
  - ninguna ruta que ejecute P3;
  - `config.yaml` en "1.0";
  - la Pi sin tocar;
  - calidad de los tests.
- **Resultado:** **ningún BLOCKER ni IMPORTANTE.** Cuatro MENOR y varias OBSERVATION.

## Qué verificó

1. **v1 idéntico.**
   - La ruta v1 pasa `levels` y `min_bars`, y la configuración de v1 es el mismo objeto.
   - La firma posicional sigue funcionando.
   - `conviction_label`, `grade`, el formatter y el texto al LLM producen el mismo texto en v1.
   - La confianza nueva solo se lee en el informe: no entra en clasificación, sizing ni
     persistencia.
2. **RR fuera de v2.** `_compute_score_v2` no lee `levels`, y la población sigue filtrada por
   `compute_levels` igual que en v1.
3. **Convicción y ATR.** v2 no tiene la dimensión de convicción, y la confianza no usa el ATR%.
4. **D-59.**
   - El modo de contexto se deriva de la versión pedida en analyzer, runner, event study y
     execution filter.
   - `legacy_v1` con v2 da error.
   - Un contexto legacy con v2 lanza `ValueError`.
   - El único sitio que pone `source="point_in_time"` es el módulo point-in-time.
5. **Presentación v2.** `grade` y `conviction_label` lanzan error en v2, y no hay textos de v1
   en el formatter ni en `ai/agents`.
6. **Sin P3 accidental.** La CLI no expone la versión, y las bandas, `capacity` y `ablation`
   rechazan observaciones v2.
7. **Configuración.**
   - `config.yaml` sin cambios.
   - "2.0" no es activable: solo `scoring_for_requested_model` usa la excepción de
     investigación.
   - Las reglas del contrato del paso 1 se conservan.
8. **La Pi.** No hay cambios en `deploy/`.
9. **Tests existentes.** No se debilitaron: solo pasan por el camino validado y reciben
   `confidence_min_bars`.
10. **Medición de la confianza.** Es correcta:
    - usa el `min_bars` de cada horizonte;
    - no lee desenlaces;
    - Media→Media en todo es lo esperado, porque el fundamental siempre falta.

## Hallazgos y cómo quedaron

| # | Clase | Hallazgo | Estado |
|---|---|---|---|
| 1 | MENOR | Con un universo sin índices asiáticos, el contexto PIT salía calculable y v2 daba 1,0 punto neutro de Asia (imputación, contra D-52 y la propiedad actual de D-60). No afecta al universo real, pero el test sobre la cosecha lo tenía así | **Corregido.** Asia vacía da `excluded_asia_missing` y v2 rechaza contextos con Asia, VIX o tendencia/SMA nulos. El test usa las cinco series asiáticas de producción |
| 2 | MENOR | `run_execution_filter_study` con v2 era incoherente: bandas v1 sobre operaciones v2, o abortaba en la primera rechazada | **Corregido.** El estudio, `_band_for_trade` y el informe del backtest rechazan v2 |
| 3 | MENOR | El test de presentación buscaba etiquetas de convicción inexistentes | **Corregido.** Toma las etiquetas reales de `Score.grade` y `conviction_label` |
| 4 | MENOR | Tres tests no discriminaban (mismo objeto de config; frescura, broker y `RiskConfig` que no llegaban al cálculo) | **Corregido.** Pasan por la ejecutabilidad y la clasificación reales y comprueban cambios observables sin mover `Score.value` v2 |
| O | OBSERVATION | Firma legacy de `compute_score` más estrecha (sin llamantes afectados); `score_label` de v2 fija «sin umbral calibrado» hasta el paso 5; valores por defecto "1.0" / `legacy_v1` en constructores | Registradas; sin cambio |

Tras la cuarta vuelta, el supervisor revisó el delta y repitió toda la verificación
(`01-verificaciones-supervisor.txt`). Las correcciones no cambian v1 ni la población de P3, así
que no se lanzó una segunda revisión completa.
