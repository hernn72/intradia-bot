# T-004 — causa de los huecos y corrección de calendario

- Fecha: 2026-09-16 · Rama `fix/hueco-barras-ausentes` · base `main` `c581fb1`
- Diagnóstico: Claude Code contra el proveedor en vivo
- Implementación: Codex · Verificación real y correcciones: Claude Code

## Las tres causas (detalle en la ficha)

| Caso | Fechas | Activos | Veredicto |
|---|---|---|---|
| Mercado cerrado | 2026-06-03, 2026-07-17 | 2 coreanos, 4 pares | KRX cerró; `exchange_calendars 4.13.2` no lo codifica y es la última versión |
| Proveedor no entrega | 2026-09-07, 2026-03-06, 2026-03-23 | 43 pares | Los índices de esas plazas sí tienen barra |
| Pipeline la pierde | — | 0 | `SAP.DE` 1y: 252 barras crudas = 252 tras el pipeline |

## Correcciones aplicadas sobre la entrega de Codex

Cuatro, todas del mismo patrón: ausencia tratada en silencio.

1. `exchange_overrides.yaml` ausente devolvía `{}` —«sin correcciones»— mientras
   `config.yaml` ausente lanza `FileNotFoundError`. Con esa asimetría, un
   despliegue que se dejara el fichero habría devuelto los huecos falsos sin
   decir nada. Ahora falla igual que los otros YAML del proyecto.
2. Una apertura forzada en domingo se añadía como sesión de Xetra sin queja, y
   una fuera del rango del calendario se descartaba en silencio. La validación
   pasa a hacerse **al cargar**: fuera de rango o día que el calendario ya
   considera sesión → error ruidoso con MIC y fecha. No se prohíben fines de
   semana: existen sesiones especiales y cada entrada lleva fuente y fecha de
   verificación.
3. El manifiesto anotaba `exchange_overrides_hash: "missing"` si faltaba el
   fichero. Ahora lo hashea siempre; si falta, la pasada muere.
4. `_decode_date_list` se tragaba en silencio JSON ilegible y fechas
   inválidas. Esa lista **define la población a clasificar**: descartar una
   fecha ilegible la haría más pequeña de lo que es. Ahora declara el valor.

Tres tests nuevos, uno por comportamiento estricto.

## Verificación contra datos reales (la que Codex no podía hacer)

`diagnosticar-barra`, ejecutado hoy contra el proveedor, clasifica los tres
casos correctamente:

| Invocación | Clase |
|---|---|
| `--symbol SAP.DE --fecha 2026-09-07` | «proveedor no la entrega» · calendario dice sesión: sí |
| `--symbol SXR8.DE --fecha 2026-03-06` | «proveedor no la entrega» |
| `--symbol 005930.KS --fecha 2026-06-03` | «mercado cerrado» · calendario dice sesión: **no (cierre_adicional)** |
| `--symbol SAP.DE --fecha 2026-09-08` | «barra presente» |

Pasada real `analizar --horizonte swing --sin-ia --sin-guardar`, `exit=0`:

- `2026-06-03` y `2026-07-17` aparecen **0 veces** en el informe.
- `005930.KS` y `000660.KS` salen **sin ninguna marca de calidad**; antes
  estaban `DEGRADADO`.
- `DEGRADADO` baja de 17 a 15; los dos que faltan son exactamente esos.
- Las ausencias que quedan son las 43 reales: `2026-09-07`, `2026-03-06` y
  `2026-03-23`, ya clasificadas como huecos del proveedor.

Suite: 451 tests, `ruff` limpio, `mypy` limpio en 59 ficheros.

## Lo que queda abierto y pasa a T-005

Los 43 huecos del proveedor **no se pueden rellenar**: el dato no existe en la
fuente. Lo que T-005 debe decidir es cómo se declaran y con qué severidad,
ahora que se sabe que son del proveedor y no del mercado.

Y el hallazgo del rango: producción pide `period: 1y` en swing y
`frescura-datos` pide `1mo`, y el proveedor devuelve series distintas según el
rango. Dos caminos del mismo sistema pueden ver huecos distintos del mismo
activo. Hoy no se contradicen; hay que declararlo o unificarlo en T-005.
