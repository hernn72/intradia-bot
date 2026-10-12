# Resultado congelado de P6 (T-022 / A-06)

_Condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)._

Transcripción de `evidence/2026-10-03-T-022-p6/run/p6-resultado.json` (commit `0771989af851748463aa0e79d4a7dc327066ca5f`), generada por
`transcribir_resultado.py`. **No se recalcula nada**: cada valor entre comillas invertidas es `repr()` del
número que escribió la ejecución única; los porcentajes redondeados son solo para leer. P6 no se repite.

## Identidad

|  |  |
| --- | --- |
| `P6_PREREG_SHA` | `03f04a42ea9d2be893e7c4cc09de76bd1c55778b` |
| `P6_CODE_SHA` | `bc0636d4320b38ef5a620fa9ae94cee35df47580` |
| `P6_RUN_HEAD_SHA` | `353876d39d03f6849847743b9f4e7f791abbed30` |
| `P6_RUN_EVIDENCE_SHA` | `0771989af851748463aa0e79d4a7dc327066ca5f` |
| `P6_DATA_ID` | `572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383` |
| `fase` | `confirmatoria` |
| `token_sha256` = sha256 de la marca | `7a05c3b80d42765bf8d7e272a7afa4419ab15aaf8611e3e15e2e9d3182a07463` |
| `fin_utc` | `2026-10-05T10:14:54.504778+00:00` |

Ventana publicada: `inicio` = `'2022-06-14'`, `fin` = `'2026-08-27'`, `ultimo_calentamiento_de_los_iniciales` = `'2022-02-25'`, `sesion_que_completa_la_sma200` = `'2022-06-13'`, `sesiones_sin_barra_en_ventana` = `27`, `instantaneas` = `1095`, `periodos_por_año` = `260.5529315960912`.

## Criterio decisorio (T-022 §16, D-69): corridas primarias a 5 pb

| Condición | B2: valor | B2 | S2: valor | S2 |
| --- | --- | --- | --- | --- |
| `N_closed>=100` | `673` | cumple | `528` | cumple |
| `profit_factor_local>1` | `1.3995145380650502` | cumple | `1.404363546229263` | cumple |
| `mean_R_local>0` | `0.24777341475087308` | cumple | `0.23830237795311177` | cumple |
| `max_drawdown>=-25%` | `-0.16595868879211273 (-16.5959 %)` | cumple | `-0.1122587263035435 (-11.2259 %)` | cumple |
| `excess_CAGR_pp>0` | `-15.767134262530824` | **NO cumple** | `-18.722782521718038` | **NO cumple** |
| **Etiqueta** |  | **NO PASA** |  | **NO PASA** |

`etiquetas_decisorias` = `{'B2': 'NO PASA', 'S2': 'NO PASA'}`.

**Supervivientes: `[]`.**

En las dos candidatas se cumplen las condiciones 1 a 4 y falla **exclusivamente** la 5,
`excess_CAGR_pp > 0`. Con la regla fijada ex ante (§16: cumple la 1 e incumple alguna de las demás),
la etiqueta es `NO PASA`.

## Benchmark: comprar y mantener del propio universo a pesos iguales (§14)

| Métrica | 5 pb | 10 pb |
| --- | --- | --- |
| equity_inicial | `100000.0` | `100000.0` |
| equity_final | `339995.31758311053` | `339647.02151481266` |
| retorno_total | `2.3999531758311052` | `2.3964702151481267` |
| cagr | `0.33802078491613186` | `0.33769450531167267` |
| dias | `1535` | `1535` |
| periodos_por_año | `260.5529315960912` | `260.5529315960912` |
| volatilidad | `0.18163294845844286` | `0.18163272034227784` |
| sharpe_rf0 | `1.6950288264842623` | `1.693686542186909` |
| sortino_mar0 | `2.485374765221142` | `2.483243442889127` |
| max_drawdown | `-0.26224893667895144` | `-0.26224999644481595` |
| dd_pico | `'2025-02-18'` | `'2025-02-18'` |
| dd_valle | `'2025-04-07'` | `'2025-04-07'` |
| dd_recuperacion | `'2025-07-16'` | `'2025-07-16'` |
| dd_duracion_dias | `148` | `148` |
| calmar | `1.288931002721057` | `1.2876816392359118` |

## Resumen de las nueve corridas

Solo las dos primeras filas deciden. El resto es **descriptivo**: no veta, no rescata y no cambia
ninguna etiqueta ni la salida (§16 y D-69).

| Corrida | Papel | N_closed | PF local | mean_R_local | Max DD | CAGR | excess_CAGR_pp | Etiqueta publicada |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `B2_primaria_5pb` | **decisoria** | 673 | 1.3995 | 0.2478 | -16.5959 % | 18.0349 % | -15.7671 | `NO PASA` |
| `S2_primaria_5pb` | **decisoria** | 528 | 1.4044 | 0.2383 | -11.2259 % | 15.0793 % | -18.7228 | `NO PASA` |
| `C0_primaria_5pb` | control descriptivo | 623 | 1.2468 | 0.1637 | -11.1428 % | 9.8883 % | -23.9138 | `NO PASA` |
| `B2_sensibilidad_10pb` | sensibilidad descriptiva | 686 | 1.4150 | 0.2624 | -12.8368 % | 18.4653 % | -15.3041 | `NO PASA` |
| `S2_sensibilidad_10pb` | sensibilidad descriptiva | 528 | 1.3784 | 0.2275 | -11.9653 % | 13.6776 % | -20.0919 | `NO PASA` |
| `B2_todas_las_barras_5pb` | puente descriptivo | 896 | 1.3411 | 0.2328 | -22.3306 % | 24.2856 % | -9.5165 | `NO PASA` |
| `S2_todas_las_barras_5pb` | puente descriptivo | 1006 | 1.4350 | 0.2728 | -27.7850 % | 28.2307 % | -5.5714 | `NO PASA` |

El simulador también calcula una etiqueta para las corridas descriptivas porque aplica la misma
función a las siete. Esas etiquetas **no son decisorias**: `etiquetas_decisorias` y `supervivientes`
se derivan solo de `B2_primaria_5pb` y `S2_primaria_5pb`.

## Señales (`senales`)

