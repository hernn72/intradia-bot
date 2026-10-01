# Confianza (D-46): cosecha y pasada local de producción

## Cosecha congelada (paso 2, sin rehacer)

`evidence/2026-09-30-T-019-paso2/confidence_impact.txt`, sha256 `32442cd9338fcd65e5884b3a98285c0625147969b815f2ce65af4378937158b7`.
Método: event study v1 sin desenlaces sobre la población A-02; fórmula antigua frente a D-46.

```text
# Impacto D-46 en Opportunity.confianza

cosecha=071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841
desenlaces=parcheados_a_None

=== swing ===
senales_A02_v1=106363
matriz antigua -> nueva:
  Alta: Alta=0 Media=0 Baja=0
  Media: Alta=0 Media=106363 Baja=0
  Baja: Alta=0 Media=0 Baja=0
motivos:
  Media->Media sin_cambio: 106363

=== medio ===
senales_A02_v1=94273
matriz antigua -> nueva:
  Alta: Alta=0 Media=0 Baja=0
  Media: Alta=0 Media=94273 Baja=0
  Baja: Alta=0 Media=0 Baja=0
motivos:
  Media->Media sin_cambio: 94273
```

## Pasada local de producción

- `timestamp_utc` de referencia: `2026-10-01T11:07:23.875061+00:00`
- `config_hash`: `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387` (`score_model_version` activa: `1.0`)
- Camino: `run_analysis` en proceso, equivalente a `analizar --sin-guardar --sin-ia`; sin Telegram,
  sin base de datos (la caché de barras no actúa), sin Pi, sin cambiar configuración.
- Producción ejecuta solo swing; medio se añade como comprobación del mismo camino.
- Antigua: ratio de la dimensión convicción de Score v1 (barras, indicadores y volatilidad).
  Nueva (D-46, `Opportunity.confianza`): cobertura de barras e indicadores presentes, sin ATR.
  En ambas, la dimensión fundamental ausente cuenta como dimensión que falta.

### swing

Oportunidades evaluadas: 93; activos omitidos por la pasada: 0.

| antigua \ nueva | Alta | Media | Baja |
|---|---|---|---|
| Alta | 0 | 0 | 0 |
| Media | 0 | 93 | 0 |
| Baja | 0 | 0 | 0 |

**Cambios: 0.**

Motivos:
- sin cambio: 93

Componentes sobre los mismos snapshots:
- dimensiones que faltan: fundamental = 93
- cobertura de barras completa: 93 de 93
- indicadores presentes: 6/6 = 93

### medio

Oportunidades evaluadas: 93; activos omitidos por la pasada: 0.

| antigua \ nueva | Alta | Media | Baja |
|---|---|---|---|
| Alta | 0 | 0 | 0 |
| Media | 0 | 93 | 0 |
| Baja | 0 | 0 | 0 |

**Cambios: 0.**

Motivos:
- sin cambio: 93

Componentes sobre los mismos snapshots:
- dimensiones que faltan: fundamental = 93
- cobertura de barras completa: 93 de 93
- indicadores presentes: 6/6 = 93

