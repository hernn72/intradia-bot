# T-024 — Lock de `T024_CODE_SHA`

`T024_CODE_SHA.txt` contiene el SHA completo del último commit que toca el ejecutor y la captura de T-024:

**`ddcdb8de7e8781f87fa860db4c0ef0b0675f8356`**

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

Este fichero se creó en un commit **exclusivo de identidad y evidencia**, posterior a
`ddcdb8de7e8781f87fa860db4c0ef0b0675f8356`. Desde ese commit no se ha tocado ninguna ruta del ejecutor.