- `B2_primaria_5pb`: `{'excluida_excluded_asia_missing': 180, 'no_operar': 83506, 'senales': 10577}`
- `B2_sensibilidad_10pb`: `{'excluida_excluded_asia_missing': 180, 'no_operar': 83506, 'senales': 10577}`
- `B2_todas_las_barras_5pb`: `{'senales': 94263}`
- `S2_primaria_5pb`: `{'excluida_excluded_asia_missing': 180, 'no_operar': 91643, 'senales': 2440}`
- `S2_sensibilidad_10pb`: `{'excluida_excluded_asia_missing': 180, 'no_operar': 91643, 'senales': 2440}`
- `S2_todas_las_barras_5pb`: `{'senales': 94263}`
- `C0_primaria_5pb`: `{'excluida_excluded_asia_missing': 180, 'no_operar': 91660, 'senales': 2423}`

## Detalle completo por corrida

### `B2_primaria_5pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `200739.02621191912` |
| trayectoria.retorno_total | `1.0073902621191912` |
| trayectoria.cagr | `0.18034944229082361` |
| trayectoria.volatilidad | `0.14215628860120702` |
| trayectoria.sharpe_rf0 | `1.2379345202890968` |
| trayectoria.sortino_mar0 | `1.76759390414707` |
| trayectoria.max_drawdown | `-0.16595868879211273` |
| trayectoria.dd_pico | `'2025-02-18'` |
| trayectoria.dd_valle | `'2025-04-07'` |
| trayectoria.dd_recuperacion | `'2025-10-06'` |
| trayectoria.dd_duracion_dias | `230` |
| trayectoria.calmar | `1.0867128657345406` |
| operaciones.n_closed | `673` |
| operaciones.n_exit_final | `12` |
| operaciones.win_rate | `0.42050520059435365` |
| operaciones.profit_factor_local | `1.3995145380650502` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.24777341475087308` |
| operaciones.median_R_local | `-1.0096672832139204` |
| operaciones.R_total_local | `166.7515081273376` |
| operaciones.profit_factor_eur | `1.4216124763605325` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.22693458989141488` |
| operaciones.median_R_eur | `-0.7671837384436377` |
| operaciones.R_total_eur | `152.7269789969222` |
| operaciones.holding_medio_barras | `16.456166419019315` |
| exposicion.exposicion_media | `0.8370945714679114` |
| exposicion.exposicion_max | `0.9998033203413811` |
| exposicion.exposicion_p95 | `0.9975783120861487` |
| exposicion.cash_medio | `0.16290542853208848` |
| exposicion.cash_minimo_eur | `31.346239370128387` |
| exposicion.posiciones_media | `10.476712328767123` |
| exposicion.posiciones_max | `16` |
| turnover.turnover_total | `113.7565211063191` |
| turnover.turnover_anual | `27.06812334467951` |
| costes_eur | `15976.31017505227` |
| slippage_eur | `7988.183714484762` |
| dividendos_eur | `10195.681958940517` |
| fx_eur | `-8858.992055660408` |
| exceso.excess_terminal_pp | `-139.2562913711914` |
| exceso.excess_CAGR_pp | `-15.767134262530824` |
| contadores.ABOVE_MAX_ENTRY | `531` |
| contadores.IGNORED_ALREADY_OPEN | `2284` |
| contadores.INSUFFICIENT_CASH | `7005` |
| contadores.INVALID_STOP | `73` |
| contadores.INVALID_TARGET | `11` |
| contadores.dividendos_abonados | `83` |
| contadores.entradas | `673` |
| contadores.salida_final | `12` |
| contadores.salida_objetivo | `214` |
| contadores.salida_stop | `359` |
| contadores.salida_tiempo | `88` |
| contadores.senales_pendientes | `8293` |
| ocupacion.entradas | `673` |
| ocupacion.rechazadas_por_cash | `7005` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.9123469653555614` |
| ocupacion.capital_pedido_rechazado_eur | `91887351.22368279` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `26608777.47381146` |
| subperiodos.por_año.2022 | `{'retorno': -0.07158571041026396, 'operaciones': 26, 'mean_R_local': -0.7261464933184245}` |
| subperiodos.por_año.2023 | `{'retorno': 0.3171307631111586, 'operaciones': 152, 'mean_R_local': 0.4048112063353855}` |
| subperiodos.por_año.2024 | `{'retorno': 0.23605935384481658, 'operaciones': 173, 'mean_R_local': 0.24907026154684495}` |
| subperiodos.por_año.2025 | `{'retorno': 0.07603249201095563, 'operaciones': 169, 'mean_R_local': 0.12195608947300107}` |
| subperiodos.por_año.2026 | `{'retorno': 0.2342308356321956, 'operaciones': 153, 'mean_R_local': 0.3947730668110894}` |
| subperiodos.mitades.primera | `{'retorno': 0.4820411472058739, 'operaciones': 275, 'mean_R_local': 0.33495725857375336}` |
| subperiodos.mitades.segunda | `{'retorno': 0.3445653003412046, 'operaciones': 398, 'mean_R_local': 0.1875333216571744}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `0.08889282616957928` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.1876 / 0.6624 / 0.3892; EMERGING_MARKETS 0.0100 / 0.1030 / 0.0996; EUROPA 0.3640 / 0.7506 / 0.6224; GLOBAL 0.0329 / 0.2027 / 0.1028; USA 0.2426 / 0.6123 / 0.4958.
- `por_divisa_cotizacion`: EUR 0.4809 / 0.9583 / 0.7457; HKD 0.0260 / 0.2172 / 0.1251; JPY 0.1020 / 0.4574 / 0.2771; USD 0.2282 / 0.5934 / 0.4810.
- `por_divisa_economica`: CNY 0.0036 / 0.1080 / 0.0000; EUR 0.3036 / 0.7506 / 0.5763; GBP 0.0357 / 0.2085 / 0.1297; HKD 0.0260 / 0.2172 / 0.1251; INR 0.0156 / 0.1091 / 0.1007; JPY 0.1133 / 0.4574 / 0.2861; KRW 0.0137 / 0.1209 / 0.1006; MULTI 0.0236 / 0.2007 / 0.1023; TWD 0.0155 / 0.1688 / 0.1013; USD 0.2866 / 0.6808 / 0.5862.
- `por_sector`: BOND_ETF 0.0094 / 0.1058 / 0.0978; Communication Services 0.0343 / 0.2475 / 0.1026; Consumer Cyclical 0.0711 / 0.2585 / 0.1974; Consumer Defensive 0.0093 / 0.1029 / 0.0955; EQUITY_ETF 0.1614 / 0.5834 / 0.4006; Energy 0.0420 / 0.3972 / 0.2072; Financial Services 0.1024 / 0.3692 / 0.2708; Healthcare 0.0192 / 0.2115 / 0.1026; Industrials 0.1357 / 0.4681 / 0.3026; Technology 0.2336 / 0.7510 / 0.5101; Utilities 0.0187 / 0.1093 / 0.1029.

