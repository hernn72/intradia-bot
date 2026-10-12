# T-024 — Guardas de desenlace y modelo de amenaza

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

## Modelo de amenaza (el mismo que P6, `evidence/2026-10-03-T-022-p6/preflight/guardas-outcome.txt`)

Las guardas impiden abrir desenlaces reales de T-024 **por accidente o por una ruta estructural del
código**, por ejemplo:
- llamar a una función pública con datos de una cosecha;
- olvidar una comprobación;
- reintentar una mirada;
- usar otra cosecha;
- elegir el corte o la cosecha decisiva mirando algo.

**No** pretenden impedir que alguien, deliberadamente, parchee el módulo o reconstruya a mano barras
etiquetadas como sintéticas a partir de una cosecha. Eso queda fuera del modelo.

## Dos caminos físicamente separados

| Camino | Módulo | Qué puede producir | Qué no puede |
|---|---|---|---|
| Captura y reconfirmación (ciego) | `advisor/research/t024_captura.py` | Señales OPERAR, señales ejecutables, rechazos por motivo, `Q_p`, `W_p` y recuentos de calidad y revisiones | Salidas, `ℓ_i`, D1–D4, R, P&L, retornos, ventanas cerradas, no solapamiento |
| Decisión | `advisor/research/t024_decision.py` | Ventanas, métricas, intervalo y etiquetas, **solo** dentro de una mirada | — |

## Guardas del camino ciego

- **Corte de la cosecha:** `capturar` trunca la cosecha en `c_e` antes de generar señales.
- **Apertura de `e_i` solo a través de la vista ciega:** la apertura sale exclusivamente de
  `VistaCiega.open_e()`. Leer `high`, `low` o `close` de `e_i`, o cualquier barra posterior, lanza
  `T024LookaheadError`.
- **Ejecutabilidad:** `evaluar_ejecutabilidad(senal, apertura)` solo recibe el escalar de la apertura.
- **Imports cerrados:** el test de AST resuelve `from advisor.research import X` y los imports locales.
  Prohíbe `t024_decision`, `p6`, `p6_sim` y todas las funciones de salida, y tiene un caso negativo.
- **Modo de desarrollo:** `desarrollo=False` exige el corte 2026-08-27 y rechaza la cosecha consumida.
  El modo de desarrollo lleva el rótulo «DESARROLLO — no decide» y nunca se usa en la decisión.

## Guardas del camino decisorio (`ejecutar_mirada`)

En este orden, antes de abrir ningún desenlace:

1. **Identidad** (`verificar_identidad()`, sin argumentos, sobre `REPO_ROOT`, la raíz git del módulo
   importado):
   - `T024_CODE_SHA` sale solo del sidecar `evidence/2026-10-05-T-024-code-lock/T024_CODE_SHA.txt`,
     versionado en `HEAD` (`git show`), con la copia de trabajo idéntica y exactamente 40 hex en minúscula;
   - `T024_PREREG_SHA` y `T024_CODE_SHA` son ancestros de `HEAD`;
   - el ejecutor no ha cambiado desde `T024_CODE_SHA`;
   - el árbol está limpio;
   - si git no está disponible, falla cerrada;
   - no hay override por argumento, variable de entorno ni otra ruta;
   - devuelve el SHA validado, que es el que registra la marca.
2. **Mirada permitida:**
   - solo existen `mirada_1` (con `c_e` < 2027-08-27) y `mirada_final` (con `c_e` = 2027-08-27);
   - los estados de la mirada 1 se leen del registro, nunca de un argumento;
   - la mirada final solo admite las políticas que quedaron pendientes, o se aplica la regla 5;
   - una marca existente deniega;
   - una mirada 1 con marca pero sin estados registrados deniega la final.
3. **Registro forward:**
   - el hash y el orden cuadran;
   - la cosecha recibida es la declarada (`data_vintage_id`);
   - `c_e` es un checkpoint del registro;
   - la cosecha decisiva es la **primera** con checkpoint ≥ `c_e` + 75 días.
4. **Reconfirmación ciega** de `Q_p` y `W_p` sobre la cosecha decisiva:
   - en la mirada 1, si alguna política no cumple, se devuelve `REPROPONER`, sin marca y sin desenlaces;
   - en la final, la política sin capacidad queda `NO EVALUABLE` y las demás se evalúan.
5. **Marca exclusiva** (`O_CREAT|O_EXCL`), que incluye ambas identidades, el hash del registro, la
   mirada, `c_e`, el checkpoint y la cosecha.
6. **`TokenMirada`:**
   - se crea solo después de la marca y va ligado a su sha256;
   - está activo únicamente mientras corre `construir_resultado` y se revoca en `finally`.

**Funciones de desenlace:**
- `barras_decision` (la única que lee precios de la cosecha) y `construir_resultado` exigen el token como
  primera instrucción;
- las barras y ventanas llevan `origen`. Con `origen` «cosecha:<id>», que solo produce `barras_decision`,
  toda función de desenlace exige el token activo: `salida_p6`, `retornos_cierre`, `drift_noche_dia`,
  `construir_ventanas`, `calcular_ventana`, `recalcular_por_politica_activo`, D3, D4 y
  `decidir_politica`;
- con datos sintéticos siguen siendo utilizables sin token, para los tests.

## Estado en esta entrega

`T024_CODE_SHA = ddcdb8de7e8781f87fa860db4c0ef0b0675f8356`, fijado en el sidecar. No existe ningún registro
forward ni ninguna cosecha forward. No se ha consumido ninguna mirada.
