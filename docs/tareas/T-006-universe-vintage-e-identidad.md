# T-006 — `universe_vintage_id` e identidad mínima de instrumentos (A-00)

Estado: PENDIENTE (intento del 2026-09-14 bloqueado por el entorno; ver handoff)
Agente: Codex (mecánico, bien especificado) → Opus (revisión breve del hash canónico)
Línea / fase: A-00 (prerrequisito de GATE P2) y B-01 (identidad para la línea B)
Gate al que contribuye: GATE P2 (requisito 3), GATE B0

## Objetivo
El universo analizable tiene una identidad versionada (`universe_vintage_id`)
que entra en el manifiesto de ejecución y en todo resultado de investigación,
y cada activo lleva los campos mínimos de identidad emisor/instrumento/listing.

## Por qué existe
Los 107 activos se eligieron el 2026-08-27/29 con conocimiento de 2026 y se
miden hacia atrás cinco años (verificado: `git log -- universe.yaml`). Ese
sesgo no se puede corregir gratis, pero sí acotar: hace falta saber
**exactamente** qué universo produjo cada número. Decisiones D-08, D-20.

## Dependencias previas
T-002 (el manifiesto consume el vintage). Puede hacerse en paralelo con T-003.

## Archivos probables
No asumir que sean exactos: verificar primero.
- `advisor/universe/models.py` (`Asset`, `Universe`)
- `advisor/universe/loader.py` (`load_universe`)
- `advisor/universe/vintage.py` (nuevo: `universe_vintage_id(universe) -> str`)
- `universe.yaml` (campos nuevos en los 126 instrumentos)
- `advisor/run/manifest.py` (T-002)
- `advisor/research/event_study.py`, `capacity.py`, `ablation.py`, `uncertainty.py` (los resultados publican el vintage)
- `.gitignore` (excepción `!data/vintages/*/manifest.json`)
- `tests/test_universe.py`, `tests/test_universe_vintage.py` (nuevo)

## Invariantes que no pueden romperse
INV-06, INV-16, INV-19 (esta tarea la establece). La carga del universo
sigue fallando ante un ISIN inválido.

## Implementación requerida
1. Campos nuevos en `Asset`, todos con valor por defecto para no romper la
   carga: `issuer_id: Optional[str]` (slug; obligatorio para `analizable:
   true` — validar), `instrument_id: str` (= ISIN si verificado, si no
   `f"{primary_symbol}@{primary_market}"`), `added_at: date` (obligatorio;
   para los 126 actuales: `2026-08-27` los del commit inicial y `2026-08-29`
   los del commit `e952f71`; obtenerlo con `git log -S` por símbolo y anotar
   el método en la ficha), `valid_to: Optional[date] = None`, `delisted_at:
   Optional[date] = None`, `ticker_history: list[str] = []`,
   `isin_verified_at: Optional[date]`, `isin_source: Optional[str]`,
   `trade_republic_checked_at: Optional[date]`.
2. Validador: `isin` sin `isin_verified_at` → error de carga («un ISIN sin
   fuente no es verificado»). Los 18 ISIN actuales: rellenar
   `isin_source: "universe inicial 2026-08-27"` y `isin_verified_at` con esa
   fecha; **no** inventar fuentes mejores.
3. `universe_vintage_id`: SHA-256 de la serialización canónica (JSON con
   claves ordenadas, sin espacios) de la lista de analizables ordenada por
   `instrument_id`, con los campos `instrument_id, issuer_id, primary_symbol,
   primary_market, primary_currency, asset_class, region, added_at, valid_to,
   benchmark`. Cambiar `name` o `notes` no cambia el vintage; cambiar la lista
   o un benchmark sí.
4. El manifiesto (T-002) y los resultados de `advisor/research/` incluyen
   `universe_vintage_id`. `comparacion-pareada` aborta si difieren, igual que
   con `data_vintage_id` (INV-08 ampliada).
5. Subcomando `universo --vintage` que imprime el id y la lista.
6. `.gitignore`: dejar de ignorar `data/vintages/*/manifest.json` y commitear
   el manifiesto de `071ddb2b…` (87 KB, verificado).

## Qué NO debe modificarse
La lista de analizables (ningún activo entra ni sale en esta tarea), los
benchmarks, `trade_republic` (sigue `unknown`).

