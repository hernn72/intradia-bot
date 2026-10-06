# Revisión independiente (subagente revisor de Claude) sobre b718917..8c5ba1f

Resultado: 0 BLOCKER, 0 IMPORTANTE, 4 MENOR. Los cuatro se corrigieron en 10f2702.

1. Un intérprete Python hijo con -I/-E o con env= explícito sin PYTHONPATH escapaba de la red (reproducido).
2. Lista de órdenes incompleta: mv, git reset --hard/checkout --/restore/stash/rm, rsync --delete,
   `-delete;` (reproducido).
3. La red fallaba abierta si data/ o evidence/ fueran enlaces simbólicos (reproducido en un repo falso).
4. `instalar.sh` borraba su temporal sin comprobar el prefijo de staging.

Guarda de producción (validar_staging, borrar_staging, promover_sin_pisar, copiar, segunda_copia): sin
defectos tras intentar romperla. Fase A sin ruta a registrar/capturar. Diff de EXECUTOR_PATHS vacío.
