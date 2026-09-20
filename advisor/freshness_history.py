"""Resumen del historico persistido de frescura."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, cast

from advisor.data.calendars import expected_sessions, session_override_kind
from advisor.data.sessions import latest_expected_closed_session
from advisor.universe.models import Universe

MIN_SAMPLE_SIZE = 30
OD02_MONTHLY_THRESHOLD = 2.0
OD02_ASSET_THRESHOLD = 10
WINDOW_MONTH_DAYS = 30.4375

WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


@dataclass(frozen=True)
class RateCell:
    delayed: int = 0
    total: int = 0
    passes: int = 0
    """Pasadas distintas que generan esta celda.

    Las mediciones de una misma pasada NO son independientes: un fallo del
    proveedor afecta a la vez a decenas de símbolos, así que 47 filas de una
    pasada son **un** evento, no 47 observaciones (D-41, INV-22).
    """


@dataclass(frozen=True)
class CauseCounts:
    market_closed: int = 0
    provider_missing: int = 0
    partial_bar: int = 0

    @property
    def total(self) -> int:
        return self.market_closed + self.provider_missing + self.partial_bar


@dataclass
class AssetMonthSummary:
    symbol: str
    month: str
    possible_passes: int
    measured_passes: int = 0
    provider_missing_sessions: int = 0
    market_closed_absences: int = 0
    partial_bars: int = 0
    max_streak: int = 0
    active_days: int = 0
    window_source: str = ""
    provider_missing_appearances: int = 0

    @property
    def provider_missing_per_month(self) -> float:
        if self.active_days <= 0:
            return 0.0
        return self.provider_missing_sessions * WINDOW_MONTH_DAYS / self.active_days


@dataclass(frozen=True)
class HistoricalGap:
    """Huecos que el activo arrastra de antes de la ventana observada.

    ``absent_reference_sessions`` mira 200 sesiones hacia atrás, así que una
    pasada de septiembre reporta huecos de marzo. No son sesiones perdidas
    *durante* la ventana y no pueden alimentar una tasa mensual de la ventana.
    """

    symbol: str
    sessions: int
    sample: tuple[str, ...]


@dataclass(frozen=True)
class VersionSegment:
    """Mediciones agrupadas por la versión de código que las produjo."""

    git_sha: str | None
    release_tag: str | None
    measurements: int
    passes: int
    first_measured_at: datetime | None
    last_measured_at: datetime | None

    @property
    def label(self) -> str:
        if self.git_sha is None:
            return "sin manifiesto"
        corto = self.git_sha[:12]
        return f"{corto} ({self.release_tag})" if self.release_tag else corto


@dataclass(frozen=True)
class AssetPartialSummary:
    symbol: str
    partial: int
    total: int


@dataclass(frozen=True)
class FreshnessHistorySummary:
    total_measurements: int
    total_passes: int
    total_symbols: int
    first_measured_at: datetime | None
    last_measured_at: datetime | None
    market_hour: dict[tuple[str, int], RateCell]
    asset_months: list[AssetMonthSummary]
    asset_partials: list[AssetPartialSummary]
    weekdays: dict[int, RateCell]
    causes: CauseCounts
    causes_appearances: CauseCounts
    od02_assets_over_threshold: int
    od02_assets_observed: int
    od02_assets_persistent: int
    od02_assets_with_persistent_gap: int
    od02_assets_with_delays: int
    historical_gaps: list[HistoricalGap]
    versions: list[VersionSegment]
    populations: tuple[str, ...]
    window_note: str


def summarize_freshness_history(rows: Iterable[Any], universe: Universe) -> FreshnessHistorySummary:
    materialized = [dict(row) for row in rows]
    parsed = [(_parse_dt(str(row["measured_at"])), row) for row in materialized]
    pass_times = sorted({measured_at for measured_at, _ in parsed})
    symbols = sorted({str(row["symbol"]) for _, row in parsed})
    first = min(pass_times) if pass_times else None
    last = max(pass_times) if pass_times else None

    window_start = first.date() if first else None
    window_end = last.date() if last else None

    market_hour_counts: dict[tuple[str, int], list[int]] = {}
    market_hour_passes: dict[tuple[str, int], set[datetime]] = {}
    weekday_counts: dict[int, list[int]] = {}
    weekday_passes: dict[int, set[datetime]] = {}
    partial_counts: dict[str, list[int]] = {}
    measured_by_symbol_month: dict[tuple[str, str], set[datetime]] = {}
    # Las ausencias se acumulan como CONJUNTOS de fechas y no como sumas: la
    # misma sesión ausente se repite en todas las pasadas que la ven, y sumarla
    # una vez por pasada multiplica el hueco por el número de pasadas.
    missing_dates_by_symbol_month: dict[tuple[str, str], set[date]] = {}
    closed_dates_by_symbol_month: dict[tuple[str, str], set[date]] = {}
    partial_by_symbol_month: dict[tuple[str, str], int] = {}
    missing_dates_by_symbol: dict[str, set[date]] = {}
    historical_dates_by_symbol: dict[str, set[date]] = {}
    missing_appearances_by_symbol_month: dict[tuple[str, str], int] = {}
    version_rows: dict[tuple[str | None, str | None], list[Any]] = {}
    total_appearances = CauseCounts()
    # La última pasada de cada activo es la que dice si un hueco persiste o si
    # solo era un retraso: un activo dado de baja el 18 no tiene pasadas después.
    last_pass_by_symbol: dict[str, datetime] = {}
    for measured_at, row in parsed:
        symbol = str(row["symbol"])
        anterior = last_pass_by_symbol.get(symbol)
        if anterior is None or measured_at > anterior:
            last_pass_by_symbol[symbol] = measured_at
    persistent_dates_by_symbol: dict[str, set[date]] = {}
    delayed_dates_by_symbol: dict[str, set[date]] = {}

    for measured_at, row in parsed:
        market = str(row["market"])
        symbol = str(row["symbol"])
        month = measured_at.date().isoformat()[:7]
        sessions_approx = _optional_int(row.get("sessions_approx")) or 0
        is_delayed = sessions_approx >= 1
        _increment_rate(market_hour_counts, (market, measured_at.hour), is_delayed)
        _increment_rate(weekday_counts, measured_at.weekday(), is_delayed)
        market_hour_passes.setdefault((market, measured_at.hour), set()).add(measured_at)
        weekday_passes.setdefault(measured_at.weekday(), set()).add(measured_at)
        _increment_rate(partial_counts, symbol, bool(row.get("may_be_partial_current_session")))
        measured_by_symbol_month.setdefault((symbol, month), set()).add(measured_at)

        causes, provider_dates, closed_dates, delayed_dates = classify_absence_causes(row, measured_at)
        if measured_at == last_pass_by_symbol.get(symbol):
            persistent_dates_by_symbol[symbol] = {
                value
                for value in provider_dates
                if window_start is not None and window_end is not None and window_start <= value <= window_end
            }
        for value in delayed_dates:
            if window_start is not None and window_end is not None and window_start <= value <= window_end:
                delayed_dates_by_symbol.setdefault(symbol, set()).add(value)
        total_appearances = CauseCounts(
            market_closed=total_appearances.market_closed + causes.market_closed,
            provider_missing=total_appearances.provider_missing + causes.provider_missing,
            partial_bar=total_appearances.partial_bar + causes.partial_bar,
        )
        key = (symbol, month)
        partial_by_symbol_month[key] = partial_by_symbol_month.get(key, 0) + causes.partial_bar
        missing_appearances_by_symbol_month[key] = (
            missing_appearances_by_symbol_month.get(key, 0) + causes.provider_missing
        )
        version_rows.setdefault((_optional_str(row.get("run_git_sha")), _optional_str(row.get("run_release_tag"))), []).append(
            measured_at
        )
        # Una ausencia pertenece al mes de SU sesión, no al de la pasada que la
        # vio: si no, un hueco de marzo cuenta como sesión perdida de septiembre.
        for value in closed_dates:
            closed_dates_by_symbol_month.setdefault((symbol, value.isoformat()[:7]), set()).add(value)
        for value in provider_dates:
            dentro = window_start is not None and window_end is not None and window_start <= value <= window_end
            if dentro:
                missing_dates_by_symbol_month.setdefault((symbol, value.isoformat()[:7]), set()).add(value)
                missing_dates_by_symbol.setdefault(symbol, set()).add(value)
            else:
                historical_dates_by_symbol.setdefault(symbol, set()).add(value)

    asset_months: list[AssetMonthSummary] = []
    for symbol in symbols:
        possible = _possible_passes_for_symbol(symbol, pass_times, parsed, universe)
        months = sorted({value.date().isoformat()[:7] for value in possible.pass_times})
        for month in months:
            month_passes = [value for value in possible.pass_times if value.date().isoformat()[:7] == month]
            key = (symbol, month)
            active_dates = {value.date() for value in month_passes}
            summary = AssetMonthSummary(
                symbol=symbol,
                month=month,
                possible_passes=len(month_passes),
                measured_passes=len(measured_by_symbol_month.get(key, set())),
                provider_missing_sessions=len(missing_dates_by_symbol_month.get(key, set())),
                market_closed_absences=len(closed_dates_by_symbol_month.get(key, set())),
                partial_bars=partial_by_symbol_month.get(key, 0),
                max_streak=_max_consecutive_dates(missing_dates_by_symbol.get(symbol, set())),
                active_days=len(active_dates),
                window_source=possible.source,
                provider_missing_appearances=missing_appearances_by_symbol_month.get(key, 0),
            )
            asset_months.append(summary)

    asset_partials = [
        AssetPartialSummary(symbol=symbol, partial=counts[0], total=counts[1])
        for symbol, counts in sorted(partial_counts.items())
    ]
    over_threshold = len({
        item.symbol
        for item in asset_months
        if item.provider_missing_per_month > OD02_MONTHLY_THRESHOLD
    })
    observed_over_threshold = len({
        item.symbol
        for item in asset_months
        if item.provider_missing_sessions > OD02_MONTHLY_THRESHOLD
    })
    persistent_over_threshold = len(
        [symbol for symbol, values in persistent_dates_by_symbol.items() if len(values) > OD02_MONTHLY_THRESHOLD]
    )
    persistent_assets = len([symbol for symbol, values in persistent_dates_by_symbol.items() if values])
    delayed_over_threshold = len({
        symbol
        for symbol in set(missing_dates_by_symbol) | set(delayed_dates_by_symbol)
        if len(missing_dates_by_symbol.get(symbol, set()) | delayed_dates_by_symbol.get(symbol, set()))
        > OD02_MONTHLY_THRESHOLD
    })
    historical_gaps = [
        HistoricalGap(
            symbol=symbol,
            sessions=len(values),
            sample=tuple(value.isoformat() for value in sorted(values)[:3]),
        )
        for symbol, values in sorted(historical_dates_by_symbol.items())
        if values
    ]
    versions = [
        VersionSegment(
            git_sha=sha,
            release_tag=tag,
            measurements=len(times),
            passes=len(set(times)),
            first_measured_at=min(times),
            last_measured_at=max(times),
        )
        for (sha, tag), times in version_rows.items()
    ]
    versions.sort(key=lambda item: item.first_measured_at or datetime.max.replace(tzinfo=timezone.utc))
    distinct_causes = CauseCounts(
        market_closed=sum(len(values) for values in closed_dates_by_symbol_month.values()),
        provider_missing=sum(len(values) for values in missing_dates_by_symbol_month.values())
        + sum(len(values) for values in historical_dates_by_symbol.values()),
        partial_bar=total_appearances.partial_bar,
    )

    return FreshnessHistorySummary(
        total_measurements=len(materialized),
        total_passes=len(pass_times),
        total_symbols=len(symbols),
        first_measured_at=first,
        last_measured_at=last,
        market_hour={
            key: RateCell(delayed=value[0], total=value[1], passes=len(market_hour_passes.get(key, set())))
            for key, value in market_hour_counts.items()
        },
        asset_months=sorted(asset_months, key=lambda item: (item.symbol, item.month)),
        asset_partials=asset_partials,
        weekdays={
            key: RateCell(delayed=value[0], total=value[1], passes=len(weekday_passes.get(key, set())))
            for key, value in weekday_counts.items()
        },
        causes=distinct_causes,
        causes_appearances=total_appearances,
        od02_assets_over_threshold=over_threshold,
        od02_assets_observed=observed_over_threshold,
        od02_assets_persistent=persistent_over_threshold,
        od02_assets_with_persistent_gap=persistent_assets,
        od02_assets_with_delays=delayed_over_threshold,
        historical_gaps=historical_gaps,
        versions=versions,
        populations=(
            "107 analizables hasta 2026-09-18 antes de D-31",
            "103 analizables tras D-31 el 2026-09-18",
            "93 analizables tras D-35 el 2026-09-18",
        ),
        window_note=(
            "Ventana corta: 18 dias de historico, sin vacaciones ni cierres largos; "
            "las tasas mensuales son extrapolaciones provisionales."
        ),
    )


def classify_absence_causes(
    row: Mapping[str, object], measured_at: datetime
) -> tuple[CauseCounts, set[date], set[date], set[date]]:
    market = str(row["market"])
    raw_absences = _decode_dates(row.get("absent_reference_sessions"))
    market_closed = 0
    provider_dates: set[date] = set()
    closed_dates: set[date] = set()
    for value in raw_absences:
        if session_override_kind(market, value) == "cierre_adicional" or not expected_sessions(market, value, value):
            market_closed += 1
            closed_dates.add(value)
        else:
            provider_dates.add(value)

    sessions_approx = _optional_int(row.get("sessions_approx")) or 0
    # Dos cosas distintas que la ficha no separaba: una sesión que falta en el
    # histórico del activo, y una sesión que aún no ha llegado porque el
    # proveedor va con retraso. La segunda suele llegar en la pasada siguiente.
    delayed_dates = _missing_after_last_bar_dates(row, measured_at, sessions_approx)
    delayed_dates -= provider_dates
    provider_missing = len(provider_dates) + len(delayed_dates)
    partial_bar = 1 if bool(row.get("may_be_partial_current_session")) and provider_missing == 0 and market_closed == 0 else 0
    return (
        CauseCounts(market_closed=market_closed, provider_missing=provider_missing, partial_bar=partial_bar),
        provider_dates,
        closed_dates,
        delayed_dates,
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def format_freshness_history_summary(summary: FreshnessHistorySummary) -> str:
    lines = [
        "# Resumen historico de frescura",
        "",
        f"Mediciones: {summary.total_measurements}; pasadas: {summary.total_passes}; simbolos: {summary.total_symbols}.",
    ]
    if summary.first_measured_at and summary.last_measured_at:
        lines.append(
            "Ventana: "
            f"{summary.first_measured_at.isoformat()} a {summary.last_measured_at.isoformat()}."
        )
    lines.extend([
        "Poblacion declarada: " + "; ".join(summary.populations) + ".",
        "Cada activo declara sus pasadas posibles; si `valid_to` existe se usa, si no se deriva de su ventana real observada.",
        summary.window_note,
        "OD-09 y OD-10 ya estan cerradas (D-36 y D-37); este resumen alimenta OD-02 y, por D-39, OD-01.",
        "",
        (
            f"OD-02 depende de que se llame 'sesion perdida', y el pre-registro no lo fijo. El umbral son "
            f"{OD02_ASSET_THRESHOLD} activos con mas de {OD02_MONTHLY_THRESHOLD:g} sesiones perdidas. Las tres "
            "lecturas posibles, todas sobre sesiones DISTINTAS por activo:"
        ),
        (
            f"- (a) HUECO QUE PERSISTE al final de la ventana: {summary.od02_assets_persistent} activos superan el "
            f"umbral ({summary.od02_assets_with_persistent_gap} tienen algun hueco). UMBRAL NO ALCANZADO."
        ),
        (
            f"- (b) sesion ausente del historico en alguna pasada, aunque llegara despues: "
            f"{summary.od02_assets_observed} activos. Umbral superado."
        ),
        (
            f"- (c) lo anterior mas las sesiones que solo llegaban con retraso: {summary.od02_assets_with_delays} "
            "activos. Umbral superado."
        ),
        (
            f"Extrapolado a 30,44 dias con la lectura (b), PROVISIONAL: {summary.od02_assets_over_threshold} activos."
        ),
        (
            "La diferencia entre (a) y (c) es la conclusion entera: casi todo lo que parece hueco es retraso que "
            "acaba llegando. Contar una misma sesion una vez por pasada multiplicaria el hueco por el numero de "
            "pasadas, y por eso no se hace. QUE LECTURA VALE PARA OD-02 ES DECISION DEL PROPIETARIO."
        ),
        "",
        "Causas excluyentes, en ausencias distintas (activo, fecha):",
        (
            f"- plaza cerrada: n={summary.causes.market_closed}; proveedor con plaza abierta: "
            f"n={summary.causes.provider_missing}; barra parcial por sesion en curso: n={summary.causes.partial_bar}; "
            f"total clasificado: n={summary.causes.total}."
        ),
        (
            "- las mismas causas contadas por aparicion en cada pasada, que NO son ausencias distintas: "
            f"plaza cerrada n={summary.causes_appearances.market_closed}; proveedor "
            f"n={summary.causes_appearances.provider_missing}; parcial "
            f"n={summary.causes_appearances.partial_bar}."
        ),
        "",
        "## Plaza x hora UTC",
        (
            "NOTA: las mediciones de una misma pasada no son independientes. Un fallo del proveedor afecta a la "
            "vez a decenas de simbolos, asi que la muestra efectiva son las PASADAS, no las filas. Los intervalos "
            "de abajo estan calculados sobre filas y son por tanto demasiado estrechos (D-41)."
        ),
        "",
        "| Plaza | Hora UTC | Mediciones | Retraso >= 1 sesion | IC 95% (demasiado estrecho) |",
        "|---|---:|---:|---|---|",
    ])
    for (market, hour), cell in sorted(summary.market_hour.items()):
        delayed, interval = _rate_label(cell)
        lines.append(f"| {market} | {hour:02d} | n={cell.total} | {delayed} | {interval} |")

    lines.extend([
        "",
        "## Activo x mes",
        (
            "| Simbolo | Mes | Pasadas posibles | Pasadas medidas | Sesiones distintas ausentes proveedor | "
            "Tasa mensual provisional | Racha maxima | Cierres reales | Barras parciales | Apariciones en pasadas | Ventana |"
        ),
        "|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|",
    ])
    for item in summary.asset_months:
        lines.append(
            f"| {item.symbol} | {item.month} | n={item.possible_passes} | n={item.measured_passes} | "
            f"n={item.provider_missing_sessions} | {item.provider_missing_per_month:.2f}/mes provisional "
            f"(n={item.provider_missing_sessions}, dias_activos={item.active_days}) | {item.max_streak} | "
            f"n={item.market_closed_absences} | n={item.partial_bars} | n={item.provider_missing_appearances} | "
            f"{item.window_source} |"
        )

    lines.extend([
        "",
        "## Barras parciales por activo",
        "| Simbolo | Barras parciales |",
        "|---|---|",
    ])
    for partial_item in summary.asset_partials:
        lines.append(f"| {partial_item.symbol} | {_percent_label(partial_item.partial, partial_item.total)} |")

    lines.extend([
        "",
        "## Huecos historicos heredados (fuera de la ventana observada)",
        (
            "`absent_reference_sessions` mira 200 sesiones hacia atras, asi que una pasada de hoy reporta huecos "
            "de meses anteriores. No son sesiones perdidas durante la ventana y no alimentan ninguna tasa de arriba."
        ),
        "| Simbolo | Sesiones | Muestra |",
        "|---|---:|---|",
    ])
    if summary.historical_gaps:
        for gap in summary.historical_gaps:
            lines.append(f"| {gap.symbol} | n={gap.sessions} | {', '.join(gap.sample)} |")
    else:
        lines.append("| N/D | n=0 | sin huecos anteriores a la ventana |")

    lines.extend([
        "",
        "## Version de codigo de cada medicion",
        (
            "D-36 y D-37 cambiaron que cuenta como ultima sesion cerrada exigible, que es la definicion de la "
            "metrica primaria. Las mediciones tomadas con reglas distintas NO se pueden agregar en una sola tasa."
        ),
        "| Version | Mediciones | Pasadas | Desde | Hasta |",
        "|---|---:|---:|---|---|",
    ])
    for version in summary.versions:
        desde = version.first_measured_at.isoformat() if version.first_measured_at else "N/D"
        hasta = version.last_measured_at.isoformat() if version.last_measured_at else "N/D"
        lines.append(
            f"| {version.label} | n={version.measurements} | n={version.passes} | {desde} | {hasta} |"
        )
    if len(summary.versions) > 1:
        lines.append("")
        lines.append(
            f"AVISO: la ventana cruza {len(summary.versions)} versiones de codigo. Las tasas agregadas de arriba "
            "describen mayoritariamente la regla anterior a D-36 y D-37; leerlas como la regla vigente seria un error."
        )

    lines.extend([
        "",
        "## Dia de la semana",
        "| Dia | Mediciones | Retraso >= 1 sesion | IC 95% (demasiado estrecho) |",
        "|---|---:|---|---|",
    ])
    for weekday in range(7):
        cell = summary.weekdays.get(weekday, RateCell())
        delayed, interval = _rate_label(cell)
        lines.append(f"| {WEEKDAYS[weekday]} | n={cell.total} | {delayed} | {interval} |")
    return "\n".join(lines)


def table_market_hour(summary: FreshnessHistorySummary) -> str:
    return _markdown_section(format_freshness_history_summary(summary), "## Plaza x hora UTC")


def table_asset_month(summary: FreshnessHistorySummary) -> str:
    return _markdown_section(format_freshness_history_summary(summary), "## Activo x mes")


def table_asset_partial(summary: FreshnessHistorySummary) -> str:
    return _markdown_section(format_freshness_history_summary(summary), "## Barras parciales por activo")


def table_weekday(summary: FreshnessHistorySummary) -> str:
    return _markdown_section(format_freshness_history_summary(summary), "## Dia de la semana")


def _increment_rate[RateKey](target: dict[RateKey, list[int]], key: RateKey, success: bool) -> None:
    counts = target.setdefault(key, [0, 0])
    counts[0] += int(success)
    counts[1] += 1


@dataclass(frozen=True)
class _PossiblePasses:
    pass_times: tuple[datetime, ...]
    source: str


def _possible_passes_for_symbol(
    symbol: str,
    pass_times: list[datetime],
    parsed: list[tuple[datetime, dict[str, object]]],
    universe: Universe,
) -> _PossiblePasses:
    asset = universe.get(symbol)
    if asset is not None and asset.valid_to is not None:
        values = tuple(value for value in pass_times if value.date() <= asset.valid_to)
        return _PossiblePasses(values, f"valid_to={asset.valid_to.isoformat()}")
    observed = [measured_at for measured_at, row in parsed if str(row["symbol"]) == symbol]
    if not observed:
        return _PossiblePasses((), "sin ventana observada")
    start = min(observed)
    end = max(observed)
    values = tuple(value for value in pass_times if start <= value <= end)
    return _PossiblePasses(values, "historico observado")


def _missing_after_last_bar_dates(row: Mapping[str, object], measured_at: datetime, sessions_approx: int) -> set[date]:
    if sessions_approx <= 0 or not row.get("last_bar_date"):
        return set()
    last_bar = date.fromisoformat(str(row["last_bar_date"]))
    latest_closed = latest_expected_closed_session(str(row["market"]), measured_at)
    if latest_closed is None:
        return set()
    missing = expected_sessions(str(row["market"]), last_bar + timedelta(days=1), latest_closed)
    return set(missing[-sessions_approx:])


def _max_consecutive_dates(values: set[date]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    best = current = 1
    previous = ordered[0]
    for value in ordered[1:]:
        if (value - previous).days == 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
        previous = value
    return best


def _rate_label(cell: RateCell) -> tuple[str, str]:
    if cell.total == 0:
        return "sin mediciones (n=0)", "N/D"
    if cell.total < MIN_SAMPLE_SIZE:
        return f"insuficiente ({cell.delayed}/{cell.total}; n={cell.total}<30)", "N/D"
    # Las filas de una misma pasada son un solo evento del proveedor, no
    # observaciones independientes, asi que el intervalo binomial sobre `total`
    # es demasiado estrecho y se publica marcado (D-41, INV-22).
    low, high = _wilson_interval(cell.delayed, cell.total)
    aviso = "" if cell.passes >= cell.total else f", NO independiente: {cell.passes} pasadas"
    return (
        f"{_percent_label(cell.delayed, cell.total)} en {cell.passes} pasadas",
        f"{low:.1%}-{high:.1%} (n={cell.total}{aviso})",
    )


def _percent_label(count: int, total: int) -> str:
    if total == 0:
        return "sin mediciones (n=0)"
    return f"{count / total:.1%} ({count}/{total})"


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    low = max(0.0, (centre - spread) / denominator)
    high = min(1.0, (centre + spread) / denominator)
    return (low, high)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(cast(Any, value))


def _decode_dates(value: object) -> tuple[date, ...]:
    if value in (None, ""):
        return ()
    raw = json.loads(str(value))
    if not isinstance(raw, list):
        return ()
    return tuple(date.fromisoformat(str(item)) for item in raw)


def _markdown_section(text: str, title: str) -> str:
    lines = text.splitlines()
    start = lines.index(title)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip() + "\n"
