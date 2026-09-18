# T-011 — Release por tag, `verificar-release` y rollback probado (C-03)

Estado: EN_REVISION (2026-09-18) — implementada junto con T-017; **falta el punto 6, el ensayo en la Pi**
Agente: Opus (ficha e implementación) → Codex (revisión independiente) → propietario (OA-04, ejecutar en la Pi)
Línea / fase: Línea C, C-03
Gate al que contribuye: GATE PROD (requisitos 2 y 7)

## Objetivo
Que la Pi deje de ejecutar «lo que haya en `main`» y ejecute **un tag
concreto, verificable**, y que volver al anterior sea un procedimiento
probado y no una improvisación.

## Por qué existe
Hoy el despliegue es manual: alguien hace `git pull` en la Pi y comprueba a
ojo. Tres consecuencias reales, todas vistas ya en este proyecto:

- Entre el 2026-09-02 y el 2026-09-16 la Pi corrió **dos entregas por
  detrás** de `main` sin que ningún comando lo dijera; se supo porque alguien
  se acordó.
- `main` admite push directo y force-push (OA-02 sigue abierta), así que
  «el SHA de la Pi está en `main`» no garantiza que ese SHA siga existiendo.
- No hay procedimiento de vuelta atrás. El 2026-09-16 se migró el esquema
  v2→v3 en producción; si hubiera salido mal, la vuelta habría sido a mano,
  de madrugada, sobre la base real.

`verificar-systemd` ya existe y compara las unidades instaladas con las
plantillas. Falta el equivalente para el **código**.

## Dependencias previas
C-00 (CI) HECHO. Esta ficha **no** depende de GATE L0: puede hacerse en
paralelo. Aplica D-11.

## Archivos probables
No asumir que sean exactos: verificar primero con búsqueda de símbolos.
- `advisor/deploy/systemd.py` — `render_units`, `find_systemd_drift`,
  `load_env_file`: el patrón de «comparar lo instalado con lo esperado» ya
  está escrito aquí y **se imita, no se reinventa**.
- `advisor/main.py` — `cmd_verificar_systemd` es el modelo de comando de
  verificación; `verificar-release` se le parece.
- `advisor/run/manifest.py` — ya recoge `git_sha` y `git_dirty` para el
  manifiesto: la fuente del SHA en ejecución ya existe, **no** se duplica.
- `deploy/install-systemd.sh`, `deploy/systemd/`.
- `.github/workflows/ci.yml` — donde se añade el job de release.

## Invariantes que no pueden romperse
INV-06 (una sola forma de leer el SHA en ejecución: la del manifiesto),
INV-16 (si no se puede determinar el tag, se dice «desconocido», nunca se
asume que coincide).

## Implementación requerida

1. **`verificar-release`**, comando nuevo en `advisor/main.py`, pensado para
   ejecutarse **en la Pi**. Comprueba y declara, cada punto por separado:
   - el SHA de `HEAD` en la Pi;
   - si `HEAD` es exactamente un tag `vX.Y.Z` (y cuál), o si está por delante
     o por detrás de él, con cuántos commits;
   - si el árbol está limpio (`git_dirty`);
   - si el tag existe en `origin` y su SHA coincide con el local;
   - y el veredicto: `EN_TAG` / `FUERA_DE_TAG` / `DESCONOCIDO`.

   Código de salida 0 solo con `EN_TAG` y árbol limpio. Sin red, el punto de
   `origin` se declara **desconocido** y no se inventa (INV-16): el veredicto
   pasa a `DESCONOCIDO`, no a fallo.

2. **Release por tag en CI.** Job que, al empujar un tag `vX.Y.Z`:
   comprueba que la suite, `ruff` y `mypy` pasan en ese tag; genera el
   changelog desde los mensajes de commit desde el tag anterior; y publica el
   release en GitHub. Un tag cuya CI no pase **no** produce release.

3. **Versión del software, legible desde dentro.** Hoy el manifiesto guarda
   `git_sha`; añadir `release_tag` (el tag exacto o `null` si `HEAD` no está
   en uno). Si esto persiste una columna nueva, **migración obligatoria**
   (INV-17) con backup previo, como las anteriores.

4. **Procedimiento de despliegue y de rollback, escrito y probado.** En
   `docs/` (sección nueva o documento propio), con los comandos literales:
   - desplegar: `git fetch --tags`, `git checkout vX.Y.Z`, reinstalar
     unidades si cambiaron, `verificar-systemd`, `verificar-release`,
     `verificar-backup`, una pasada real;
   - volver atrás: los mismos pasos con el tag anterior, **incluido qué
     hacer con el esquema de la base** si el tag anterior espera una versión
     menor. Esto último es lo que hoy no está pensado: una migración
     v3→v4 no se deshace sola. La regla que esta ficha fija: el rollback de
     código **no** deshace migraciones; si el tag anterior no sabe leer el
     esquema actual, se restaura el backup previo a la migración, que
     `verificar-backup` ya sabe comprobar. Escribirlo explícitamente.