### `S2_primaria_5pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `180445.84056884746` |
| trayectoria.retorno_total | `0.8044584056884745` |
| trayectoria.cagr | `0.15079295969895146` |
| trayectoria.volatilidad | `0.11233980733088395` |
| trayectoria.sharpe_rf0 | `1.306738360707693` |
| trayectoria.sortino_mar0 | `1.90662823637852` |
| trayectoria.max_drawdown | `-0.1122587263035435` |
| trayectoria.dd_pico | `'2024-07-09'` |
| trayectoria.dd_valle | `'2024-09-06'` |
| trayectoria.dd_recuperacion | `'2024-11-08'` |
| trayectoria.dd_duracion_dias | `122` |
| trayectoria.calmar | `1.3432626991616918` |
| operaciones.n_closed | `528` |
| operaciones.n_exit_final | `8` |
| operaciones.win_rate | `0.4602272727272727` |
| operaciones.profit_factor_local | `1.404363546229263` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.23830237795311177` |
| operaciones.median_R_local | `-0.8032214436547236` |
| operaciones.R_total_local | `125.82365555924301` |
| operaciones.profit_factor_eur | `1.4947325949439345` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.22581139999656516` |
| operaciones.median_R_eur | `-0.5833104350892973` |
| operaciones.R_total_eur | `119.2284191981864` |
| operaciones.holding_medio_barras | `14.886363636363637` |
| exposicion.exposicion_media | `0.6053556936504817` |
| exposicion.exposicion_max | `0.999896661403623` |
| exposicion.exposicion_p95 | `0.968472154865402` |
| exposicion.cash_medio | `0.3946443063495183` |
| exposicion.cash_minimo_eur | `12.850513753153777` |
| exposicion.posiciones_media | `7.421917808219178` |
| exposicion.posiciones_max | `15` |
| turnover.turnover_total | `89.68341711896056` |
| turnover.turnover_anual | `21.339979220000224` |
| costes_eur | `11399.188546067058` |
| slippage_eur | `5699.6172562210695` |
| dividendos_eur | `5611.89358539531` |
| fx_eur | `-3006.01192229321` |
| exceso.excess_terminal_pp | `-159.54947701426306` |
| exceso.excess_CAGR_pp | `-18.722782521718038` |
| contadores.ABOVE_MAX_ENTRY | `1175` |
| contadores.IGNORED_ALREADY_OPEN | `390` |
| contadores.INSUFFICIENT_CASH | `319` |
| contadores.INVALID_STOP | `17` |
| contadores.INVALID_TARGET | `11` |
| contadores.dividendos_abonados | `72` |
| contadores.entradas | `528` |
| contadores.salida_final | `8` |
| contadores.salida_objetivo | `208` |
| contadores.salida_stop | `272` |
| contadores.salida_tiempo | `40` |
| contadores.senales_pendientes | `2050` |
| ocupacion.entradas | `528` |
| ocupacion.rechazadas_por_cash | `319` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.37662337662337664` |
| ocupacion.capital_pedido_rechazado_eur | `3496193.260062365` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `1861279.834006892` |
| subperiodos.por_año.2022 | `{'retorno': -0.045262071287675676, 'operaciones': 10, 'mean_R_local': -0.6384377962283513}` |
| subperiodos.por_año.2023 | `{'retorno': 0.15866217241953318, 'operaciones': 129, 'mean_R_local': 0.23859693374690247}` |
| subperiodos.por_año.2024 | `{'retorno': 0.2248939749900729, 'operaciones': 144, 'mean_R_local': 0.2405005735854802}` |
| subperiodos.por_año.2025 | `{'retorno': 0.12171733409431762, 'operaciones': 132, 'mean_R_local': 0.24249457820125517}` |
| subperiodos.por_año.2026 | `{'retorno': 0.18720014642097182, 'operaciones': 113, 'mean_R_local': 0.3078554172504538}` |
| subperiodos.mitades.primera | `{'retorno': 0.2765564224459647, 'operaciones': 227, 'mean_R_local': 0.26268206876733313}` |
| subperiodos.mitades.segunda | `{'retorno': 0.41048495084087344, 'operaciones': 301, 'mean_R_local': 0.21991636527926373}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `0.07820194131114806` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.1336 / 0.4594 / 0.3371; EMERGING_MARKETS 0.0121 / 0.1030 / 0.0996; EUROPA 0.2248 / 0.7310 / 0.5033; GLOBAL 0.0224 / 0.2011 / 0.1026; USA 0.2125 / 0.5735 / 0.4551.
- `por_divisa_cotizacion`: EUR 0.3107 / 0.8446 / 0.6207; HKD 0.0149 / 0.1731 / 0.1046; JPY 0.0619 / 0.3509 / 0.2014; USD 0.2178 / 0.7005 / 0.4611.
- `por_divisa_economica`: CNY 0.0066 / 0.1043 / 0.0962; EUR 0.1731 / 0.6193 / 0.4357; GBP 0.0292 / 0.1834 / 0.1357; HKD 0.0149 / 0.1731 / 0.1046; INR 0.0081 / 0.2155 / 0.0985; JPY 0.0706 / 0.3509 / 0.2051; KRW 0.0086 / 0.1060 / 0.0998; MULTI 0.0218 / 0.2061 / 0.1001; TWD 0.0247 / 0.1884 / 0.1028; USD 0.2477 / 0.7019 / 0.5048.
- `por_sector`: BOND_ETF 0.0046 / 0.1017 / 0.0000; Communication Services 0.0243 / 0.3132 / 0.0964; Consumer Cyclical 0.0436 / 0.2506 / 0.1755; Consumer Defensive 0.0047 / 0.1051 / 0.0000; EQUITY_ETF 0.1212 / 0.5986 / 0.3080; Energy 0.0213 / 0.2051 / 0.1031; Financial Services 0.0606 / 0.3074 / 0.2017; Healthcare 0.0412 / 0.2917 / 0.1857; Industrials 0.0938 / 0.5041 / 0.2932; Technology 0.1814 / 0.5567 / 0.4318; Utilities 0.0086 / 0.1065 / 0.0989.

