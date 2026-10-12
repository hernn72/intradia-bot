# Reproducción de los agregados publicados de P4 (C0, B2, S2)

_condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)_

Fuente: `p5-preflight.json` → `p4_reproduccion`. Igualdad de **cadenas** con el formato de P4 (`"{:.6f}"`), sin tolerancia.

- `p4_published_results_reproduced = True`; 162/162 cadenas iguales.
- C0: `advisor_config_hash_ok = True`, diferencias de niveles con la enumeración del event study = 0, sin niveles = 0 (los tres son ahora controles del preflight).
- Condiciones de veto de P4 congeladas antes de la marca (`p4_reproduccion.condiciones_p4`, leídas de `criterio.tsv` con su sha256 verificado sobre los mismos bytes):
  - B2: P4_1=True, P4_2=True, P4_3=True, P4_5=True, P4_6=True, P4_8=True, P4_9=True, P4_10=True
  - S2: P4_1=True, P4_2=True, P4_3=True, P4_5=True, P4_6=True, P4_8=True, P4_9=True, P4_10=True

| Clave | Columna | Esperado (P4) | Observado (P5) | Igual |
|---|---|---|---|---|
| B2 / primaria_60 | n_pares | 101226 | 101226 | sí |
| B2 / primaria_60 | n_bloques | 20 | 20 | sí |
| B2 / primaria_60 | min_pares_bloque | 3599 | 3599 | sí |
| B2 / primaria_60 | media_delta_r | 0.071656 | 0.071656 | sí |
| B2 / primaria_60 | media_agrupada_delta_r | 0.072914 | 0.072914 | sí |
| B2 / primaria_60 | ic_inferior | 0.006112 | 0.006112 | sí |
| B2 / primaria_60 | ic_superior | 0.135643 | 0.135643 | sí |
| B2 / primaria_60 | ic_nivel | 0.987500 | 0.987500 | sí |
| B2 / primaria_60 | remuestreos | 20000 | 20000 | sí |
| B2 / bloque_120 | n_pares | 101226 | 101226 | sí |
| B2 / bloque_120 | n_bloques | 10 | 10 | sí |
| B2 / bloque_120 | min_pares_bloque | 8842 | 8842 | sí |
| B2 / bloque_120 | media_delta_r | 0.072639 | 0.072639 | sí |
| B2 / bloque_120 | media_agrupada_delta_r | 0.072914 | 0.072914 | sí |
| B2 / bloque_120 | ic_inferior | 0.023783 | 0.023783 | sí |
| B2 / bloque_120 | ic_superior | 0.114642 | 0.114642 | sí |
| B2 / bloque_120 | ic_nivel | 0.950000 | 0.950000 | sí |
| B2 / bloque_120 | remuestreos | 2000 | 2000 | sí |
| B2 / cota_conservadora | n_pares | 101251 | 101251 | sí |
| B2 / cota_conservadora | n_bloques | 20 | 20 | sí |
| B2 / cota_conservadora | min_pares_bloque | 3599 | 3599 | sí |
| B2 / cota_conservadora | media_delta_r | 0.070988 | 0.070988 | sí |
| B2 / cota_conservadora | media_agrupada_delta_r | 0.072240 | 0.072240 | sí |
| B2 / cota_conservadora | ic_inferior | 0.020438 | 0.020438 | sí |
| B2 / cota_conservadora | ic_superior | 0.122310 | 0.122310 | sí |
| B2 / cota_conservadora | ic_nivel | 0.950000 | 0.950000 | sí |
| B2 / cota_conservadora | remuestreos | 2000 | 2000 | sí |
| B2 / cota_favorable | n_pares | 101251 | 101251 | sí |
| B2 / cota_favorable | n_bloques | 20 | 20 | sí |
| B2 / cota_favorable | min_pares_bloque | 3599 | 3599 | sí |
| B2 / cota_favorable | media_delta_r | 0.071630 | 0.071630 | sí |
| B2 / cota_favorable | media_agrupada_delta_r | 0.072896 | 0.072896 | sí |
| B2 / cota_favorable | ic_inferior | 0.021050 | 0.021050 | sí |
| B2 / cota_favorable | ic_superior | 0.123060 | 0.123060 | sí |
| B2 / cota_favorable | ic_nivel | 0.950000 | 0.950000 | sí |
| B2 / cota_favorable | remuestreos | 2000 | 2000 | sí |
| B2 / mitades / bloques_2_11 | n_pares | 50923 | 50923 | sí |
| B2 / mitades / bloques_2_11 | n_bloques | 10 | 10 | sí |
| B2 / mitades / bloques_2_11 | min_pares_bloque | 4782 | 4782 | sí |
| B2 / mitades / bloques_2_11 | media_delta_r | 0.069304 | 0.069304 | sí |
| B2 / mitades / bloques_2_11 | media_agrupada_delta_r | 0.070074 | 0.070074 | sí |
| B2 / mitades / bloques_2_11 | ic_inferior | -0.020049 | -0.020049 | sí |
| B2 / mitades / bloques_2_11 | ic_superior | 0.160767 | 0.160767 | sí |
| B2 / mitades / bloques_2_11 | ic_nivel | 0.950000 | 0.950000 | sí |
| B2 / mitades / bloques_2_11 | remuestreos | 2000 | 2000 | sí |
| B2 / mitades / bloques_12_21 | n_pares | 50303 | 50303 | sí |
| B2 / mitades / bloques_12_21 | n_bloques | 10 | 10 | sí |
| B2 / mitades / bloques_12_21 | min_pares_bloque | 3599 | 3599 | sí |
| B2 / mitades / bloques_12_21 | media_delta_r | 0.074008 | 0.074008 | sí |
| B2 / mitades / bloques_12_21 | media_agrupada_delta_r | 0.075790 | 0.075790 | sí |
| B2 / mitades / bloques_12_21 | ic_inferior | 0.026285 | 0.026285 | sí |
| B2 / mitades / bloques_12_21 | ic_superior | 0.119696 | 0.119696 | sí |
| B2 / mitades / bloques_12_21 | ic_nivel | 0.950000 | 0.950000 | sí |
| B2 / mitades / bloques_12_21 | remuestreos | 2000 | 2000 | sí |
| B2 / nivel.tsv | n | 101251 | 101251 | sí |
| B2 / nivel.tsv | n_bloques | 20 | 20 | sí |
| B2 / nivel.tsv | media_net_r | 0.175396 | 0.175396 | sí |
| B2 / nivel.tsv | ic_inferior | 0.025100 | 0.025100 | sí |
| B2 / nivel.tsv | ic_superior | 0.329756 | 0.329756 | sí |
| B2 / nivel.tsv | profit_factor_agrupado | 1.263439 | 1.263439 | sí |
| B2 / capacidad.tsv | ok | True | True | sí |
| B2 / capacidad.tsv | motivos |  |  | sí |
| B2 / capacidad.tsv | bloques_con_pares | 20 | 20 | sí |
| B2 / capacidad.tsv | min_pares_bloque | 3599 | 3599 | sí |
| B2 / capacidad.tsv | tasa_descarte | 0.000247 | 0.000247 | sí |
| B2 / capacidad.tsv | exit_final_c | 0.013975 | 0.013975 | sí |
| B2 / capacidad.tsv | exit_final_v | 0.018607 | 0.018607 | sí |
| B2 / capacidad.tsv | anchura_ic95 | 0.101970 | 0.101970 | sí |
| B2 / emparejamiento / senales_poblacion | valor | 101251 | 101251 | sí |
| B2 / emparejamiento / sin_niveles | valor | 0 | 0 | sí |
| B2 / emparejamiento / con_niveles | valor | 101251 | 101251 | sí |
| B2 / emparejamiento / dropped_only_c0 | valor | 25 | 25 | sí |
| B2 / emparejamiento / dropped_only_variant | valor | 0 | 0 | sí |
| B2 / emparejamiento / dropped_both | valor | 0 | 0 | sí |
| B2 / emparejamiento / pares_finales | valor | 101226 | 101226 | sí |
| B2 / emparejamiento / bloques_60_sin_pares | valor | [] | [] | sí |
| B2 / emparejamiento / fraccion_pares | valor | 0.999753 | 0.999753 | sí |
| B2 / emparejamiento / tasa_descarte_ambiguedad | valor | 0.000247 | 0.000247 | sí |
| B2 / emparejamiento / pares_no_calculable_context | valor | 7157 | 7157 | sí |
| B2 / emparejamiento / ambiguas_en_los_dos_brazos | valor | 0 | 0 | sí |
| B2 / emparejamiento / vela_ambigua_compartida | valor | 0 | 0 | sí |
| S2 / primaria_60 | n_pares | 101225 | 101225 | sí |
| S2 / primaria_60 | n_bloques | 20 | 20 | sí |
| S2 / primaria_60 | min_pares_bloque | 3599 | 3599 | sí |
| S2 / primaria_60 | media_delta_r | 0.034786 | 0.034786 | sí |
| S2 / primaria_60 | media_agrupada_delta_r | 0.034676 | 0.034676 | sí |
| S2 / primaria_60 | ic_inferior | 0.007608 | 0.007608 | sí |
| S2 / primaria_60 | ic_superior | 0.059691 | 0.059691 | sí |
| S2 / primaria_60 | ic_nivel | 0.987500 | 0.987500 | sí |
| S2 / primaria_60 | remuestreos | 20000 | 20000 | sí |
| S2 / bloque_120 | n_pares | 101225 | 101225 | sí |
| S2 / bloque_120 | n_bloques | 10 | 10 | sí |
| S2 / bloque_120 | min_pares_bloque | 8842 | 8842 | sí |
| S2 / bloque_120 | media_delta_r | 0.034592 | 0.034592 | sí |
| S2 / bloque_120 | media_agrupada_delta_r | 0.034676 | 0.034676 | sí |
| S2 / bloque_120 | ic_inferior | 0.013093 | 0.013093 | sí |
| S2 / bloque_120 | ic_superior | 0.053171 | 0.053171 | sí |
| S2 / bloque_120 | ic_nivel | 0.950000 | 0.950000 | sí |
| S2 / bloque_120 | remuestreos | 2000 | 2000 | sí |
| S2 / cota_conservadora | n_pares | 101251 | 101251 | sí |
| S2 / cota_conservadora | n_bloques | 20 | 20 | sí |
| S2 / cota_conservadora | min_pares_bloque | 3599 | 3599 | sí |
| S2 / cota_conservadora | media_delta_r | 0.034303 | 0.034303 | sí |
| S2 / cota_conservadora | media_agrupada_delta_r | 0.034181 | 0.034181 | sí |
| S2 / cota_conservadora | ic_inferior | 0.013857 | 0.013857 | sí |
| S2 / cota_conservadora | ic_superior | 0.053170 | 0.053170 | sí |
| S2 / cota_conservadora | ic_nivel | 0.950000 | 0.950000 | sí |
| S2 / cota_conservadora | remuestreos | 2000 | 2000 | sí |
| S2 / cota_favorable | n_pares | 101251 | 101251 | sí |
| S2 / cota_favorable | n_bloques | 20 | 20 | sí |
| S2 / cota_favorable | min_pares_bloque | 3599 | 3599 | sí |
| S2 / cota_favorable | media_delta_r | 0.035073 | 0.035073 | sí |
| S2 / cota_favorable | media_agrupada_delta_r | 0.034969 | 0.034969 | sí |
| S2 / cota_favorable | ic_inferior | 0.014842 | 0.014842 | sí |
| S2 / cota_favorable | ic_superior | 0.054038 | 0.054038 | sí |
| S2 / cota_favorable | ic_nivel | 0.950000 | 0.950000 | sí |
| S2 / cota_favorable | remuestreos | 2000 | 2000 | sí |
| S2 / mitades / bloques_2_11 | n_pares | 50922 | 50922 | sí |
| S2 / mitades / bloques_2_11 | n_bloques | 10 | 10 | sí |
| S2 / mitades / bloques_2_11 | min_pares_bloque | 4782 | 4782 | sí |
| S2 / mitades / bloques_2_11 | media_delta_r | 0.023950 | 0.023950 | sí |
| S2 / mitades / bloques_2_11 | media_agrupada_delta_r | 0.024256 | 0.024256 | sí |
| S2 / mitades / bloques_2_11 | ic_inferior | -0.008830 | -0.008830 | sí |
| S2 / mitades / bloques_2_11 | ic_superior | 0.053884 | 0.053884 | sí |
| S2 / mitades / bloques_2_11 | ic_nivel | 0.950000 | 0.950000 | sí |
| S2 / mitades / bloques_2_11 | remuestreos | 2000 | 2000 | sí |
| S2 / mitades / bloques_12_21 | n_pares | 50303 | 50303 | sí |
| S2 / mitades / bloques_12_21 | n_bloques | 10 | 10 | sí |
| S2 / mitades / bloques_12_21 | min_pares_bloque | 3599 | 3599 | sí |
| S2 / mitades / bloques_12_21 | media_delta_r | 0.045623 | 0.045623 | sí |
| S2 / mitades / bloques_12_21 | media_agrupada_delta_r | 0.045224 | 0.045224 | sí |
| S2 / mitades / bloques_12_21 | ic_inferior | 0.020658 | 0.020658 | sí |
| S2 / mitades / bloques_12_21 | ic_superior | 0.069846 | 0.069846 | sí |
| S2 / mitades / bloques_12_21 | ic_nivel | 0.950000 | 0.950000 | sí |
| S2 / mitades / bloques_12_21 | remuestreos | 2000 | 2000 | sí |
| S2 / nivel.tsv | n | 101246 | 101246 | sí |
| S2 / nivel.tsv | n_bloques | 20 | 20 | sí |
| S2 / nivel.tsv | media_net_r | 0.138756 | 0.138756 | sí |
| S2 / nivel.tsv | ic_inferior | 0.011831 | 0.011831 | sí |
| S2 / nivel.tsv | ic_superior | 0.258789 | 0.258789 | sí |
| S2 / nivel.tsv | profit_factor_agrupado | 1.242589 | 1.242589 | sí |
| S2 / capacidad.tsv | ok | True | True | sí |
| S2 / capacidad.tsv | motivos |  |  | sí |
| S2 / capacidad.tsv | bloques_con_pares | 20 | 20 | sí |
| S2 / capacidad.tsv | min_pares_bloque | 3599 | 3599 | sí |
| S2 / capacidad.tsv | tasa_descarte | 0.000257 | 0.000257 | sí |
| S2 / capacidad.tsv | exit_final_c | 0.013975 | 0.013975 | sí |
| S2 / capacidad.tsv | exit_final_v | 0.018676 | 0.018676 | sí |
| S2 / capacidad.tsv | anchura_ic95 | 0.040415 | 0.040415 | sí |
| S2 / emparejamiento / senales_poblacion | valor | 101251 | 101251 | sí |
| S2 / emparejamiento / sin_niveles | valor | 0 | 0 | sí |
| S2 / emparejamiento / con_niveles | valor | 101251 | 101251 | sí |
| S2 / emparejamiento / dropped_only_c0 | valor | 21 | 21 | sí |
| S2 / emparejamiento / dropped_only_variant | valor | 1 | 1 | sí |
| S2 / emparejamiento / dropped_both | valor | 4 | 4 | sí |
| S2 / emparejamiento / pares_finales | valor | 101225 | 101225 | sí |
| S2 / emparejamiento / bloques_60_sin_pares | valor | [] | [] | sí |
| S2 / emparejamiento / fraccion_pares | valor | 0.999743 | 0.999743 | sí |
| S2 / emparejamiento / tasa_descarte_ambiguedad | valor | 0.000257 | 0.000257 | sí |
| S2 / emparejamiento / pares_no_calculable_context | valor | 7157 | 7157 | sí |
| S2 / emparejamiento / ambiguas_en_los_dos_brazos | valor | 4 | 4 | sí |
| S2 / emparejamiento / vela_ambigua_compartida | valor | 4 | 4 | sí |
