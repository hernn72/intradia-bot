# Superbot IA — plan de rentabilidad

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Documento vivo. Abierto el 2026-11-12 (D-82). Cada fase se actualiza aquí al cerrarla: qué se
hizo, qué se midió y qué decisión queda.

## Punto de partida

Ningún plan garantiza que el bot gane dinero. Lo que este plan sí hace es averiguar barato si
hay ventaja y cortar si no la hay. La vara de medir es `EUNL.DE` (MSCI World) con el mismo
capital: si el bot no lo bate neto de comisiones y de API, el dinero está mejor en el fondo.

Revisión del 2026-11-12, sobre 4,5 sesiones en activo:

| # | Hallazgo | Estado |
|---|---|---|
| 1 | La IA solo ve el JSON técnico que el Score ya resume; tiene prohibidas noticias y fundamentales. Es un filtro sobre el Score, no una fuente de información nueva | Abierto: fase 2 |
| 2 | El Score de base no tiene ventaja demostrada (D-70; P2.5 indeterminado) | Abierto |
| 3 | El tope de 5 €/mes se agotaba en una semana: el bot habría operado ~5 sesiones de 21 | Cerrado en D-82 |
| 4 | Coste real ~0,9 €/día (~20 €/mes, un 4,8 % anual sobre 5.000 €) | Reducido a la mitad en fase 1 |
| 5 | 8 de 74 llamadas de riesgo se pagaban y se tiraban (`CIFRA_EN_TEXTO`) | Cerrado en fase 1 |
| 6 | 6 de 11 compras aprobadas se rechazaron en la apertura (`ABOVE_MAX_ENTRY`) | Abierto: fase 3 |
| 7 | No se podía saber si ganaba: equity a coste, sin referencia ni caída máxima | Cerrado en fase 0 |
| 8 | Paper sin comisión ni deslizamiento | Estimado en fase 0 (no en la contabilidad) |
| 9 | Stop congelado y sin toma de beneficios: `target1`/`target2` solo se usan en el gate de entrada | Abierto: fase 3 |
| 10 | El dashboard mostraba el precio en USD de los fills como EUR | Cerrado en fase 0 |

## Fase 0 — Poder medir · HECHA (código), pendiente de desplegar

- **Valor a mercado por pasada** (`ia_valoracion`, `superbot/ia/medicion.py`): cada posición al
  último cierre de su plaza y con el cambio de esa sesión. La contabilidad a coste no cambia.
- **Referencia**: los mismos flujos de capital invertidos en `EUNL.DE` al primer cierre
  posterior a cada flujo, con los mismos costes supuestos.
- **Costes estimados**: 1 € por orden y 0,10 % de deslizamiento por lado. Son supuestos, no
  medidas; se restan en la «equity neta» junto al gasto real de API, no en el efectivo.
- **Rentabilidad ponderada por tiempo y caída máxima**, para que una aportación no parezca ganancia.
- **Dashboard**: sección «Medición a mercado» y valor, resultado y cierre usado por posición.

Primera foto real (copia de la base de producción, 2026-11-12 09:09 UTC): equity a mercado
4.986,26 € (−0,27 %); neta de costes 4.975,42 € (−0,49 %); `EUNL.DE` +0,04 %. Cuatro sesiones
no dicen nada todavía: sirve para comprobar que el instrumento mide.

Límites conocidos:
- yfinance sirve algunos valores europeos con retraso: en esa foto las posiciones iban al cierre
  del 11 y `EUNL.DE` al del 10. El dashboard enseña el cierre usado en cada lado.
- Una pasada sin análisis o sin cambio de una posición la cuenta a su coste y lo declara.

**Contrafactual de los descartes — AUTORIZADO y HECHO el 2026-11-12** (`superbot/ia/contrafactual.py`). Es la prueba
que dice si la IA aporta algo: comparar qué hicieron después las candidatas que aprobó frente a
las que descartó (51 descartes y 11 aprobadas registrados ese día, con sus niveles). Enseña
desenlaces de candidatas del Score v1 que el bot no compró, un canal lateral más ancho que el
que D-81 aceptó para T-025; el propietario lo acepta expresamente (D-82 §7). Las sesiones ya
estaban `CONSUMIDA` desde `SIA_T0`, así que el coste adicional es para la ceguera de T-025.

Cada decisión de compra se sigue como si se hubiera comprado en la apertura de su sesión
objetivo, con el mismo gate y el mismo stop que la cartera y los niveles congelados al decidir, y
se cierra por stop o a las 20 sesiones. Comprobado contra la realidad: reproduce las 11 órdenes
reales (5 ejecutadas, 6 rechazadas por `ABOVE_MAX_ENTRY`) con sus precios de entrada.

