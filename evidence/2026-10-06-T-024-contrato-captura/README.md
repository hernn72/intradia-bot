# T-024 — Contrato de captura forward y nuevo lock de código (2026-10-06)

## Qué cambia

El pre-registro T-024 (§7, D-72) exige que cada cosecha forward registre su petición exacta: `symbols`,
`start`, `end`, `interval = 1d`, `auto_adjust = False` y `actions = True`. `freeze_vintage` y
`MarketDataProvider.get_raw_history` solo sabían pedir por `period`. Esta entrega implementa fielmente ese
contrato **sin cambiar ninguna regla metodológica**: `T024_PREREG_SHA = dfcca0ef…` no cambia.

- **Petición exacta.** Modo `start`/`end` retrocompatible: `start` inclusivo y `end` exclusivo, como en
  yfinance. El modo `period` sigue igual byte a byte; la cosecha consumida `071ddb2b…` carga y verifica
  con su id original.
- **`advisor/research/t024_forward.py`:**
  - lista de 126 símbolos derivada del manifiesto consumido
    (`SIMBOLOS_FORWARD_SHA256 = c7a896ab…b50b5`);
  - `start = 2021-08-30`; regla de los 5 días hábiles con festivos declarados;
  - cosecha apta o no registrable; procedencia ligada a checkpoint, festivos e identidades;
  - registro forward canónico (el único que acepta `cargar_registro_forward`);
  - salida de captura de solo conteos;
  - CLI `peticion | congelar | registrar | capturar`.
- **Primer checkpoint:** 2026-11-03 (el 2026-11-02 es festivo laboral en Canarias), con
  **`end = 2026-10-26`** exclusivo. Quedan fuera los días 26 a 30 de octubre. Runbook en
  `docs/tareas/T-024-runbook-checkpoint.md`.

## Identidad

| | SHA |
|---|---|
| `T024_PREREG_SHA` (sin cambios) | `dfcca0ef3428df916089480a0ca574f47e550c24` |
| `T024_CODE_SHA` anterior, **supersedido** | `ddcdb8de7e8781f87fa860db4c0ef0b0675f8356` |
| **`T024_CODE_SHA` nuevo** | **`1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`** |

**`ddcdb8d…` quedó supersedido antes de cualquier captura forward**, por esta corrección de
implementación del contrato de captura. Con `ddcdb8d…`:
- no se descargó ningún dato posterior al 2026-08-27;
- no se congeló ninguna cosecha forward;
- no se creó ninguna entrada del registro forward;
- no se ejecutó `ejecutar_mirada` ni se consumió ninguna mirada;
- no se calculó ningún desenlace (D1, D2, D2o, D2c, D3, D4).

Desde `1a697c3` no se ha tocado ningún `EXECUTOR_PATH`. El ejecutor de `1a697c3` es idéntico al de
`80bc617`, el que revisó Codex en la ronda final (`1a697c3` solo añade una aserción de test).

## Revisiones (`revisiones/`)

| Ronda | Rango | Resultado |
|---|---|---|
| Revisor (Claude) | `3bec864..49acbe5` | 0 BLOCKER, 1 IMPORTANTE, 1 MENOR: corregidos en `c703d7b` |
| Codex r1 | `3bec864..49acbe5` | 1 BLOCKER, 3 IMPORTANTE, 2 MENOR: corregidos en `c703d7b` |
| Codex r2 | `3bec864..c703d7b` | 2 BLOCKER, 1 IMPORTANTE: corregidos en `dc81fc7` |
| Codex r3 | `3bec864..dc81fc7` | 2 BLOCKER, 1 IMPORTANTE, 2 MENOR: corregidos en `c958fac` |
| Codex r4 | `3bec864..c958fac` | 1 BLOCKER: corregido en `80bc617` |
| **Codex r5 (final)** | `3bec864..80bc617` | **0 BLOCKER / 0 IMPORTANTE / 0 MENOR**; 1 observación atendida en `1a697c3` |

Dos hallazgos de Codex se resolvieron con criterio propio, verificado con datos reales:
- **r3 B1.** No se revalida el límite inferior del rango. En la cosecha real, la zona del activo adelanta
  un día la primera barra de `EURUSD=X`, y una barra anterior a `start` no es información posterior. El
  superior (`end` exclusivo) es estricto al congelar, al registrar, al capturar y en la mirada.
- **r4.** La cosecha decisiva en memoria se liga a sus hashes de disco. El modelo de amenaza sigue siendo
  el de `evidence/2026-10-05-T-024-codigo/guardas-modelo-amenaza.md`: rutas accidentales o
  estructurales, no la falsificación deliberada.

Verificación en `verificacion.txt`.
