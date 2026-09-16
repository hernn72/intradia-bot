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

---

## Revisión independiente y segunda ronda de correcciones

Veredicto **CORREGIR**, con siete defectos, todos reproducidos por el revisor y
confirmados uno a uno antes de corregirlos. Corregidos por Codex y verificados
aquí; suite final **469 tests**, `ruff` y `mypy` limpios.

El más grave era **mío, no de Codex**: al corregir su primera entrega validé
`aperturas_forzadas` y dejé sin validar `cierres_adicionales`, que es
precisamente la lista que se usa —la de aperturas está vacía—. Un cierre
declarado en sábado o en 1850 se cargaba sin una queja, de modo que un dedazo
en una fecha habría dejado la entrada como no-op invisible **y** el hueco falso
seguiría ahí. La asimetría estaba al revés de lo que interesa.

| # | Defecto | Reproducción (antes → después) |
|---|---|---|
| 1 | Clave MIC duplicada descartaba el bloque anterior en silencio | dos bloques `XKRX:` → solo quedaba el segundo · ahora `ValueError: clave duplicada en YAML: XKRX` |
| 2 | `fecha` numérica se convertía en `1970-01-01` | `fecha: 20260603` → `1970-01-01` · ahora error; solo se acepta ISO o fecha nativa de YAML. También se rechaza `"06/03/2026"`, que pandas leía como 3 de junio |
| 3 | `cierres_adicionales` sin validar | sábado y 1850 aceptados · ahora error con MIC y fecha; las dos listas comparten validación |
| 4 | Fichero vacío o solo con comentarios = «sin correcciones» | devolvía `{}` · ahora error |
| 5 | Fallo de descarga se presentaba como «proveedor no la entrega» | 5 descargas fallidas invisibles en la tabla · ahora clase «descarga fallida» y columna de error |
| 6 | La etapa `dropna` era ciega | `get_raw_history` ya hacía `dropna`, así que nunca podía diferir de `raw`. Ahora el diagnóstico pide `drop_na=False` |
| 7 | Fecha futura o fuera del rango consultado acusaba al proveedor | `AAPL 2026-10-01` y `AAPL 2015-01-05` · ahora «fuera del rango consultado» |
| 8 | Los 19 activos de contexto mataban el comando | `^VIX` → exit 1 · ahora degrada esa fila y nombra la plaza |
| 9 | `--todos-los-huecos` descargaba 6 veces por par | **>30 min → 121 s** con memoización `(symbol, period)` |

Añadido además, al verificar: la tabla masiva no decía **de qué pasada** era la
población. La única medición guardada en local es del **2026-09-02**, anterior
a T-003, y por eso 82 de sus 115 ausencias salen hoy como «mercado cerrado»:
eran festivos ajenos que el benchmark marcaba y el calendario de plaza no. Es
una confirmación independiente de que T-003 los eliminó, pero quien leyera la
tabla habría creído estar viendo la población de hoy. Ahora la declara.

### Verificación contra datos reales tras las correcciones

| Caso | Clase |
|---|---|
| `EXSA.DE 2026-09-15` | «pipeline la pierde»: el proveedor entrega la fila con el OHLC en NaN y la capa de datos la descarta. Antes se acusaba al proveedor |
| `^VIX 2026-09-07` | «plaza sin calendario declarado», sin matar el comando |
| `AAPL 2026-10-01` y `2015-01-05` | «fuera del rango consultado» |
| `005930.KS 2026-06-03` | «mercado cerrado», con `no (cierre_adicional)` |
| `SAP.DE 2026-09-07` | «proveedor no la entrega»: la conclusión del ticket se mantiene |

Las siete reproducciones del revisor fallan ahora ruidosamente y el fichero
real sigue cargando sus dos fechas. Pasada real `exit=0`, con `2026-06-03` y
`2026-07-17` apareciendo **cero veces**.

La cosecha de investigación no se mueve: `advisor/research/vintage.py` conserva
el valor por defecto de `drop_na` y el parámetro nuevo es keyword-only (INV-13).

### Lo que queda como afinado para T-005, decidido con datos

De los 115 pares diagnosticados, **cero** caen en «pipeline la pierde». El caso
`EXSA.DE` es reciente y no está en esa población. La etiqueta es discutible
—descartar una fila con el OHLC en NaN es correcto, y llamarlo «el pipeline la
pierde» puede inducir a arreglar lo que no está roto—, pero el mecanismo ya es
visible: aparece el `raw timestamp` y la columna `dropna` dice que no. T-005
decide cómo se declara.
