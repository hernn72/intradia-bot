"""Transcribe p6-resultado.json a resultado-p6.md sin recalcular nada ni abrir la cosecha.

Cada número es `repr()` del valor que escribió la ejecución única de P6; las versiones redondeadas que
aparecen junto a él son solo para leer. No importa nada de `advisor`.

Uso, desde la raíz del repositorio:
python evidence/2026-10-05-T-022-p6-cierre/transcribir_resultado.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

RUN = Path("evidence/2026-10-03-T-022-p6/run")
OUT = Path(__file__).with_name("resultado-p6.md")
EVIDENCE_COMMIT = "0771989af851748463aa0e79d4a7dc327066ca5f"

PRIMARY = ("B2_primaria_5pb", "S2_primaria_5pb")
DESCRIPTIVE = ("C0_primaria_5pb", "B2_sensibilidad_10pb", "S2_sensibilidad_10pb",
               "B2_todas_las_barras_5pb", "S2_todas_las_barras_5pb")
CONDITIONS = ("N_closed>=100", "profit_factor_local>1", "mean_R_local>0", "max_drawdown>=-25%",
              "excess_CAGR_pp>0")


def pct(value: float) -> str:
    return f"{value * 100:.4f} %"


def row(cells: List[Any]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def criterion_value(run: Dict[str, Any], name: str) -> str:
    ops, path, excess = run["operaciones"], run["trayectoria"], run["exceso"]
    return {
        "N_closed>=100": repr(ops["n_closed"]),
        "profit_factor_local>1": repr(ops["profit_factor_local"]),
        "mean_R_local>0": repr(ops["mean_R_local"]),
        "max_drawdown>=-25%": f"{path['max_drawdown']!r} ({pct(path['max_drawdown'])})",
        "excess_CAGR_pp>0": repr(excess["excess_CAGR_pp"]),
    }[name]


def run_block(run_id: str, run: Dict[str, Any]) -> List[str]:
    path, ops, exp = run["trayectoria"], run["operaciones"], run["exposicion"]
    lines = [f"### `{run_id}`", ""]
    lines.append(row(["Métrica", "Valor publicado"]))
    lines.append(row(["---", "---"]))
    for key in ("equity_inicial", "equity_final", "retorno_total", "cagr", "volatilidad", "sharpe_rf0",
                "sortino_mar0", "max_drawdown", "dd_pico", "dd_valle", "dd_recuperacion", "dd_duracion_dias",
                "calmar"):
        lines.append(row([f"trayectoria.{key}", f"`{path[key]!r}`"]))
    for key, value in ops.items():
        lines.append(row([f"operaciones.{key}", f"`{value!r}`"]))
    for key in ("exposicion_media", "exposicion_max", "exposicion_p95", "cash_medio", "cash_minimo_eur",
                "posiciones_media", "posiciones_max"):
        lines.append(row([f"exposicion.{key}", f"`{exp[key]!r}`"]))
    for key, value in run["turnover"].items():
        lines.append(row([f"turnover.{key}", f"`{value!r}`"]))
    for key in ("costes_eur", "slippage_eur", "dividendos_eur", "fx_eur"):
        lines.append(row([key, f"`{run[key]!r}`"]))
    for key, value in run["exceso"].items():
        lines.append(row([f"exceso.{key}", f"`{value!r}`"]))
    for key, value in run["contadores"].items():
        lines.append(row([f"contadores.{key}", f"`{value!r}`"]))
    for key, value in run["ocupacion"].items():
        lines.append(row([f"ocupacion.{key}", f"`{value!r}`"]))
    sub = run["subperiodos"]
    for year, values in sub["por_año"].items():
        lines.append(row([f"subperiodos.por_año.{year}", f"`{values!r}`"]))
    for half, values in sub["mitades"].items():
        lines.append(row([f"subperiodos.mitades.{half}", f"`{values!r}`"]))
    lines.append(row(["subperiodos.media_por_bloque_R_local_INV14_descriptiva",
                      f"`{sub['media_por_bloque_R_local_INV14_descriptiva']!r}`"]))
    lines.append(row(["criterio.etiqueta", f"`{run['criterio']['etiqueta']}`"]))
    lines.append("")
    lines.append(f"Rótulo de subperiodos publicado: «{sub['rotulo']}».")
    lines.append("")
    lines.append("Exposición por región, divisa de cotización, divisa económica y sector (media / máx. / p95):")
    lines.append("")
    for group in ("por_region", "por_divisa_cotizacion", "por_divisa_economica", "por_sector"):
        parts = [f"{name} {v['media']:.4f} / {v['max']:.4f} / {v['p95']:.4f}" for name, v in exp[group].items()]
        lines.append(f"- `{group}`: " + "; ".join(parts) + ".")
    lines.append("")
    return lines


def main() -> int:
    result = json.loads((RUN / "p6-resultado.json").read_text(encoding="utf-8"))
    runs: Dict[str, Any] = result["corridas"]
    window = result["ventana"]
    out: List[str] = [
        "# Resultado congelado de P6 (T-022 / A-06)",
        "",
        f"_{result['label'][0].upper()}{result['label'][1:]}._",
        "",
        f"Transcripción de `{RUN}/p6-resultado.json` (commit `{EVIDENCE_COMMIT}`), generada por",
        "`transcribir_resultado.py`. **No se recalcula nada**: cada valor entre comillas invertidas es `repr()` del",
        "número que escribió la ejecución única; los porcentajes redondeados son solo para leer. P6 no se repite.",
        "",
        "## Identidad",
        "",
        row(["", ""]),
        row(["---", "---"]),
        row(["`P6_PREREG_SHA`", "`03f04a42ea9d2be893e7c4cc09de76bd1c55778b`"]),
        row(["`P6_CODE_SHA`", "`bc0636d4320b38ef5a620fa9ae94cee35df47580`"]),
        row(["`P6_RUN_HEAD_SHA`", "`353876d39d03f6849847743b9f4e7f791abbed30`"]),
        row(["`P6_RUN_EVIDENCE_SHA`", f"`{EVIDENCE_COMMIT}`"]),
        row(["`P6_DATA_ID`", "`572e09141dbfe0fc9c53a7b529f1abcff46e16027fe9b47d1f3e26330c1e5383`"]),
        row(["`fase`", f"`{result['fase']}`"]),
        row(["`token_sha256` = sha256 de la marca", f"`{result['token_sha256']}`"]),
        row(["`fin_utc`", f"`{result['fin_utc']}`"]),
        "",
        "Ventana publicada: " + ", ".join(f"`{k}` = `{v!r}`" for k, v in window.items()) + ".",
        "",
        "## Criterio decisorio (T-022 §16, D-69): corridas primarias a 5 pb",
        "",
        row(["Condición", "B2: valor", "B2", "S2: valor", "S2"]),
        row(["---", "---", "---", "---", "---"]),
    ]
    for name in CONDITIONS:
        cells = [f"`{name}`"]
        for run_id in PRIMARY:
            cells += [f"`{criterion_value(runs[run_id], name)}`",
                      "cumple" if runs[run_id]["criterio"]["condiciones"][name] else "**NO cumple**"]
        out.append(row(cells))
    out.append(row(["**Etiqueta**", "", f"**{runs[PRIMARY[0]]['criterio']['etiqueta']}**", "",
                    f"**{runs[PRIMARY[1]]['criterio']['etiqueta']}**"]))
    out += [
        "",
        f"`etiquetas_decisorias` = `{result['etiquetas_decisorias']!r}`.",
        "",
        f"**Supervivientes: `{result['supervivientes']!r}`.**",
        "",
        "En las dos candidatas se cumplen las condiciones 1 a 4 y falla **exclusivamente** la 5,",
        "`excess_CAGR_pp > 0`. Con la regla fijada ex ante (§16: cumple la 1 e incumple alguna de las demás),",
        "la etiqueta es `NO PASA`.",
        "",
        "## Benchmark: comprar y mantener del propio universo a pesos iguales (§14)",
        "",
        row(["Métrica", "5 pb", "10 pb"]),
        row(["---", "---", "---"]),
    ]
    bench = result["benchmark"]
    for key in bench["5.0pb"]:
        out.append(row([key, f"`{bench['5.0pb'][key]!r}`", f"`{bench['10.0pb'][key]!r}`"]))
    out += [
        "",
        "## Resumen de las nueve corridas",
        "",
        "Solo las dos primeras filas deciden. El resto es **descriptivo**: no veta, no rescata y no cambia",
        "ninguna etiqueta ni la salida (§16 y D-69).",
        "",
        row(["Corrida", "Papel", "N_closed", "PF local", "mean_R_local", "Max DD", "CAGR", "excess_CAGR_pp",
             "Etiqueta publicada"]),
        row(["---"] * 9),
    ]
    roles = {"B2_primaria_5pb": "**decisoria**", "S2_primaria_5pb": "**decisoria**",
             "C0_primaria_5pb": "control descriptivo", "B2_sensibilidad_10pb": "sensibilidad descriptiva",
             "S2_sensibilidad_10pb": "sensibilidad descriptiva",
             "B2_todas_las_barras_5pb": "puente descriptivo", "S2_todas_las_barras_5pb": "puente descriptivo"}
    for run_id in PRIMARY + DESCRIPTIVE:
        r = runs[run_id]
        out.append(row([f"`{run_id}`", roles[run_id], r["operaciones"]["n_closed"],
                        f"{r['operaciones']['profit_factor_local']:.4f}", f"{r['operaciones']['mean_R_local']:.4f}",
                        pct(r["trayectoria"]["max_drawdown"]), pct(r["trayectoria"]["cagr"]),
                        f"{r['exceso']['excess_CAGR_pp']:.4f}", f"`{r['criterio']['etiqueta']}`"]))
    out += [
        "",
        "El simulador también calcula una etiqueta para las corridas descriptivas porque aplica la misma",
        "función a las siete. Esas etiquetas **no son decisorias**: `etiquetas_decisorias` y `supervivientes`",
        "se derivan solo de `B2_primaria_5pb` y `S2_primaria_5pb`.",
        "",
        "## Señales (`senales`)",
        "",
    ]
    for run_id, counts in result["senales"].items():
        out.append(f"- `{run_id}`: `{counts!r}`")
    out += ["", "## Detalle completo por corrida", ""]
    for run_id in PRIMARY + DESCRIPTIVE:
        out += run_block(run_id, runs[run_id])
    out += [
        "## Conciliación contable publicada",
        "",
        "El simulador impone durante la corrida, con tolerancia 1e-6 EUR, que el efectivo de cada fila del",
        "ledger encadene con la anterior y cuadre con sus flujos, y que V_T − V_0 = Σ pnl_neto_EUR =",
        "Σ pnl_bruto + dividendos − comisiones (`_check_identity`, `check_ledger_flows`). Si fallara, habría",
        "lanzado `AccountingError` y escrito `p6-parada.json`, que no existe. La verificación posterior sobre",
        "los CSV publicados está en `revision-final.md`.",
        "",
    ]
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"ok: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