5. **`verificar-backup` distingue «no registrado» de «corrupto».** Medido en el
   despliegue del 2026-09-18: una copia manual `cp intradia.db …` con
   `integrity_check = ok`, esquema 4 y los mismos recuentos que la base viva
   sale como «Backup inválido», porque el comando solo valida contra
   `backup_log`, donde las copias manuales no existen. En un rollback de
   madrugada ese mensaje lleva a descartar la copia buena. El comando debe:
   comprobar integridad y recuentos de **cualquier** fichero SQLite que se le
   pase; decir «registrado en `backup_log`» o «no registrado (copia manual)»
   como dato aparte; y reservar «inválido» para lo que de verdad no se puede
   restaurar. Test con una copia manual válida y con un fichero corrupto.

6. **Ensayo real (OA-04, propietario).** Etiquetar el estado aceptado como
   `v0.2.0`, desplegarlo en la Pi, ejecutar las tres verificaciones y una
   pasada; después **volver a propósito** al tag anterior, verificar, y
   regresar a `v0.2.0`. Sin este ensayo la ficha no se acepta: un rollback no
   probado no es un rollback.

## Qué NO debe modificarse
La lógica de análisis, el informe y el esquema fuera de la columna que esta
ficha añada. Las unidades systemd salvo que el despliegue por tag lo exija.

## Tests unitarios
- `test_verificar_release_en_tag_exacto`: repositorio temporal con un tag en
  `HEAD` → `EN_TAG`, salida 0.
- `test_verificar_release_por_delante_del_tag`: dos commits después del tag →
  `FUERA_DE_TAG`, con el número exacto de commits, salida ≠ 0.
- `test_verificar_release_con_arbol_sucio`: `FUERA_DE_TAG` aunque el SHA
  coincida.
- `test_verificar_release_sin_red_declara_desconocido` (INV-16).
- `test_manifiesto_guarda_release_tag_o_null`.
- Los tests crean repositorios git temporales; **ninguno** toca el repo real.

## Verificación contra datos reales
En el portátil:
```bash
.venv/bin/python -m advisor.main verificar-release
```
En la Pi (`ssh -i ~/.ssh/id_ed25519_rpi_bot fer@192.168.1.113`):
```bash
cd ~/intradia-bot && git fetch --tags && git checkout v0.2.0
python -m advisor.main verificar-systemd
python -m advisor.main verificar-release
python -m advisor.main verificar-backup
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
```
Comprobar a mano: que el SHA que imprime `verificar-release` es el mismo que
`git rev-list -n 1 v0.2.0`, comparado carácter a carácter, y el mismo que el
`git_sha` del manifiesto de la pasada.

## Medición del impacto
- Ninguno sobre las recomendaciones: esta ficha no toca el análisis. Debe
  confirmarse ejecutando una pasada antes y después y comparando la salida.
- Sí sobre la operación: a partir de aquí, «qué corre la Pi» tiene respuesta
  comprobable.

## Criterio de aceptación
- `verificar-release` distingue los tres veredictos y falla cuando debe.
- El tag `v0.2.0` existe, con CI verde y changelog.
- El rollback se ha ejecutado de verdad en la Pi y está documentado, incluido
  el caso del esquema.
- `pytest`, `ruff`, `mypy` limpios; CI en verde.

