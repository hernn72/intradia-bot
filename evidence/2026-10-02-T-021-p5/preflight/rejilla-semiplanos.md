# Rejilla, ausencias y semiplanos (D-66)

_condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)_

`grid_sha256 = d29e37cf2700672b204665d9a34682d289c0e24a5cae86c956f56a0a5f56f66c`

| Celda | Centro | Rol | s | targets | m3_auxiliar | Motivo | levels_sha256 |
|---|---|---|---|---|---|---|---|
| C0 | C0 | CONTROL | 2.0 | [1.5, 3.0, 5.0] | False |  | `e07a33a9a713c6b3662baa615c718ba2621a9070e736c84d4fb5458f32b79f75` |
| B2_s1p75_m24p500 | B2 | DIAGNOSTIC_NEIGHBOR | 1.75 | [1.5, 4.5, 5.0] | False |  | `e95992e4b9fe03eab307eb10abd59997e90256d722bbeaee499e14003235415a` |
| B2_s1p75_m24p875 | B2 | DIAGNOSTIC_NEIGHBOR | 1.75 | [1.5, 4.875, 5.0] | False |  | `a4aad26815adb32d379a24dc07ac9d3d3155da2b080f986a7b545b5de9800d57` |
| B2_s1p75_m25p250 | B2 | DIAGNOSTIC_NEIGHBOR | 1.75 | [1.5, 5.25, 5.625] | True |  | `40c0c063cbca8a36fece63a2d9a880f8a5871fc75a516bce41a0a07de7a47385` |
| B2_s2p00_m24p500 | B2 | DIAGNOSTIC_NEIGHBOR | 2.0 | [1.5, 4.5, 5.0] | False |  | `ceaede3bfa9a31eea3c10dad1d1bcec9a3519d39e087e24628b253f08233f1ee` |
| B2 | B2 | CENTER_CANDIDATE | 2.0 | [1.5, 4.875, 5.0] | False |  | `f18694c316c0ad6d94ac566107db52bde0b7335a72a1206d2b49e731b54fbd02` |
| B2_s2p00_m25p250 | B2 | DIAGNOSTIC_NEIGHBOR | 2.0 | [1.5, 5.25, 5.625] | True |  | `23f4f0614abbc6e9ac0822b6309cceb71846d43d16d0ac56ef2b96cfc8c6bff1` |
| B2_s2p25_m24p500 | B2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 4.5, 5.0] | False |  | `e9102b97f60ad9f79a64f4e8120d850004cabe90faac9a99c03aba7748052f32` |
| B2_s2p25_m24p875 | B2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 4.875, 5.0] | False |  | `e254d8d3ad057e0badb6b6fe3cfb95c1d9d97041c28c604e200c00cc9d673b5d` |
| B2_s2p25_m25p250 | B2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 5.25, 5.625] | True |  | `67d2dfccd7647a3de64a2820e074aac78da8f62eba4f20c6494d741f2e3bdadd` |
| S2_s2p25_m23p375 | S2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 3.375, 5.0] | False |  | `9e968204a84dfa7e73c6cc0fc2de9c5bf14b7da712812ab67fd65888bf7efe07` |
| S2_s2p25_m23p750 | S2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 3.75, 5.0] | False |  | `a8ac35467ffd453a5f66b0127c26e7e7e597271cd2ce1ce7af4b315ac32f77bb` |
| S2_s2p25_m24p125 | S2 | DIAGNOSTIC_NEIGHBOR | 2.25 | [1.5, 4.125, 5.0] | False |  | `f18576e83cd1d2aabbe1f91d733ebe30251f3b3ea3e663a799e302bb9feeee35` |
| S2_s2p50_m23p375 | S2 | STRUCTURAL_ABSENCE | 2.5 | [1.5, 3.375, 5.0] | False | RR < 1.5 | — |
| S2 | S2 | CENTER_CANDIDATE | 2.5 | [1.5, 3.75, 5.0] | False |  | `8c3b3e0a81274a9cb4c9b8c2c33a9b763f769a5b16079db64079121dd4016a8c` |
| S2_s2p50_m24p125 | S2 | DIAGNOSTIC_NEIGHBOR | 2.5 | [1.5, 4.125, 5.0] | False |  | `8fc7fac47695c6136ae0a2f9821fd7d20634c0fc4bda2a9bb3b8e8febfcaff98` |
| S2_s2p75_m23p375 | S2 | STRUCTURAL_ABSENCE | 2.75 | [1.5, 3.375, 5.0] | False | RR < 1.5 | — |
| S2_s2p75_m23p750 | S2 | STRUCTURAL_ABSENCE | 2.75 | [1.5, 3.75, 5.0] | False | RR < 1.5 | — |
| S2_s2p75_m24p125 | S2 | DIAGNOSTIC_NEIGHBOR | 2.75 | [1.5, 4.125, 5.0] | False |  | `bd361a1499ed368807356f5dc3b02d73a4e9a0b49b55d6254ad906fbfdd660ac` |

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
