# Backups tras el incidente (2026-10-06)

Hechos **antes** de volver a ejecutar tests o a Codex con capacidad de ejecución. Están fuera del
repositorio y fuera de iCloud, en `~/intradia-backups/2026-10-06/` (portátil).

| Fichero | Contenido | Verificación |
|---|---|---|
| `intradia-bot-arbol-completo.tgz` | árbol de trabajo completo del portátil, incluido `.git` (sin `.venv` ni cachés) | SHA256 en `SHA256SUMS`, `shasum -c` OK; 1090 entradas de `.git` |
| `no-versionado-portatil.tgz` | `data/vintages/` (solo queda el manifiesto de 071ddb2b…), los 12 `* 2.md` sin seguimiento de `evidence/` y `graphify-out/` | SHA256 en `SHA256SUMS`, `shasum -c` OK; 122 entradas |
| `pi/intradia.db.copia-api-20261006` | base viva de la Pi, copiada con la API `backup` de SQLite (consistente, sin parar el bot) | `PRAGMA quick_check = ok`; SHA256 en `pi/SHA256SUMS-copia-api` |
| `pi/intradia.db.*` (21 ficheros) | todas las copias `.bak`/`.rollback` de la Pi | idénticas byte a byte a la Pi (`pi/SHA256SUMS-pi-original`, 21/21 OK); `quick_check = ok` en las 22 bases |

SHA256 de los dos archivos del portátil:

```
5a86c28b7cd91000d23523597886c9ee022bb8aaa4cf69e8e939d7e835b53cd8  intradia-bot-arbol-completo.tgz
d6f9f630aef85d08adede701837bfd269970d1dda6eb019cd71bb1a14a57500f  no-versionado-portatil.tgz
```

En la Pi, `/home/fer/intradia-bot` sigue en `v0.4.1` con el árbol limpio. `intradia.db` y sus 21 copias
pasan `quick_check` allí mismo, y `intradia-bot.timer` e `intradia-bot-event.timer` siguen activos.

El portátil ya no tiene ninguna base `*.db`: se perdieron en el incidente, y la de producción está en la
Pi y en esta copia.

**Limitación:** las bases de la Pi y su copia de seguridad están en la misma tarjeta SD de la Pi. La copia
de `~/intradia-backups` es la primera copia fuera de ese dispositivo.
