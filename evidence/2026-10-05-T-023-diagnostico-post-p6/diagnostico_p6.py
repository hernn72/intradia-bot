from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/2026-10-05-T-023-diagnostico-post-p6"
RUN = ROOT / "evidence/2026-10-03-T-022-p6/run"
TABLAS = RUN / "tablas"
CAPITAL = 100000.0

PRINCIPALES = ("B2_primaria_5pb", "S2_primaria_5pb", "C0_primaria_5pb")
TODAS_BARRAS = ("B2_todas_las_barras_5pb", "S2_todas_las_barras_5pb")
SENSIBILIDAD = ("B2_sensibilidad_10pb", "S2_sensibilidad_10pb")
POLITICAS = PRINCIPALES + TODAS_BARRAS + SENSIBILIDAD
OCUPACION = PRINCIPALES + TODAS_BARRAS
SLIPPAGE: dict[str, str] = {
    "B2_primaria_5pb": "5.0pb",
    "S2_primaria_5pb": "5.0pb",
    "C0_primaria_5pb": "5.0pb",
    "B2_todas_las_barras_5pb": "5.0pb",
    "S2_todas_las_barras_5pb": "5.0pb",
    "B2_sensibilidad_10pb": "10.0pb",
    "S2_sensibilidad_10pb": "10.0pb",
}
CSV_SALIDAS = (
    "trayectorias.csv",
    "brecha-temporal.csv",
    "ocupacion-cash.csv",
    "presion-capital.csv",
    "operaciones-por-salida.csv",
    "contribucion-por-activo.csv",
    "contribucion-region-sector-divisa.csv",
    "costes-fx-dividendos.csv",
    "comparativa-primaria-todas-barras.csv",
)

FUENTES_BASE: dict[str, Any] = {
    "main_sha": "26dea364f32866d135f938f128aba541d20b6469",
    "P6_PREREG_SHA": "03f04a42ea9d2be893e7c4cc09de76bd1c55778b",
    "P6_CODE_SHA": "bc0636d4320b38ef5a620fa9ae94cee35df47580",
    "P6_RUN_HEAD_SHA": "353876d39d03f6849847743b9f4e7f791abbed30",
    "P6_RUN_EVIDENCE_SHA": "0771989af851748463aa0e79d4a7dc327066ca5f",
    "etiqueta_universo": "condicionado al universo seleccionado en 2026 (sesgo de supervivencia y selección no corregido)",
}


Row = dict[str, str]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def input_paths() -> list[str]:
    rutas = [
        "evidence/2026-10-03-T-022-p6/run/p6-resultado.json",
        "evidence/2026-10-03-T-022-p6/run/SHA256SUMS-ejecucion.txt",
        "evidence/2026-10-03-T-022-p6/run/apertura-payload.json",
    ]
    for corrida in POLITICAS:
        for sufijo in ("ledger", "operaciones", "serie-diaria"):
            rutas.append(f"evidence/2026-10-03-T-022-p6/run/tablas/{corrida}-{sufijo}.csv")
    for bench in ("benchmark_5pb", "benchmark_10pb"):
        for sufijo in ("ledger", "serie-diaria"):
            rutas.append(f"evidence/2026-10-03-T-022-p6/run/tablas/{bench}-{sufijo}.csv")
    rutas += [
        "evidence/2026-10-03-T-022-p6-datos/p6-sector-map.yaml",
        "universe.yaml",
    ]
    return sorted(rutas)


