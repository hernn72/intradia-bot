Veredicto final global: **MENOR**. No veo nada que bloquee PR #46 ni una ruta restante para que Fase A registre, capture, abra desenlaces o cambie el contrato.

**BLOCKER:** vacío.

**IMPORTANTE:** vacío.

**MENOR:**
- [deploy/t024/instalar.sh](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/instalar.sh:78): el instalador valida que `T024_ARTEFACTOS_DIR`, su copia por defecto y `T024_DATA_DIR` queden fuera de `T024_REPO_DIR`, pero no valida la relación entre artefactos/copia y `T024_DATA_DIR`. Escenario: `T024_ARTEFACTOS_DIR=$T024_DATA_DIR/art` pasa instalación porque está fuera del worktree T-024; luego el wrapper sale con `11` antes de escribir o descargar. No rompe la captura ni causa escritura peligrosa, porque [checkpoint.py](/Users/fer/Desktop/Trading%20bot/intradia-bot/deploy/t024/checkpoint.py:409) sí lo bloquea antes de crear artefactos, pero el instalador no comprueba “lo mismo” y puede dejar un timer instalado que nunca capturará.

**OBSERVACIÓN:**
- [evidence/2026-10-05-T-024-codigo/guardas-modelo-amenaza.md](/Users/fer/Desktop/Trading%20bot/intradia-bot/evidence/2026-10-05-T-024-codigo/guardas-modelo-amenaza.md:82): el modelo de amenaza referenciado conserva un “Estado en esta entrega” con `T024_CODE_SHA = ddcdb8de...`, mientras el sidecar y calendario actuales declaran `1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0`. Lo trato como documentación histórica/ruido, no como defecto operativo.

Confirmado por lectura: `git diff 1a697c3 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt` sale vacío; el calendario fija `1a697c3...`; el wrapper solo permite `peticion` y `congelar`; `OnCalendar` usa `Atlantic/Canary` y `Persistent=true`; la configuración inválida del wrapper devuelve `11` antes de escribir o descargar. No ejecuté pytest ni comandos de escritura.

Codex session ID: 01a1118b-e237-73a0-88f1-5c33936756a3
Resume in Codex: codex resume 01a1118b-e237-73a0-88f1-5c33936756a3