Primera lectura (copia de producción, 2026-11-12, posiciones de 1 a 2 sesiones de vida): las 5
aprobadas ejecutables van −0,61 % de media; las 18 descartadas ejecutables, +0,96 %. **No
demuestra nada todavía**: muestra mínima, periodos solapados y valores repetidos. Sí deja un
dato firme: el gate de apertura deja fuera a más de la mitad en los dos grupos (6 de 11 y 21 de
39), así que el hallazgo 6 pesa tanto como el criterio de la IA.

Qué mirar cuando haya muestra (antes de leerlo, fijar el criterio en la fase 4): diferencia de
retorno medio y de R medio entre grupos, por valores distintos y no por decisiones.

## Fase 1 — Que la IA quepa en el presupuesto · HECHA en parte

Hecho, sin cambiar ninguna resolución del comité:
- **Riesgo solo cuando puede cambiar el resultado.** En compra se consulta a oportunidad y, solo
  si vota `COMPRAR`, a riesgo. En las 62 decisiones reales riesgo no vetó ninguna compra aprobada
  por oportunidad; 51 de sus consultas no podían cambiar nada.
- **Validador**: nombrar un valor del paquete con dígitos (`MUV2.DE`) ya no invalida el dictamen.
  Las 8 respuestas rechazadas validan; las otras 136 reales no cambian.
- Gasto esperado: de ~20 €/mes a ~10 €/mes. Se confirma con las primeras sesiones tras desplegar.

Corrección al plan inicial: «una pasada de decisión por plaza y día» ya era así. La clave de
decisión (`valor|sesión señal|sesión objetivo`) impide volver a preguntar en la misma sesión; lo
que se repite es el mismo valor en sesiones consecutivas.

Decidido y pendiente:
- **Espera tras un descarte**: DESCARTADA por ahora (propietario, 2026-11-12). Ahorraría
  llamadas, pero cambia operaciones: `MUV2.DE` y `RACE.MI`, dos de las cinco posiciones de ese
  día, se compraron al día siguiente de un descarte. Se reabre con el contrafactual en la mano.
- **Batch API** (−50 %): encaja porque se decide horas antes de la apertura, pero convierte la
  pasada en dos pasos (enviar y recoger) y toca el contrato causal. Con ~10 €/mes ahorra ~5.
- **Modelo más barato como primer filtro**: cambia la calidad del dictamen; solo con el
  contrafactual en la mano se puede saber si se pierde algo.

## Fase 2 — Dar a la IA información que el Score no tiene · NO AUTORIZADA

La única vía realista de ventaja: resultados empresariales, noticias fechadas y calendario de
eventos, todo point-in-time y con reglas antes que IA. Base aprovechable: `trader-news`
corregido (240 pruebas). Bloqueada por la Línea B (D-81 §7): necesita decisión propia.
No se puede backtestear —el modelo recuerda el pasado—: solo vale la validación hacia delante.

## Fase 3 — Entradas y salidas · PENDIENTE

Determinista, así que sí se puede backtestear sobre la cosecha congelada, siempre en 2 y 5 años:
- Orden limitada durante la sesión en vez del gate de solo apertura (hallazgo 6).
- Stop dinámico, salida parcial en `target1` y salida por tiempo (hallazgo 9).

## Fase 4 — Validación con criterio escrito antes de mirar · PENDIENTE

- Mínimo 100 operaciones cerradas o 6 meses.
- Supera la prueba solo si la rentabilidad neta bate a `EUNL.DE` con caída máxima acotada; el
  umbral exacto se escribe aquí antes de la primera lectura.
- Si no la supera, se retira y el capital va al fondo.

## Fase 5 — Capital real, pequeño y escalonado · PENDIENTE

Solo si pasa la fase 4. Trade Republic no tiene API oficial: o ejecución manual desde los avisos
de Telegram, o un bróker con API. Con 5.000 € los costes fijos pesan: decidir antes el capital.

## Registro de avances

| Fecha | Qué |
|---|---|
| 2026-11-12 | Revisión inicial y plan. Fase 0 y parte de la fase 1 implementadas (D-82): 400 pruebas de `superbot/ia` y 2.098 de toda la batería antes de la revisión, comprobado con una copia de la base de producción y datos reales |
| 2026-11-12 | Contrafactual de aprobadas frente a descartadas construido (D-82 §7), verificado contra las 11 órdenes reales |
| 2026-11-12 | Revisión independiente: sin críticos ni importantes; 4 menores corregidos con prueba (foto partida por una aportación simultánea, referencia que caducaba a los 2 años, `migrar-politica` que creaba tablas en una base ajena, «cierre usado» inventado en posiciones a coste). Pendiente la revisión cruzada de Codex antes de fusionar |
