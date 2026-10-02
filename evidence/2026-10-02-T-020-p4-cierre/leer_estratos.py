"""Lector puro de los estratos congelados de P4: solo parsea `estimaciones.tsv` y lo formatea.

No calcula ninguna estimación ni ningún intervalo: copia literalmente las filas que escribió la
ejecución única (evidence/2026-10-01-T-020-p4/run/) y cuenta signos de valores ya publicados.
Escribe `estratos-congelados.md` junto a este script.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
TSV = HERE.parents[0] / "2026-10-01-T-020-p4" / "run" / "tablas" / "estimaciones.tsv"
OUT = HERE / "estratos-congelados.md"
KINDS = ("regiones", "regimenes", "terciles", "stop_basis", "activos")
LABEL = "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)"


def read_rows() -> list[dict[str, str]]:
    lines = [line for line in TSV.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def fmt(value: str) -> str:
    # Texto literal de la celda (6 decimales), con signo explícito; sin redondear de nuevo.
    return value if value.startswith("-") else f"+{value}"


def table(rows: list[dict[str, str]]) -> list[str]:
    out = ["| estrato | n pares | bloques | ΔR | IC95 inferior | IC95 superior | heterogeneidad |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        out.append(
            f"| {row['estrato']} | {row['n_pares']} | {row['n_bloques']} | {fmt(row['media_delta_r'])} | "
            f"{fmt(row['ic_inferior'])} | {fmt(row['ic_superior'])} | {row['heterogeneidad']} |"
        )
    return out


def asset_counts(rows: list[dict[str, str]]) -> str:
    deltas = [float(r["media_delta_r"]) for r in rows]
    lower = [float(r["ic_inferior"]) for r in rows]
    upper = [float(r["ic_superior"]) for r in rows]
    return (
        f"{len(rows)} activos; ΔR puntual > 0: {sum(d > 0 for d in deltas)}; < 0: {sum(d < 0 for d in deltas)}; "
        f"= 0: {sum(d == 0 for d in deltas)}; IC95 entero > 0: {sum(lo > 0 for lo in lower)}; "
        f"IC95 entero < 0: {sum(up < 0 for up in upper)}"
    )


def main() -> None:
    rows = read_rows()
    lines = [
        "# Estratos congelados de P4 (lectura literal de `estimaciones.tsv`)",
        "",
        f"_{LABEL}_",
        "",
        "Generado por `leer_estratos.py`, que solo parsea la tabla de la ejecución única. Ningún valor es nuevo.",
        "Todas las filas son descriptivas (IC95, 2.000 remuestreos, bloque 60); ninguna es confirmatoria.",
    ]
    for gid in ("B2", "S2", "S1", "B1"):
        lines += ["", f"## {gid}"]
        for kind in KINDS:
            subset = [r for r in rows if r["comparacion"] == gid and r["estimacion"] == kind]
            if not subset:
                continue
            lines += ["", f"### {kind}", ""]
            if kind == "activos":
                lines += [f"Resumen: {asset_counts(subset)}", ""]
            lines += table(subset)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for gid in ("B2", "S2", "S1"):
        subset = [r for r in rows if r["comparacion"] == gid and r["estimacion"] == "activos"]
        print(gid, asset_counts(subset))


if __name__ == "__main__":
    main()
