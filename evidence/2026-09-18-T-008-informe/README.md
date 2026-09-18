# Evidencia T-008 — informe e invariantes

Fecha: 2026-09-18
Instante de cierre: 2026-09-18 09:38:16 WEST
Rama esperada: `refactor/report-states`
Commit base observado: `36f7260`
Árbol: cambios sin commitear de T-008; `graphify-out/` ya estaba sin seguimiento.

## Comandos

Línea base previa guardada en `antes.txt`:

```bash
source .venv/bin/activate
python -m pytest -q
ruff check .
mypy advisor
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main analizar --horizonte medio --sin-ia --sin-guardar
```

Verificación posterior:

```bash
python -m pytest -q
ruff check .
mypy advisor
.venv/bin/python -m advisor.main analizar --horizonte swing --sin-ia --sin-guardar
.venv/bin/python -m advisor.main analizar --horizonte medio --sin-ia --sin-guardar
```

Comparación de impacto:

```bash
git archive HEAD | tar -x -C /tmp/t008-head-...
python - <<'PY'  # run_analysis swing sobre HEAD exportado -> actions_antes_head.csv
python - <<'PY'  # run_analysis swing sobre worktree -> actions_despues_worktree.csv
python - <<'PY'  # extrae fichas, recuentos y verificación manual
```

`git archive` fue lectura pura; no se ejecutó `git checkout`, `git branch`,
`git commit` ni comandos que escriban refs.

## Conclusión

- Tests: `531 passed`.
- Ruff: limpio.
- Mypy: limpio.
- Impacto de acción/radar: 0 cambios sobre 107 activos.
- Conteos antes y después: DESCARTAR/DESCARTAR 83, OPERAR/COMPRAR 1,
  VIGILAR/ESPERAR 23.
- Descartes por los siete grupos: score insuficiente 82, RR/ejecución 0,
  datos 0, tendencia 0, sobreextensión 0, broker 1, otros 0.
- Entrada dominante: RR 102, técnica 5.
- Verificación manual AMD: RR `(611.02 - 545.09) / (545.09 - 501.14) =
  1.500114`, impreso `1.50`; entrada aplicada `min(561.57, 545.09) = 545.09`.

## Archivos

- `antes.txt`, `despues.txt`: salidas completas antes/después.
- `ficha_AMD_antes.txt`, `ficha_AMD_despues.txt`: misma ficha antes/después.
- `tabla_acciones_antes_despues.csv`: comparación símbolo a símbolo.
- `impacto_resumen.md`: resumen legible de impacto.
- `recuento_descartes_siete_grupos.csv`: grupos fase 12.
- `recuento_entradas_maximas.csv`: técnica vs RR.
- `verificacion_manual_AMD.txt`: cálculo manual.
- `actions_antes_head.csv`, `actions_despues_worktree.csv`: medición completa.
