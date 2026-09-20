## Pregunta, métrica y criterio — PRE-REGISTRO
Se escribe antes de mirar los datos. Lo que se decida después de verlos se
etiqueta `exploratorio`.

- **Pregunta primaria:** ¿con qué frecuencia el dato que ve el asesor está
  retrasado o ausente, desglosado por plaza y por hora de pasada?
- **Métrica primaria:** para cada par (plaza, hora de pasada), el **porcentaje
  de mediciones con retraso ≥ 1 sesión**, con su intervalo de confianza y su
  denominador. El denominador se publica siempre: un 100 % sobre 4 mediciones
  no es lo mismo que sobre 400.
- **Métricas secundarias:** sesiones ausentes por activo y por mes (la cifra
  del umbral de OD-02); racha máxima de sesiones consecutivas ausentes por
  activo; porcentaje de barras parciales por activo (la cifra de OD-10);
  distribución por día de la semana (la sospecha del lunes); y cuántas
  ausencias coinciden con un `exchange_overrides.yaml` ya registrado —esas no
  son huecos, son cierres reales.
- **Población:** todas las mediciones persistidas en la Pi desde el
  2026-09-02 hasta la fecha de ejecución, los 107 analizables. Se declara el
  número exacto de pasadas y de mediciones.
- **Criterio de decisión de OD-02, fijado antes de medir:** el umbral ya
  propuesto —más de 2 sesiones perdidas por mes en más de 10 activos— se
  evalúa tal cual. Si sale por encima, OD-02 se reabre con la cifra; si sale
  por debajo, se cierra como «no procede por ahora» con la cifra. **Este
  informe no decide**: prepara la decisión.
- **Tratamiento de la incertidumbre:** intervalo binomial por celda. Una
  celda con menos de 30 mediciones se publica como insuficiente y **no** se
  agrega con otra para alcanzar el mínimo.
- **Sesgo conocido que hay que declarar:** el histórico empieza el
  2026-09-02, cubre pocas semanas y **no** incluye ningún periodo de
  vacaciones ni cierres largos. Cualquier tasa mensual extrapolada de aquí es
  provisional y se etiqueta como tal.

## Dependencias previas
