# T-021 / A-05 — Cierre de P5 y GATE P5

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

**P5 se ejecutó exactamente una vez** (2026-10-03, marca a las 09:44:05 UTC) y no se repite. Este
directorio registra su resultado y el cierre del gate **sin recalcular nada** desde la cosecha y sin
tocar `evidence/2026-10-02-T-021-p5/run/`.

## Identidad

| | |
|---|---|
| `P5_PREREG_SHA` | `a7c3d238d651b4ea8f48834848c03c0a5a462dfa` |
| `P5_CODE_SHA` | `6c7f9135774f157e82634b6abf82a847d9b99bd9` |
| `P5_PREFLIGHT_HEAD` | `7446602114b26f56cae549d2ec299d7bbc07b459` |
| `P5_RUN_HEAD_SHA` | `282b1ce991bb4567ff2ad41a28e00c9518662115` |
| `P5_RUN_EVIDENCE_COMMIT` | `86ddd5baf8ceabe6e9d3747d645c7c99d719343c` |
| D-67 (resultado) | `7c9e8758b6f21c85ffb2c015109847cba9c840f9` |
| Marca: sha256 = `token_sha256` | `f50d5ec9cc7e2c266515778592c4398001ee8588dbcdcc2b4c783bcca87c1f8c` |

## Resultado (D-67)

- 71/71 comparaciones, 0 confirmatorias nuevas.
- **B2 ROBUSTA** y **S2 ROBUSTA**: `centro_p4 = True` y F1–F6 = False en las dos.
- 13/13 vecinos ACEPTABLES (B2 8/8, S2 5/5).
- 6/6 LOCRO estimables con IC95 inferior > 0.
- **Supervivientes `[B2, S2]`**, sin orden entre ellas.

## Gate (D-68)

GATE P5 **CRUZADO**: los cuatro requisitos están satisfechos y la revisión final no deja ningún
BLOCKER, ningún IMPORTANTE ni ningún MENOR. A-05 / T-021 queda ACEPTADA. P6 queda desbloqueado y no
iniciado.

Producción no cambia: B2 y S2 no se activan, `config.yaml` sigue en `"1.0"`, Score v2 sigue inactivo
y la Pi en `v0.4.1`.

## Ficheros

| Fichero | Contenido |
|---|---|
| `resultado-p5.md` | Transcripción literal de `run/`: criterio, clases, superficie completa (y el TSV íntegro), ausencias, LOCRO, concentración, supervivientes y descartes |
| `politicas-finales.json` | B2 y S2: `id`, `advisor_config_hash`, `policy_payload`, `canonical_json` y `policy_sha256` |
| `generar_politicas.py` | Genera el JSON anterior con `policy_payload`/`canonical_json` (sin desenlaces) y para si algún hash no coincide |
| `revision-final.md` | Revisión final independiente (Codex, literal) y verificación propia |
| `gate-p5-final.md` | Matriz de los cuatro requisitos de GATE P5 |
| `hashes-evidencia.txt` | SHA256 de `run/` y de este directorio |
| `final-pytest-ruff-mypy.txt` | ruff, mypy y la suite completa al cerrar |