## Tests unitarios
- `test_vintage_estable_ante_cambios_de_nombre_o_notas`.
- `test_vintage_cambia_si_entra_o_sale_un_activo`.
- `test_vintage_cambia_si_cambia_el_benchmark`.
- `test_isin_sin_fuente_falla_al_cargar`.
- `test_universe_real_tiene_107_analizables_y_vintage_conocido`: carga
  `universe.yaml` y fija el id en el test (se actualiza a propósito cuando el
  universo cambia, con entrada en el decision log).

## Tests de integración
`test_comparacion_pareada_aborta_con_universo_distinto`.

## Verificación contra datos reales
```bash
python -m advisor.main universo --vintage
python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar | tail -3
```
Comprobar a mano: el id impreso al pie del informe coincide con el del
subcomando; editar un `notes` y comprobar que no cambia; revertir.

## Medición del impacto
- nº activos afectados: 0 en decisión; 126 en metadatos.
- nº señales afectadas: 0.
- cambio en resultados relevantes: cada resultado futuro lleva vintage.

## Criterio de aceptación
- 107 analizables con `issuer_id`, `added_at` e `instrument_id`; carga sin errores.
- Vintage estable y testeado; manifiesto de cosecha commiteado.
- CI en verde.

## Criterio de rechazo
- Un ISIN nuevo «encontrado» sin fuente primaria.
- Un `added_at` inventado (debe salir de `git log`).

## Evidencia que debe quedar registrada
`evidence/<fecha>-T-006-universe-vintage/README.md` con el id, el comando
`git log -S` usado y la lista de `added_at` por commit.

## Commit esperado
Rama `feat/universe-vintage`. Mensaje:
`feat(universe): identidad mínima de instrumentos y universe_vintage_id en manifiesto y resultados`.

## Actualización documental requerida
`docs/roadmap.md`: A-00 → ACEPTADA; sección «Universo» con el id.
`docs/decision-log.md`: entrada con el primer vintage registrado.

## Handoff al siguiente agente

### Intento del 2026-09-14 — BLOQUEADA por el entorno, sin trabajo perdido

Se delegó a Codex sobre un git worktree hermano
(`../intradia-bot-t006`, rama `feat/universe-vintage` desde `1c76add`) para
ejecutarla en paralelo con T-003. **La sesión de Codex no puede escribir fuera
del directorio principal del repositorio**: falló antes de la línea base con

```text
mkdir: evidence/2026-09-14-T-006-universe-vintage: Operation not permitted
```

No se modificó ni creó ningún fichero, no se calculó el vintage nuevo y el
worktree quedó limpio. El worktree se retiró; la rama `feat/universe-vintage`
sigue apuntando a `1c76add`.

### Cómo retomarla

1. Desde el repositorio principal: `git checkout feat/universe-vintage`
   (o rehacerla desde el HEAD de `fix/exchange-calendars` una vez esa entrega
   esté aceptada, para no arrastrar un `universe.yaml` desactualizado).
2. Ejecutarla **después** de T-003, no en paralelo: con Codex las fichas
   simultáneas se serializan porque no admite worktrees.
3. Cambios respecto a la ficha original, ya sabidos:
   - T-002 dejó en `advisor/run/manifest.py` un `universe_vintage_id`
     provisional (hash de la lista de símbolos analizables) que hay que
     sustituir por la definición canónica de esta ficha, preferiblemente en
     `advisor/universe/vintage.py` con un import desde el manifiesto.
   - El vintage de las pasadas ya persistidas,
     `80d05f21abad212757d2f06d9f2dd53032b92a342dba90904b3086ea970d0b59`,
     cambia por definición nueva: hay que anotarlo en el decision log y en la
     evidencia, y dejar claro que las pasadas anteriores llevan el provisional.
   - `added_at` sale de `git log --diff-filter=A -S'primary_symbol: <SYM>'
     --format=%ad --date=short -- universe.yaml`; los 126 instrumentos deben
     caer entre `93009da` (2026-08-27) y `e952f71` (2026-08-29).
   - T-003 ya usa `exchange_calendars` y deriva la plaza de `primary_market`;
     si T-003 no llegó a añadir `exchange_calendar`/`exchange_timezone` al
     YAML, esta ficha es un buen sitio para hacerlo junto con el resto de
     campos de identidad.
