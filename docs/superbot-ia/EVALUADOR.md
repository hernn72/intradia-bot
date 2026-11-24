# Superbot IA — evaluador final del contrafactual (D-87)

**SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL.**
_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Implementa `CRITERIO-CONTRAFACTUAL.md`, que manda y no cambia. Código: `superbot_lab/{evaluador,evaluacion,evaluar}.py`,
que producción no importa. **No se ha ejecutado sobre resultados reales y hoy se niega a hacerlo**: falta
`AUTORIZACION-EVALUACION.json`, que solo se escribe cuando el propietario autorice la evaluación.

## 1. Procedimiento

1. `madurez` avisa de que toca. Se copia la base de la Pi tras una pasada `OK` y sin `-wal`. **T** es el
   instante de la última pasada de esa copia: no lo elige nadie.
2. A partir del día siguiente a T, `congelar` descarga `EUNL.DE`, los pares y los valores hasta el día de T. Solo
   mira decisiones y si la apertura fue ejecutable.
3. `identidades` da lo que la autorización debe llevar: criterio, código, base, T y entorno. Se añaden `cosecha`,
   `autoriza: true` y, si hace falta, `series_ausentes`. El propietario la ratifica y se comitea.
4. `puertas` comprueba; `evaluar` ejecuta una vez y escribe `evidence/superbot-ia/contrafactual/`.

Todos: `python -m superbot_lab.evaluar --db COPIA --cosecha-raiz DIR <orden>`, desde la raíz del repositorio.

## 2. Qué impide mirar antes

Puertas, en orden: autorización idéntica a `HEAD` y coincidente; sin apertura ni resultado previos; git limpio;
congelación intacta, toca evaluar y los episodios cuadran con `madurez`; 30 por grupo. La base se abre en solo
lectura por fases: en la 0 no se lee la tabla sellada; en la 1, solo estado y validez; en la 2, todo, y solo
después de escribir `apertura.json`. Si algo falla tras abrir, no hay segunda ejecución.

Es una defensa contra errores, **no una barrera**: quien edite el código o abra la base a mano puede leerla, y un
segundo clon permitiría repetir el cálculo, con idéntico resultado.

## 3. Interpretaciones que el criterio no fijaba (pendientes de ratificar)

| Asunto | Lo implementado |
|---|---|
| Percentil | Rango más cercano: posiciones ⌊0,025 n⌋ y ⌈0,975 n⌉−1 de las réplicas válidas |
| Coste de API | Todas las llamadas de compra desde el corte hasta T; constante en las réplicas |
| `INCONCLUSO` por muestra, datos o bloques | No lee rendimientos: no publica medias ni carteras (§6 las pide «junto al resultado») |
| Sin entrada tras 20 sesiones | Cuenta como dato no válido de su grupo, en el 5 % |
| Apertura que el proveedor corrige después | Si la entrada constó y luego el estado es `NO_EJECUTABLE`: dato no válido, en el 5 % |
| `EUNL.DE` | Solo barras de sesiones oficiales de Xetra; una barra en festivo se ignora |
| Carteras | Tamaño con 5.000 EUR fijos; efectivo de una salida, disponible al día siguiente; abiertas, a mercado |
| Serie de un valor ausente o que empieza tarde | Solo si se lista en la autorización, y no se admite listar uno que sí tiene datos; se omite en las dos carteras y no toca la métrica |
| Carteras o §7 fallan | Se publica el error y el veredicto sale igual |

## 4. Decisiones del propietario, antes de que haya casos maduros

**4.1 Valor que deja de cotizar con el episodio abierto.** Nunca completa sus 20 sesiones, queda `ABIERTA` y hoy
**bloquea la evaluación sin salida**. El criterio no lo prevé y el evaluador no lo inventa. Opción propuesta:
pasadas 25 sesiones de calendario sin completarse, `DATOS_INCOMPLETOS` y al 5 %.

**4.2 El intervalo es demasiado estrecho con 6 o 7 bloques.** Con datos inventados (50 por grupo, dispersión
supuesta del 7 %, 1.500 repeticiones, sin efecto real), conclusiones falsas sumando las dos:

| Intervalo | 6 bloques | 7 bloques | Detecta +2 / +4 / +6 puntos (6 bloques) |
|---|---|---|---|
| Percentil (criterio actual) | 12–14 % | 12–14 % | 41 / 86 / 99 % |
| t con los mismos bloques (jackknife, K−1 grados) | 5–6 % | 4–6 % | 22 / 61 / 92 % |

El 95 % nominal equivale a un 87 %. El t lo corrige perdiendo potencia: más `INCONCLUSO`. Calibración en
`evidence/superbot-ia/calibracion-evaluador/`. En 47 evaluaciones sintéticas completas sin efecto real, con
entradas repartidas en pocos bloques desiguales, 14 (30 %) concluyeron algo falso: puede ser peor. Hoy el código aplica el criterio tal como está.

## 5. Límites

Revisado con 55 ejecuciones de punta a punta que usan el `contrafactual.actualizar` de producción y un proveedor
defectuoso (huecos, NaN, aperturas revisadas, splits, apagones): ningún fallo tras abrir, y en las 29 con
estimador de la última tanda coincide con un cálculo aparte. Aun así es sintético: no prueba que los datos reales lleguen completos. Los festivos dependen de `exchange_calendars`, cuya
versión se fija en la autorización. La métrica usa los desenlaces que guardó el bot, no los recalcula.