### `C0_primaria_5pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `148628.67780931763` |
| trayectoria.retorno_total | `0.48628677809317633` |
| trayectoria.cagr | `0.09888299470999651` |
| trayectoria.volatilidad | `0.1041136369552021` |
| trayectoria.sharpe_rf0 | `0.9579204720455686` |
| trayectoria.sortino_mar0 | `1.3702940851603964` |
| trayectoria.max_drawdown | `-0.11142778269575515` |
| trayectoria.dd_pico | `'2025-11-03'` |
| trayectoria.dd_valle | `'2026-03-09'` |
| trayectoria.dd_recuperacion | `'2026-05-06'` |
| trayectoria.dd_duracion_dias | `184` |
| trayectoria.calmar | `0.8874177724597535` |
| operaciones.n_closed | `623` |
| operaciones.n_exit_final | `8` |
| operaciones.win_rate | `0.4189406099518459` |
| operaciones.profit_factor_local | `1.2468459000833998` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.16365974893128543` |
| operaciones.median_R_local | `-1.031102338166099` |
| operaciones.R_total_local | `101.96002358419082` |
| operaciones.profit_factor_eur | `1.276440276413925` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.1593585436051313` |
| operaciones.median_R_eur | `-0.849219984900235` |
| operaciones.R_total_eur | `99.2803726659968` |
| operaciones.holding_medio_barras | `9.959871589085072` |
| exposicion.exposicion_media | `0.5313221187586629` |
| exposicion.exposicion_max | `0.9998908935722783` |
| exposicion.exposicion_p95 | `0.9796530282071806` |
| exposicion.cash_medio | `0.46867788124133714` |
| exposicion.cash_minimo_eur | `11.790008249068705` |
| exposicion.posiciones_media | `5.851141552511415` |
| exposicion.posiciones_max | `13` |
| turnover.turnover_total | `116.55611508989371` |
| turnover.turnover_anual | `27.734280805591972` |
| costes_eur | `14124.906409241787` |
| slippage_eur | `7062.469251373372` |
| dividendos_eur | `5629.040264084642` |
| fx_eur | `-2778.482524979797` |
| exceso.excess_terminal_pp | `-191.36663977379288` |
| exceso.excess_CAGR_pp | `-23.913779020613536` |
| contadores.ABOVE_MAX_ENTRY | `1197` |
| contadores.IGNORED_ALREADY_OPEN | `322` |
| contadores.INSUFFICIENT_CASH | `241` |
| contadores.INVALID_STOP | `26` |
| contadores.INVALID_TARGET | `14` |
| contadores.dividendos_abonados | `60` |
| contadores.entradas | `623` |
| contadores.salida_final | `8` |
| contadores.salida_objetivo | `239` |
| contadores.salida_stop | `357` |
| contadores.salida_tiempo | `19` |
| contadores.senales_pendientes | `2101` |
| ocupacion.entradas | `623` |
| ocupacion.rechazadas_por_cash | `241` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.2789351851851852` |
| ocupacion.capital_pedido_rechazado_eur | `2716003.576539289` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `1121406.6272067642` |
| subperiodos.por_año.2022 | `{'retorno': -0.0662939056254187, 'operaciones': 15, 'mean_R_local': -1.0354797407414902}` |
| subperiodos.por_año.2023 | `{'retorno': 0.1594669649523357, 'operaciones': 159, 'mean_R_local': 0.15919292317818312}` |
| subperiodos.por_año.2024 | `{'retorno': 0.23188450706708497, 'operaciones': 173, 'mean_R_local': 0.258963510226485}` |
| subperiodos.por_año.2025 | `{'retorno': 0.00497861134280031, 'operaciones': 162, 'mean_R_local': 0.15629163906144586}` |
| subperiodos.por_año.2026 | `{'retorno': 0.10893790691275229, 'operaciones': 114, 'mean_R_local': 0.19351414134075368}` |
| subperiodos.mitades.primera | `{'retorno': 0.3020759183268411, 'operaciones': 291, 'mean_R_local': 0.1781947978292039}` |
| subperiodos.mitades.segunda | `{'retorno': 0.1373453492124297, 'operaciones': 332, 'mean_R_local': 0.15091969101172437}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `-0.0535035053869245` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.1095 / 0.4554 / 0.3084; EMERGING_MARKETS 0.0076 / 0.1037 / 0.0998; EUROPA 0.2067 / 0.7943 / 0.5032; GLOBAL 0.0222 / 0.2065 / 0.1024; USA 0.1853 / 0.6972 / 0.4637.
- `por_divisa_cotizacion`: EUR 0.2872 / 0.8944 / 0.6607; HKD 0.0138 / 0.2344 / 0.1011; JPY 0.0542 / 0.3562 / 0.2017; USD 0.1761 / 0.6026 / 0.4702.
- `por_divisa_economica`: CNY 0.0036 / 0.1029 / 0.0000; EUR 0.1654 / 0.7871 / 0.4089; GBP 0.0287 / 0.2012 / 0.1017; HKD 0.0138 / 0.2344 / 0.1011; INR 0.0064 / 0.2066 / 0.0961; JPY 0.0611 / 0.3562 / 0.2052; KRW 0.0063 / 0.1041 / 0.0984; MULTI 0.0199 / 0.2066 / 0.1011; TWD 0.0183 / 0.2002 / 0.1024; USD 0.2077 / 0.6972 / 0.5055.
- `por_sector`: BOND_ETF 0.0031 / 0.1008 / 0.0000; Communication Services 0.0199 / 0.2131 / 0.1009; Consumer Cyclical 0.0469 / 0.2846 / 0.1975; Consumer Defensive 0.0023 / 0.1042 / 0.0000; EQUITY_ETF 0.1007 / 0.6601 / 0.3068; Energy 0.0155 / 0.2063 / 0.1013; Financial Services 0.0665 / 0.4001 / 0.2035; Healthcare 0.0282 / 0.2050 / 0.1050; Industrials 0.0881 / 0.5519 / 0.3461; Technology 0.1557 / 0.6761 / 0.4228; Utilities 0.0045 / 0.1045 / 0.0000.

