# Rejilla, ausencias y semiplanos (D-66)

_condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)_

`grid_sha256 = d29e37cf2700672b204665d9a34682d289c0e24a5cae86c956f56a0a5f56f66c`

| Celda | Centro | Rol | s | targets | m3_auxiliar | Motivo |
|---|---|---|---|---|---|---|
| C0 | C0 | CONTROL | 2.0 | [1.5, 3.0, 5.0] | False |  |
| B2_s1p75_m24p500 | B2 | DIAGNOSTIC_NEIGHBOR | 1.75 | [1.5, 4.5, 5.0] | False |  |
| B2_s1p75_m24p875 | B2 | DIAGNOSTIC_NEIGHBOR | 1.75 | [1.5, 4.875, 5.0] | False |  |
| B2_s1p75_m25p250 | B2 | DIAGNOSTIC_NEIGHBOR | 1.75 | [1.5, 5.25, 5.625] | True |  |
| B2_s2p00_m24p500 | B2 | DIAGNOSTIC_NEIGHBOR | 2.0 | [1.5, 4.5, 5.0] | False |  |
| B2 | B2 | CENTER_CANDIDATE | 2.0 | [1.5, 4.875, 5.0] | False |  |
| B2_s2p00_m25p250 | B2 | DIAGNOSTIC_NEIGHBOR | 2.0 | [1.5, 5.25, 5.625] | True |  |
| B2_s2p25_m24p500 | B2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 4.5, 5.0] | False |  |
| B2_s2p25_m24p875 | B2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 4.875, 5.0] | False |  |
| B2_s2p25_m25p250 | B2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 5.25, 5.625] | True |  |
| S2_s2p25_m23p375 | S2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 3.375, 5.0] | False |  |
| S2_s2p25_m23p750 | S2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 3.75, 5.0] | False |  |
| S2_s2p25_m24p125 | S2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 4.125, 5.0] | False |  |
| S2_s2p50_m23p375 | S2 | STRUCTURAL_ABSENCE | 2.5 | [1.5, 3.375, 5.0] | False | RR < 1.5 |
| S2 | S2 | CENTER_CANDIDATE | 2.5 | [1.5, 3.75, 5.0] | False |  |
| S2_s2p50_m24p125 | S2 | DIAGNOSTIC_NEIGHBOR | 2.5 | [1.5, 4.125, 5.0] | False |  |
| S2_s2p75_m23p375 | S2 | STRUCTURAL_ABSENCE | 2.75 | [1.5, 3.375, 5.0] | False | RR < 1.5 |
| S2_s2p75_m23p750 | S2 | STRUCTURAL_ABSENCE | 2.75 | [1.5, 3.75, 5.0] | False | RR < 1.5 |
| S2_s2p75_m24p125 | S2 | DIAGNOSTIC_NEIGHBOR | 2.75 | [1.5, 4.125, 5.0] | False |  |

## Semiplanos

- B2 `s_minus`: B2_s1p75_m24p500, B2_s1p75_m24p875, B2_s1p75_m25p250
- B2 `s_plus`: B2_s2p25_m24p500, B2_s2p25_m24p875, B2_s2p25_m25p250
- B2 `m2_minus`: B2_s1p75_m24p500, B2_s2p00_m24p500, B2_s2p25_m24p500
- B2 `m2_plus`: B2_s1p75_m25p250, B2_s2p00_m25p250, B2_s2p25_m25p250
- S2 `s_minus`: S2_s2p25_m23p375, S2_s2p25_m23p750, S2_s2p25_m24p125
- S2 `s_plus`: S2_s2p75_m24p125
- S2 `m2_minus`: S2_s2p25_m23p375
- S2 `m2_plus`: S2_s2p25_m24p125, S2_s2p50_m24p125, S2_s2p75_m24p125

## LOCRO estructural (sin desenlaces)

- sin USA: población 56353, pares mínimos 50718
- sin EUROPA: población 66629, pares mínimos 59967
- sin ASIA: población 83298, pares mínimos 74969
