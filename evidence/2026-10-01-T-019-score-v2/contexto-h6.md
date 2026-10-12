# Contexto / H-6

No se mezcla exclusión con imputación. El hueco puntual de STOXX se publica aparte.

## swing

- Asia imputada en población final: 0.
- VIX imputado en población final: 0.
- Tendencia/SMA imputada en población final: 0.
- Exclusiones previas: Asia ausente 396; SMA200 sin historia 6937; VIX no calculable 0; crypto 5112; unión excluida 12269.
- STOXX último cierre causal, ni excluido ni imputado: 1406 señales; edades observadas {1: 624, 3: 700, 4: 82}.

## medio

- Asia imputada en población final: 0.
- VIX imputado en población final: 0.
- Tendencia/SMA imputada en población final: 0.
- Exclusiones previas: Asia ausente 218; SMA200 sin historia 0; VIX no calculable 0; crypto 4722; unión excluida 4940.
- STOXX último cierre causal, ni excluido ni imputado: 1312 señales; edades observadas {1: 620, 3: 610, 4: 82}.

El recuento de imputados se obtiene re-resolviendo el contexto con `PointInTimeContextResolver` sobre cada señal final.
El recuento de VIX no calculable sale de la misma re-resolución; `census_p3_population` falla cerrada ante `NO_CALCULABLE_CONTEXT_VIX`, por eso el censo congelado no publica filas excluidas de VIX.
Fuente de censo: `evidence/2026-09-30-T-019-paso2a-code/` y constantes reproducidas por `advisor.research.p3.EXPECTED_POPULATION`.