### `B2_sensibilidad_10pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `203832.9291525274` |
| trayectoria.retorno_total | `1.0383292915252738` |
| trayectoria.cagr | `0.18465304670860583` |
| trayectoria.volatilidad | `0.13935633893387128` |
| trayectoria.sharpe_rf0 | `1.2860987537635868` |
| trayectoria.sortino_mar0 | `1.8437904233241453` |
| trayectoria.max_drawdown | `-0.12836837355301967` |
| trayectoria.dd_pico | `'2024-07-10'` |
| trayectoria.dd_valle | `'2024-09-06'` |
| trayectoria.dd_recuperacion | `'2024-11-07'` |
| trayectoria.dd_duracion_dias | `120` |
| trayectoria.calmar | `1.4384621507441555` |
| operaciones.n_closed | `686` |
| operaciones.n_exit_final | `15` |
| operaciones.win_rate | `0.42565597667638483` |
| operaciones.profit_factor_local | `1.4150189323537146` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.26243917025796154` |
| operaciones.median_R_local | `-1.021870810438623` |
| operaciones.R_total_local | `180.03327079696163` |
| operaciones.profit_factor_eur | `1.4207148801255056` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.24345568148793384` |
| operaciones.median_R_eur | `-0.8061892646117242` |
| operaciones.R_total_eur | `167.0105975007226` |
| operaciones.holding_medio_barras | `15.880466472303207` |
| exposicion.exposicion_media | `0.834647908877768` |
| exposicion.exposicion_max | `0.9999748587014656` |
| exposicion.exposicion_p95 | `0.9967772892747263` |
| exposicion.cash_medio | `0.16535209112223195` |
| exposicion.cash_minimo_eur | `3.7362039497111255` |
| exposicion.posiciones_media | `10.28310502283105` |
| exposicion.posiciones_max | `16` |
| turnover.turnover_total | `116.51428242810289` |
| turnover.turnover_anual | `27.72432681228963` |
| costes_eur | `16125.66904361473` |
| slippage_eur | `16125.794806644093` |
| dividendos_eur | `10321.362809792194` |
| fx_eur | `-8042.528876690552` |
| exceso.excess_terminal_pp | `-135.8140923622853` |
| exceso.excess_CAGR_pp | `-15.304145860306683` |
| contadores.ABOVE_MAX_ENTRY | `605` |
| contadores.IGNORED_ALREADY_OPEN | `2409` |
| contadores.INSUFFICIENT_CASH | `6802` |
| contadores.INVALID_STOP | `65` |
| contadores.INVALID_TARGET | `10` |
| contadores.dividendos_abonados | `74` |
| contadores.entradas | `686` |
| contadores.salida_final | `15` |
| contadores.salida_objetivo | `218` |
| contadores.salida_stop | `370` |
| contadores.salida_tiempo | `83` |
| contadores.senales_pendientes | `8168` |
| ocupacion.entradas | `686` |
| ocupacion.rechazadas_por_cash | `6802` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.9083867521367521` |
| ocupacion.capital_pedido_rechazado_eur | `87352873.86985634` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `26152675.99509305` |
| subperiodos.por_año.2022 | `{'retorno': -0.07349955742506997, 'operaciones': 28, 'mean_R_local': -0.7654513551668731}` |
| subperiodos.por_año.2023 | `{'retorno': 0.28760575847337844, 'operaciones': 158, 'mean_R_local': 0.38233989261626367}` |
| subperiodos.por_año.2024 | `{'retorno': 0.2797831344617798, 'operaciones': 180, 'mean_R_local': 0.26100371074632617}` |
| subperiodos.por_año.2025 | `{'retorno': 0.08702983424439359, 'operaciones': 174, 'mean_R_local': 0.14709164377461553}` |
| subperiodos.por_año.2026 | `{'retorno': 0.22819678948779631, 'operaciones': 146, 'mean_R_local': 0.4690519983365931}` |
| subperiodos.mitades.primera | `{'retorno': 0.4402735502548065, 'operaciones': 290, 'mean_R_local': 0.28985790779980214}` |
| subperiodos.mitades.segunda | `{'retorno': 0.3997842972444774, 'operaciones': 396, 'mean_R_local': 0.24235979175509847}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `0.09880717806138507` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.1884 / 0.6538 / 0.3957; EMERGING_MARKETS 0.0137 / 0.1048 / 0.1003; EUROPA 0.3702 / 0.8259 / 0.6728; GLOBAL 0.0279 / 0.2095 / 0.1125; USA 0.2344 / 0.6175 / 0.4758.
- `por_divisa_cotizacion`: EUR 0.4848 / 0.8733 / 0.7547; HKD 0.0289 / 0.2168 / 0.1339; JPY 0.1040 / 0.3605 / 0.2690; USD 0.2170 / 0.6064 / 0.4320.
- `por_divisa_economica`: CNY 0.0052 / 0.1052 / 0.0952; EUR 0.3090 / 0.7189 / 0.5809; GBP 0.0415 / 0.2037 / 0.1470; HKD 0.0289 / 0.2168 / 0.1339; INR 0.0214 / 0.2122 / 0.1017; JPY 0.1138 / 0.3643 / 0.3039; KRW 0.0083 / 0.1230 / 0.1009; MULTI 0.0281 / 0.2064 / 0.1032; TWD 0.0109 / 0.1070 / 0.1005; USD 0.2676 / 0.6175 / 0.5134.
- `por_sector`: BOND_ETF 0.0090 / 0.1034 / 0.0980; Communication Services 0.0423 / 0.2435 / 0.1633; Consumer Cyclical 0.0604 / 0.2994 / 0.1987; Consumer Defensive 0.0116 / 0.1016 / 0.0949; EQUITY_ETF 0.1655 / 0.5062 / 0.4059; Energy 0.0311 / 0.4214 / 0.1983; Financial Services 0.1079 / 0.4382 / 0.3016; Healthcare 0.0274 / 0.2043 / 0.1022; Industrials 0.1507 / 0.5896 / 0.3393; Technology 0.2067 / 0.7252 / 0.4471; Utilities 0.0222 / 0.1097 / 0.1028.

