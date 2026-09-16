# Despliegue de `main` en la Pi — 2026-09-16 (OA-04)

Primer despliegue desde el 2026-09-14. La Pi pasa de `1c76add` (T-002) a
`a8a70e2`, es decir, entra de golpe PR 1 (capa de ejecución), T-001 (CI),
y T-003 (calendarios de plaza) con las correcciones de su revisión.

Ejecutado por SSH desde el portátil, en la ventana entre la pasada de las
08:30 y la de las 14:30 BST.

## Pasos y resultado

| Paso | Resultado |
|---|---|
| Copia manual previa | `intradia.db.bak-manual-pre-t003-20260916-091613` (1,8 MB), con `user_version = 2`, 3.465 recomendaciones, 2.140 mediciones, 9 pasadas |
| `git fetch` + `checkout main` + `pull --ff-only` | `a8a70e2`, árbol limpio salvo `logs/` |
| `pip install -r requirements.txt` | `exit=0`; `exchange_calendars 4.13.2`, `pandas 3.0.5`, `yfinance 1.7.0` |
| `pytest -q` | **432 pasan, 3 se saltan** (los que necesitan la cosecha, que en la Pi no está): son los 435 de local |
| `verificar-systemd` | «Unidades systemd alineadas con las plantillas versionadas», `exit=0` |
| `frescura-datos` | `exit=0`, 145 filas de tabla, las 11 plazas de contexto declaradas sin calendario. **Es el comando que antes de la corrección moría con código 1** |
| `analizar --horizonte swing` (con IA, sin Telegram) | `exit=0`, 107 activos |
| Timers | los dos `active`; próxima pasada 14:30 BST |
| Reloj | sincronizado; zona `Europe/London` (BST, +0100) |

## Migración de esquema v2 → v3

Corrió dentro de la pasada real, bajo supervisión, no de madrugada sin nadie
delante. Backup previo automático `intradia.db.bak-20260916-082212-pre-v3`,
`user_version = 3` después, y la columna `calendar` presente en
`data_freshness_measurement`. Contadores tras la pasada: 3.572 recomendaciones
(+107), 2.247 mediciones de frescura (+107), 10 pasadas.

## Lo que se comprobó del dato persistido, no solo del código

El patrón de fallo conocido es que con la IA activada —que es como corre la
Pi— un campo nuevo se pierda en silencio al reconstruir el resultado. Por eso
se miró la base, no el informe:

- Manifiesto de la pasada `beda75e7`: `git_sha = a8a70e28`, `schema = 3`,
  `provider_versions = {"exchange_calendars": "4.13.2", "pandas": "3.0.5",
  "yfinance": "1.7.0"}`. La versión de calendarios es la corrección de hoy, ya
  en producción.
- **107 de 107** mediciones con calendario, repartidas en 12 MIC: XETR 31,
  XNAS 25, XNYS 19, XTKS 7, XPAR 6, XMAD 4, XHKG 4, XMIL 3, CRYPTO_24_7 3,
  XKRX 2, XAMS 2, XCSE 1.
- Las tres criptos: calendario `CRYPTO_24_7`, `may_be_partial_current_session
  = 1` y calidad `OK`. La corrección de la barra parcial llega al dato
  guardado, y no cambia la calidad, que es justo lo pretendido.

Calidad de la pasada: 17 `DEGRADADO`, 24 `INCOMPLETO`. Difiere de la medición
del 14 por el retraso del proveedor europeo ese día, no por el código.

## Salidas completas

`frescura-datos-pi.txt` y `pasada-real-pi.txt`, tal como las produjo la Pi.
