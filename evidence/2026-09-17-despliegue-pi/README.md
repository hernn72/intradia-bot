# Despliegue en la Pi de T-004 y T-005 (OA-04)

- Fecha: 2026-09-17, mañana · Commit desplegado: `572192c` (`main`)
- Estado previo de la Pi: `c581fb1`, **dos entregas por detrás** desde el
  2026-09-16 (le faltaban T-004 y T-005, que se desplegaron juntas a propósito)
- Ejecutado por: Claude Code, supervisado en el momento para que la migración
  de esquema no cayera en una pasada automática de madrugada

## Orden seguido

1. `git status --porcelain` en la Pi: **limpio**, sin cambios locales que
   pisar.
2. Copia manual previa: `intradia.db.bak-manual-pre-t005-20260917-092548`
   (2.158.592 bytes), además del backup automático que hace la propia
   migración.
3. `git fetch && git checkout main && git pull --ff-only` → `572192c`.
4. `pip install -r requirements.txt`.
5. `python -m pytest -q` → **491 pasan, 3 saltados**, 2 min 53 s.
6. `python -m advisor.main verificar-systemd` → «Unidades systemd alineadas con
   las plantillas versionadas», código 0.
7. Pasada real supervisada `analizar --horizonte swing` —con IA y persistiendo,
   como corre producción—, que es la que provoca la migración v3→v4: 107
   mediciones de frescura y 107 recomendaciones guardadas.

## Verificado sobre la base, no sobre el informe

```
schema:                    4
columna `warnings`:        presente
recomendaciones totales:   4.107   (las 4.000 anteriores intactas + 107)
última pasada:             f9b975ba, 107 filas
discard_code:              LOW_SCORE 106 · ninguno 1 (el único OPERAR)
execution_code:            BROKER_UNVERIFIED 57 · MISSING_RECENT_DATA 28 · STALE_DATA 19 · PARTIAL_BAR 3
advertencias persistidas:  AMD → «precio extendido 1.0·ATR sobre su media rápida…»
manifiesto:                git_sha 572192c…, schema_version 4
```

Dos comprobaciones que importan más que el resto:

- **El reparto de `execution_code` coincide exactamente con el del portátil**
  (57 · 28 · 19 · 3), medido media hora antes sobre el mismo universo. Dos
  máquinas distintas, mismo veredicto.
- **La advertencia de precio extendido llegó a la base de datos.** Es la
  corrección que la segunda revisión encontró a medias —el aviso había dejado
  de persistirse al salir de `decision_reasons`— y aquí queda verificada en
  producción, no solo en test.

## Estado final

Timers vivos: `intradia-bot.timer` próxima a las 14:30 BST,
`intradia-bot-event.timer` a las 22:30 BST. Reloj sincronizado, zona
Europe/London. Disco al 15 %.

**La Pi queda al día con `main`**, por primera vez desde el 2026-09-16 por la
mañana.
