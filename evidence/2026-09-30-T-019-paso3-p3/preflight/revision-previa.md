# Revisión independiente previa a la ejecución de P3

Revisor: agente `revisor` (Claude), independiente del autor del ejecutor. Trabajó en solo
lectura, **sin leer ni calcular desenlaces reales** y sin ejecutar la fase confirmatoria sobre la
cosecha; sus scripts sobre la cosecha usaron `with_outcomes=False` o evaluadores sustituidos.

## Primera vuelta: REQUIERE CAMBIOS (sin BLOCKER)

| # | Clase | Hallazgo | Corrección |
|---|---|---|---|
| I1 | IMPORTANTE | La opción global `--config` podía cambiar la geometría de niveles (y con ella los desenlaces) sin que el preflight lo detectara | Control `config_hash == 89406d28…` en el preflight |
| I2 | IMPORTANTE | El ruido de coma flotante en `score_sin_X` (218/3 → …666/…667) incumplía «igual al corte → banda superior»: movía 752/78/480 observaciones de swing en las ablaciones | Scores canonicalizados a 9 decimales (fórmula exacta) |
| M1 | MENOR | La confirmatoria podía repetirse cambiando `--salida` | Ruta fija `evidence/2026-09-30-T-019-paso3-p3/run`; la CLI rechaza `--salida` en esa fase |
| M2 | MENOR | Se analizaba swing antes de verificar la población de medio | Las dos poblaciones se verifican antes de cualquier análisis |
| M3 | MENOR | `p3-parada.json` sin identidad ni etiqueta | Añadidas |
| M4 | MENOR | 826 valores distintos publicados frente a 817 reales | Resuelto por la canonicalización |

## Segunda vuelta: APROBADO

Sin BLOCKER ni IMPORTANTE. El revisor verificó sobre la cosecha, sin desenlaces:
- con una configuración alterada, el preflight falla exactamente en `config_hash`;
- el redondeo a 9 decimales no fusiona valores distintos (separación mínima ≥ 0,0078) ni parte
  grupos (dispersión ≤ 3e-14);
- los cortes del score completo y sus n no cambian;
- la ruta fija y la marca impiden una segunda ejecución desde el mismo checkout.

Observaciones que no cambian nada:
- la marca solo protege el checkout donde existe, así que la regla de una sola ejecución sigue
  dependiendo también del procedimiento;
- el cuantil Bonferroni del instrumento existente es asimétrico por una muestra (índice 24 de
  20.000);
- los bloques sin ninguna de las dos bandas no se listan en el Δ.
