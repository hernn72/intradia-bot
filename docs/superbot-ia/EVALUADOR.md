# Superbot IA — evaluador final del contrafactual (D-87, D-88)

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Implementa `CRITERIO-CONTRAFACTUAL.md` con su §9 (D-88), que manda. Código: `superbot_lab/{evaluador,evaluacion,evaluar}.py`,
que producción no importa. **No se ha ejecutado sobre resultados reales y hoy se niega a hacerlo**: falta
`AUTORIZACION-EVALUACION.json`, que solo se escribe cuando el propietario autorice la evaluación.

## 1. Procedimiento

1. `madurez` avisa de que toca. Se copia la base de la Pi tras una pasada `OK` y sin `-wal`. **T** es el
   instante de la última pasada de esa copia: no lo elige nadie.
2. A partir del día siguiente a T, `congelar` descarga `EUNL.DE`, los pares y los valores hasta el día de T. Solo
   mira decisiones y si la apertura fue ejecutable.
3. `identidades` da lo que la autorización debe llevar: criterio, código, base, T y entorno. Se añaden `cosecha`,
   `autoriza: true` y, si `congelar` los señala, `series_ausentes` y `referencia_ausente` (valor o sesión, y justificación) y `episodios_truncados`
   (`decision_id`, `tipo`, `justificacion`, `fuente`; con `EXCLUSION`, además `sesion_salida`, `precio_entrada` y
   `precio_salida`). El propietario la ratifica y se comitea.
4. `puertas` comprueba; `evaluar` ejecuta una vez y escribe `evidence/superbot-ia/contrafactual/`.

Todos: `python -m superbot_lab.evaluar --db COPIA --cosecha-raiz DIR <orden>`, desde la raíz del repositorio.

## 2. Qué impide mirar antes

Puertas, en orden: autorización idéntica a `HEAD` y coincidente; sin apertura ni resultado previos; git limpio;
congelación intacta, toca evaluar y los episodios cuadran con `madurez`; 30 por grupo. La base se abre en solo
lectura por fases: en la 0 no se lee la tabla sellada; en la 1, solo estado, fecha y validez, que se contrastan con la cosecha sin calcular rendimientos; en la 2, todo, y solo
después de escribir `apertura.json`. Si algo falla tras abrir, no hay segunda ejecución.

Es una defensa contra errores, **no una barrera**: quien edite el código o abra la base a mano puede leerla, y un
segundo clon permitiría repetir el cálculo, con idéntico resultado.

## 3. Interpretaciones ratificadas (D-88)

| Asunto | Aplicado |
|---|---|
| Intervalo | t con jackknife por bloques; el percentil queda retirado |
| Coste de API | Todas las llamadas de compra desde el corte hasta T; constante al quitar bloques |
| `INCONCLUSO` por muestra, datos o bloques | No lee rendimientos ni publica medias o carteras |
| Sin entrada tras 20 sesiones | Dato inválido solo si falta por los datos; si el gate habría rechazado la apertura de la cosecha, no |
| Apertura que el proveedor invalida o retira después | Dato inválido, sea cual sea su desenlace: se decide con la cosecha |
| `EUNL.DE` y divisas | Solo barras de sesiones oficiales de Xetra; sesiones repetidas o dos cambios distintos en un día, denegado; un cambio fuera de 0,001–100.000 por euro cuenta como que falta |
| Carteras | Tamaño con 5.000 EUR fijos; efectivo de una salida, disponible al día siguiente; abiertas, a mercado |
| Serie ausente, que empieza tarde o con sesiones repetidas | Solo si se identifica y justifica; se omite en las dos carteras y no se admite listar una que está |
| Desenlace con huecos | `sesiones` y `hasta_session` guardadas deben cuadrar con el calendario; si no, dato inválido y fuera de carteras |
| Entrada de una exclusión | La guardada; se publica en `entradas_de_exclusiones` |
| Un caso sin desenlace utilizable, también el que sigue abierto pasadas 20 sesiones | Se omite en las dos carteras y se publica su identificador |
| Fallo de carteras o §7 | Se publica y el veredicto sale igual, salvo que toque divisa o referencia: `INCONCLUSO` |

Detalles fijados al implementar D-88: K cuenta bloques con casos utilizables; mínimos de 4 bloques y 3 por grupo,
por calibración; 25 sesiones contando la de entrada; una declaración es obligatoria para todo valor truncado, haya
saltado o no su stop, para que la lista no revele nada.

## 4. Calibración del intervalo (datos inventados, 50 por grupo, dispersión supuesta del 7 %)

| Intervalo | Conclusiones falsas, 6–7 bloques | Detecta +2 / +4 / +6 puntos (6 bloques) |
|---|---|---|
| Percentil (retirado) | 12–14 % | 41 / 86 / 99 % |
| t con jackknife | 4–6 % | 22 / 63 / 92 % |

Con 4 o 5 bloques, repartos desiguales, colas pesadas o un bloque que concentra la mitad de un grupo, el t sigue en
3–6 %. Con un grupo en solo 2 bloques sube al 6–7 %: por eso se exigen 3. **Con dependencia fuerte entre
bloques contiguos sube al 9–14 %**: es el límite principal.

## 5. Límites

Revisado con ejecuciones de punta a punta que usan el `contrafactual.actualizar` de producción y un proveedor defectuoso
(huecos, NaN, aperturas revisadas, splits, apagones, exclusiones): ningún fallo tras abrir y todos los estimadores
coinciden con un cálculo aparte. Con el intervalo actual, 8 conclusiones falsas en 85 (9 %, con exclusiones ruinosas añadidas al azar); con el percentil, 14 en 47 (30 %).
Aun así es sintético: no prueba que los datos reales lleguen completos. Los festivos dependen de `exchange_calendars`,
cuya versión se fija en la autorización. La métrica usa los precios que guardó el bot; la cosecha solo puede invalidar un desenlace, no cambiarlo. Queda una
exclusión que depende en parte del desenlace: un split o un hueco posteriores a un stop ya no lo afectan, y sí al que
seguía vivo. El precio de una exclusión lo aporta el propietario: el evaluador exige fuente y rango, no puede verificarlo.
Un stop guardado con huecos es dato inválido si se declara `SIN_DATOS` o el valor sigue cotizando, y manda si se declara `EXCLUSION`.
En las carteras, que no deciden, una posición sin cierre desde su compra se valora a su precio de entrada.
