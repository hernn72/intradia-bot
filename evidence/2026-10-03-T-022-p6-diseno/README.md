# T-022 / A-06 — Diseño de P6: censo estructural sin desenlaces

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

- Base: `main = 0c144ba9ad672817bbff80011c61fb62587b0409` (GATE P5 cruzado).
- **P6 no se ha ejecutado.** No se ha simulado ninguna cartera ni calculado ninguna métrica de sistema
  de B2, S2, C0 o el buy-and-hold.
- `censo_p6.py` lee el universo vigente, la cosecha `071ddb2b…` (columnas, recuentos de dividendos y
  splits, fechas) y la lista de los 90 activos de P4/P5. **No convierte ningún precio en retorno.**
- `censo-p6.json`: resumen y una fila por activo con región, clase, plaza, zona, divisas, necesidad y
  disponibilidad de FX, sector (0/90), eventos de dividendo y de split, barras, primera y última
  fecha de sesión local (y marca UTC aparte), calentamiento y los hashes de la serie y de las acciones corporativas.

Resultados estructurales en la sección 4 de `docs/tareas/T-022-p6-sistema-completo.md`:
- FX: solo `EURUSD=X` en la cosecha; faltan `EURJPY=X` y `EURHKD=X` (9 activos);
- sector: 0/90;
- dividendos: 821 eventos en 64 activos, sin fecha de pago;
- splits: 17 eventos en 16 activos;
- ARM y Q8Y0.DE con historia tardía.

Reproducir, desde la raíz del repositorio: `python evidence/2026-10-03-T-022-p6-diseno/censo_p6.py`.
