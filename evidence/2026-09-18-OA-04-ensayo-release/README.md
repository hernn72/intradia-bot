# OA-04 — primer release por tag y primer rollback probado

Fecha: 2026-09-18, 14:36–14:52 UTC
Máquina: la Pi (`fer@192.168.1.113`), base de producción real
Tags: `v0.1.0` = `11efae8` (lo que corría antes) · `v0.2.0` = `785daf4` (T-011 + T-017)

Este es el punto 6 de T-011, el que faltaba para aceptar la ficha: **un rollback
no probado no es un rollback**. Aquí está probado sobre la base real, con sus
5.169 recomendaciones y sus 25 manifiestos.

## Qué se hizo, en orden

| Fichero | Paso |
|---|---|
| `01-parada-y-copia.txt` | timers parados, **ningún servicio activo**, copia manual previa |
| `02-despliegue-v020.txt` | `checkout v0.2.0`, `verificar-systemd`, `verificar-release`, SHA comparado a mano |
| `03-config-hash.txt` | `config_hash` de las dos máquinas con las dos reglas — **y la corrección al motivo de T-017** |
| `04-base-antes-de-migrar.txt` | esquema v4, 25 manifiestos, conteos |
| `05-pasada-migracion.txt` | la pasada real que persiste y dispara v4→v5 |
| `06-base-despues-de-migrar.txt` | esquema v5, backup automático `pre-v5` verificado |
| `07-manifiesto-y-perdidas.txt` | manifiesto de la pasada y qué se perdería al restaurar |
| `08-rollback.txt` | el ensayo de vuelta atrás completo |
| `09-vuelta-a-v020.txt` | regreso a `v0.2.0` y recuperación de la base v5 |
| `10-estado-final.txt` | estado final y timers reanudados |

## Lo que demuestra

**`verificar-release` funciona en producción.** `EN_TAG`, código 0, y los tres
SHA idénticos carácter a carácter: `git rev-list -n 1 v0.2.0`, el que imprime el
comando, y el `git_sha` del manifiesto de la pasada.

**La migración v4→v5 conserva la historia.** 25 manifiestos antiguos intactos,
marcados `config_hash_version = 1`; el nuevo con `2`, `release_tag = v0.2.0`,
`schema_version = 5`. El backup automático `intradia.db.bak-20260918-143726-pre-v5`
queda registrado en `backup_log`, con esquema v4 y los conteos de antes
(25 / 5.169 / 3.844).

**El rollback es real, no un párrafo.** Se restauró el backup previo (esquema
vuelve a v4, 25 manifiestos), se volvió a `v0.1.0` y se ejecutó una pasada real
con el código viejo: código 0, y la base **sigue en v4**. Lo que se perdía estaba
contado antes de hacerlo: 1 manifiesto, 103 recomendaciones, 103 mediciones de
frescura. Se recuperaron después desde la copia de seguridad que el propio
procedimiento manda hacer (`intradia.db.rollback-20260918-144036`).

**El defecto de `verificar-backup` reproducido en producción.** Con el código de
`v0.1.0`, la copia manual íntegra sale «Backup inválido» y código 1. Con
`v0.2.0`, sale `VALIDO` con «no figura en backup_log: copia manual». Es
exactamente el mensaje que el 2026-09-18 llevó a dudar de una copia buena.

**`verificar-release` no existe en `v0.1.0`**, y el error lo dice: es la prueba
de que el tag anterior es anterior a T-011.

**El vintage por grupo, en producción**: `--grupos cripto` declara `d0c7c4dc`
frente a `c8496446` de los 103.

## La corrección que hay que anotar: el motivo de T-017 no era cierto aquí

El hallazgo 2 de T-017 decía que «la misma configuración en el portátil y en la
Pi da hashes distintos». **Medido: no.** Las dos máquinas dan `271d46b2` con la
regla 1 y `1294c526` con la regla 2, porque las dos usan las mismas rutas
relativas (`intradia.db`, `universe.yaml`) y la cadena que entra en el hash es
idéntica.

El cambio sigue siendo correcto por la otra mitad de D-33 —la identidad de una
configuración no puede depender de dónde están los ficheros— y empieza a importar
en cuanto aparece una ruta absoluta, que es justo lo que introduce el
procedimiento de rollback al copiar la base a otro nombre. Pero **el criterio de
aceptación «portátil y Pi dan el mismo `config_hash`» ya se cumplía antes**, y
presentarlo como prueba del cambio sería falso.

## Estado al cerrar

`HEAD` en `v0.2.0` (`785daf4`), árbol limpio, esquema v5 con 26 manifiestos,
timers activos, próxima pasada automática a las 21:00 BST, reloj sincronizado.
