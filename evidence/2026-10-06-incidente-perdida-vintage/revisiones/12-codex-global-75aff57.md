**Veredicto Final**

**BLOCKER:** vacío.

**IMPORTANTE:**
1. [deploy/t024/traer_cosecha.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/traer_cosecha.py:170): `verificar()` no fija `symbols_sha256` al hash contractual `c7a896…`, ni exige lista ordenada/única/congelada.  
   Escenario: una cosecha/artifacto autoconsistente con 126 símbolos distintos y `symbols_sha256` recalculado puede pasar la verificación de Fase B si manifiesto, petición y `SHA256SUMS` cuadran entre sí. Esto deja incompleta la “petición completa” del contrato.

2. [deploy/t024/checkpoint.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:421): un directorio de checkpoint existente sin `intento.json` ni `estado.json` no se marca como `PERDIDO` al día siguiente.  
   Escenario: caída entre `dir_cp.mkdir()` y la escritura de `intento.json` en [checkpoint.py:451](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:451) deja el checkpoint para siempre como `SIN_ESTADO` en [checkpoint.py:570](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:570), fuera de los estados operativos esperados (`PERDIDO`, `INTERRUMPIDO`, `ERROR_*`, `NO_APTA`).

**MENOR:** vacío.

**OBSERVACIÓN:**
- `T024_CODE_SHA=1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0` sigue consistente: calendario y sidecar coinciden, y `git diff 1a697c3... HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` no mostró cambios.
- No ejecuté pytest ni comandos de escritura, conforme a la instrucción.

Codex session ID: 01a11181-0b0d-7430-a703-039608c32df1
Resume in Codex: codex resume 01a11181-0b0d-7430-a703-039608c32df1
