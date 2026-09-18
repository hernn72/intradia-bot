# Despliegue en la Pi de la línea 0 completa y la baja de cuatro activos (OA-04)

- Fecha: 2026-09-18, 12:20–12:30 BST · Commit desplegado: `c2ff1d7` (`main`)
- Estado previo de la Pi: `894fa75`, **nueve commits por detrás** (T-007, T-008,
  T-009, T-010 y la baja D-31; le faltaba toda la capa de ejecución honesta)
- Ejecutado por: Claude Code, supervisado; ventana elegida a propósito antes
  del timer de las 14:30 BST para que la primera pasada con el código nuevo
  fuera vigilada y no automática
- Sin migración de esquema: la Pi ya estaba en v4 y `main` no añade ninguna

## Orden seguido

1. `git status --porcelain` en la Pi: **limpio** (solo `logs/` sin seguimiento).
2. Copia manual previa `intradia.db.bak-manual-pre-l0-20260918-121348`
   (2.928.640 bytes), aunque no hubiera migración.
3. `git fetch && git checkout main && git pull --ff-only` → `c2ff1d7`.
4. `pip install -r requirements.txt` (sin cambios desde `894fa75`).
5. `python -m pytest -q` en la Pi → **547 pasan, 3 saltados**, 3 min 00 s. Los
   tres saltados son los que dependen de la cosecha congelada, que no está en
   la Pi, y lo declaran.
6. `verificar-systemd` → «Unidades systemd alineadas con las plantillas
   versionadas», código 0.
7. Pasada real supervisada `analizar --horizonte swing` —con IA y
   persistiendo, como corre producción; sin `--telegram` para no enviar una
   notificación manual—: código 0, 103 activos, 0 errores ni trazas, 2 min 35 s.

## Verificado sobre la base, no sobre el informe

```
git HEAD:                  c2ff1d7
schema:                    4
recomendaciones totales:   5.066   (las 4.963 anteriores intactas + 103)
última pasada:             2d654dc3, 103 filas
accion:                    DESCARTAR 79 · ESPERAR 23 · COMPRAR 1
discard_code:              LOW_SCORE 101 · ∅ 2
execution_code:            EXECUTABLE 49 · STALE_DATA 23 · MISSING_RECENT_DATA 22
                           · BROKER_UNAVAILABLE 6 · PARTIAL_BAR 3   (suma 103)
filas de los 4 de baja:    0
manifiesto:                git_sha c2ff1d7…, schema 4, universe_vintage c8496446…,
                           config_hash 271d46b2… (el mismo que el portátil)
```

Tres comprobaciones que importan más que el resto:

- **`BROKER_UNVERIFIED` pasa de 57 (despliegue del 17/09) a 0, y `EXECUTABLE`
  de 0 a 49.** Es el efecto conjunto de OA-03 y de la baja: producción ya no
  tiene ningún activo sin verificar en el broker.
- **El manifiesto lleva el vintage nuevo `c8496446…`**, es decir, la baja está
  en producción y cualquier recomendación desde esta pasada es atribuible a los
  103, no a los 107.
- **`config_hash` coincide con el del portátil** (`271d46b2`). El hallazgo de
  T-017 sobre las rutas no muerde aquí porque las rutas relativas son las
  mismas en ambas máquinas.

## Hallazgo del despliegue

`verificar-backup --ruta <copia manual>` devuelve **«Backup inválido»** para una
copia que es un SQLite íntegro (`integrity_check = ok`, esquema 4, mismos
recuentos que la base viva). El comando solo valida contra `backup_log`, donde
las copias manuales no existen. En un rollback de madrugada ese mensaje lleva a
descartar la copia buena. Incorporado como requisito 5 de **T-011**.

## Estado final

Timers vivos: `intradia-bot.timer` a las 14:30 BST, `intradia-bot-event.timer`
a las 22:30 BST. Reloj sincronizado, NTP activo. Disco al 15 %.

**La Pi queda al día con `main` por primera vez desde el 17/09**, con GATE L0
completo y el universo de 103.
