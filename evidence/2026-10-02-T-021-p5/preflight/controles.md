# Controles del preflight

_condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)_

94/94 controles OK.

| Control | Observado | Esperado | OK |
|---|---|---|---|
| A-02 swing | 106363 | 106363 | sí |
| cripto excluido | 5112 | 5112 | sí |
| activos cripto | ["BTC-EUR", "ETH-EUR", "SOL-EUR"] | ["BTC-EUR", "ETH-EUR", "SOL-EUR"] | sí |
| población P4 | 101251 | 101251 | sí |
| activos | 90 | 90 | sí |
| (activo, sesión) únicos | 101251 | 101251 | sí |
| p4_population_sha256 | "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141" | "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141" | sí |
| signal_ids_sha256 | "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f" | "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f" | sí |
| regiones | {"ASIA": 17953, "EMERGING_MARKETS": 1151, "EUROPA": 34622, "GLOBAL": 2627, "USA": 44898} | {"ASIA": 17953, "EMERGING_MARKETS": 1151, "EUROPA": 34622, "GLOBAL": 2627, "USA": 44898} | sí |
| régimen PIT | {"CAUTELA": 12431, "NO_CALCULABLE_CONTEXT": 7157, "RISK_OFF": 7944, "RISK_ON": 73719} | {"CAUTELA": 12431, "NO_CALCULABLE_CONTEXT": 7157, "RISK_OFF": 7944, "RISK_ON": 73719} | sí |
| espina de sesiones | 1302 | 1302 | sí |
| bloques 40: ocupados | 30 | 30 | sí |
| bloques 40: más corto | 22 | 22 | sí |
| bloques 40: válida P2.5 | false | false | sí |
| bloques 60: ocupados | 20 | 20 | sí |
| bloques 60: más corto | 42 | 42 | sí |
| bloques 60: válida P2.5 | true | true | sí |
| bloques 80: ocupados | 16 | 16 | sí |
| bloques 80: más corto | 22 | 22 | sí |
| bloques 80: válida P2.5 | false | false | sí |
| bloques 120: ocupados | 10 | 10 | sí |
| bloques 120: más corto | 102 | 102 | sí |
| bloques 120: válida P2.5 | true | true | sí |
| bloques 60 = mitades 2–11 ∪ 12–21 | [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21] | [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21] | sí |
| data_vintage_id | "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841" | "071ddb2b2c43c28c36517fd55b4388cee00aac16d11d27a992e250e8af253841" | sí |
| universe_vintage_id | "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19" | "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19" | sí |
| population_sha256 | "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141" | "78024050f7081ad4e1dd5cefaefbfa1a1668ff5b1a2ced8c34e62b6501873141" | sí |
| signal_ids_sha256 | "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f" | "9faa4a45beaba3eb8dafabf7990906cd8c89e8e06ae2f25edec7839cd48e629f" | sí |
| config_hash | "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387" | "89406d28c7b4b6e6c4f032cd63b6868c927af3e926dfb52d430dfa6654d06387" | sí |
| score_model_version | "1.0" | "1.0" | sí |
| P5_PREREG_SHA en la historia | true | true | sí |
| C0 levels_config igual a config.levels | {"atr_stop_multiple": 2.0, "entry_max_atr": 0.75, "entry_pullback_atr": 0.5, "lookback_… | {"atr_stop_multiple": 2.0, "entry_max_atr": 0.75, "entry_pullback_atr": 0.5, "lookback_… | sí |
| C0 min_rr igual a config.risk.min_rr_ratio | 1.5 | 1.5 | sí |
| recuento P5 | 71 | 71 | sí |
| confirmatorias nuevas | 0 | 0 | sí |
| LOCRO sin USA | 56353 | 56353 | sí |
| LOCRO sin EUROPA | 66629 | 66629 | sí |
| LOCRO sin ASIA | 83298 | 83298 | sí |
| regiones LOCRO exactas | ["USA", "EUROPA", "ASIA"] | ["USA", "EUROPA", "ASIA"] | sí |
| vecinos válidos B2 completos | 8 | 8 | sí |
| vecinos válidos S2 completos | 5 | 5 | sí |
| ausencias estructurales (solo S2) | [3, 3] | [3, 3] | sí |
| sha256 evidence/2026-10-01-T-020-p4/run/tablas/criterio.tsv | "be1f94e54a70e4bffaa686a7be42a4832799da40fb4410132bff6708e246a596" | "be1f94e54a70e4bffaa686a7be42a4832799da40fb4410132bff6708e246a596" | sí |
| sha256 evidence/2026-10-01-T-020-p4/run/tablas/estimaciones.tsv | "dd178515bddb759b4045fa694060e234c86b75873605e74ff681778dddc7ad60" | "dd178515bddb759b4045fa694060e234c86b75873605e74ff681778dddc7ad60" | sí |
| sha256 evidence/2026-10-01-T-020-p4/run/tablas/nivel.tsv | "1d6d7e862dc5870107460316d4c68806e8bc6e2228114a6df74ce21e3049c01f" | "1d6d7e862dc5870107460316d4c68806e8bc6e2228114a6df74ce21e3049c01f" | sí |
| sha256 evidence/2026-10-01-T-020-p4/run/tablas/capacidad.tsv | "ec5c5af6eaae362a9bc705b1096ba45b26d1724bfe0f5fc43a2344117d1f23b6" | "ec5c5af6eaae362a9bc705b1096ba45b26d1724bfe0f5fc43a2344117d1f23b6" | sí |
| sha256 evidence/2026-10-01-T-020-p4/run/tablas/emparejamiento.tsv | "b40f5be02056070d02da1f0b4e6c5d27f6dc068933121de630f5e452e633a4dd" | "b40f5be02056070d02da1f0b4e6c5d27f6dc068933121de630f5e452e633a4dd" | sí |
| sha256 evidence/2026-10-01-T-020-p4/preflight/p4-preflight.json | "1b939dc7ab94dfb55ba7cad4260b5a249366a421733d3854b3f8b1ab30e900b2" | "1b939dc7ab94dfb55ba7cad4260b5a249366a421733d3854b3f8b1ab30e900b2" | sí |
| sha256 evidence/2026-10-02-T-021-p5-diseno/inventario-estructural.json | "c49598011e39685fc3d0239dd12b13d835c9ee045c5586fc892a0a20145da0e2" | "c49598011e39685fc3d0239dd12b13d835c9ee045c5586fc892a0a20145da0e2" | sí |
| hash C0 por rol canónico | ["advisor_config_hash", "policy_sha256", "procedencia"] | ["advisor_config_hash", "policy_sha256", "procedencia"] | sí |
| hash B2_s1p75_m24p500 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2_s1p75_m24p875 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2_s1p75_m25p250 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2_s2p00_m24p500 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2 por rol canónico | ["advisor_config_hash", "policy_sha256", "procedencia"] | ["advisor_config_hash", "policy_sha256", "procedencia"] | sí |
| hash B2_s2p00_m25p250 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2_s2p25_m24p500 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2_s2p25_m24p875 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash B2_s2p25_m25p250 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash S2_s2p25_m23p375 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash S2_s2p25_m23p750 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash S2_s2p25_m24p125 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash S2 por rol canónico | ["advisor_config_hash", "policy_sha256", "procedencia"] | ["advisor_config_hash", "policy_sha256", "procedencia"] | sí |
| hash S2_s2p50_m24p125 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| hash S2_s2p75_m24p125 por rol canónico | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | ["advisor_config_hash", "diagnostico_sha256", "procedencia"] | sí |
| P4 publicado reproducido | true | true | sí |
| C0 advisor_config_hash_ok | true | true | sí |
| C0 niveles_event_study_diferencias | 0 | 0 | sí |
| C0 sin_niveles | 0 | 0 | sí |
| condiciones P4 de veto B2 exactas y cumplidas | {"P4_1": true, "P4_10": true, "P4_2": true, "P4_3": true, "P4_5": true, "P4_6": true, "… | {"P4_1": true, "P4_10": true, "P4_2": true, "P4_3": true, "P4_5": true, "P4_6": true, "… | sí |
| condiciones P4 de veto S2 exactas y cumplidas | {"P4_1": true, "P4_10": true, "P4_2": true, "P4_3": true, "P4_5": true, "P4_6": true, "… | {"P4_1": true, "P4_10": true, "P4_2": true, "P4_3": true, "P4_5": true, "P4_6": true, "… | sí |
| inventario estructural 2.0|3.0|5.0 | {"incoherencias": {}, "manda": {"RR": 96969, "TECNICO": 4282}, "none": {}, "pares_stop_… | {"incoherencias": {}, "manda": {"RR": 96969, "TECNICO": 4282}, "none": {}, "pares_stop_… | sí |
| inventario estructural 1.75|4.5|5.0 | {"incoherencias": {}, "manda": {"EMPATE": 86860, "TECNICO": 14391}, "none": {}, "pares_… | {"incoherencias": {}, "manda": {"EMPATE": 86860, "TECNICO": 14391}, "none": {}, "pares_… | sí |
| inventario estructural 1.75|4.875|5.0 | {"incoherencias": {}, "manda": {"TECNICO": 101251}, "none": {}, "pares_stop_basis_vs_c0… | {"incoherencias": {}, "manda": {"TECNICO": 101251}, "none": {}, "pares_stop_basis_vs_c0… | sí |
| inventario estructural 1.75|5.25|5.625 | {"incoherencias": {}, "manda": {"TECNICO": 101251}, "none": {}, "pares_stop_basis_vs_c0… | {"incoherencias": {}, "manda": {"TECNICO": 101251}, "none": {}, "pares_stop_basis_vs_c0… | sí |
| inventario estructural 2.0|4.5|5.0 | {"incoherencias": {}, "manda": {"RR": 86860, "TECNICO": 14391}, "none": {}, "pares_stop… | {"incoherencias": {}, "manda": {"RR": 86860, "TECNICO": 14391}, "none": {}, "pares_stop… | sí |
| inventario estructural 2.0|4.875|5.0 | {"incoherencias": {}, "manda": {"EMPATE": 84108, "TECNICO": 17143}, "none": {}, "pares_… | {"incoherencias": {}, "manda": {"EMPATE": 84108, "TECNICO": 17143}, "none": {}, "pares_… | sí |
| inventario estructural 2.0|5.25|5.625 | {"incoherencias": {}, "manda": {"TECNICO": 101251}, "none": {}, "pares_stop_basis_vs_c0… | {"incoherencias": {}, "manda": {"TECNICO": 101251}, "none": {}, "pares_stop_basis_vs_c0… | sí |
| inventario estructural 2.25|4.5|5.0 | {"incoherencias": {}, "manda": {"RR": 86860, "TECNICO": 14391}, "none": {}, "pares_stop… | {"incoherencias": {}, "manda": {"RR": 86860, "TECNICO": 14391}, "none": {}, "pares_stop… | sí |
| inventario estructural 2.25|4.875|5.0 | {"incoherencias": {}, "manda": {"EMPATE": 6, "RR": 84102, "TECNICO": 17143}, "none": {}… | {"incoherencias": {}, "manda": {"EMPATE": 6, "RR": 84102, "TECNICO": 17143}, "none": {}… | sí |
| inventario estructural 2.25|5.25|5.625 | {"incoherencias": {}, "manda": {"EMPATE": 81382, "TECNICO": 19869}, "none": {}, "pares_… | {"incoherencias": {}, "manda": {"EMPATE": 81382, "TECNICO": 19869}, "none": {}, "pares_… | sí |
| inventario estructural 2.25|3.375|5.0 | {"incoherencias": {}, "manda": {"RR": 94603, "TECNICO": 6648}, "none": {}, "pares_stop_… | {"incoherencias": {}, "manda": {"RR": 94603, "TECNICO": 6648}, "none": {}, "pares_stop_… | sí |
| inventario estructural 2.25|3.75|5.0 | {"incoherencias": {}, "manda": {"RR": 92148, "TECNICO": 9103}, "none": {}, "pares_stop_… | {"incoherencias": {}, "manda": {"RR": 92148, "TECNICO": 9103}, "none": {}, "pares_stop_… | sí |
| inventario estructural 2.25|4.125|5.0 | {"incoherencias": {}, "manda": {"RR": 89582, "TECNICO": 11669}, "none": {}, "pares_stop… | {"incoherencias": {}, "manda": {"RR": 89582, "TECNICO": 11669}, "none": {}, "pares_stop… | sí |
| inventario estructural 2.5|3.375|5.0 | {"incoherencias": {"P_SOBRE_ENTRY_MAX": 81381, "RR_EN_P_BAJO_MIN_RR": 81381}, "manda": … | {"incoherencias": {"P_SOBRE_ENTRY_MAX": 81381, "RR_EN_P_BAJO_MIN_RR": 81381}, "manda": … | sí |
| inventario estructural 2.5|3.75|5.0 | {"incoherencias": {}, "manda": {"RR": 92148, "TECNICO": 9103}, "none": {}, "pares_stop_… | {"incoherencias": {}, "manda": {"RR": 92148, "TECNICO": 9103}, "none": {}, "pares_stop_… | sí |
| inventario estructural 2.5|4.125|5.0 | {"incoherencias": {}, "manda": {"RR": 89582, "TECNICO": 11669}, "none": {}, "pares_stop… | {"incoherencias": {}, "manda": {"RR": 89582, "TECNICO": 11669}, "none": {}, "pares_stop… | sí |
| inventario estructural 2.75|3.375|5.0 | {"incoherencias": {"P_SOBRE_ENTRY_MAX": 81381, "RR_EN_P_BAJO_MIN_RR": 81381}, "manda": … | {"incoherencias": {"P_SOBRE_ENTRY_MAX": 81381, "RR_EN_P_BAJO_MIN_RR": 81381}, "manda": … | sí |
| inventario estructural 2.75|3.75|5.0 | {"incoherencias": {"P_SOBRE_ENTRY_MAX": 78601, "RR_EN_P_BAJO_MIN_RR": 78601}, "manda": … | {"incoherencias": {"P_SOBRE_ENTRY_MAX": 78601, "RR_EN_P_BAJO_MIN_RR": 78601}, "manda": … | sí |
| inventario estructural 2.75|4.125|5.0 | {"incoherencias": {}, "manda": {"RR": 89582, "TECNICO": 11669}, "none": {}, "pares_stop… | {"incoherencias": {}, "manda": {"RR": 89582, "TECNICO": 11669}, "none": {}, "pares_stop… | sí |
| levels_sha256 C0 coincide con P4 | "e07a33a9a713c6b3662baa615c718ba2621a9070e736c84d4fb5458f32b79f75" | "e07a33a9a713c6b3662baa615c718ba2621a9070e736c84d4fb5458f32b79f75" | sí |
| levels_sha256 B2 coincide con P4 | "f18694c316c0ad6d94ac566107db52bde0b7335a72a1206d2b49e731b54fbd02" | "f18694c316c0ad6d94ac566107db52bde0b7335a72a1206d2b49e731b54fbd02" | sí |
| levels_sha256 S2 coincide con P4 | "8c3b3e0a81274a9cb4c9b8c2c33a9b763f769a5b16079db64079121dd4016a8c" | "8c3b3e0a81274a9cb4c9b8c2c33a9b763f769a5b16079db64079121dd4016a8c" | sí |
| levels_sha256 distintos por celda válida | 16 | 16 | sí |

## sha256 de la evidencia de P4 leída por P5

- `evidence/2026-10-01-T-020-p4/run/tablas/criterio.tsv`: `be1f94e54a70e4bffaa686a7be42a4832799da40fb4410132bff6708e246a596`
- `evidence/2026-10-01-T-020-p4/run/tablas/estimaciones.tsv`: `dd178515bddb759b4045fa694060e234c86b75873605e74ff681778dddc7ad60`
- `evidence/2026-10-01-T-020-p4/run/tablas/nivel.tsv`: `1d6d7e862dc5870107460316d4c68806e8bc6e2228114a6df74ce21e3049c01f`
- `evidence/2026-10-01-T-020-p4/run/tablas/capacidad.tsv`: `ec5c5af6eaae362a9bc705b1096ba45b26d1724bfe0f5fc43a2344117d1f23b6`
- `evidence/2026-10-01-T-020-p4/run/tablas/emparejamiento.tsv`: `b40f5be02056070d02da1f0b4e6c5d27f6dc068933121de630f5e452e633a4dd`
- `evidence/2026-10-01-T-020-p4/preflight/p4-preflight.json`: `1b939dc7ab94dfb55ba7cad4260b5a249366a421733d3854b3f8b1ab30e900b2`
- `evidence/2026-10-02-T-021-p5-diseno/inventario-estructural.json`: `c49598011e39685fc3d0239dd12b13d835c9ee045c5586fc892a0a20145da0e2`
