# Declaracion de sesgo del universo — copia literal para GATE P2 requisito 3

GATE P2 requisito 3 exige el `universe_vintage_id` calculado y registrado
"con la declaracion de sesgo de la seccion «Universo» de \`docs/roadmap.md\`
copiada en la evidencia". Esto es esa copia, literal y sin editar.

Fuente: `docs/roadmap.md`, lineas 121-170, en el commit de esta entrega.
El roadmap NO se ha modificado para producir esta copia.

---

## Universo: sesgo de supervivencia y de selección

**Hecho.** Los 107 analizables se eligieron el 2026-08-27 y 2026-08-29 con
conocimiento de 2026 (tamaño, liquidez, notoriedad, presencia en Trade
Republic) y se miden desde 2021. Ninguno ha sido excluido de cotización;
`ARM`, `DFEN.DE`, `Q8Y0.DE` son jóvenes. No hay fuente gratuita de
constituyentes históricos ni de exclusiones.

**Identidad del universo (A-00, D-23).** El vintage vigente es
`c8496446d9b04795b8533e25e794c6141a4e73db73c0ef9bf98599b70f952132` (D-31,
2026-09-18: 103 analizables tras cuatro bajas por no estar en el broker; el
anterior, `894ce776…`, era el de los 107), y **se mueve con cada cambio de la lista**, porque el `instrument_id` de un activo pasa de
`SYMBOL@MARKET` a su ISIN en cuanto se verifica. Todo resultado publicado debe
llevar el vintage con el que se calculó; las pasadas anteriores al 2026-09-17
llevan el id provisional `80d05f21…`, que era solo la lista de símbolos.

`added_at` se derivó comparando las tres versiones de `universe.yaml`: **20
activos del 2026-08-27 y 106 del 2026-08-29**. Los ocho listados alemanes del
universo inicial que pasaron a su símbolo primario (`APC.DE` → `AAPL` y
compañía) son **instrumentos distintos**, no renombrados, porque cambian plaza,
calendario, divisa y fuente de barras. Consecuencia vinculante: **ningún
resultado sobre `AAPL` y los otros siete puede reclamar antigüedad del 27 de
agosto**, aunque su emisor ya estuviera considerado.

**Sesgos presentes, por orden de gravedad:**

| Sesgo | Efecto sobre la medición |
|---|---|
| Supervivencia | Solo activos que llegaron a 2026: la tasa de desplomes y quiebras está subestimada; la expectancy larga, sobreestimada |
| Selección con información futura | Elegidos por ser grandes/fuertes en 2026: deriva alcista media superior a la del mercado en el periodo |
| Conocimiento futuro en benchmarks | `benchmark` por activo elegido en 2026. Solo 2 de los 107 lo declaran; los otros 105 lo heredan de `config.yaml`, que el vintage **no** hashea: ese lado lo pinea `config_hash` en el manifiesto |
| Selección por disponibilidad en el broker | Desde el 2026-09-17, 10 activos están marcados no disponibles y quedan vetados. El universo **analizado** no cambia, pero el **ejecutable** sí, y no es el mismo con el que se midió el pasado |

**Qué se puede afirmar y qué no** (regla vinculante hasta P10):

| Afirmación | Permitida | Condición |
|---|---|---|
| «La política B mejora a la A en ΔR por bloque» (P4, P2.6, pareado por `signal_id`) | Sí | Ambas medidas sobre las mismas señales: el sesgo afecta a las dos por igual. Etiqueta: «condicionado al universo 2026» |
| «El score ordena entre bandas» (P3) | Sí, con cautela | Las dimensiones de momento correlacionan con lo que hizo sobrevivir a estos activos; publicar también la ordenación **dentro** de cada activo (por bloques temporales), que el sesgo de selección no infla |
| «Expectancy neta X R, CAGR Y %, drawdown Z %» (P6, P7) | Solo con etiqueta | «Fuera de muestra en el tiempo, condicionado al universo seleccionado en 2026; cota optimista». Publicar siempre el exceso sobre el buy-and-hold del propio universo en la misma ventana |
| «El sistema tiene ventaja» (general) | **No** | Solo tras P10 |

**Mecanismo:** `universe_vintage_id` (T-006) en cada manifiesto y resultado;
cualquier cambio en la lista → vintage nuevo + entrada en el decision log
(INV-19); campos `added_at`, `valid_to`, `delisted_at`, `ticker_history`
presentes desde ya, vacíos hasta que haga falta. Si aparece una fuente de
constituyentes históricos, se abre A-08 y P7 se repite.

---

