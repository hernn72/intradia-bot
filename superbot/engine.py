"""Motor de la cartera paper visible: señal → orden → fill → posición → salida.

Cada ejecución procesa, por símbolo, las barras diarias **cerradas** posteriores
a la última que ya procesó (``symbol_state``). La «siguiente barra» es la del
propio símbolo en su plaza: XETRA, NYSE y una plaza 24/7 no comparten sesiones,
y un símbolo cuya barra aún no ha llegado se recoge en la ejecución siguiente.

Precedencia dentro de una barra (convención fija, no observable con datos
diarios):

1. Órdenes SELL pendientes: se ejecutan en la apertura.
2. Órdenes BUY pendientes: en la apertura, con el cash de ese momento.
3. Stop de las posiciones abiertas —incluida la abierta en esta misma
   apertura—, con el stop vigente desde la víspera: si la apertura ya está en
   o bajo el stop, sale a la apertura (``GAP_STOP``); si no y el mínimo lo
   toca, sale al stop (``STOP``). Suponer que el mínimo llega después de la
   entrada es la lectura pesimista.
4. Objetivos T1/T2 tocados por el máximo (aviso, no salida).
5. Trailing con el cierre y el ATR de la barra: vale desde la sesión siguiente.
6. Señales con el cierre → órdenes PENDING para la próxima barra del símbolo.

Toda la ejecución va en una transacción: si algo falla no queda medio
procesada, y como el estado por símbolo avanza en la misma transacción, repetir
la ejecución no duplica fills ni avisos.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Protocol, Set

import pandas as pd

from superbot import notify
from superbot.config import CostParams, SuperbotConfig
from superbot.store import SuperbotStore, utcnow_iso
from superbot.strategy import evaluate, initial_levels, momentum_score, trailed_stop


class FxSource(Protocol):
    def rate(self, currency: str, on: date) -> Optional[float]:
        """EUR por 1 unidad de ``currency`` vigente en la sesión ``on``."""


@dataclass
class BarSeries:
    """Histórico diario cerrado y enriquecido de un símbolo, indexado por fecha de sesión."""

    symbol: str
    name: str
    currency: str
    frame: pd.DataFrame
    market: str = ""


@dataclass
class ProcessResult:
    bars: int = 0
    dates: List[date] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    operations: List[str] = field(default_factory=list)


def buy_price(price: float, costs: CostParams) -> float:
    return price * (1 + costs.spread_pct / 2 + costs.slippage_pct)


def sell_price(price: float, costs: CostParams) -> float:
    return price * (1 - costs.spread_pct / 2 - costs.slippage_pct)


def commission(notional_eur: float, costs: CostParams) -> float:
    if notional_eur <= 0:
        return 0.0
    return max(notional_eur * costs.commission_pct, costs.commission_fixed_eur)


class PaperEngine:
    def __init__(self, store: SuperbotStore) -> None:
        self.store = store
        self.config: SuperbotConfig = store.config()

    # --- entrada ------------------------------------------------------------

    def process(self, series: Dict[str, BarSeries], fx: FxSource, run_id: int, today: date) -> ProcessResult:
        start = self.store.start_date()
        watermarks = self.store.last_bar_dates()
        # Frontera por plaza: la sesión más reciente ya procesada entre los
        # símbolos de la misma plaza. Un símbolo nuevo (o que nunca cargó)
        # empieza ahí, no en el inicio: reconstruirlo desde el inicio abriría
        # posiciones en el pasado con el cash de hoy. Es por plaza y no global
        # porque el proveedor sirve a veces Europa con sesiones de retraso
        # respecto a EE. UU., y eso no convierte a Europa en «atrasada».
        global_frontier = max(watermarks.values()) if watermarks else None
        frontiers: Dict[str, date] = {}
        for symbol, bars in series.items():
            mark = watermarks.get(symbol)
            if mark is not None and (bars.market not in frontiers or mark > frontiers[bars.market]):
                frontiers[bars.market] = mark
        work: Dict[date, List[str]] = defaultdict(list)
        for symbol, bars in series.items():
            floor = watermarks.get(symbol) or frontiers.get(bars.market) or start - timedelta(days=1)
            for session in bars.frame.index:
                if session > floor:
                    work[session].append(symbol)

        thresholds = {bars.market: frontiers.get(bars.market, global_frontier) for bars in series.values()}

        result = ProcessResult()
        notify_from = today - timedelta(days=self.config.notify_max_age_days)
        with self.store.transaction() as conn:
            last_snapshot_row = conn.execute("SELECT MAX(date) FROM equity_snapshots").fetchone()[0]
            last_snapshot = date.fromisoformat(last_snapshot_row) if last_snapshot_row else None
            self._expire_buys(conn, today)
            for session in sorted(work):
                symbols = sorted(work[session])
                # Sesión anterior a la frontera de su plaza (o a la global, si la
                # plaza aún no tiene ninguna) = barras atrasadas: se gestiona lo que
                # ya existe —split, órdenes emitidas, salidas, stops— pero no nacen
                # señales de compra en el pasado.
                stale = {s for s in symbols if (threshold := thresholds[series[s].market]) and session < threshold}
                ctx = _Session(conn, session, run_id, fx, series, session >= notify_from, result, stale)
                for symbol in symbols:
                    self._apply_split(ctx, symbol)
                for symbol in symbols:
                    self._fill_sell(ctx, symbol)
                for symbol in symbols:
                    self._fill_buy(ctx, symbol)
                for symbol in symbols:
                    self._manage_position(ctx, symbol)
                candidates = [c for symbol in symbols if (c := self._signal(ctx, symbol)) is not None]
                self._place_buys(ctx, candidates)
                for symbol in symbols:
                    conn.execute(
                        "INSERT INTO symbol_state (symbol, last_bar_date) VALUES (?, ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET last_bar_date = excluded.last_bar_date",
                        (symbol, session.isoformat()),
                    )
                # La curva ya guardada no se reescribe con el estado de hoy.
                if last_snapshot is None or session >= last_snapshot:
                    self._snapshot(ctx)
                result.bars += len(symbols)
                result.dates.append(session)
            if result.operations:
                conn.execute(
                    "INSERT OR IGNORE INTO notifications (key, created_at, kind, text, status) "
                    "VALUES (?, ?, 'OPERACIONES', ?, 'PENDING')",
                    (f"run:{run_id}", utcnow_iso(),
                     notify.operations_message(result.operations, self._portfolio_text(conn))),
                )
        return result

    def _portfolio_text(self, conn: sqlite3.Connection) -> str:
        positions = conn.execute("SELECT * FROM positions WHERE status = 'OPEN'").fetchall()
        invested = sum(float(p["quantity"]) * float(p["last_close"]) * float(p["last_fx"]) for p in positions)
        cash = self._cash(conn)
        return notify.portfolio_block(cash + invested, cash, len(positions), self.config.initial_capital_eur)

    def _expire_buys(self, conn: sqlite3.Connection, today: date) -> None:
        """Caduca las compras pendientes por calendario, tenga o no barras el símbolo.

        Sin esto, una orden de un símbolo que deja de cargar no se resolvía nunca
        y ocupaba un hueco de la cartera para siempre.
        """

        limit = today - timedelta(days=self.config.buy_order_expiry_days)
        conn.execute(
            "UPDATE orders SET status = 'CANCELLED', resolved_date = ?, detail = 'caducada: sin barra en el plazo' "
            "WHERE side = 'BUY' AND status = 'PENDING' AND signal_date < ?",
            (today.isoformat(), limit.isoformat()),
        )

    # --- piezas -------------------------------------------------------------

    def _cash(self, conn: sqlite3.Connection) -> float:
        row = conn.execute("SELECT COALESCE(SUM(cash_delta_eur), 0) FROM fills").fetchone()
        return self.config.initial_capital_eur + float(row[0])

    def _open_position(self, conn: sqlite3.Connection, symbol: str) -> Optional[sqlite3.Row]:
        row: Optional[sqlite3.Row] = conn.execute(
            "SELECT * FROM positions WHERE symbol = ? AND status = 'OPEN'", (symbol,)
        ).fetchone()
        return row

    def _pending(self, conn: sqlite3.Connection, symbol: str, side: str, before: date) -> List[sqlite3.Row]:
        return conn.execute(
            "SELECT * FROM orders WHERE symbol = ? AND side = ? AND status = 'PENDING' AND signal_date < ? "
            "ORDER BY id",
            (symbol, side, before.isoformat()),
        ).fetchall()

    def _resolve(self, ctx: _Session, order_id: int, status: str, detail: str) -> None:
        ctx.conn.execute(
            "UPDATE orders SET status = ?, resolved_date = ?, detail = ? WHERE id = ?",
            (status, ctx.session.isoformat(), detail, order_id),
        )

    def _apply_split(self, ctx: _Session, symbol: str) -> None:
        """Reescala la posición abierta en la sesión de un split.

        El histórico del proveedor viene ajustado por splits: tras un 2:1 la
        apertura sale a mitad de precio y, sin reescalar, la posición saltaría
        por su stop con una pérdida ficticia del 50 %.
        """

        raw = ctx.row(symbol).get("Stock Splits")
        ratio = float(raw) if raw is not None and pd.notna(raw) else 0.0
        if ratio <= 0 or ratio == 1:
            return
        position = self._open_position(ctx.conn, symbol)
        if position is None or position["entry_date"] >= ctx.session.isoformat():
            return
        ctx.conn.execute(
            "UPDATE positions SET quantity = quantity * ?, entry_price_native = entry_price_native / ?, "
            "initial_stop = initial_stop / ?, stop = stop / ?, target1 = target1 / ?, target2 = target2 / ?, "
            "last_close = last_close / ? WHERE id = ?",
            (ratio, ratio, ratio, ratio, ratio, ratio, ratio, position["id"]),
        )
        ctx.emit(f"SPLIT {symbol} factor {ratio:g}")

    def _fill_sell(self, ctx: _Session, symbol: str) -> None:
        for order in self._pending(ctx.conn, symbol, "SELL", ctx.session):
            position = self._open_position(ctx.conn, symbol)
            if position is None:
                self._resolve(ctx, order["id"], "CANCELLED", "sin posición abierta")
                continue
            row = ctx.row(symbol)
            # Una salida no espera al tipo de cambio: sin el de la sesión, el último conocido.
            fx_rate = ctx.fx_rate(symbol) or float(position["last_fx"])
            self._close(ctx, position, sell_price(float(row["Open"]), self.config.costs), fx_rate,
                        "SIGNAL_EXIT", order["id"], "Señal de salida ejecutada en la apertura")
            self._resolve(ctx, order["id"], "FILLED", "ejecutada en la apertura")

    def _fill_buy(self, ctx: _Session, symbol: str) -> None:
        cfg = self.config
        for order in self._pending(ctx.conn, symbol, "BUY", ctx.session):
            signal_date = date.fromisoformat(order["signal_date"])
            if (ctx.session - signal_date).days > cfg.buy_order_expiry_days:
                self._resolve(ctx, order["id"], "CANCELLED", "caducada: sin barra en el plazo")
                continue
            if self._open_position(ctx.conn, symbol) is not None:
                self._resolve(ctx, order["id"], "CANCELLED", "ya hay posición abierta")
                continue
            fx_rate = ctx.fx_rate(symbol)
            if fx_rate is None:
                continue
            open_count = ctx.conn.execute("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'").fetchone()[0]
            if open_count >= cfg.sizing.max_positions:
                self._reject(ctx, order, f"cupo lleno ({cfg.sizing.max_positions} posiciones)")
                continue

            budget = self._budget(self._cash(ctx.conn))
            if budget < cfg.sizing.min_position_value_eur:
                self._reject(ctx, order, f"tamaño {budget:.2f} EUR por debajo del mínimo")
                continue
            row = ctx.row(symbol)
            price = buy_price(float(row["Open"]), cfg.costs)
            # Unidades enteras, como una orden manual en Trade Republic. La
            # comisión sobre el nocional real nunca supera la estimada sobre el
            # presupuesto, así que nocional + comisión ≤ presupuesto ≤ cash.
            units = math.floor((budget - commission(budget, cfg.costs)) / (price * fx_rate))
            if units < 1:
                self._reject(ctx, order, "una unidad supera el tamaño permitido")
                continue
            notional = units * price * fx_rate
            fee = commission(notional, cfg.costs)
            stop, target1, target2 = initial_levels(price, cfg.strategy)
            cursor = ctx.conn.execute(
                "INSERT INTO positions (symbol, name, currency, status, quantity, entry_order_id, entry_date, "
                "entry_price_native, entry_fx, cost_eur, initial_stop, stop, target1, target2, last_date, "
                "last_close, last_fx) VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, ctx.series[symbol].name, ctx.series[symbol].currency, units, order["id"],
                 ctx.session.isoformat(), price, fx_rate, notional + fee, stop, stop, target1, target2,
                 ctx.session.isoformat(), float(row["Open"]), fx_rate),
            )
            position_id = int(cursor.lastrowid or 0)
            ctx.conn.execute(
                "INSERT INTO fills (position_id, order_id, symbol, side, kind, bar_date, currency, price_native, "
                "fx_rate, quantity, notional_eur, commission_eur, cash_delta_eur) "
                "VALUES (?, ?, ?, 'BUY', 'ENTRY', ?, ?, ?, ?, ?, ?, ?, ?)",
                (position_id, order["id"], symbol, ctx.session.isoformat(), ctx.series[symbol].currency, price,
                 fx_rate, units, notional, fee, -(notional + fee)),
            )
            self._resolve(ctx, order["id"], "FILLED", "ejecutada en la apertura")
            position = ctx.conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
            ctx.emit(f"COMPRA {symbol} {units} uds", notify.buy_block(dict(position)))

    def _reject(self, ctx: _Session, order: sqlite3.Row, detail: str) -> None:
        self._resolve(ctx, order["id"], "REJECTED", detail)
        ctx.emit(f"ORDEN RECHAZADA {order['symbol']}: {detail}")

    def _close(self, ctx: _Session, position: sqlite3.Row, price: float, fx_rate: float, kind: str,
               order_id: Optional[int], reason: str) -> None:
        cfg = self.config
        units = float(position["quantity"])
        proceeds = units * price * fx_rate
        fee = commission(proceeds, cfg.costs)
        net = proceeds - fee
        pnl = net - float(position["cost_eur"])
        pnl_pct = pnl / float(position["cost_eur"])
        ctx.conn.execute(
            "INSERT INTO fills (position_id, order_id, symbol, side, kind, bar_date, currency, price_native, "
            "fx_rate, quantity, notional_eur, commission_eur, cash_delta_eur) "
            "VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (position["id"], order_id, position["symbol"], kind, ctx.session.isoformat(), position["currency"],
             price, fx_rate, units, proceeds, fee, net),
        )
        ctx.conn.execute(
            "UPDATE positions SET status = 'CLOSED', exit_date = ?, exit_price_native = ?, exit_fx = ?, "
            "exit_reason = ?, proceeds_eur = ?, pnl_eur = ?, pnl_pct = ? WHERE id = ?",
            (ctx.session.isoformat(), price, fx_rate, reason, net, pnl, pnl_pct, position["id"]),
        )
        closed = ctx.conn.execute("SELECT * FROM positions WHERE id = ?", (position["id"],)).fetchone()
        trailed = kind == "STOP" and float(position["stop"]) > float(position["initial_stop"])
        ctx.emit(f"VENTA {position['symbol']} ({kind}): {reason}",
                 notify.sell_block(dict(closed), "TRAILING" if trailed else kind))

    def _manage_position(self, ctx: _Session, symbol: str) -> None:
        position = self._open_position(ctx.conn, symbol)
        if position is None:
            return
        cfg = self.config
        row = ctx.row(symbol)
        fx_rate = ctx.fx_rate(symbol) or float(position["last_fx"])
        stop = float(position["stop"])
        bar_open, low, high, close = (float(row[c]) for c in ("Open", "Low", "High", "Close"))
        if bar_open <= stop:
            self._close(ctx, position, sell_price(bar_open, cfg.costs), fx_rate, "GAP_STOP", None,
                        f"Apertura {bar_open:.2f} en o bajo el stop {stop:.2f}")
            return
        if low <= stop:
            self._close(ctx, position, sell_price(stop, cfg.costs), fx_rate, "STOP", None,
                        f"Mínimo {low:.2f} tocó el stop {stop:.2f}")
            return

        updates: Dict[str, object] = {}
        for column, label in (("t1_hit_date", "target1"), ("t2_hit_date", "target2")):
            if position[column] is None and high >= float(position[label]):
                updates[column] = ctx.session.isoformat()
                name = "T1" if label == "target1" else "T2"
                ctx.emit(f"{name} TOCADO {symbol}", notify.target_block(dict(position), name))
        atr_value = row.get("atr")
        new_stop = trailed_stop(stop, close, float(atr_value) if pd.notna(atr_value) else None, cfg.strategy)
        updates.update(stop=new_stop, last_date=ctx.session.isoformat(), last_close=close, last_fx=fx_rate)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        ctx.conn.execute(f"UPDATE positions SET {assignments} WHERE id = ?", (*updates.values(), position["id"]))

    def _signal(self, ctx: _Session, symbol: str) -> Optional[_BuyCandidate]:
        """Crea la orden SELL si toca; una señal BUY se devuelve como candidata."""

        row = ctx.row(symbol)
        has_position = self._open_position(ctx.conn, symbol) is not None
        if not has_position:
            exited_today = ctx.conn.execute(
                "SELECT 1 FROM positions WHERE symbol = ? AND exit_date = ?", (symbol, ctx.session.isoformat())
            ).fetchone()
            if exited_today is not None:
                return None
        signal = evaluate(row, self.config.strategy, has_position)
        if signal.action == "HOLD" or self._has_pending(ctx, symbol, signal.action):
            return None
        if signal.action == "BUY":
            if symbol in ctx.stale:
                return None
            close = ctx.series[symbol].frame["Close"].loc[: ctx.session]
            return _BuyCandidate(symbol, signal.reason, momentum_score(close, self.config.strategy))
        order_id = self._place_order(ctx, symbol, "SELL", signal.reason, None)
        if order_id is not None:
            ctx.emit(f"ORDEN VENTA {symbol}: {signal.reason}")
        return None

    def _has_pending(self, ctx: _Session, symbol: str, side: str) -> bool:
        row = ctx.conn.execute(
            "SELECT 1 FROM orders WHERE symbol = ? AND side = ? AND status = 'PENDING'", (symbol, side)
        ).fetchone()
        return row is not None

    def _place_buys(self, ctx: _Session, candidates: List[_BuyCandidate]) -> None:
        """Como iTrade: las compras de mayor momentum primero, y solo las que caben.

        Huecos = máximo de posiciones − abiertas − compras ya pendientes; y como
        mucho ``max_new_positions_per_session`` por sesión (escalonado). Las
        candidatas que no caben no generan orden: si su señal sigue viva, vuelven
        a competir en la sesión siguiente.
        """

        candidates = [c for c in candidates if self._affordable(ctx, c.symbol)]
        if not candidates:
            return
        sizing = self.config.sizing
        open_count = ctx.conn.execute("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'").fetchone()[0]
        pending = ctx.conn.execute(
            "SELECT COUNT(*) FROM orders WHERE side = 'BUY' AND status = 'PENDING'"
        ).fetchone()[0]
        slots = min(sizing.max_positions - open_count - pending, sizing.max_new_positions_per_session)
        ranked = sorted(
            candidates,
            key=lambda c: (c.momentum if c.momentum is not None else float("-inf"), c.symbol),
            reverse=True,
        )
        for candidate in ranked[: max(slots, 0)]:
            symbol = candidate.symbol
            order_id = self._place_order(ctx, symbol, "BUY", candidate.reason, candidate.momentum)
            if order_id is not None:
                ctx.emit(f"ORDEN COMPRA {symbol}: {candidate.reason}")

    def _budget(self, cash: float) -> float:
        cfg = self.config
        return min(
            cash * cfg.sizing.max_risk_pct_per_trade / cfg.strategy.stop_loss_pct,
            cash * cfg.sizing.max_position_pct,
        )

    def _affordable(self, ctx: _Session, symbol: str) -> bool:
        """¿Cabe al menos una unidad al cierre con el cash actual?

        Sin este filtro, un valor caro se señala cada día, se rechaza cada
        apertura y le quita el hueco a otro que sí cabe. El fill vuelve a
        comprobarlo con el precio de la apertura.
        """

        fx_rate = ctx.fx_rate(symbol)
        if fx_rate is None:
            return False
        budget = self._budget(self._cash(ctx.conn))
        if budget < self.config.sizing.min_position_value_eur:
            return False
        price = buy_price(float(ctx.row(symbol)["Close"]), self.config.costs)
        return budget - commission(budget, self.config.costs) >= price * fx_rate

    def _place_order(self, ctx: _Session, symbol: str, side: str, reason: str,
                     momentum: Optional[float]) -> Optional[int]:
        row = ctx.row(symbol)

        def _num(column: str) -> Optional[float]:
            value = row.get(column)
            return float(value) if value is not None and pd.notna(value) else None

        cursor = ctx.conn.execute(
            "INSERT OR IGNORE INTO signals (run_id, symbol, bar_date, action, close, sma_fast, sma_slow, rsi, atr, "
            "momentum, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ctx.run_id, symbol, ctx.session.isoformat(), side, float(row["Close"]), _num("sma_fast"),
             _num("sma_slow"), _num("rsi"), _num("atr"), momentum, reason),
        )
        if cursor.rowcount == 0:
            return None
        order = ctx.conn.execute(
            "INSERT INTO orders (signal_id, symbol, side, status, signal_date, created_at) "
            "VALUES (?, ?, ?, 'PENDING', ?, ?)",
            (int(cursor.lastrowid or 0), symbol, side, ctx.session.isoformat(), utcnow_iso()),
        )
        return int(order.lastrowid or 0)

    def _snapshot(self, ctx: _Session) -> None:
        invested = 0.0
        positions = ctx.conn.execute("SELECT * FROM positions WHERE status = 'OPEN'").fetchall()
        for position in positions:
            fx_rate = ctx.fx.rate(position["currency"], ctx.session) or float(position["last_fx"])
            invested += float(position["quantity"]) * float(position["last_close"]) * fx_rate
        cash = self._cash(ctx.conn)
        ctx.conn.execute(
            "INSERT INTO equity_snapshots (date, cash_eur, invested_eur, equity_eur, open_positions) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(date) DO UPDATE SET cash_eur = excluded.cash_eur, "
            "invested_eur = excluded.invested_eur, equity_eur = excluded.equity_eur, "
            "open_positions = excluded.open_positions",
            (ctx.session.isoformat(), cash, invested, cash + invested, len(positions)),
        )


@dataclass(frozen=True)
class _BuyCandidate:
    symbol: str
    reason: str
    momentum: Optional[float]


@dataclass
class _Session:
    conn: sqlite3.Connection
    session: date
    run_id: int
    fx: FxSource
    series: Dict[str, BarSeries]
    notify_events: bool
    result: ProcessResult
    stale: Set[str] = field(default_factory=set)

    def row(self, symbol: str) -> pd.Series:
        row: pd.Series = self.series[symbol].frame.loc[self.session]
        return row

    def fx_rate(self, symbol: str) -> Optional[float]:
        return self.fx.rate(self.series[symbol].currency, self.session)

    def emit(self, line: str, telegram_block: Optional[str] = None) -> None:
        """Anota el evento en el log de la ejecución; las operaciones recientes van además a Telegram."""

        self.result.events.append(f"{self.session} {line}")
        if telegram_block is not None and self.notify_events:
            self.result.operations.append(telegram_block)