### `S2_sensibilidad_10pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `171387.49809709704` |
| trayectoria.retorno_total | `0.7138749809709704` |
| trayectoria.cagr | `0.13677585522890157` |
| trayectoria.volatilidad | `0.11269409754601953` |
| trayectoria.sharpe_rf0 | `1.1942203497200117` |
| trayectoria.sortino_mar0 | `1.7217498337883619` |
| trayectoria.max_drawdown | `-0.11965308175604406` |
| trayectoria.dd_pico | `'2024-07-16'` |
| trayectoria.dd_valle | `'2024-09-06'` |
| trayectoria.dd_recuperacion | `'2024-11-11'` |
| trayectoria.dd_duracion_dias | `118` |
| trayectoria.calmar | `1.1431034890331404` |
| operaciones.n_closed | `528` |
| operaciones.n_exit_final | `8` |
| operaciones.win_rate | `0.4583333333333333` |
| operaciones.profit_factor_local | `1.3783590676927566` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.22748589794924579` |
| operaciones.median_R_local | `-0.8736754045494131` |
| operaciones.R_total_local | `120.11255411720177` |
| operaciones.profit_factor_eur | `1.4392612047509814` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.22007836461042576` |
| operaciones.median_R_eur | `-0.6542234779570426` |
| operaciones.R_total_eur | `116.2013765143048` |
| operaciones.holding_medio_barras | `14.545454545454545` |
| exposicion.exposicion_media | `0.5856055831412957` |
| exposicion.exposicion_max | `0.9997783266614655` |
| exposicion.exposicion_p95 | `0.96753860189946` |
| exposicion.cash_medio | `0.4143944168587043` |
| exposicion.cash_minimo_eur | `26.853969525154753` |
| exposicion.posiciones_media | `7.249315068493151` |
| exposicion.posiciones_max | `14` |
| turnover.turnover_total | `89.27613132673673` |
| turnover.turnover_anual | `21.243066428072044` |
| costes_eur | `11029.22618418675` |
| slippage_eur | `11029.314473233751` |
| dividendos_eur | `5156.991170337379` |
| fx_eur | `-1749.5081879262148` |
| exceso.excess_terminal_pp | `-168.25952341771563` |
| exceso.excess_CAGR_pp | `-20.09186500827711` |
| contadores.ABOVE_MAX_ENTRY | `1217` |
| contadores.IGNORED_ALREADY_OPEN | `403` |
| contadores.INSUFFICIENT_CASH | `264` |
| contadores.INVALID_STOP | `17` |
| contadores.INVALID_TARGET | `11` |
| contadores.dividendos_abonados | `72` |
| contadores.entradas | `528` |
| contadores.salida_final | `8` |
| contadores.salida_objetivo | `208` |
| contadores.salida_stop | `273` |
| contadores.salida_tiempo | `39` |
| contadores.senales_pendientes | `2037` |
| ocupacion.entradas | `528` |
| ocupacion.rechazadas_por_cash | `264` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.3333333333333333` |
| ocupacion.capital_pedido_rechazado_eur | `2808103.9031983037` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `1485375.8837624316` |
| subperiodos.por_año.2022 | `{'retorno': -0.03903731576257796, 'operaciones': 9, 'mean_R_local': -0.6113793990486225}` |
| subperiodos.por_año.2023 | `{'retorno': 0.11792861750680994, 'operaciones': 127, 'mean_R_local': 0.15881529894117288}` |
| subperiodos.por_año.2024 | `{'retorno': 0.22273627181612454, 'operaciones': 146, 'mean_R_local': 0.3185970057636079}` |
| subperiodos.por_año.2025 | `{'retorno': 0.11254662923428782, 'operaciones': 133, 'mean_R_local': 0.21244816347278983}` |
| subperiodos.por_año.2026 | `{'retorno': 0.17275562310116244, 'operaciones': 113, 'mean_R_local': 0.2714571430065718}` |
| subperiodos.mitades.primera | `{'retorno': 0.2703687690666816, 'operaciones': 226, 'mean_R_local': 0.2702507601048817}` |
| subperiodos.mitades.segunda | `{'retorno': 0.34695949178508734, 'operaciones': 302, 'mean_R_local': 0.1954830540844321}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `0.06998764242710398` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.1416 / 0.4621 / 0.3550; EMERGING_MARKETS 0.0121 / 0.1026 / 0.0994; EUROPA 0.2061 / 0.7278 / 0.4818; GLOBAL 0.0257 / 0.2005 / 0.1023; USA 0.2001 / 0.6359 / 0.4302.
- `por_divisa_cotizacion`: EUR 0.2927 / 0.8403 / 0.5853; HKD 0.0179 / 0.1716 / 0.1041; JPY 0.0615 / 0.3498 / 0.1999; USD 0.2135 / 0.7237 / 0.4599.
- `por_divisa_economica`: CNY 0.0072 / 0.1037 / 0.0966; EUR 0.1546 / 0.5365 / 0.4197; GBP 0.0290 / 0.2005 / 0.1339; HKD 0.0179 / 0.1716 / 0.1041; INR 0.0124 / 0.2142 / 0.0984; JPY 0.0702 / 0.3498 / 0.2036; KRW 0.0083 / 0.1060 / 0.0995; MULTI 0.0236 / 0.2057 / 0.1005; TWD 0.0256 / 0.1876 / 0.1028; USD 0.2367 / 0.6649 / 0.5055.
- `por_sector`: BOND_ETF 0.0039 / 0.1016 / 0.0000; Communication Services 0.0234 / 0.3131 / 0.0957; Consumer Cyclical 0.0381 / 0.2507 / 0.1580; Consumer Defensive 0.0047 / 0.1050 / 0.0000; EQUITY_ETF 0.1157 / 0.5210 / 0.3022; Energy 0.0216 / 0.2053 / 0.1031; Financial Services 0.0573 / 0.3431 / 0.1985; Healthcare 0.0391 / 0.2909 / 0.1660; Industrials 0.0924 / 0.5433 / 0.3207; Technology 0.1844 / 0.6073 / 0.4514; Utilities 0.0049 / 0.1065 / 0.0000.