## Criterio de rechazo
- Un segundo camino para leer el SHA distinto del manifiesto (INV-06).
- Asumir que el tag coincide cuando no se puede comprobar (INV-16).
- Dar por probado un rollback que solo está escrito.
- Un procedimiento de rollback que no diga qué pasa con las migraciones.

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-011-release/` con README.md, la salida de las tres
verificaciones en la Pi antes y después del rollback, el SHA del tag
comparado a mano, y la pasada real con su manifiesto.

## Commit esperado
Rama `feat/release-by-tag`. Mensaje:
`feat(deploy): release por tag, verificar-release y rollback documentado y probado`

## Actualización documental requerida
`docs/roadmap.md`: fila C-03 a EN_REVISION y luego ACEPTADA.
`docs/decision-log.md`: D-nn con la regla de que el rollback de código no
deshace migraciones y se resuelve restaurando el backup previo. OA-04
actualizada con el ensayo hecho.

## Qué se implementó, punto por punto

1. **`verificar-release`** en `advisor/main.py` (`cmd_verificar_release`), con la
   lógica en `advisor/deploy/release.py`. Publica por separado SHA de `HEAD`,
   tag exacto, SHA del tag, árbol modificado y estado de `origin`, y después el
   veredicto `EN_TAG` / `FUERA_DE_TAG` / `DESCONOCIDO`. Salida 0 solo con
   `EN_TAG` y árbol limpio. Acepta `--repo`, `--remote` y `--sin-red`.
2. **Release por tag en CI**: `.github/workflows/release.yml` se dispara con
   `v[0-9]+.[0-9]+.[0-9]+`, **reutiliza** `ci.yml` vía `workflow_call` (para que
   «el tag pasó la CI» sea literalmente la misma comprobación, no una copia que
   se desincroniza), construye el changelog desde el tag anterior y publica el
   release. Sin CI verde no hay release.
3. **`release_tag` en el manifiesto**, con su columna en la migración v5
   (compartida con T-017, una sola migración).
4. **`docs/despliegue-y-rollback.md`**: despliegue y vuelta atrás con comandos
   literales, incluido qué pasa con el esquema (D-32: el rollback de código no
   deshace migraciones; se restaura el backup previo y se declara la pérdida).
5. **`verificar-backup` distingue «no registrado» de «corrupto»**: `check_backup`
   devuelve integridad, esquema, conteos de la copia y de la base viva, y el
   registro en `backup_log` como dato aparte.

## Invariantes ejercitadas

- **INV-06**: los primitivos de git viven en `advisor/run/git.py` y los usan el
  manifiesto y `verificar-release`; no hay dos formas de leer el SHA ni el tag.
- **INV-16**: `test_verificar_release_sin_red_declara_desconocido` y
  `test_git_dirty_es_null_cuando_git_status_falla`, ambos comprobados inyectando
  el defecto (`evidence/.../inyeccion-de-defectos.txt`).
- **INV-17**: la columna `release_tag` entra por la migración v5, con backup
  previo verificado sobre una copia de la base real.
- INV-01 a INV-05, INV-07 a INV-15, INV-18 a INV-20: no aplica, la ficha no toca
  análisis, niveles ni investigación.

## Medición del impacto

Ninguno sobre las recomendaciones: el diff no toca `advisor/analysis`,
`advisor/report` ni `advisor/research`. Confirmado con una pasada real
(`evidence/.../pasada-rama.txt`). Lo único que cambia en el informe es el pie del
manifiesto, que ahora puede decir `+dirty?` cuando no se pudo comprobar el árbol.

## Revisión independiente

Codex revisó el diff en solo lectura (2026-09-18) y encontró **un BLOCKER y tres
defectos importantes**, todos corregidos en la misma entrega:

- **BLOCKER**: `verificar-release` aceptaba *cualquier* tag exacto, no solo
  `vX.Y.Z`. Un tag `release-test` en `HEAD` daba `EN_TAG` y salida 0, es decir,
  daba por desplegado algo que la CI de release nunca construyó. Corregido con
  `git tag --points-at HEAD` filtrado por patrón, que además resuelve el caso de
  varios tags en el mismo commit quedándose con la versión mayor.
- `check_backup` daba `VALIDO` a cualquier SQLite íntegro, incluido uno vacío.
  Ahora exige las tablas del asesor.
- Una copia registrada con **más** filas que el registro pasaba sin comentario.
  No impide restaurar, así que no cambia el veredicto, pero ahora se declara que
  la copia cambió desde que se registró.
- Camino real sin registrar: una base v2/v3/v4 **sin** `backup_log` hacía la
  copia previa a v5 y no podía anotarla. Ahora `_init_schema` aplica la DDL
  versionada antes del bucle de migraciones.

## Handoff al siguiente agente

**Lo que falta para aceptar la ficha es el punto 6, y solo lo puede hacer el
propietario:** etiquetar el estado aceptado como `v0.2.0`, desplegarlo en la Pi,
ejecutar las tres verificaciones y una pasada, **volver a propósito** al estado
anterior, verificar, y regresar. Un rollback no probado no es un rollback, así
que la ficha sigue en EN_REVISION hasta entonces.

Dos avisos para ese ensayo:

- El tag anterior a `v0.2.0` no existe: este será el primer release etiquetado.
  El ensayo de vuelta atrás tendrá que hacerse contra un commit anterior
  etiquetado a mano (por ejemplo `v0.1.0` sobre `11efae8`) o aceptar que el
  primer rollback probado es el de `v0.2.0` → `v0.1.0` creado para la ocasión.
- **`v0.2.0` migra la base de producción v4→v5** en la primera pasada. Se hace
  supervisado, con la copia manual previa del paso 0 del procedimiento, y
  comprobando después que los manifiestos antiguos de la Pi conservan su
  `config_hash` con `config_hash_version = 1`.
