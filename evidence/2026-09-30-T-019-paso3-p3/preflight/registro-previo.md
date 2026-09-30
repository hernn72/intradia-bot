# Registro previo a la ejecución confirmatoria de P3

Escrito **antes** de abrir ningún desenlace de P3 (FASE A). Nada de esta carpeta usa `net_R`,
salidas, TARGET_FIRST/STOP_FIRST ni expectancy.

- **P3_EXECUTOR_SHA:** `87309da148772f834fd49c3f2357692e48ed9273` (árbol limpio; no se modifica
  después).
- **Pre-registro de P3:** `8b2dddb8fd66423d9550df496d1a2a85abd066b6`.
- **Cosecha:** `data_vintage_id` `071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`.
- **Universo:** `universe_vintage_id` `237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19`.
- **Configuración:** `config_hash` `89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387`;
  `config.yaml` con `score_model_version` "1.0". P3 mide Score "2.0" en investigación, con
  contexto PIT (D-59).
- **Parámetros fijados:** coste 0,2, semilla 20260830, capacidad IC95 con 2.000 remuestreos y
  Bonferroni m=20 (confianza 0,9975, 20.000 remuestreos).
- **Suite sobre el SHA** (`00-suite.txt`): `ruff` limpio, `mypy` limpio y `pytest` con 774 passed.
- **Preflight oficial** (`p3-preflight.json`/`.txt`, exit 0): **OK en los 40 controles**.
  - Swing: 94.094 señales, hash `4aa12d85…`, 90 activos, 5 regiones y 19 bloques. Exclusiones:
    cripto 5.112, Asia 396, SMA200 6.937, Asia∩SMA 176, unión 12.269. Huecos STOXX: 1.406.
    Horizonte válido: bloque ocupado más corto de 42 sesiones > 40.
  - Medio: 89.333 señales, hash `4d6eaab9…`, 90 activos, 5 regiones y 5 bloques. Exclusiones:
    cripto 4.722, Asia 218, SMA200 0, unión 4.940. Huecos STOXX: 1.312. Horizonte inválido:
    102 ≤ 250, veredicto forzado.
  - Antigüedades STOXX: solo 1, 3 y 4 días.
- **Cortes sin desenlaces** (nearest-rank `x[(k*n+99)//100-1]`):
  - swing p20/p40/p60/p80 = **28.0 / 39.6 / 49.6 / 57.6**, 817 valores distintos, n por quintil
    18.292 / 18.740 / 19.405 / 17.205 / 20.452, sin empates;
  - medio p20/p40/p60/p80 = **29.6 / 40.0 / 49.6 / 57.6**, 730 distintos, sin empates;
  - candidatos swing p50/p60/p70/p80/p90 = **43.6 / 49.6 / 53.6 / 57.6 / 63.6**, **sin colapsos**
    (5 distintos); m=20.
  - Ablaciones, cortes propios (swing):
    - sin catalizador 40.0 / 59.333333333 / 72.666666667 / 82.666666667;
    - sin técnico 27.666666667 / 31.666666667 / 36.0 / 43.333333333;
    - sin contexto 20.0 / 30.0 / 42.5 / 52.5;
    - todas OK.
- **Revisión independiente previa** (agente `revisor`):
  - primera vuelta: sin BLOCKER; 2 IMPORTANTE (`--config` sin `config_hash` esperado; ruido de
    coma flotante en las ablaciones) y 4 MENOR, todos corregidos;
  - segunda vuelta: **APROBADO**, sin BLOCKER ni IMPORTANTE (`revision-previa.md`).
- **Comando único:** `python -m advisor.main p3 --fase confirmatoria`, que escribe en
  `evidence/2026-09-30-T-019-paso3-p3/run/`. Consola, horas y código de salida van en
  `../consola/`.