def fijar_fuentes() -> None:
    data = dict(FUENTES_BASE)
    data["inputs"] = [{"ruta": ruta, "sha256": sha256(ROOT / ruta)} for ruta in input_paths()]
    (OUT / "fuentes.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verificar_fuentes() -> None:
    path = OUT / "fuentes.json"
    if not path.exists():
        raise SystemExit("Falta fuentes.json; ejecútese una vez con --fijar-fuentes para fijar hashes.")
    data = json.loads(path.read_text(encoding="utf-8"))
    for clave, esperado in FUENTES_BASE.items():
        if data.get(clave) != esperado:
            raise SystemExit(f"fuentes.json no coincide en {clave}: {data.get(clave)!r} != {esperado!r}")
    entradas = data.get("inputs")
    if not isinstance(entradas, list):
        raise SystemExit("fuentes.json no contiene inputs como lista.")
    rutas = [e.get("ruta") for e in entradas if isinstance(e, dict)]
    if rutas != input_paths():
        raise SystemExit("La lista de inputs de fuentes.json no coincide con la lista exhaustiva esperada.")
    for entrada in entradas:
        ruta = entrada["ruta"]
        path_input = ROOT / ruta
        if not path_input.exists():
            raise SystemExit(f"Falta input fijado: {ruta}")
        actual = sha256(path_input)
        if actual != entrada["sha256"]:
            raise SystemExit(f"Hash no coincide para {ruta}: {actual} != {entrada['sha256']}")
    manifiesto = parse_manifest(RUN / "SHA256SUMS-ejecucion.txt")
    for rel, esperado in manifiesto.items():
        actual = sha256(RUN / rel)
        if actual != esperado:
            raise SystemExit(f"SHA256SUMS-ejecucion.txt no valida {rel}: {actual} != {esperado}")


def parse_manifest(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        out[rel.strip()] = digest
    return out


def read_csv(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(nombre: str, header: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    with (OUT / nombre).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(header), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: fmt(row.get(k, "")) for k in header})


def fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def f(row: Row, key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    return default if value == "" or value is None else float(value)


def serie(corrida: str) -> list[tuple[str, float]]:
    return [(r["dia"], f(r, "equity_eur")) for r in read_csv(TABLAS / f"{corrida}-serie-diaria.csv")]


def snapshots(corrida: str) -> list[tuple[str, float]]:
    return serie(corrida)[1:]


def ledger(corrida: str) -> list[Row]:
    return read_csv(TABLAS / f"{corrida}-ledger.csv")


def operaciones(corrida: str) -> list[Row]:
    return read_csv(TABLAS / f"{corrida}-operaciones.csv")


def bench_name(pb: str) -> str:
    return "benchmark_10pb" if pb == "10.0pb" else "benchmark_5pb"


def mean(xs: Sequence[float]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def median(xs: Sequence[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def percentile(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (len(ys) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def assert_close(label: str, actual: float, esperado: float, rel: float = 1e-9, abs_tol: float = 1e-9) -> None:
    if not math.isclose(actual, esperado, rel_tol=rel, abs_tol=abs_tol):
        raise SystemExit(f"Validación fallida {label}: reconstruido={actual!r}, publicado={esperado!r}")


def cargar_json() -> dict[str, Any]:
    return json.loads((RUN / "p6-resultado.json").read_text(encoding="utf-8"))


def generar_trayectorias() -> None:
    cols = ["dia", *POLITICAS, "benchmark_5pb"]
    series = {c: snapshots(c) for c in (*POLITICAS, "benchmark_5pb")}
    n = len(series["benchmark_5pb"])
    rows: list[dict[str, object]] = []
    for i in range(n):
        dia = series["benchmark_5pb"][i][0]
        row: dict[str, object] = {"dia": dia}
        for c in (*POLITICAS, "benchmark_5pb"):
            if series[c][i][0] != dia:
                raise SystemExit(f"Fechas no alineadas en trayectorias para {c} índice {i}")
            row[c] = series[c][i][1] / CAPITAL * 100.0
        rows.append(row)
    write_csv("trayectorias.csv", cols, rows)


def brecha_temporal(result: dict[str, Any]) -> None:
    rows: list[dict[str, object]] = []
    bench = snapshots("benchmark_5pb")
    for corrida in PRINCIPALES:
        sist = snapshots(corrida)
        gaps: list[tuple[str, float]] = []
        for (dia, eq), (bdia, beq) in zip(sist, bench, strict=True):
            if dia != bdia:
                raise SystemExit(f"Fechas no alineadas en brecha temporal {corrida}")
            gap = ((eq / CAPITAL - 1.0) - (beq / CAPITAL - 1.0)) * 100.0
            gaps.append((dia, gap))
            rows.append({"corrida": corrida, "tipo": "diario", "clave": f"{dia}:gap_pp", "valor": gap})
        by_year: dict[str, tuple[str, float]] = {}
        by_month_last: dict[str, tuple[str, float, float]] = {}
        for (dia, eq), (_, beq), (_, gap) in zip(sist, bench, gaps, strict=True):
            by_year[dia[:4]] = (dia, gap)
            by_month_last[dia[:7]] = (dia, eq, beq)
        for year in sorted(by_year):
            dia, gap = by_year[year]
            rows.append({"corrida": corrida, "tipo": "cierre_anio", "clave": f"{year}:{dia}:gap_pp", "valor": gap})
        mitad_idx = len(gaps) // 2
        for clave, idx in (("primera_mitad", mitad_idx), ("final", len(gaps) - 1)):
            rows.append({"corrida": corrida, "tipo": "mitad", "clave": clave + ":" + gaps[idx][0] + ":gap_pp", "valor": gaps[idx][1]})
        monthly: list[tuple[str, float, float, float]] = []
        prev_s = CAPITAL
        prev_b = CAPITAL
        for month in sorted(by_month_last):
            _, eq, beq = by_month_last[month]
            rs = eq / prev_s - 1.0
            rb = beq / prev_b - 1.0
            ex = rs - rb
            monthly.append((month, ex, rs, rb))
            rows += [
                {"corrida": corrida, "tipo": "exceso_mensual", "clave": month + ":exceso_pp", "valor": ex * 100.0},
                {"corrida": corrida, "tipo": "exceso_mensual", "clave": month + ":r_sis_pp", "valor": rs * 100.0},
                {"corrida": corrida, "tipo": "exceso_mensual", "clave": month + ":r_bench_pp", "valor": rb * 100.0},
            ]
            prev_s, prev_b = eq, beq
        for tipo, subset in (("mejores_meses", sorted(monthly, key=lambda x: (-x[1], x[0]))[:5]), ("peores_meses", sorted(monthly, key=lambda x: (x[1], x[0]))[:5])):
            for month, ex, _, _ in subset:
                rows.append({"corrida": corrida, "tipo": tipo, "clave": month + ":exceso_pp", "valor": ex * 100.0})
        rows += [
            {"corrida": corrida, "tipo": "conteo_meses", "clave": "exceso_gt_0_n", "valor": sum(1 for _, ex, _, _ in monthly if ex > 0.0)},
            {"corrida": corrida, "tipo": "conteo_meses", "clave": "exceso_lt_0_n", "valor": sum(1 for _, ex, _, _ in monthly if ex < 0.0)},
            {"corrida": corrida, "tipo": "conteo_meses", "clave": "total_n", "valor": len(monthly)},
        ]
        prev_s_year = CAPITAL
        prev_b_year = CAPITAL
        prev_log_gap = 0.0
        suma_aportes_log = 0.0
        sist_por_dia = dict(sist)
        bench_por_dia = dict(bench)
        for year in sorted(by_year):
            dia, _gap = by_year[year]
            eq = sist_por_dia[dia]
            beq = bench_por_dia[dia]
            rs_year = eq / prev_s_year - 1.0
            rb_year = beq / prev_b_year - 1.0
            ex_year = rs_year - rb_year
            log_gap = math.log(eq / beq)
            aporte = log_gap - prev_log_gap
            suma_aportes_log += aporte
            rows += [
                {"corrida": corrida, "tipo": "exceso_anual", "clave": f"{year}:r_sis_pp", "valor": rs_year * 100.0},
                {"corrida": corrida, "tipo": "exceso_anual", "clave": f"{year}:r_bench_pp", "valor": rb_year * 100.0},
                {"corrida": corrida, "tipo": "exceso_anual", "clave": f"{year}:exceso_pp", "valor": ex_year * 100.0},
                {"corrida": corrida, "tipo": "log_gap", "clave": f"{year}:{dia}:log_adimensional", "valor": log_gap},
                {"corrida": corrida, "tipo": "log_gap_aporte_anual", "clave": f"{year}:log_adimensional", "valor": aporte},
            ]
            prev_s_year = eq
            prev_b_year = beq
            prev_log_gap = log_gap
        final_log_gap = math.log(sist[-1][1] / bench[-1][1])
        assert_close(f"suma aportes log_gap {corrida}", suma_aportes_log, final_log_gap)
        rows.append({"corrida": corrida, "tipo": "log_gap", "clave": f"final:{sist[-1][0]}:log_adimensional", "valor": final_log_gap})
        max_gap = max(gaps, key=lambda x: (x[1], x[0]))
        min_gap = min(gaps, key=lambda x: (x[1], x[0]))
        rows += [
            {"corrida": corrida, "tipo": "gap_max", "clave": max_gap[0] + ":gap_pp", "valor": max_gap[1]},
            {"corrida": corrida, "tipo": "gap_min", "clave": min_gap[0] + ":gap_pp", "valor": min_gap[1]},
            {"corrida": corrida, "tipo": "inicio_apertura", "clave": "definicion", "valor": "Primera fecha desde la cual el gap ya no vuelve a ser >= 0 hasta el final."},
        ]
        inicio = ""
        for i, (dia, _gap) in enumerate(gaps):
            if all(g < 0.0 for _, g in gaps[i:]):
                inicio = dia
                break
        rows.append({"corrida": corrida, "tipo": "inicio_apertura", "clave": "gap_pp_siempre_negativo_desde_fecha", "valor": inicio})
        for hito in (-5.0, -10.0, -20.0):
            fecha = next((dia for dia, gap in gaps if gap <= hito), "")
            rows.append({"corrida": corrida, "tipo": "inicio_apertura", "clave": f"primer_gap_le_{hito}_pp", "valor": fecha})
        fechas = result["corridas"][corrida]["trayectoria"]
        for clave_json, etiqueta in (("dd_pico", "pico_sistema"), ("dd_valle", "valle_sistema"), ("dd_recuperacion", "recuperacion_sistema")):
            dia = fechas[clave_json]
            rows.append({"corrida": corrida, "tipo": "alrededor_dd", "clave": etiqueta + ":" + dia + ":gap_pp", "valor": dict(gaps)[dia]})
        bdd = result["benchmark"]["5.0pb"]
        for clave_json, etiqueta in (("dd_pico", "pico_benchmark"), ("dd_valle", "valle_benchmark"), ("dd_recuperacion", "recuperacion_benchmark")):
            dia = bdd[clave_json]
            rows.append({"corrida": corrida, "tipo": "alrededor_dd", "clave": etiqueta + ":" + dia + ":gap_pp", "valor": dict(gaps)[dia]})
        final_gap = gaps[-1][1]
        publicado = result["corridas"][corrida]["exceso"]["excess_terminal_pp"]
        assert_close(f"brecha final {corrida}", final_gap, publicado, rel=1e-9, abs_tol=1e-7)
    write_csv("brecha-temporal.csv", ["corrida", "tipo", "clave", "valor"], rows)


def reconstruir_ocupacion(corrida: str) -> list[dict[str, float | str]]:
    led = ledger(corrida)
    snaps = snapshots(corrida)
    out: list[dict[str, float | str]] = []
    idx = 0
    cash = CAPITAL
    posiciones = 0
    for dia, eq in snaps:
        limite = dia + "T23:59:59Z"
        while idx < len(led) and led[idx]["timestamp_utc"] <= limite:
            row = led[idx]
            cash = f(row, "cash_after", cash)
            if row["event_type"] == "ENTRY":
                posiciones += 1
            elif row["event_type"] == "EXIT":
                posiciones -= 1
            idx += 1
        out.append({"dia": dia, "cash": cash, "equity": eq, "exposicion": 1.0 - cash / eq, "posiciones": float(posiciones)})
    return out


def ocupacion_cash(result: dict[str, Any]) -> None:
    rows: list[dict[str, object]] = []
    bench_ret = retornos_diarios("benchmark_5pb")
    for corrida in OCUPACION:
        rec = reconstruir_ocupacion(corrida)
        exp = [float(r["exposicion"]) for r in rec]
        cash_ratio = [float(r["cash"]) / float(r["equity"]) for r in rec]
        cash_abs = [float(r["cash"]) for r in rec]
        pos = [float(r["posiciones"]) for r in rec]
        pub = result["corridas"][corrida]["exposicion"]
        assert_close(f"exposición media {corrida}", mean(exp), pub["exposicion_media"])
        assert_close(f"cash medio {corrida}", mean(cash_ratio), pub["cash_medio"])
        assert_close(f"cash mínimo {corrida}", min(cash_abs), pub["cash_minimo_eur"])
        assert_close(f"posiciones media {corrida}", mean(pos), pub["posiciones_media"])
        assert_close(f"posiciones max {corrida}", max(pos), float(pub["posiciones_max"]))
        for clave, reconstruido, publicado in (
            ("exposicion_media", mean(exp), pub["exposicion_media"]),
            ("cash_medio_fraccion", mean(cash_ratio), pub["cash_medio"]),
            ("cash_minimo_eur", min(cash_abs), pub["cash_minimo_eur"]),
            ("posiciones_media", mean(pos), pub["posiciones_media"]),
            ("posiciones_max", max(pos), float(pub["posiciones_max"])),
        ):
            rows.append({"corrida": corrida, "tipo": "resumen", "clave": clave + "_reconstruida", "valor": reconstruido})
            rows.append({"corrida": corrida, "tipo": "resumen", "clave": clave + "_publicada", "valor": publicado})
        rows.append({"corrida": corrida, "tipo": "resumen", "clave": "exposicion_p95_publicada", "valor": pub["exposicion_p95"]})
        dist = Counter(int(x) for x in pos)
        for k in sorted(dist):
            rows.append({"corrida": corrida, "tipo": "distribucion_posiciones", "clave": k, "valor": dist[k]})
        rows.append({"corrida": corrida, "tipo": "bucket_exposicion", "clave": "definicion", "valor": "Retorno r_t=V_t/V_{t-1}-1; exposición al cierre del día t-1."})
        ret_s = retornos_diarios(corrida)
        buckets = [("[0,0.25]", 0.0, 0.25), ("(0.25,0.5]", 0.25, 0.5), ("(0.5,0.75]", 0.5, 0.75), ("(0.75,0.9]", 0.75, 0.9), ("(0.9,1]", 0.9, 1.0)]
        for label, lo, hi in buckets:
            vals_s: list[float] = []
            vals_b: list[float] = []
            for i in range(1, len(rec)):
                eprev = float(rec[i - 1]["exposicion"])
                ok = (lo == 0.0 and 0.0 <= eprev <= hi) or (lo < eprev <= hi)
                if ok:
                    dia = str(rec[i]["dia"])
                    vals_s.append(ret_s[dia])
                    vals_b.append(bench_ret[dia])
            exceso = [a - b for a, b in zip(vals_s, vals_b, strict=True)]
            for metrica, valor in (
                ("dias", float(len(vals_s))),
                ("media_r_sis", mean(vals_s)),
                ("mediana_r_sis", median(vals_s)),
                ("media_r_bench", mean(vals_b)),
                ("mediana_r_bench", median(vals_b)),
                ("media_exceso", mean(exceso)),
                ("mediana_exceso", median(exceso)),
                ("suma_exceso", sum(exceso)),
            ):
                rows.append({"corrida": corrida, "tipo": "bucket_exposicion", "clave": f"{label}:{metrica}", "valor": valor})
        for label, lo, hi in buckets:
            por_anio: Counter[str] = Counter()
            for item in rec:
                e = float(item["exposicion"])
                ok = (lo == 0.0 and 0.0 <= e <= hi) or (lo < e <= hi)
                if ok:
                    por_anio[str(item["dia"])[:4]] += 1
            for year in sorted(por_anio):
                rows.append({"corrida": corrida, "tipo": "bucket_exposicion_por_anio", "clave": f"{year}:{label}:dias", "valor": por_anio[year]})
    write_csv("ocupacion-cash.csv", ["corrida", "tipo", "clave", "valor"], rows)


def retornos_diarios(corrida: str) -> dict[str, float]:
    s = serie(corrida)
    out: dict[str, float] = {}
    for i in range(1, len(s)):
        out[s[i][0]] = s[i][1] / s[i - 1][1] - 1.0
    return out


def equity_previa_fecha(snaps: Sequence[tuple[str, float]], dia_entry: str) -> float:
    prev = CAPITAL
    for dia, eq in snaps:
        if dia >= dia_entry:
            return prev
        prev = eq
    return prev


def presion_capital(result: dict[str, Any]) -> None:
    rows: list[dict[str, object]] = []
    for corrida in OCUPACION:
        led = ledger(corrida)
        pub = result["corridas"][corrida]["ocupacion"]
        counts = Counter(r["event_type"] for r in led)
        reason_rej = Counter(r["reason"] for r in led if r["event_type"] == "ENTRY_REJECTED")
        reason_ign = Counter(r["reason"] for r in led if r["event_type"] == "SIGNAL_IGNORED")
        for event in ("SIGNAL_PENDING", "ENTRY", "ENTRY_REJECTED"):
            rows.append({"corrida": corrida, "tipo": "evento", "clave": event, "valor": counts[event]})
        for reason in sorted(reason_rej):
            rows.append({"corrida": corrida, "tipo": "ENTRY_REJECTED", "clave": reason, "valor": reason_rej[reason]})
        for reason in sorted(reason_ign):
            rows.append({"corrida": corrida, "tipo": "SIGNAL_IGNORED", "clave": reason, "valor": reason_ign[reason]})
        insuf = [r for r in led if r["event_type"] == "ENTRY_REJECTED" and r["reason"] == "INSUFFICIENT_CASH"]
        entradas = counts["ENTRY"]
        frac = len(insuf) / (entradas + len(insuf)) if entradas + len(insuf) else 0.0
        assert_close(f"fracción rechazadas cash {corrida}", frac, pub["fraccion_ejecutables_rechazadas_por_cash"])
        cap_pedido = sum(f(r, "cash_requerido_base") for r in insuf)
        cap_disp = sum(f(r, "cash_after") for r in insuf)
        assert_close(f"capital pedido rechazado {corrida}", cap_pedido, pub["capital_pedido_rechazado_eur"], rel=1e-9, abs_tol=1e-6)
        assert_close(f"capital disponible rechazos {corrida}", cap_disp, pub["capital_disponible_en_esos_rechazos_eur"], rel=1e-9, abs_tol=1e-6)
        for clave, valor in (
            ("fraccion_insufficient_cash_sobre_ejecutables", frac),
            ("fraccion_publicada", pub["fraccion_ejecutables_rechazadas_por_cash"]),
            ("capital_pedido_rechazado_eur", cap_pedido),
            ("capital_disponible_en_esos_rechazos_eur", cap_disp),
            ("ratio_pedido_disponible", cap_pedido / cap_disp if cap_disp else 0.0),
        ):
            rows.append({"corrida": corrida, "tipo": "resumen", "clave": clave, "valor": valor})
        for periodo_len, tipo in ((4, "por_anio"), (7, "por_mes")):
            agg: dict[str, Counter[str]] = defaultdict(Counter)
            for r in led:
                clave = r["session_date"][:periodo_len]
                if r["event_type"] == "ENTRY":
                    agg[clave]["entradas"] += 1
                elif r["event_type"] == "EXIT":
                    agg[clave]["salidas"] += 1
                elif r["event_type"] == "ENTRY_REJECTED" and r["reason"] == "INSUFFICIENT_CASH":
                    agg[clave]["rechazos_cash"] += 1
                elif tipo == "por_anio" and r["event_type"] == "ENTRY_REJECTED" and r["reason"] == "ABOVE_MAX_ENTRY":
                    agg[clave]["rechazos_above_max_entry"] += 1
                elif tipo == "por_anio" and r["event_type"] == "ENTRY_REJECTED" and r["reason"] == "INVALID_STOP":
                    agg[clave]["rechazos_invalid_stop"] += 1
                elif tipo == "por_anio" and r["event_type"] == "ENTRY_REJECTED" and r["reason"] == "INVALID_TARGET":
                    agg[clave]["rechazos_invalid_target"] += 1
                elif tipo == "por_anio" and r["event_type"] == "SIGNAL_IGNORED" and r["reason"] == "IGNORED_ALREADY_OPEN":
                    agg[clave]["ignoradas_ya_abierta"] += 1
            for clave in sorted(agg):
                metricas = ["entradas", "rechazos_cash", "salidas"]
                if tipo == "por_anio":
                    metricas += ["rechazos_above_max_entry", "rechazos_invalid_stop", "rechazos_invalid_target", "ignoradas_ya_abierta"]
                for metrica in metricas:
                    rows.append({"corrida": corrida, "tipo": tipo, "clave": f"{clave}:{metrica}", "valor": agg[clave][metrica]})
        dias_inst = {d for d, _ in snapshots(corrida)}
        rechazo_dia = Counter(r["session_date"] for r in insuf)
        dias_rechazo = sum(1 for d in rechazo_dia if d in dias_inst)
        rows.append({"corrida": corrida, "tipo": "dias_rechazo_cash", "clave": "n", "valor": dias_rechazo})
        rows.append({"corrida": corrida, "tipo": "dias_rechazo_cash", "clave": "fraccion_sobre_instantaneas", "valor": dias_rechazo / len(dias_inst)})
        señales_dia = Counter(r["session_date"] for r in led if r["event_type"] in {"SIGNAL_PENDING", "ENTRY_REJECTED", "SIGNAL_IGNORED"})
        rechazos_con_senal = [float(rechazo_dia[d]) for d in sorted(señales_dia)]
        for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            rows.append({"corrida": corrida, "tipo": "percentil_rechazos_cash_por_dia_con_senal", "clave": f"p{int(q*100)}", "valor": percentile(rechazos_con_senal, q)})
    write_csv("presion-capital.csv", ["corrida", "tipo", "clave", "valor"], rows)


def operaciones_por_salida(result: dict[str, Any]) -> None:
    rows: list[dict[str, object]] = []
    for corrida in OCUPACION:
        ops = operaciones(corrida)
        led = ledger(corrida)
        entry_by_position = {r["position_id"]: r for r in led if r["event_type"] == "ENTRY"}
        snaps_corrida = snapshots(corrida)
        rvals = [f(r, "trade_R_local") for r in ops]
        pos = sum(x for x in rvals if x > 0.0)
        neg = sum(x for x in rvals if x < 0.0)
        pf = pos / abs(neg) if neg else math.inf
        assert_close(f"profit factor local {corrida}", pf, result["corridas"][corrida]["operaciones"]["profit_factor_local"])
        win_rate = mean([1.0 if f(r, "pnl_neto_eur") > 0.0 else 0.0 for r in ops])
        assert_close(f"win rate eur {corrida}", win_rate, result["corridas"][corrida]["operaciones"]["win_rate"])
        resumen = {
            "N": len(ops),
            "win_rate": win_rate,
            "win_rate_local": mean([1.0 if f(r, "pnl_neto_local") > 0.0 else 0.0 for r in ops]),
            "mean_R_local": mean(rvals),
            "median_R_local": median(rvals),
            "profit_factor_local": pf,
            "holding_medio": mean([f(r, "bars_held") for r in ops]),
            "p10_R_local": percentile(rvals, 0.1),
            "p25_R_local": percentile(rvals, 0.25),
            "p50_R_local": percentile(rvals, 0.5),
            "p75_R_local": percentile(rvals, 0.75),
            "p90_R_local": percentile(rvals, 0.9),
            "pnl_ganadores_eur": sum(f(r, "pnl_neto_eur") for r in ops if f(r, "pnl_neto_eur") > 0.0),
            "pnl_perdedores_eur": sum(f(r, "pnl_neto_eur") for r in ops if f(r, "pnl_neto_eur") < 0.0),
        }
        for k, v in resumen.items():
            rows.append({"corrida": corrida, "tipo": "resumen", "clave": k, "valor": v})
        for reason in sorted({r["exit_reason"] for r in ops}):
            part = [r for r in ops if r["exit_reason"] == reason]
            for k, v in {
                "N": len(part),
                "mean_R_local": mean([f(r, "trade_R_local") for r in part]),
                "median_R_local": median([f(r, "trade_R_local") for r in part]),
                "pnl_neto_eur": sum(f(r, "pnl_neto_eur") for r in part),
                "holding_medio": mean([f(r, "bars_held") for r in part]),
            }.items():
                rows.append({"corrida": corrida, "tipo": "exit_reason", "clave": f"{reason}:{k}", "valor": v})
        for year in sorted({r["exit_ts"][:4] for r in ops}):
            part = [r for r in ops if r["exit_ts"].startswith(year)]
            for k, v in {
                "N": len(part),
                "mean_R": mean([f(r, "trade_R_local") for r in part]),
                "pnl_neto_eur": sum(f(r, "pnl_neto_eur") for r in part),
                "R_total_eur": sum(f(r, "trade_R_eur") for r in part),
                "mean_R_eur": mean([f(r, "trade_R_eur") for r in part]),
            }.items():
                rows.append({"corrida": corrida, "tipo": "anio_salida", "clave": f"{year}:{k}", "valor": v})
        risk_vals = [f(r, "risk_eur") for r in ops]
        ratios_risk: list[float] = []
        ratios_notional: list[float] = []
        identidad_lhs = 0.0
        identidad_rhs = 0.0
        for op in ops:
            pos_id = op["position_id"]
            if pos_id not in entry_by_position:
                raise SystemExit(f"No se encuentra ENTRY para {corrida} position_id={pos_id}")
            entry = entry_by_position[pos_id]
            dia_entry = op["entry_ts"][:10]
            eq_prev = equity_previa_fecha(snaps_corrida, dia_entry)
            ratios_risk.append(f(op, "risk_eur") / eq_prev)
            ratios_notional.append(f(entry, "notional_base") / eq_prev)
            identidad_lhs += f(op, "trade_R_eur") * f(op, "risk_eur")
            identidad_rhs += f(op, "pnl_neto_eur")
        assert_close(f"identidad R*risk=pnl {corrida}", identidad_lhs, identidad_rhs, rel=1e-9, abs_tol=1e-6)
        for k, v in {
            "risk_eur_media": mean(risk_vals),
            "risk_eur_mediana": median(risk_vals),
            "risk_eur_sobre_equity_previa_media": mean(ratios_risk),
            "notional_entrada_sobre_equity_previa_media": mean(ratios_notional),
            "identidad_trade_R_eur_por_risk_eur": identidad_lhs,
            "identidad_pnl_neto_eur": identidad_rhs,
        }.items():
            rows.append({"corrida": corrida, "tipo": "riesgo_tamano", "clave": k, "valor": v})
    write_csv("operaciones-por-salida.csv", ["corrida", "tipo", "clave", "valor"], rows)


def contribucion_activo(result: dict[str, Any]) -> dict[str, dict[str, float]]:
    rows: list[dict[str, object]] = []
    contribs: dict[str, dict[str, float]] = {}
    notional_entry: dict[str, dict[str, float]] = {}
    activos_operados: dict[str, set[str]] = {}
    for corrida in OCUPACION:
        ops = operaciones(corrida)
        pnl: dict[str, float] = defaultdict(float)
        nops: Counter[str] = Counter()
        for r in ops:
            pnl[r["asset"]] += f(r, "pnl_neto_eur")
            nops[r["asset"]] += 1
        notionals: dict[str, float] = defaultdict(float)
        for r in ledger(corrida):
            if r["event_type"] == "ENTRY":
                notionals[r["asset"]] += f(r, "notional_base")
        contribs[corrida] = dict(pnl)
        notional_entry[corrida] = dict(notionals)
        activos_operados[corrida] = set(pnl)
        total = sum(pnl.values())
        esperado = snapshots(corrida)[-1][1] - CAPITAL
        assert_close(f"contribución activos política {corrida}", total, esperado, rel=1e-9, abs_tol=1e-6)
        for asset in sorted(pnl):
            rows.append({"corrida": corrida, "tipo": "activo", "clave": asset, "operaciones": nops[asset], "pnl_neto_eur": pnl[asset], "notional_entrada_eur": notionals[asset], "valor": pnl[asset]})
        filas_resumen(rows, corrida, pnl)
    for bench in ("benchmark_5pb",):
        bcontrib = benchmark_contrib(bench)
        pesos_benchmark = benchmark_pesos_iniciales(bench)
        contribs[bench] = bcontrib
        total = sum(bcontrib.values())
        esperado = snapshots(bench)[-1][1] - CAPITAL
        assert_close(f"contribución activos {bench}", total, esperado, rel=1e-9, abs_tol=1e-6)
        for asset in sorted(bcontrib):
            rows.append({"corrida": bench, "tipo": "activo", "clave": asset, "operaciones": "", "pnl_neto_eur": bcontrib[asset], "notional_entrada_eur": "", "valor": bcontrib[asset]})
        filas_resumen(rows, bench, bcontrib)
        top10 = {a for a, _ in sorted(bcontrib.items(), key=lambda x: (-x[1], x[0]))[:10]}
        top20 = {a for a, _ in sorted(bcontrib.items(), key=lambda x: (-x[1], x[0]))[:20]}
        for base, conjunto in (("top10_benchmark", top10), ("top20_benchmark", top20)):
            for pol in ("B2_primaria_5pb", "S2_primaria_5pb"):
                pnl_pol = contribs[pol]
                total_pol = sum(pnl_pol.values())
                total_notional_pol = sum(notional_entry[pol].values())
                notional_conjunto = sum(v for a, v in notional_entry[pol].items() if a in conjunto)
                val = sum(v for a, v in pnl_pol.items() if a in conjunto)
                rows += [
                    {"corrida": pol, "tipo": base, "clave": "activos_operados", "operaciones": len(conjunto & activos_operados[pol]), "pnl_neto_eur": "", "notional_entrada_eur": "", "valor": ""},
                    {"corrida": pol, "tipo": base, "clave": "fraccion_pnl", "operaciones": "", "pnl_neto_eur": val, "notional_entrada_eur": "", "valor": val / total_pol if total_pol else 0.0},
                    {"corrida": pol, "tipo": base, "clave": "notional_asignado", "operaciones": "", "pnl_neto_eur": "", "notional_entrada_eur": notional_conjunto, "valor": ""},
                    {"corrida": pol, "tipo": base, "clave": "fraccion_notional", "operaciones": "", "pnl_neto_eur": "", "notional_entrada_eur": notional_conjunto, "valor": notional_conjunto / total_notional_pol if total_notional_pol else 0.0},
                    {"corrida": pol, "tipo": base, "clave": "peso_inicial_benchmark", "operaciones": "", "pnl_neto_eur": "", "notional_entrada_eur": "", "valor": sum(v for a, v in pesos_benchmark.items() if a in conjunto)},
                ]
    write_csv("contribucion-por-activo.csv", ["corrida", "tipo", "clave", "operaciones", "pnl_neto_eur", "notional_entrada_eur", "valor"], rows)
    return contribs


def filas_resumen(rows: list[dict[str, object]], corrida: str, pnl: dict[str, float]) -> None:
    total = sum(pnl.values())
    ordered = sorted(pnl.items(), key=lambda x: (-x[1], x[0]))
    bottom = sorted(pnl.items(), key=lambda x: (x[1], x[0]))[:5]
    for label, subset in (("top5", ordered[:5]), ("top10", ordered[:10]), ("bottom5", bottom)):
        rows.append({"corrida": corrida, "tipo": "resumen", "clave": label, "operaciones": "", "pnl_neto_eur": sum(v for _, v in subset), "notional_entrada_eur": "", "valor": ";".join(f"{a}:{v!r}" for a, v in subset)})
    rows.append({"corrida": corrida, "tipo": "resumen", "clave": "fraccion_top5", "valor": sum(v for _, v in ordered[:5]) / total if total else 0.0})
    rows.append({"corrida": corrida, "tipo": "resumen", "clave": "fraccion_top10", "valor": sum(v for _, v in ordered[:10]) / total if total else 0.0})
    rows.append({"corrida": corrida, "tipo": "resumen", "clave": "activos_contribucion_positiva", "valor": sum(1 for v in pnl.values() if v > 0.0)})
    rows.append({"corrida": corrida, "tipo": "resumen", "clave": "activos_contribucion_negativa", "valor": sum(1 for v in pnl.values() if v < 0.0)})


def benchmark_contrib(bench: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in ledger(bench):
        asset = r["asset"]
        if r["event_type"] == "BH_BUY":
            out[asset] -= f(r, "notional_base") + f(r, "fee_base")
        elif r["event_type"] == "BH_SELL_FINAL":
            out[asset] += f(r, "notional_base") - f(r, "fee_base")
        elif r["event_type"] == "BH_DIVIDEND":
            out[asset] += f(r, "dividend_base")
    return dict(out)


def benchmark_pesos_iniciales(bench: str) -> dict[str, float]:
    buys = {r["asset"]: f(r, "notional_base") + f(r, "fee_base") for r in ledger(bench) if r["event_type"] == "BH_BUY"}
    total = sum(buys.values())
    if total <= 0.0:
        raise SystemExit(f"No hay compras iniciales BH_BUY para {bench}")
    return {asset: value / total for asset, value in buys.items()}


def universe_maps() -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    uni = yaml.safe_load((ROOT / "universe.yaml").read_text(encoding="utf-8"))
    meta: dict[str, dict[str, str]] = {}
    for items in uni["groups"].values():
        for item in items:
            sym = item["primary_symbol"]
            meta[sym] = {
                "region": item["region"],
                "divisa_cotizacion": item["primary_currency"],
                "divisa_economica": item["economic_currency"],
            }
    sector_yaml = yaml.safe_load((ROOT / "evidence/2026-10-03-T-022-p6-datos/p6-sector-map.yaml").read_text(encoding="utf-8"))
    sectores = {item["asset"]: item["sector"] for item in sector_yaml["instrumentos"]}
    return meta, sectores


def contribucion_dims(result: dict[str, Any], contribs: dict[str, dict[str, float]]) -> None:
    meta, sectores = universe_maps()
    rows: list[dict[str, object]] = []
    for corrida in PRINCIPALES:
        pnl = contribs[corrida]
        notionals: dict[str, float] = defaultdict(float)
        nops: Counter[str] = Counter()
        for r in operaciones(corrida):
            nops[r["asset"]] += 1
        for r in ledger(corrida):
            if r["event_type"] == "ENTRY":
                notionals[r["asset"]] += f(r, "notional_base")
        total = sum(pnl.values())
        for dim in ("region", "sector", "divisa_cotizacion"):
            pub_key = {"region": "por_region", "sector": "por_sector", "divisa_cotizacion": "por_divisa_cotizacion"}[dim]
            agg: dict[str, dict[str, float]] = defaultdict(lambda: {"operaciones": 0.0, "notional": 0.0, "pnl": 0.0})
            for asset, val in pnl.items():
                key = dim_value(asset, dim, meta, sectores)
                agg[key]["pnl"] += val
                agg[key]["operaciones"] += nops[asset]
                agg[key]["notional"] += notionals[asset]
            for key in sorted(agg):
                pub = result["corridas"][corrida]["exposicion"][pub_key].get(key, {}).get("media", "")
                rows.append({"corrida": corrida, "dimension": dim, "clave": key, "operaciones": agg[key]["operaciones"], "notional_entrada_eur": agg[key]["notional"], "pnl_neto_eur": agg[key]["pnl"], "fraccion_total": agg[key]["pnl"] / total if total else 0.0, "exposicion_media_publicada": pub, "activos": ""})
    bcontrib = contribs["benchmark_5pb"]
    total_b = sum(bcontrib.values())
    for dim in ("region", "sector", "divisa_cotizacion"):
        agg_b: dict[str, dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "activos": 0.0})
        for asset, val in bcontrib.items():
            key = dim_value(asset, dim, meta, sectores)
            agg_b[key]["pnl"] += val
            agg_b[key]["activos"] += 1.0
        for key in sorted(agg_b):
            rows.append({"corrida": "benchmark_5pb", "dimension": dim, "clave": key, "operaciones": "", "notional_entrada_eur": "", "pnl_neto_eur": agg_b[key]["pnl"], "fraccion_total": agg_b[key]["pnl"] / total_b if total_b else 0.0, "exposicion_media_publicada": "", "activos": agg_b[key]["activos"]})
    write_csv("contribucion-region-sector-divisa.csv", ["corrida", "dimension", "clave", "operaciones", "notional_entrada_eur", "pnl_neto_eur", "fraccion_total", "exposicion_media_publicada", "activos"], rows)


def dim_value(asset: str, dim: str, meta: dict[str, dict[str, str]], sectores: dict[str, str]) -> str:
    if asset not in meta:
        raise SystemExit(f"Activo {asset} no aparece en universe.yaml")
    if asset not in sectores:
        raise SystemExit(f"Activo {asset} no aparece en p6-sector-map.yaml")
    if dim == "sector":
        return sectores[asset]
    return meta[asset][dim]


def costes_fx_dividendos(result: dict[str, Any]) -> None:
    rows: list[dict[str, object]] = []
    for corrida in POLITICAS:
        led = ledger(corrida)
        ops = operaciones(corrida)
        vals = {
            "comisiones": sum(f(r, "fee_base") for r in led),
            "slippage": sum(f(r, "slippage_base") for r in led),
            "dividendos": sum(f(r, "dividend_base") for r in led),
            "fx": sum(f(r, "fx_eur") for r in ops),
        }
        pub = result["corridas"][corrida]
        assert_close(f"costes {corrida}", vals["comisiones"], pub["costes_eur"], rel=1e-9, abs_tol=1e-6)
        assert_close(f"slippage {corrida}", vals["slippage"], pub["slippage_eur"], rel=1e-9, abs_tol=1e-6)
        assert_close(f"dividendos {corrida}", vals["dividendos"], pub["dividendos_eur"], rel=1e-9, abs_tol=1e-6)
        assert_close(f"fx {corrida}", vals["fx"], pub["fx_eur"], rel=1e-9, abs_tol=1e-6)
        final = snapshots(corrida)[-1][1] - CAPITAL
        bench_profit = snapshots(bench_name(SLIPPAGE[corrida]))[-1][1] - CAPITAL
        brecha = final - bench_profit
        for comp, val in vals.items():
            rows.append({"corrida": corrida, "componente": comp, "valor_eur": val, "frac_capital_inicial": val / CAPITAL, "frac_beneficio_neto_final": val / final if final else "", "brecha_final_eur": brecha, "frac_abs_brecha": val / abs(brecha) if brecha else "", "motivo": ""})
    for bench in ("benchmark_5pb", "benchmark_10pb"):
        led = ledger(bench)
        vals_b = {
            "comisiones": sum(f(r, "fee_base") for r in led),
            "slippage": sum(f(r, "slippage_base") for r in led),
            "dividendos": sum(f(r, "dividend_base") for r in led),
        }
        final_b = snapshots(bench)[-1][1] - CAPITAL
        for comp, val in vals_b.items():
            rows.append({"corrida": bench, "componente": comp, "valor_eur": val, "frac_capital_inicial": val / CAPITAL, "frac_beneficio_neto_final": val / final_b if final_b else "", "brecha_final_eur": "", "frac_abs_brecha": "", "motivo": ""})
        rows.append({"corrida": bench, "componente": "fx", "valor_eur": "", "frac_capital_inicial": "", "frac_beneficio_neto_final": "", "brecha_final_eur": "", "frac_abs_brecha": "", "motivo": "NO_IDENTIFICABLE: el ledger benchmark no separa efecto FX realizado como columna fx_eur."})
    write_csv("costes-fx-dividendos.csv", ["corrida", "componente", "valor_eur", "frac_capital_inicial", "frac_beneficio_neto_final", "brecha_final_eur", "frac_abs_brecha", "motivo"], rows)


def comparativa(result: dict[str, Any]) -> None:
    rows: list[dict[str, object]] = []
    corridas = ("B2_primaria_5pb", "B2_todas_las_barras_5pb", "S2_primaria_5pb", "S2_todas_las_barras_5pb", "C0_primaria_5pb")
    for corrida in corridas:
        c = result["corridas"][corrida]
        vals = {
            "N": c["operaciones"]["n_closed"],
            "PF": c["operaciones"]["profit_factor_local"],
            "mean_R": c["operaciones"]["mean_R_local"],
            "max_DD": c["trayectoria"]["max_drawdown"],
            "CAGR": c["trayectoria"]["cagr"],
            "excess_CAGR_pp": c["exceso"]["excess_CAGR_pp"],
            "exposicion_media": c["exposicion"]["exposicion_media"],
            "cash_medio": c["exposicion"]["cash_medio"],
            "posiciones_media": c["exposicion"]["posiciones_media"],
            "posiciones_max": c["exposicion"]["posiciones_max"],
            "turnover_anual": c["turnover"]["turnover_anual"],
            "holding": c["operaciones"]["holding_medio_barras"],
            "fraccion_rechazada_cash": c["ocupacion"]["fraccion_ejecutables_rechazadas_por_cash"],
            "senales": result["senales"][corrida]["senales"],
            "entradas": c["ocupacion"]["entradas"],
        }
        for k, v in vals.items():
            rows.append({"corrida": corrida, "tipo": "metrica", "clave": k, "valor": v})
        rot: dict[str, Counter[str]] = defaultdict(Counter)
        for r in ledger(corrida):
            year = r["session_date"][:4]
            if r["event_type"] == "ENTRY":
                rot[year]["entradas"] += 1
            elif r["event_type"] == "EXIT":
                rot[year]["salidas"] += 1
        for year in sorted(rot):
            rows.append({"corrida": corrida, "tipo": "rotacion_anual", "clave": f"{year}:entradas", "valor": rot[year]["entradas"]})
            rows.append({"corrida": corrida, "tipo": "rotacion_anual", "clave": f"{year}:salidas", "valor": rot[year]["salidas"]})
    b = result["benchmark"]["5.0pb"]
    for k in ("equity_final", "retorno_total", "cagr", "max_drawdown"):
        rows.append({"corrida": "benchmark_5pb", "tipo": "metrica", "clave": k, "valor": b[k]})
    write_csv("comparativa-primaria-todas-barras.csv", ["corrida", "tipo", "clave", "valor"], rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fijar-fuentes", action="store_true")
    args = parser.parse_args()
    if args.fijar_fuentes:
        fijar_fuentes()
        return
    verificar_fuentes()
    result = cargar_json()
    generar_trayectorias()
    brecha_temporal(result)
    ocupacion_cash(result)
    presion_capital(result)
    operaciones_por_salida(result)
    contribs = contribucion_activo(result)
    contribucion_dims(result, contribs)
    costes_fx_dividendos(result)
    comparativa(result)


if __name__ == "__main__":
    main()