### `B2_todas_las_barras_5pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `249352.0521702358` |
| trayectoria.retorno_total | `1.493520521702358` |
| trayectoria.cagr | `0.24285596361136053` |
| trayectoria.volatilidad | `0.18316186023490444` |
| trayectoria.sharpe_rf0 | `1.2792191688884884` |
| trayectoria.sortino_mar0 | `1.8298152510982826` |
| trayectoria.max_drawdown | `-0.2233056611630626` |
| trayectoria.dd_pico | `'2025-02-18'` |
| trayectoria.dd_valle | `'2025-04-09'` |
| trayectoria.dd_recuperacion | `'2025-07-31'` |
| trayectoria.dd_duracion_dias | `163` |
| trayectoria.calmar | `1.0875495155226802` |
| operaciones.n_closed | `896` |
| operaciones.n_exit_final | `24` |
| operaciones.win_rate | `0.39955357142857145` |
| operaciones.profit_factor_local | `1.3410622127558587` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.23284077828313252` |
| operaciones.median_R_local | `-1.0162509829390554` |
| operaciones.R_total_local | `208.62533734168673` |
| operaciones.profit_factor_eur | `1.4058087756834143` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.20354459868504468` |
| operaciones.median_R_eur | `-0.823257482390293` |
| operaciones.R_total_eur | `182.37596042180004` |
| operaciones.holding_medio_barras | `15.958705357142858` |
| exposicion.exposicion_media | `0.955023767832368` |
| exposicion.exposicion_max | `0.9999707959856761` |
| exposicion.exposicion_p95 | `0.9984628652684385` |
| exposicion.cash_medio | `0.044976232167632094` |
| exposicion.cash_minimo_eur | `6.211580297685941` |
| exposicion.posiciones_media | `13.58904109589041` |
| exposicion.posiciones_max | `19` |
| turnover.turnover_total | `131.75739785716593` |
| turnover.turnover_anual | `31.351393854938014` |
| costes_eur | `21482.89954189673` |
| slippage_eur | `10741.493146891593` |
| dividendos_eur | `8072.667158767738` |
| fx_eur | `-18432.401876565724` |
| exceso.excess_terminal_pp | `-90.64326541287473` |
| exceso.excess_CAGR_pp | `-9.516482130477133` |
| contadores.ABOVE_MAX_ENTRY | `4027` |
| contadores.IGNORED_ALREADY_OPEN | `14299` |
| contadores.INSUFFICIENT_CASH | `74218` |
| contadores.INVALID_STOP | `791` |
| contadores.INVALID_TARGET | `32` |
| contadores.dividendos_abonados | `79` |
| contadores.entradas | `896` |
| contadores.salida_final | `24` |
| contadores.salida_objetivo | `257` |
| contadores.salida_stop | `494` |
| contadores.salida_tiempo | `121` |
| contadores.senales_pendientes | `79964` |
| ocupacion.entradas | `896` |
| ocupacion.rechazadas_por_cash | `74218` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.9880714647069787` |
| ocupacion.capital_pedido_rechazado_eur | `1083349054.6202934` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `232344082.14059547` |
| subperiodos.por_año.2022 | `{'retorno': -0.06215806610323549, 'operaciones': 135, 'mean_R_local': -0.3493523046466258}` |
| subperiodos.por_año.2023 | `{'retorno': 0.4848322055861596, 'operaciones': 183, 'mean_R_local': 0.5885137753335937}` |
| subperiodos.por_año.2024 | `{'retorno': 0.30067546207332607, 'operaciones': 200, 'mean_R_local': 0.2396578952065893}` |
| subperiodos.por_año.2025 | `{'retorno': 0.1624560057632618, 'operaciones': 215, 'mean_R_local': 0.2075772379608107}` |
| subperiodos.por_año.2026 | `{'retorno': 0.18429650567118006, 'operaciones': 163, 'mean_R_local': 0.34066989190209446}` |
| subperiodos.mitades.primera | `{'retorno': 0.6380115931011434, 'operaciones': 415, 'mean_R_local': 0.26951345404992627}` |
| subperiodos.mitades.segunda | `{'retorno': 0.5047459833787278, 'operaciones': 481, 'mean_R_local': 0.2012001120810131}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `0.20541329915129247` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.4180 / 0.8781 / 0.6619; EMERGING_MARKETS 0.0084 / 0.1049 / 0.0993; EUROPA 0.3077 / 0.8078 / 0.5499; GLOBAL 0.0270 / 0.1504 / 0.1025; USA 0.1939 / 0.4598 / 0.3516.
- `por_divisa_cotizacion`: EUR 0.3980 / 0.8078 / 0.6302; HKD 0.0968 / 0.3136 / 0.2397; JPY 0.2834 / 0.5711 / 0.4998; USD 0.1768 / 0.4443 / 0.3419.
- `por_divisa_economica`: CNY 0.0060 / 0.1026 / 0.0659; EUR 0.2624 / 0.7736 / 0.4921; GBP 0.0411 / 0.2092 / 0.1517; HKD 0.0968 / 0.3136 / 0.2397; INR 0.0041 / 0.1020 / 0.0000; JPY 0.2930 / 0.6069 / 0.5295; KRW 0.0062 / 0.1045 / 0.0526; MULTI 0.0267 / 0.2078 / 0.1025; TWD 0.0119 / 0.1655 / 0.0998; USD 0.2068 / 0.4711 / 0.3710.
- `por_sector`: BOND_ETF 0.0096 / 0.1071 / 0.0959; Communication Services 0.0555 / 0.2667 / 0.1345; Consumer Cyclical 0.1288 / 0.3322 / 0.2421; Consumer Defensive 0.0056 / 0.1148 / 0.1017; EQUITY_ETF 0.1144 / 0.4130 / 0.2981; Energy 0.0310 / 0.2076 / 0.1041; Financial Services 0.0637 / 0.3332 / 0.2023; Healthcare 0.0030 / 0.1681 / 0.0000; Industrials 0.2059 / 0.4614 / 0.3393; Technology 0.3345 / 0.7276 / 0.5318; Utilities 0.0030 / 0.0835 / 0.0000.

### `S2_todas_las_barras_5pb`

