# T-016 — Auditoría retrospectiva del centinela `(0.0, 1.0)`

Ejecutado el 2026-09-18 sobre `main` `6902d3d`, cosecha
`071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841`,
universo vigente `c8496446…` (103 analizables tras D-31).

```bash
python -m advisor.main capacidad-estadistica <vintage completo> --horizonte swing
python -m advisor.main capacidad-estadistica <vintage completo> --horizonte medio
```

## La pregunta

`bootstrap_block_mean_interval` devuelve el centinela `(0.0, 1.0)` cuando hay
menos de dos bloques. En T-009 se vio publicado como intervalo de confianza en
`filtro-ejecucion`. `capacity.py` llama a la misma función y es quien emite el
veredicto de P2.5, del que depende GATE P2. **¿Cuántas celdas de ese veredicto
lo llevaban?**

## La respuesta: cero

| Horizonte | Celda | Bloques | Intervalo publicado |
|---|---|---:|---|
| swing | global | 21 | [0.344, 0.443] |
| swing | <50 | 21 | [0.362, 0.456] |
| swing | 50-60 | 21 | [0.310, 0.425] |
| swing | 60-70 | 20 | [0.341, 0.461] |
| swing | 70-80 | 20 | [0.301, 0.470] |
| swing | 80+ | 16 | [0.420, 0.661] |
| medio | global | 5 | [0.363, 0.475] |
| medio | <50 | 5 | [0.371, 0.499] |
| medio | 50-60 | 5 | [0.341, 0.456] |
| medio | 60-70 | 5 | [0.394, 0.468] |
| medio | 70-80 | 5 | [0.186, 0.498] |
| medio | 80+ | **4** | [0.363, 0.606] |

**El mínimo de todo el veredicto son 4 bloques**, y el centinela solo salta por
debajo de 2. Ninguna celda lo publicó, y ninguna quedó cerca.

La conclusión es robusta frente al cambio de universo de D-31: el número de
bloques depende de la **ventana temporal** y de `block_length` (60 sesiones en
swing, 300 en medio), no de cuántos activos haya. Pasar de 107 a 103 cambia el
número de señales por celda, no el de bloques.

## Qué implica

1. **GATE P2 no arrastra ningún resultado inválido por esta causa.** El
   veredicto de P2.5 —swing LIMITADA, medio INSUFICIENTE, y «no se permite
   calibrar un threshold apoyándose en 80+»— se apoya en intervalos calculados
   de verdad.
2. **T-016 deja de ser previa a A-02.** Se escribió con esa condición cuando el
   alcance era desconocido; medido, es higiene: la función sigue pudiendo
   fabricar un valor y hay que arreglarla, pero no bloquea nada.
3. **El único consumidor que lo publicó fue `filtro-ejecucion`**, y ya se
   corrigió en T-009 (tramo 80+ → `SIN INTERVALO`).

Y una razón de fondo por la que capacidad no cayó donde sí cayó
`filtro-ejecucion`: capacidad agrupa por bloques de 60 o 300 sesiones sobre
toda la ventana, mientras que `filtro-ejecucion` reparte además por población
(`EJECUTADAS` / `PERDIDAS`), y esa segunda partición deja tramos pequeños
concentrados en pocas fechas.

## Hallazgo de paso (OBSERVATION)

`capacidad-estadistica` exige el `data_vintage_id` **completo** y como
argumento posicional; `filtro-ejecucion`, creado en T-009, acepta el prefijo
`071ddb2b` con `--vintage`. Dos comandos del mismo laboratorio con dos
convenciones. No es un defecto, pero cuesta un intento cada vez. Recogido en
T-016 como parte de su limpieza.
