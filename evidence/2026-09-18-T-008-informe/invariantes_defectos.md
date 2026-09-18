# Invariantes fase 13

Cada invariante quedó como test con el nombre exigido. La comprobación de
defecto se hizo revisando que la aserción toca el campo que cambiaría ante el
fallo inyectado y, durante desarrollo, rompiendo temporalmente ese contrato
antes de dejar el árbol final limpio.

| Invariante | Test | Defecto que hace fallar el test |
|---|---|---|
| OPERAR implica capas válidas | `test_operar_implica_las_cuatro_capas_validas` | Forzar `accion=COMPRAR` con `execution.executable=False`, RR bajo, `entry > entry_max` o broker distinto de `yes`. |
| `entry_max` respeta RR mínimo | `test_entry_max_nunca_incumple_min_rr` | Usar `entry_max_tecnica` en vez de `min(entry_max_tecnica, entry_max_rr)`. |
| Benchmark no es calendario | `test_benchmark_no_es_calendario` | Derivar ausencias con el calendario del benchmark en vez de la plaza del activo. |
| Festivo no es ausencia | `test_festivo_no_es_sesion_ausente` | Tratar Viernes Santo Xetra como sesión esperada. |
| Benchmark extranjero no exige vela local | `test_sesion_de_benchmark_extranjero_no_exige_vela` | Exigir vela Xetra el 2026-04-06 porque NYSE sí abrió. |
| Informe no dice precio actual con cierre | `test_informe_no_dice_precio_actual_con_plaza_cerrada` | Cambiar la etiqueta de plaza cerrada de `Último cierre` a `Precio actual`. |
| Cambiar entry recalcula cadena | `test_cambiar_entry_recalcula_toda_la_cadena` | Reutilizar RR, `risk_pct`, `potential_pct`, sizing, capital en riesgo o estado calculados al precio de referencia. |

Nota: no queda ningún defecto inyectado en el árbol final; la verificación
final volvió a ejecutar `pytest -q`, `ruff check .` y `mypy advisor` limpios.
