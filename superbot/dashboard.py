"""Dashboard HTML autocontenido para la cartera paper visible."""

from __future__ import annotations

import html
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from superbot import LABEL
from superbot.store import SuperbotStore


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _text(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/D"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    return f"{_num(value)} EUR"


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    return f"{_num(value * 100)} %"


def _qty(value: object) -> str:
    number = _float(value)
    return _num(number, 0) if number.is_integer() else _num(number, 4)


def _signed_class(value: Optional[float]) -> str:
    if value is None or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"


def _open_value(position: Dict[str, Any]) -> float:
    return _float(position["quantity"]) * _float(position["last_close"]) * _float(position["last_fx"])


def _max_drawdown(equity_curve: List[Dict[str, Any]]) -> float:
    peak: Optional[float] = None
    worst = 0.0
    for point in equity_curve:
        equity = _float(point["equity_eur"])
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            worst = min(worst, equity / peak - 1)
    return worst


def build_stats(store: SuperbotStore) -> Dict[str, Any]:
    """Calcula las métricas principales de la cartera visible."""

    config = store.config()
    initial = float(config.initial_capital_eur)
    cash = store.cash_eur()
    open_positions = store.open_positions()
    closed_positions = store.closed_positions()
    fills = store.fills()
    equity_curve = store.equity_curve()

    invested = sum(_open_value(position) for position in open_positions)
    open_pnl = sum(_open_value(position) - _float(position["cost_eur"]) for position in open_positions)
    equity = cash + invested
    realized = sum(_float(position["pnl_eur"]) for position in closed_positions)
    closed_count = len(closed_positions)
    wins = [_float(position["pnl_eur"]) for position in closed_positions if _float(position["pnl_eur"]) > 0]
    losses = [_float(position["pnl_eur"]) for position in closed_positions if _float(position["pnl_eur"]) < 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    best = max(closed_positions, key=lambda row: _float(row["pnl_eur"]), default=None)
    worst = min(closed_positions, key=lambda row: _float(row["pnl_eur"]), default=None)

    return {
        "initial_capital_eur": initial,
        "cash_eur": cash,
        "invested_eur": invested,
        "equity_eur": equity,
        "total_return_pct": equity / initial - 1 if initial else 0.0,
        "realized_pnl_eur": realized,
        "open_pnl_eur": open_pnl,
        "closed_trades": closed_count,
        "win_rate": len(wins) / closed_count if closed_count else None,
        "avg_win_eur": gross_win / len(wins) if wins else None,
        "avg_loss_eur": gross_loss / len(losses) if losses else None,
        "profit_factor": None if not losses else gross_win / abs(gross_loss),
        "expectancy_eur": realized / closed_count if closed_count else None,
        "max_drawdown_pct": _max_drawdown(equity_curve),
        "best_trade": best,
        "worst_trade": worst,
        "total_commissions_eur": sum(_float(fill["commission_eur"]) for fill in fills),
    }


def _polyline(points: List[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _line_chart(
    rows: List[Dict[str, Any]],
    value_key: str,
    title: str,
    *,
    reference: Optional[float] = None,
    percent: bool = False,
) -> str:
    width = 720
    height = 220
    pad = 28
    if len(rows) < 2:
        return (
            f'<div class="chart empty"><h2>{_text(title)}</h2>'
            '<p>sin datos todavía</p><svg viewBox="0 0 720 120" role="img" aria-label="sin datos"></svg></div>'
        )
    values = [_float(row[value_key]) for row in rows]
    if reference is not None:
        values.append(reference)
    low = min(values)
    high = max(values)
    if high == low:
        high += 1
        low -= 1

    def x_at(index: int) -> float:
        return pad + index * ((width - 2 * pad) / (len(rows) - 1))

    def y_at(value: float) -> float:
        return height - pad - ((value - low) / (high - low)) * (height - 2 * pad)

    points = [(x_at(index), y_at(_float(row[value_key]))) for index, row in enumerate(rows)]
    path = _polyline(points)
    ref_line = ""
    if reference is not None:
        y_ref = y_at(reference)
        ref_line = f'<line x1="{pad}" y1="{y_ref:.2f}" x2="{width - pad}" y2="{y_ref:.2f}" class="ref" />'
    first = _text(rows[0]["date"])
    last = _text(rows[-1]["date"])
    low_label = _pct(low) if percent else _eur(low)
    high_label = _pct(high) if percent else _eur(high)
    return f"""
    <div class="chart">
      <h2>{_text(title)}</h2>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="{_text(title)}">
        <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" class="axis" />
        <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" class="axis" />
        {ref_line}
        <polyline points="{path}" class="series" />
        <text x="{pad}" y="{height - 6}" class="tick">{first}</text>
        <text x="{width - pad}" y="{height - 6}" class="tick end">{last}</text>
        <text x="{pad + 4}" y="{pad + 12}" class="tick">{_text(high_label)}</text>
        <text x="{pad + 4}" y="{height - pad - 6}" class="tick">{_text(low_label)}</text>
      </svg>
    </div>
    """


def _drawdown_rows(equity_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    peak: Optional[float] = None
    for point in equity_curve:
        equity = _float(point["equity_eur"])
        if peak is None or equity > peak:
            peak = equity
        drawdown = equity / peak - 1 if peak and peak > 0 else 0.0
        rows.append({"date": point["date"], "drawdown": drawdown})
    return rows


def _kpi(label: str, value: str, css_class: str = "neutral") -> str:
    return f'<div class="kpi"><span>{_text(label)}</span><strong class="{css_class}">{_text(value)}</strong></div>'


def _table(headers: List[str], rows: List[List[str]], empty: str = "Sin datos") -> str:
    head = "".join(f"<th>{_text(header)}</th>" for header in headers)
    if not rows:
        return f'<table><thead><tr>{head}</tr></thead><tbody><tr><td colspan="{len(headers)}">{_text(empty)}</td></tr></tbody></table>'
    body = "".join("<tr>" + "".join(cell for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _td(value: object, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"<td{class_attr}>{_text(value)}</td>"


def _open_positions_table(rows: List[Dict[str, Any]]) -> str:
    body: List[List[str]] = []
    for row in rows:
        value = _open_value(row)
        pnl = value - _float(row["cost_eur"])
        pnl_pct = pnl / _float(row["cost_eur"]) if _float(row["cost_eur"]) else 0.0
        body.append([
            _td(row["symbol"]),
            _td(row.get("name")),
            _td(row["entry_date"]),
            _td(_qty(row["quantity"]), "num"),
            _td(f'{_num(_float(row["entry_price_native"]))} {row["currency"]}', "num"),
            _td(f'{_num(_float(row["last_close"]))} {row["currency"]}', "num"),
            _td(f'{_num(_float(row["stop"]))} {row["currency"]}', "num"),
            _td(f'{_num(_float(row["target1"]))} {"✓" if row.get("t1_hit_date") else ""}', "num"),
            _td(f'{_num(_float(row["target2"]))} {"✓" if row.get("t2_hit_date") else ""}', "num"),
            _td(_eur(value), "num"),
            _td(f"{_eur(pnl)} ({_pct(pnl_pct)})", f"num {_signed_class(pnl)}"),
        ])
    return _table(
        ["Símbolo", "Nombre", "Entrada", "Unidades", "Precio entrada", "Último", "Stop", "T1", "T2", "Valor EUR", "P&L abierto"],
        body,
    )


def _pending_orders_table(rows: List[Dict[str, Any]]) -> str:
    body = [[_td(row["id"]), _td(row["symbol"]), _td(row["side"]), _td(row["signal_date"]), _td(row.get("detail"))] for row in rows]
    return _table(["ID", "Símbolo", "Lado", "Fecha señal", "Detalle"], body)


def _closed_positions_table(rows: List[Dict[str, Any]]) -> str:
    body: List[List[str]] = []
    for row in rows:
        pnl = _float(row["pnl_eur"])
        body.append([
            _td(row["symbol"]),
            _td(row.get("name")),
            _td(row["entry_date"]),
            _td(row.get("exit_date")),
            _td(_qty(row["quantity"]), "num"),
            _td(f'{_num(_float(row["entry_price_native"]))} {row["currency"]}', "num"),
            _td(f'{_num(_float(row.get("exit_price_native")))} {row["currency"]}', "num"),
            _td(row.get("exit_reason")),
            _td(_eur(pnl), f"num {_signed_class(pnl)}"),
            _td(_pct(_float(row.get("pnl_pct"))), f"num {_signed_class(pnl)}"),
        ])
    return _table(["Símbolo", "Nombre", "Entrada", "Salida", "Unidades", "Precio entrada", "Precio salida", "Motivo", "P&L EUR", "P&L %"], body)


def _orders_table(rows: List[Dict[str, Any]]) -> str:
    body = [
        [
            _td(row["id"]),
            _td(row["symbol"]),
            _td(row["side"]),
            _td(row["status"]),
            _td(row["signal_date"]),
            _td(row.get("resolved_date")),
            _td(row.get("detail")),
        ]
        for row in rows
    ]
    return _table(["ID", "Símbolo", "Lado", "Estado", "Señal", "Resolución", "Detalle"], body)


def _fills_table(rows: List[Dict[str, Any]]) -> str:
    body = [
        [
            _td(row["bar_date"]),
            _td(row["symbol"]),
            _td(row["side"]),
            _td(row["kind"]),
            _td(_qty(row["quantity"]), "num"),
            _td(f'{_num(_float(row["price_native"]))} {row["currency"]}', "num"),
            _td(_num(_float(row["fx_rate"]), 4), "num"),
            _td(_eur(_float(row["notional_eur"])), "num"),
            _td(_eur(_float(row["commission_eur"])), "num"),
            _td(_eur(_float(row["cash_delta_eur"])), f"num {_signed_class(_float(row['cash_delta_eur']))}"),
        ]
        for row in reversed(rows)
    ]
    return _table(
        ["Sesión", "Símbolo", "Lado", "Tipo", "Unidades", "Precio", "FX", "Nocional", "Comisión", "Δ cash"], body
    )


def _stats_table(stats: Dict[str, Any]) -> str:
    best = stats["best_trade"]
    worst = stats["worst_trade"]
    rows = [
        ["Operaciones cerradas", str(stats["closed_trades"])],
        ["Win rate", _pct(stats["win_rate"])],
        ["Media ganadora", _eur(stats["avg_win_eur"])],
        ["Media perdedora", _eur(stats["avg_loss_eur"])],
        ["Profit factor", _num(stats["profit_factor"])],
        ["Expectancy por operación", _eur(stats["expectancy_eur"])],
        ["Max drawdown", _pct(stats["max_drawdown_pct"])],
        ["Mejor operación", "N/D" if best is None else f'{best["symbol"]} {_eur(_float(best["pnl_eur"]))}'],
        ["Peor operación", "N/D" if worst is None else f'{worst["symbol"]} {_eur(_float(worst["pnl_eur"]))}'],
        ["Comisiones totales", _eur(stats["total_commissions_eur"])],
    ]
    return _table(["Métrica", "Valor"], [[_td(label), _td(value, "num")] for label, value in rows])


def _runs_table(rows: List[Dict[str, Any]]) -> str:
    body = [
        [
            _td(row["id"]),
            _td(row["started_at"]),
            _td(row.get("finished_at")),
            _td(row["status"]),
            _td(row.get("symbols_ok"), "num"),
            _td(row.get("symbols_err"), "num"),
            _td(row.get("bars"), "num"),
            _td(row.get("detail")),
        ]
        for row in rows
    ]
    return _table(["ID", "Inicio", "Fin", "Estado", "OK", "Errores", "Barras", "Detalle"], body)


def render_html(store: SuperbotStore, now_label: str) -> str:
    """Renderiza una página HTML completa y autocontenida."""

    stats = build_stats(store)
    equity_curve = store.equity_curve()
    open_positions = store.open_positions()
    start_date = store.get_meta("start_date") or "N/D"
    retrospective = store.get_meta("retrospective") == "1"
    retrospective_banner = ""
    if retrospective:
        retrospective_banner = (
            f'<div class="banner secondary">ARRANQUE RETROSPECTIVO desde {_text(start_date)}: '
            "las operaciones anteriores a la primera ejecución se simularon sobre histórico</div>"
        )
    kpis = "".join([
        _kpi("Capital inicial", _eur(stats["initial_capital_eur"])),
        _kpi("Cash", _eur(stats["cash_eur"])),
        _kpi("Equity", _eur(stats["equity_eur"]), _signed_class(stats["total_return_pct"])),
        _kpi("Rentabilidad total", _pct(stats["total_return_pct"]), _signed_class(stats["total_return_pct"])),
        _kpi("P&L realizado", _eur(stats["realized_pnl_eur"]), _signed_class(stats["realized_pnl_eur"])),
        _kpi("P&L abierto", _eur(stats["open_pnl_eur"]), _signed_class(stats["open_pnl_eur"])),
        _kpi("Posiciones abiertas", str(len(open_positions))),
    ])
    generated = _text(now_label)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="300">
  <title>Superbot paper visible</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #18202f;
      --muted: #647084;
      --line: #d9e0eb;
      --red: #b42318;
      --green: #067647;
      --bad: #d92d20;
      --blue: #175cd3;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg: #101319; --panel: #171b24; --text: #edf1f7; --muted: #9aa4b2; --line: #2a3342; }}
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
    main {{ width: min(1280px, 100%); margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: clamp(1.6rem, 3vw, 2.4rem); }}
    h2 {{ margin: 0 0 14px; font-size: 1.05rem; }}
    .top {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 16px; }}
    .muted {{ color: var(--muted); }}
    .banner {{ margin: 0 0 12px; padding: 14px 16px; border-radius: 8px; background: var(--red); color: white; font-weight: 800; letter-spacing: .02em; }}
    .banner.secondary {{ background: #7a271a; font-weight: 650; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 18px 0; }}
    .kpi, section, .chart {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }}
    .kpi {{ padding: 14px; min-height: 92px; }}
    .kpi span {{ display: block; color: var(--muted); font-size: .86rem; }}
    .kpi strong {{ display: block; margin-top: 10px; font-size: 1.35rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    section, .chart {{ margin-top: 16px; padding: 16px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }}
    td.num, th.num {{ text-align: right; white-space: nowrap; }}
    .positive {{ color: var(--green); }}
    .negative {{ color: var(--bad); }}
    .neutral {{ color: var(--text); }}
    svg {{ width: 100%; height: auto; display: block; }}
    .axis {{ stroke: var(--line); stroke-width: 1; }}
    .series {{ fill: none; stroke: var(--blue); stroke-width: 3; stroke-linejoin: round; stroke-linecap: round; }}
    .ref {{ stroke: var(--muted); stroke-width: 1.5; stroke-dasharray: 6 5; }}
    .tick {{ fill: var(--muted); font-size: 12px; }}
    .tick.end {{ text-anchor: end; }}
    .empty p {{ margin: 24px 0; color: var(--muted); }}
    @media (max-width: 720px) {{
      main {{ padding: 14px; }}
      .top {{ display: block; }}
      table {{ min-width: 680px; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>Superbot paper visible</h1>
        <div class="muted">Actualizado: {generated}</div>
      </div>
    </div>
    <div class="banner">{_text(LABEL)}</div>
    {retrospective_banner}
    <div class="kpis">{kpis}</div>
    <div class="grid">
      {_line_chart(equity_curve, "equity_eur", "Curva de equity", reference=stats["initial_capital_eur"])}
      {_line_chart(_drawdown_rows(equity_curve), "drawdown", "Drawdown", percent=True)}
    </div>
    <section><h2>Posiciones abiertas</h2>{_open_positions_table(open_positions)}</section>
    <section><h2>Órdenes pendientes</h2>{_pending_orders_table(store.pending_orders())}</section>
    <section><h2>Operaciones cerradas</h2>{_closed_positions_table(store.closed_positions())}</section>
    <section><h2>Historial de operaciones (fills)</h2>{_fills_table(store.fills())}</section>
    <section><h2>Historial de órdenes</h2>{_orders_table(store.orders(200))}</section>
    <section><h2>Estadísticas</h2>{_stats_table(stats)}</section>
    <section><h2>Últimas ejecuciones</h2>{_runs_table(store.runs())}</section>
  </main>
</body>
</html>
"""


def write_html(db_path: str | Path, output_path: str | Path) -> None:
    """Escribe el dashboard estático a ``output_path``."""

    store = SuperbotStore(db_path)
    try:
        html_text = render_html(store, datetime.now().isoformat(timespec="seconds"))
    finally:
        store.close()
    Path(output_path).write_text(html_text, encoding="utf-8")


def serve(db_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Sirve el dashboard en HTTP, refrescando desde SQLite en cada petición."""

    db = Path(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                payload = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path != "/":
                self.send_error(404)
                return
            store = SuperbotStore(db)
            try:
                payload = render_html(store, datetime.now().isoformat(timespec="seconds")).encode("utf-8")
            finally:
                store.close()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()
