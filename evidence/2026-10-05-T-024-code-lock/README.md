# T-024 — Lock de `T024_CODE_SHA`

`T024_CODE_SHA.txt` contiene el SHA completo del último commit que toca el ejecutor y la captura de T-024:

**`1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`** (desde el 2026-10-06)

> **Supersesión.** El valor anterior, `ddcdb8de7e8781f87fa860db4c0ef0b0675f8356`, quedó supersedido el
> 2026-10-06, **antes de cualquier captura forward**, por la corrección de implementación del contrato
> de captura:
> - petición exacta `start`/`end` exigida por §7 de la ficha;
> - registro forward canónico.
>
> No cambia ninguna regla metodológica y `T024_PREREG_SHA` sigue igual. Detalle y revisiones en
> `evidence/2026-10-06-T-024-contrato-captura/`.

- El fichero vive fuera de `advisor/` y de los demás `EXECUTOR_PATHS` a propósito. Escribir el SHA dentro
  de `advisor/` cambiaría el ejecutor después de ese SHA, y `executor_unchanged_since` fallaría siempre.
- `advisor/research/t024_decision.py` lo lee con `cargar_t024_code_sha`:
  - **solo** desde `HEAD` (`git show`), en el repositorio del módulo importado (`REPO_ROOT`);
  - la copia de trabajo debe coincidir byte a byte;
  - el contenido es exactamente 40 caracteres hexadecimales en minúscula y un salto de línea opcional;
  - no admite override ni otra ruta, variable de entorno o argumento.
- `verificar_identidad()` exige, en este orden:
  1. el SHA cargado;
  2. `T024_PREREG_SHA` ancestro de `HEAD`;
  3. `T024_CODE_SHA` ancestro de `HEAD`;
  4. ejecutor sin cambios desde `T024_CODE_SHA`;
  5. árbol limpio.

  Devuelve el SHA validado, que es el que registra la marca de cada mirada.

Este fichero se actualiza solo en commits **exclusivos de identidad y evidencia**:
- se creó después de `ddcdb8de7e8781f87fa860db4c0ef0b0675f8356`;
- se reescribió después de `1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`.

Desde `1a697c3` no se ha tocado ninguna ruta del ejecutor.