| Métrica | Valor publicado |
| --- | --- |
| trayectoria.equity_inicial | `100000.0` |
| trayectoria.equity_final | `284346.361330937` |
| trayectoria.retorno_total | `1.8434636133093703` |
| trayectoria.cagr | `0.2823072371908142` |
| trayectoria.volatilidad | `0.17254941552861375` |
| trayectoria.sharpe_rf0 | `1.5282442773822689` |
| trayectoria.sortino_mar0 | `2.2026235634310036` |
| trayectoria.max_drawdown | `-0.27785021238259555` |
| trayectoria.dd_pico | `'2025-02-18'` |
| trayectoria.dd_valle | `'2025-04-09'` |
| trayectoria.dd_recuperacion | `'2025-10-03'` |
| trayectoria.dd_duracion_dias | `227` |
| trayectoria.calmar | `1.0160411063572676` |
| operaciones.n_closed | `1006` |
| operaciones.n_exit_final | `21` |
| operaciones.win_rate | `0.4393638170974155` |
| operaciones.profit_factor_local | `1.43498264642161` |
| operaciones.profit_factor_local_sin_perdidas | `False` |
| operaciones.mean_R_local | `0.2728046069060882` |
| operaciones.median_R_local | `-1.0089067156610714` |
| operaciones.R_total_local | `274.44143454752475` |
| operaciones.profit_factor_eur | `1.4362306716239897` |
| operaciones.profit_factor_eur_sin_perdidas | `False` |
| operaciones.mean_R_eur | `0.2537828933746073` |
| operaciones.median_R_eur | `-0.7492008397296059` |
| operaciones.R_total_eur | `255.30559073485495` |
| operaciones.holding_medio_barras | `14.848906560636182` |
| exposicion.exposicion_media | `0.9507091081962176` |
| exposicion.exposicion_max | `0.999904438784701` |
| exposicion.exposicion_p95 | `0.9989667004784205` |
| exposicion.cash_medio | `0.049290891803782454` |
| exposicion.cash_minimo_eur | `19.59345013510392` |
| exposicion.posiciones_media | `14.189041095890412` |
| exposicion.posiciones_max | `21` |
| turnover.turnover_total | `146.81217704597816` |
| turnover.turnover_anual | `34.933646687976236` |
| costes_eur | `25578.277709070273` |
| slippage_eur | `12789.19203371746` |
| dividendos_eur | `9997.096101522857` |
| fx_eur | `-15849.873834882517` |
| exceso.excess_terminal_pp | `-55.6489562521735` |
| exceso.excess_CAGR_pp | `-5.571354772531767` |
| contadores.ABOVE_MAX_ENTRY | `38064` |
| contadores.IGNORED_ALREADY_OPEN | `14938` |
| contadores.INSUFFICIENT_CASH | `39543` |
| contadores.INVALID_STOP | `648` |
| contadores.INVALID_TARGET | `64` |
| contadores.dividendos_abonados | `85` |
| contadores.entradas | `1006` |
| contadores.salida_final | `21` |
| contadores.salida_objetivo | `349` |
| contadores.salida_stop | `534` |
| contadores.salida_tiempo | `102` |
| contadores.senales_pendientes | `79325` |
| ocupacion.entradas | `1006` |
| ocupacion.rechazadas_por_cash | `39543` |
| ocupacion.fraccion_ejecutables_rechazadas_por_cash | `0.9751905102468619` |
| ocupacion.capital_pedido_rechazado_eur | `600261095.750735` |
| ocupacion.capital_disponible_en_esos_rechazos_eur | `125980318.40747212` |
| subperiodos.por_año.2022 | `{'retorno': 0.02073586346934908, 'operaciones': 133, 'mean_R_local': 0.049779670743151205}` |
| subperiodos.por_año.2023 | `{'retorno': 0.45447545546153023, 'operaciones': 210, 'mean_R_local': 0.3698631377829637}` |
| subperiodos.por_año.2024 | `{'retorno': 0.310818819719892, 'operaciones': 218, 'mean_R_local': 0.24867470759889337}` |
| subperiodos.por_año.2025 | `{'retorno': 0.10355703949579653, 'operaciones': 246, 'mean_R_local': 0.2714409942002292}` |
| subperiodos.por_año.2026 | `{'retorno': 0.3240075172698571, 'operaciones': 199, 'mean_R_local': 0.34755732951983986}` |
| subperiodos.mitades.primera | `{'retorno': 0.798020716825409, 'operaciones': 465, 'mean_R_local': 0.30434443401816663}` |
| subperiodos.mitades.segunda | `{'retorno': 0.5677469104000206, 'operaciones': 541, 'mean_R_local': 0.24569551336243492}` |
| subperiodos.media_por_bloque_R_local_INV14_descriptiva | `0.25746316796901547` |
| criterio.etiqueta | `NO PASA` |

Rótulo de subperiodos publicado: «robustez temporal interna sobre datos de desarrollo».

Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):

- `por_region`: ASIA 0.3804 / 0.7376 / 0.6086; EMERGING_MARKETS 0.0113 / 0.1076 / 0.0993; EUROPA 0.3279 / 0.8341 / 0.5755; GLOBAL 0.0141 / 0.1386 / 0.0989; USA 0.2170 / 0.5602 / 0.4224.
- `por_divisa_cotizacion`: EUR 0.3949 / 0.8341 / 0.6233; HKD 0.0933 / 0.2799 / 0.2181; JPY 0.2414 / 0.5485 / 0.4246; USD 0.2211 / 0.5602 / 0.4116.
- `por_divisa_economica`: CNY 0.0081 / 0.1032 / 0.0955; EUR 0.2893 / 0.7083 / 0.4936; GBP 0.0237 / 0.2093 / 0.1014; HKD 0.0933 / 0.2799 / 0.2181; INR 0.0107 / 0.1048 / 0.0987; JPY 0.2508 / 0.6381 / 0.4480; KRW 0.0074 / 0.1028 / 0.0902; MULTI 0.0176 / 0.2110 / 0.0996; TWD 0.0101 / 0.1604 / 0.0680; USD 0.2398 / 0.6366 / 0.4410.
- `por_sector`: BOND_ETF 0.0059 / 0.1015 / 0.0854; Communication Services 0.0588 / 0.2356 / 0.1432; Consumer Cyclical 0.1304 / 0.3584 / 0.2609; Consumer Defensive 0.0060 / 0.1088 / 0.0809; EQUITY_ETF 0.0967 / 0.3867 / 0.2061; Energy 0.0508 / 0.2898 / 0.1500; Financial Services 0.0660 / 0.2366 / 0.1880; Healthcare 0.0123 / 0.1411 / 0.0953; Industrials 0.1761 / 0.4578 / 0.3359; Technology 0.3410 / 0.6654 / 0.5670; Utilities 0.0067 / 0.1067 / 0.0976.

## Conciliación contable publicada

El simulador impone durante la corrida, con tolerancia 1e-6 EUR, que el efectivo de cada fila del
ledger encadene con la anterior y cuadre con sus flujos, y que V_T − V_0 = Σ pnl_neto_EUR =
Σ pnl_bruto + dividendos − comisiones (`_check_identity`, `check_ledger_flows`). Si fallara, habría
lanzado `AccountingError` y escrito `p6-parada.json`, que no existe. La verificación posterior sobre
los CSV publicados está en `revision-final.md`.
