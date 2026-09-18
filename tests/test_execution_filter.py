from __future__ import annotations

from advisor.research.execution_filter import (
    POP_EXECUTED,
    ExecutionFilterResult,
    PopulationStats,
    _format_stats_row,
    format_execution_filter_report,
)


def test_celda_con_muestra_insuficiente_se_declara_insuficiente() -> None:
    result = _result_with_table(
        PopulationStats(
            population=POP_EXECUTED,
            band="80+",
            n=9,
            sufficient=False,
            wins=4,
            target_exits=3,
            stop_exits=5,
            mean_net_r=None,
            block_mean_net_r=None,
            ci_low=None,
            ci_high=None,
            median_net_r=None,
            p10_net_r=None,
            p90_net_r=None,
            profit_factor=None,
            payoff=None,
        )
    )

    report = format_execution_filter_report(result)

    assert "INSUFICIENTE (<10)" in report
    assert "| 80+ | EJECUTADAS | 9 | INSUFICIENTE (<10) | 4/9 |" in report


def test_la_salida_declara_los_dos_vintages() -> None:
    result = _result_with_table()

    report = format_execution_filter_report(result)

    assert "data_vintage_id=071ddb2b" in report
    assert "universe_vintage_id=universo-123" in report


def _result_with_table(*table: PopulationStats) -> ExecutionFilterResult:
    return ExecutionFilterResult(
        data_vintage_id="071ddb2b",
        universe_vintage_id="universo-123",
        git_sha="abc123",
        config_hash="cfg123",
        horizonte="swing",
        cost_pct=0.2,
        evaluated_assets=("SAP.DE",),
        skipped=(),
        executed=(),
        lost=(),
        counterfactual_lost=(),
        broker_neutral_delta_by_asset={},
        table=table,
    )


def test_una_celda_con_un_solo_bloque_no_publica_intervalo() -> None:
    """Regresión de la revisión de T-009.

    ``bootstrap_block_mean_interval`` devuelve el centinela ``(0.0, 1.0)`` cuando
    hay menos de dos bloques. En unidades de R eso se lee como un intervalo
    plausible —«entre 0 y 1 R»— y no lo es: es la ausencia de intervalo. La fila
    debe decirlo, no disfrazarlo de resultado.
    """

    fila = PopulationStats(
        population="EJECUTADAS",
        band="80+",
        n=28,
        sufficient=True,
        wins=13,
        target_exits=13,
        stop_exits=15,
        mean_net_r=0.4391,
        block_mean_net_r=0.4391,
        ci_low=None,
        ci_high=None,
        median_net_r=-1.0234,
        p10_net_r=-1.0817,
        p90_net_r=2.4108,
        profit_factor=1.7197,
        payoff=1.9842,
    )

    linea = _format_stats_row(fila)

    assert "N/D (menos de 2 bloques)" in linea
    assert "SIN INTERVALO" in linea
    assert "[0.0000, 1.0000]" not in linea
