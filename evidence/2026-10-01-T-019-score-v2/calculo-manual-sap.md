# Cálculo manual SAP.DE

- signal_id: `SAP.DE|swing|2022-06-12T22:00:00Z`
- signal_timestamp crudo: `2022-06-12T22:00:00+00:00`
- sesión de señal (XETRA): `2022-06-13`
- sesión de entrada (XETRA): `2022-06-14`
- catalizador v1: 1.000000000 / 20.0
- técnico v1: 0.000000000 / 20.0
- contexto PIT: 1.200000000 / 10.0
- RR v1: 20.000000000 / 20.0
- convicción v1: 10.000000000 / 10.0
- evaluable_max v1: 80.0
- Score v1 PIT: 40.250000000
- Score v2: 4.400000000

Score v2 = 100 x (1.000000000 + 0.000000000 + 1.200000000) / 50 = 4.400000000.
Comprobación automática: `100·(cat+tec+ctx)/50 == record.score` -> `4.400000000 == 4.400000000`.
Cortes swing congelados: 28.0 / 39.6 / 49.6 / 57.6; quintil: Q1.

No se consulta `net_R`.
