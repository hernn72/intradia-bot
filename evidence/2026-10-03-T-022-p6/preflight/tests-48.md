# Los 48 tests obligatorios de T-022 §20

_condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)_

Salida de `pytest -v tests/test_p6.py` sobre el ejecutor congelado. Todos con datos sintéticos o identidades estructurales.

| # | Requisito (T-022 §20) | Test pytest | Estado |
|---|---|---|---|
| 1 | una operación simple sin costes | `test_t01_operacion_simple_sin_costes` | PASSED |
| 2 | sizing por riesgo | `test_t02_sizing_por_riesgo` | PASSED |
| 3 | tope del 10 % | `test_t03_tope_del_10_por_ciento` | PASSED |
| 4 | cash insuficiente → `INSUFFICIENT_CASH` | `test_t04_cash_insuficiente` | PASSED |
| 5 | dos entradas simultáneas | `test_t05_dos_entradas_simultaneas` | PASSED |
| 6 | orden determinista por `sha256(b"intradia.p6.desempate.v1" + signal_id.encode("utf-8")).hexdigest()` | `test_t06_desempate_sha256_sin_alfabeto` | PASSED |
| 7 | stop por hueco | `test_t07_stop_por_hueco` | PASSED |
| 8 | stop y objetivo en la misma vela → stop | `test_t08_stop_y_objetivo_misma_vela_gana_stop` | PASSED |
| 9 | una salida intradía no financia una entrada anterior a su cierre | `test_t09_salida_intradia_no_financia_entrada_anterior` | PASSED |
| 10 | una salida en Asia libera cash para una apertura posterior en Estados Unidos | `test_t10_salida_en_asia_financia_apertura_posterior_en_eeuu` | PASSED |
| 11 | dividendo ex | `test_t11_dividendo_ex` | PASSED |
| 12 | compra en la fecha ex sin dividendo | `test_t12_compra_en_fecha_ex_sin_dividendo` | PASSED |
| 13 | venta en la apertura ex con derecho | `test_t13_venta_en_apertura_ex_con_derecho` | PASSED |
| 14 | split 2:1 | `test_t14_split_2_a_1` | PASSED |
| 15 | FX constante | `test_t15_fx_constante` | PASSED |
| 16 | FX que se mueve sin que se mueva el activo | `test_t16_fx_se_mueve_sin_mover_el_activo` | PASSED |
| 17 | exposición por divisa de cotización frente a `economic_currency` (incluido `MULTI`) | `test_t17_exposicion_divisa_cotizacion_frente_a_economica` | PASSED |
| 18 | turnover | `test_t18_turnover` | PASSED |
| 19 | max DD con fechas | `test_t19_max_drawdown_con_fechas` | PASSED |
| 20 | Sharpe y Sortino | `test_t20_sharpe_y_sortino` | PASSED |
| 21 | benchmark con pesos iguales | `test_t21_benchmark_pesos_iguales` | PASSED |
| 22 | dividendo del benchmark reinvertido | `test_t22_dividendo_del_benchmark_reinvertido` | PASSED |
| 23 | conciliación del ledger | `test_t23_conciliacion_del_ledger` | PASSED |
| 24 | `system_sha256` de B2 y S2 | `test_t24_system_sha256_de_b2_y_s2` | PASSED |
| 25 | C0 como control | `test_t25_c0_como_control` | PASSED |
| 26 | el mismo resultado repetido byte a byte | `test_t26_mismo_resultado_byte_a_byte` | PASSED |
| 27 | `IGNORED_ALREADY_OPEN` contado | `test_t27_ignored_already_open_contado` | PASSED |
| 28 | FX con `timestamp_available` posterior al evento → no se usa | `test_t28_fx_posterior_al_evento_no_se_usa` | PASSED |
| 29 | instantánea a las 23:59:59 UTC sin cierres futuros | `test_t29_instantanea_sin_cierres_futuros` | PASSED |
| 30 | activo tardío (ARM) que entra al terminar su calentamiento | `test_t30_activo_tardio_entra_al_terminar_su_calentamiento` | PASSED |
| 31 | dividendo en un activo con split (escala coherente) | `test_t31_dividendo_en_activo_con_split` | PASSED |
| 32 | ejecutabilidad con precio efectivo que rechaza una entrada que el precio observado admitiría | `test_t32_precio_efectivo_rechaza_lo_que_el_observado_admitiria` | PASSED |
| 33 | coste 0,10 % + 0,10 % = coste de P4 cuando X = E | `test_t33_coste_igual_a_p4_cuando_salida_igual_a_entrada` | PASSED |
| 34 | cash nunca negativo bajo entradas simultáneas | `test_t34_cash_nunca_negativo_con_entradas_simultaneas` | PASSED |
| 35 | el `policy_sha256` de P5 se regenera dentro del preflight | `test_t35_policy_sha256_de_p5_se_regenera` | PASSED |
| 36 | contrasplit (factor 0,5) | `test_t36_contrasplit` | PASSED |
| 37 | cash insuficiente solo por la comisión | `test_t37_cash_insuficiente_solo_por_la_comision` | PASSED |
| 38 | PF sin pérdidas con n ≥ N_min | `test_t38_pf_sin_perdidas_con_n_minimo` | PASSED |
| 39 | sesión del calendario sin barra (entrada en la barra siguiente) | `test_t39_sesion_sin_barra_entra_en_la_barra_siguiente` | PASSED |
| 40 | contexto point-in-time: `available_at ≤ analysis_timestamp` para VIX, tendencia, Asia y la serie | `test_t40_contexto_point_in_time_causal` | PASSED |
| 41 | clave de desempate común a B2, S2 y C0 e independiente del `system_sha256` | `test_t41_desempate_comun_e_independiente_del_system_sha256` | PASSED |
| 42 | R local frente a R en EUR con FX que se mueve (el veto usa el local) | `test_t42_r_local_frente_a_r_eur_decide_el_local` | PASSED |
| 43 | sentido del FX (`EURUSD=X` = 1,10 → 1 USD = 0,909 EUR) | `test_t43_sentido_del_fx` | PASSED |
| 44 | sizing una vez por lote: el orden del lote no cambia el tamaño | `test_t44_sizing_una_vez_por_lote` | PASSED |
| 45 | una posición comprada después de su último cierre se valora a su entrada efectiva hasta su primer | `test_t45_posicion_comprada_tras_su_cierre_se_valora_a_su_entrada` | PASSED |
| 46 | `MarketContext.source == "point_in_time"` en todas las señales con score (nunca `legacy_v1`) | `test_t46_contexto_point_in_time_nunca_legacy` | PASSED |
| 47 | una salida de cierre con el mismo instante que una apertura de otra plaza no financia esa entrada | `test_t47_salida_de_cierre_empatada_no_financia_apertura_de_otra_plaza` | PASSED |
| 48 | cadena causal por plaza: `cierre de la sesión t disponible ≤ analysis_timestamp < apertura de la | `test_t48_cadena_causal_por_plaza[XETRA]`<br>`test_t48_cadena_causal_por_plaza[PAR]`<br>`test_t48_cadena_causal_por_plaza[AMS]`<br>`test_t48_cadena_causal_por_plaza[MIL]`<br>`test_t48_cadena_causal_por_plaza[MCE]`<br>`test_t48_cadena_causal_por_plaza[NYSE]`<br>`test_t48_cadena_causal_por_plaza[NASDAQ]`<br>`test_t48_cadena_causal_por_plaza[JPX]`<br>`test_t48_cadena_causal_por_plaza[HKG]` | PASSED |

**48/48 PASSED.** Ausentes: ninguno.
