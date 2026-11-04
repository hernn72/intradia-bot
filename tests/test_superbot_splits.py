"""Splits en la cartera paper: en qué base de precios está cada posición.

El proveedor sirve siempre el histórico ya ajustado por los splits conocidos en
el momento de la descarga: medido con NVDA, AVGO, PANW, NFLX, NOW, AZN, CRWD y
8035.T, el salto entre el cierre previo y la apertura de la fecha ex es de 0,99
a 1,03, con o sin ``auto_adjust``. Las series de estos tests tienen esa forma.
Una posición guarda los precios de la descarga en la que se abrió, así que:

- abierta en una ejecución anterior al split: base vieja, hay que reescalar;
- abierta con una descarga que ya incluye el split (réplica retrospectiva o
  recuperación tras días sin ejecutar): base actual, reescalar la duplicaría.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pytest

from superbot.config import SizingParams, SuperbotConfig
from superbot.engine import SPLIT_WINDOW_BARS, BarSeries, PaperEngine
from superbot.store import SuperbotStore

START = date(2026, 3, 2)
BUY = {"sma_fast": 95.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}
HOLD = {"sma_fast": 105.0, "sma_slow": 90.0, "rsi": 60.0, "atr": 2.0, "trend_break": False}


class NoFx:
    def rate(self, currency: str, on: date) -> Optional[float]:
        return 1.0


def bar(o: float, h: float, low: float, c: float, ind: dict = HOLD, split: float = 0.0) -> dict:
    return {"Open": o, "High": h, "Low": low, "Close": c, **ind, "Stock Splits": split}


def frame(bars: List[dict], start: date = START) -> Dict[str, BarSeries]:
    index = [start + timedelta(days=i) for i in range(len(bars))]
    return {"SAP.DE": BarSeries(symbol="SAP.DE", name="SAP SE", currency="EUR",
                                frame=pd.DataFrame(bars, index=index), market="XETRA")}


def rebased(bars: List[dict], factor: float) -> List[dict]:
    """Las mismas barras en la base de una descarga posterior: precios y ATR entre ``factor``."""

    columns = ("Open", "High", "Low", "Close", "sma_fast", "sma_slow", "atr")
    return [{k: (v / factor if k in columns else v) for k, v in b.items()} for b in bars]


@pytest.fixture
def store(tmp_path: Path) -> SuperbotStore:
    created = SuperbotStore(tmp_path / "superbot.db")
    created.initialize(SuperbotConfig(initial_capital_eur=10_000.0, sizing=SizingParams()), START, retrospective=False)
    return created


def run(store: SuperbotStore, data: Dict[str, BarSeries], today: date = START + timedelta(days=30)):
    return PaperEngine(store).process(data, NoFx(), store.start_run(), today)


def position(store: SuperbotStore) -> dict:
    return dict(store.connect().execute("SELECT * FROM positions").fetchone())


def ledger(store: SuperbotStore) -> dict:
    conn = store.connect()
    return {
        table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        for table in ("positions", "fills")
    } | {"equity": store.equity_curve(), "cash": store.cash_eur()}


# Compra a 100; el 2:1 llega con la serie ya continua: 50 antes y 51 después.
PRE = [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103)]
RETRO = [*rebased(PRE, 2), bar(51, 52, 50.5, 51.5, split=2.0), bar(52, 53, 51, 52.5)]


def test_replica_con_historico_ajustado_no_multiplica_la_posicion(store: SuperbotStore) -> None:
    run(store, frame(RETRO))
    held = position(store)
    bought = store.connect().execute("SELECT quantity, price_native FROM fills").fetchone()
    assert held["quantity"] == bought["quantity"]
    assert held["entry_price_native"] == pytest.approx(bought["price_native"])
    # Equity ≈ cash + unidades · 52,5: una subida del 5 % sobre lo invertido, no el doble.
    assert store.equity_curve()[-1]["invested_eur"] == pytest.approx(bought["quantity"] * 52.5)


def test_el_aviso_de_split_no_cambia_ninguna_cifra_de_la_replica(store: SuperbotStore, tmp_path: Path) -> None:
    run(store, frame(RETRO))
    other = SuperbotStore(tmp_path / "sin-aviso.db")
    other.initialize(store.config(), START, retrospective=False)
    run(other, frame([{**b, "Stock Splits": 0.0} for b in RETRO]))
    assert ledger(store) == ledger(other)


def test_replica_deja_constancia_del_split_que_no_aplica(store: SuperbotStore) -> None:
    result = run(store, frame(RETRO))
    assert any("SPLIT SAP.DE factor 2 ya incluido" in line for line in result.events)


def test_paper_en_vivo_reescala_la_posicion_de_una_ejecucion_anterior(store: SuperbotStore) -> None:
    run(store, frame(PRE))                                  # ejecución previa: base vieja
    before = position(store)
    invested = before["quantity"] * before["last_close"]
    result = run(store, frame(RETRO))                       # descarga nueva, ya ajustada
    held = position(store)
    assert held["status"] == "OPEN"
    assert held["quantity"] == pytest.approx(before["quantity"] * 2)
    assert held["entry_price_native"] == pytest.approx(before["entry_price_native"] / 2)
    assert held["initial_stop"] == pytest.approx(before["initial_stop"] / 2)
    assert held["target1"] == pytest.approx(before["target1"] / 2)
    assert held["target2"] == pytest.approx(before["target2"] / 2)
    assert held["cost_eur"] == before["cost_eur"]
    assert any("SPLIT SAP.DE factor 2" in line and "incluido" not in line for line in result.events)
    # El split no crea ni destruye valor: 103 antes, 52,5 · 2 = 105 tras subir el 2 %.
    assert store.equity_curve()[-1]["invested_eur"] == pytest.approx(invested * 105 / 103)
    assert len(store.fills()) == 1


def test_paper_en_vivo_con_dividendo_en_la_misma_descarga(store: SuperbotStore) -> None:
    # auto_adjust reescribe también el pasado por dividendos: la base no coincide exacta.
    run(store, frame(PRE))
    before = position(store)
    run(store, frame([*rebased(PRE, 2 / 0.98), bar(51, 52, 50.5, 51.5, split=2.0)]))
    assert position(store)["quantity"] == pytest.approx(before["quantity"] * 2)


@pytest.mark.parametrize("factor", [0.5, 1.5, 4.0, 10.0])
def test_factores_reales_en_vivo_y_en_replica(store: SuperbotStore, tmp_path: Path, factor: float) -> None:
    after = [bar(100 / factor, 104 / factor, 99 / factor, 103 / factor, split=factor)]
    run(store, frame(PRE))
    before = position(store)
    run(store, frame([*rebased(PRE, factor), *after]))
    assert position(store)["quantity"] == pytest.approx(before["quantity"] * factor)

    replay = SuperbotStore(tmp_path / "replica.db")
    replay.initialize(store.config(), START, retrospective=True)
    run(replay, frame([*rebased(PRE, factor), *after]))
    assert position(replay)["quantity"] == replay.connect().execute("SELECT quantity FROM fills").fetchone()[0]


def test_recuperacion_distingue_la_posicion_vieja_de_la_abierta_en_la_misma_descarga(tmp_path: Path) -> None:
    created = SuperbotStore(tmp_path / "superbot.db")
    created.initialize(SuperbotConfig(initial_capital_eur=10_000.0), START, retrospective=False)
    old = [bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103)]
    new = [bar(99, 101, 98, 100), bar(100, 104, 99, 103), bar(99, 101, 98, 100, BUY), bar(100, 104, 99, 103)]

    def both(a: List[dict], b: List[dict]) -> Dict[str, BarSeries]:
        data = frame(a)
        data["BMW.DE"] = BarSeries(symbol="BMW.DE", name="BMW AG", currency="EUR",
                                   frame=frame(b)["SAP.DE"].frame, market="XETRA")
        return data

    run(created, both(old, new[:2]))
    after = bar(51, 52, 50.5, 51.5, split=2.0)
    run(created, both([*rebased(old, 2), bar(51, 52, 50, 51), bar(51, 52, 50, 51), after],
                      [*rebased(new, 2), after]))
    rows = {r["symbol"]: dict(r) for r in created.open_positions()}
    bought = {r["symbol"]: r["quantity"] for r in created.fills()}
    assert rows["BMW.DE"]["quantity"] == bought["BMW.DE"]          # nació en la base actual
    assert rows["SAP.DE"]["quantity"] == pytest.approx(bought["SAP.DE"] * 2)


def test_recuperacion_tras_dias_sin_ejecutar_no_dispara_el_stop(store: SuperbotStore) -> None:
    # Las sesiones perdidas llegan ajustadas antes de la fecha ex: sin pasar la
    # posición a la base nueva, 51 quedaría bajo su stop de 95 y saldría con −50 %.
    run(store, frame(PRE))
    before = position(store)
    gap = [bar(51, 52, 50.5, 51.5), bar(51.5, 52, 51, 51.5), bar(51, 52, 50.5, 51.5, split=2.0)]
    run(store, frame([*rebased(PRE, 2), *gap]))
    held = position(store)
    assert held["status"] == "OPEN"
    assert held["quantity"] == pytest.approx(before["quantity"] * 2)
    assert len(store.fills()) == 1


def test_dos_splits_en_la_misma_recuperacion(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    before = position(store)
    # La sesión previa a los dos splits ya llega en la base final: con la mitad del
    # ajuste, el stop quedaría por encima del precio.
    run(store, frame([*rebased(PRE, 4), bar(25.5, 26, 25, 25.5), bar(25.5, 26, 25, 25.5, split=2.0),
                      bar(25.5, 26, 25, 25.5, split=2.0)]))
    held = position(store)
    assert held["status"] == "OPEN"
    assert held["quantity"] == pytest.approx(before["quantity"] * 4)
    assert held["initial_stop"] == pytest.approx(before["initial_stop"] / 4)


def test_posicion_abierta_con_una_descarga_que_ya_traia_el_split(store: SuperbotStore) -> None:
    # La barra ex llega en una ejecución posterior, pero el histórico ya estaba ajustado.
    run(store, frame(rebased(PRE, 2)))
    before = position(store)
    run(store, frame(RETRO))
    assert position(store)["quantity"] == before["quantity"]


def test_repetir_la_ejecucion_no_aplica_dos_veces(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    before = position(store)
    run(store, frame(RETRO))
    run(store, frame(RETRO))
    assert position(store)["quantity"] == pytest.approx(before["quantity"] * 2)


def test_descarga_sin_ajustar_sigue_reescalando(store: SuperbotStore) -> None:
    # Un proveedor que publica la barra ex sin ajustar el pasado: la serie salta.
    run(store, frame(PRE))
    run(store, frame([*PRE, bar(51, 52, 50.5, 51.5, split=2.0)]))
    bought = store.connect().execute("SELECT quantity FROM fills").fetchone()[0]
    assert position(store)["quantity"] == pytest.approx(bought * 2)


def test_caida_real_el_dia_del_split_no_se_confunde_con_el_ajuste(store: SuperbotStore) -> None:
    drop = [*rebased(PRE, 2), bar(42, 43, 41, 42, split=2.0)]      # −18 % real, stop en 47,5 aún lejos del cero
    run(store, frame(drop))
    bought = store.connect().execute("SELECT quantity FROM fills").fetchone()[0]
    assert store.connect().execute("SELECT quantity FROM positions").fetchone()[0] == bought


def test_sin_la_barra_de_referencia_decide_la_apertura(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    before = position(store)
    # La descarga nueva ya no trae la sesión en la que se valoró la posición.
    later = frame([bar(51, 52, 50.5, 51.5, split=2.0)], start=START + timedelta(days=2))
    run(store, later)
    assert position(store)["quantity"] == pytest.approx(before["quantity"] * 2)


@pytest.mark.parametrize("value", [0.0, 1.0, float("nan"), -2.0])
def test_valores_sin_split_no_tocan_la_posicion(store: SuperbotStore, value: float) -> None:
    run(store, frame(PRE))
    before = position(store)
    run(store, frame([*PRE, bar(103, 104, 102, 103, split=value)]))
    assert position(store)["quantity"] == before["quantity"]


def test_split_en_la_sesion_de_entrada_no_reescala(store: SuperbotStore) -> None:
    cheap = {**BUY, "sma_fast": 47.0, "sma_slow": 45.0}
    run(store, frame([bar(49.5, 50.5, 49, 50, cheap), bar(50, 52, 49.5, 51, split=2.0)]))
    bought = store.connect().execute("SELECT quantity FROM fills").fetchone()[0]
    assert position(store)["quantity"] == bought


@pytest.mark.parametrize("factor,change,units,status", [
    (2.0, -0.31, 2.0, "CLOSED"), (4.0, -0.52, 4.0, "CLOSED"), (10.0, -0.70, 10.0, "CLOSED"), (0.5, 0.45, 0.5, "OPEN"),
])
def test_caida_real_en_la_fecha_ex_tras_reconciliar_no_ajusta_dos_veces(
    store: SuperbotStore, factor: float, change: float, units: float, status: str
) -> None:
    run(store, frame(PRE))
    before = position(store)
    opening = 103 / factor * (1 + change)
    high = max(opening, 103 / factor) * 1.01
    result = run(store, frame([*rebased(PRE, factor), bar(opening, high, opening * 0.99, opening, split=factor)]))
    held = position(store)
    assert held["quantity"] == pytest.approx(before["quantity"] * units)
    assert held["status"] == status
    assert sum("SPLIT SAP.DE" in line and "incluido" not in line for line in result.events) == 1


@pytest.mark.parametrize("factor", [2.0, 0.5])
def test_barra_ex_aun_abierta_tambien_reconcilia_la_posicion(store: SuperbotStore, factor: float) -> None:
    # Ejecución en plena fecha ex tras perder la de la víspera: la barra ex se
    # recorta, pero la sesión pendiente ya llega ajustada.
    run(store, frame(PRE))
    before = position(store)
    pending = bar(102 / factor, 104 / factor, 101 / factor, 103 / factor)
    data = frame([*rebased(PRE, factor), pending])
    data["SAP.DE"].unclosed_split = factor
    run(store, data)
    held = position(store)
    assert held["status"] == "OPEN"
    assert held["quantity"] == pytest.approx(before["quantity"] * factor)
    # La barra ex llega después, ya cerrada: no se aplica otra vez.
    ex = bar(103 / factor, 104 / factor, 102 / factor, 103 / factor, split=factor)
    run(store, frame([*rebased(PRE, factor), pending, ex]))
    assert position(store)["quantity"] == pytest.approx(before["quantity"] * factor)


def test_barra_ex_abierta_sin_historico_ajustado_no_toca_la_posicion(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    before = position(store)
    data = frame([*PRE, bar(103, 104, 102, 103)])
    data["SAP.DE"].unclosed_split = 2.0
    run(store, data)
    assert position(store)["quantity"] == before["quantity"]


def test_un_fallo_tras_reconciliar_deshace_el_ajuste(store: SuperbotStore, monkeypatch: pytest.MonkeyPatch) -> None:
    run(store, frame(PRE))
    before = position(store)

    def boom(*args: object) -> None:
        raise RuntimeError("fallo tras reconciliar")

    monkeypatch.setattr(PaperEngine, "_fill_sell", boom)
    with pytest.raises(RuntimeError):
        run(store, frame(RETRO))
    assert position(store) == before
    monkeypatch.undo()
    run(store, frame(RETRO))
    assert position(store)["quantity"] == pytest.approx(before["quantity"] * 2)


@pytest.mark.parametrize("factor,change,status", [
    (2.0, 0.0, "OPEN"), (0.5, 0.0, "OPEN"), (2.0, -0.31, "CLOSED"), (10.0, -0.70, "CLOSED"), (0.5, 0.45, "OPEN"),
])
def test_camino_diario_tarde_y_noche_de_la_fecha_ex(
    store: SuperbotStore, factor: float, change: float, status: str
) -> None:
    # La ejecución de la tarde ve la serie ajustada con la barra ex aún abierta y
    # sin sesiones pendientes: espera. La de la noche trae la barra ex y aplica el
    # split una sola vez, también si esa apertura es una caída real.
    run(store, frame(PRE))
    before = position(store)
    adjusted = frame(rebased(PRE, factor))
    adjusted["SAP.DE"].unclosed_split = factor
    assert run(store, adjusted).bars == 0
    assert position(store) == before
    opening = 103 / factor * (1 + change)
    high = max(opening, 103 / factor) * 1.01
    run(store, frame([*rebased(PRE, factor), bar(opening, high, opening * 0.99, opening, split=factor)]))
    held = position(store)
    assert held["quantity"] == pytest.approx(before["quantity"] * factor)
    assert held["status"] == status


# --- Ajuste ambiguo ----------------------------------------------------------
#
# Sin un salto de base que comparar, el precio de la fecha ex no siempre distingue
# una serie discontinua de una caída real. El libro dice lo que ya se aplicó, y lo
# que siga sin decidirse espera: mejor una sesión sin procesar que un ajuste falso.


def bought(store: SuperbotStore) -> float:
    return float(store.connect().execute("SELECT quantity FROM fills WHERE side = 'BUY'").fetchone()[0])


def watermark(store: SuperbotStore) -> date:
    return store.last_bar_dates()["SAP.DE"]


EVE = bar(103, 104, 102, 103)


@pytest.mark.parametrize("factor,drop", [(2.0, 0.35), (2.0, 0.60), (4.0, 0.60), (10.0, 0.75)])
def test_ejecucion_perdida_y_caida_real_en_la_fecha_ex_ajusta_una_sola_vez(
    store: SuperbotStore, factor: float, drop: float
) -> None:
    # 18:15 de la fecha ex sin haber corrido la víspera: la descarga ya viene
    # ajustada, hay una sesión pendiente y se reescala con el split de la barra abierta.
    run(store, frame(PRE))
    afternoon = frame(rebased([*PRE, EVE], factor))
    afternoon["SAP.DE"].unclosed_split = factor
    run(store, afternoon)
    assert position(store)["quantity"] == pytest.approx(bought(store) * factor)
    # 22:45: la barra ex trae una caída real mayor que 1 − 1/√factor.
    opening = 103 / factor * (1 - drop)
    run(store, frame([*rebased([*PRE, EVE], factor),
                      bar(opening, opening * 1.01, opening * 0.99, opening, split=factor)]))
    assert position(store)["quantity"] == pytest.approx(bought(store) * factor)


def test_dos_splits_el_libro_solo_descarta_el_ya_aplicado(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    afternoon = frame(rebased([*PRE, EVE], 2))
    afternoon["SAP.DE"].unclosed_split = 2.0
    run(store, afternoon)
    ex = bar(51.5, 52, 51, 51.5, split=2.0)
    run(store, frame([*rebased([*PRE, EVE], 2), ex]))
    assert position(store)["quantity"] == pytest.approx(bought(store) * 2)
    # Un segundo split con la serie saltando otra vez sí se aplica.
    run(store, frame([*rebased([*PRE, EVE], 2), ex, bar(17.2, 17.5, 17, 17.2, split=3.0)]))
    assert position(store)["quantity"] == pytest.approx(bought(store) * 6)


def test_salto_ambiguo_retiene_el_simbolo_sin_tocar_la_posicion(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    before = position(store)
    mark = watermark(store)
    result = run(store, frame([*PRE, bar(70, 71, 69, 70, split=2.0)]))    # ¿−32 % real o 2:1 con +36 %?
    assert result.held == ["SAP.DE"]
    assert position(store) == before
    assert watermark(store) == mark
    assert len(store.fills()) == 1


def test_el_salto_ambiguo_se_resuelve_cuando_la_descarga_ajusta_el_pasado(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    run(store, frame([*PRE, bar(70, 71, 69, 70, split=2.0)]))
    result = run(store, frame([*rebased(PRE, 2), bar(70, 71, 69, 70, split=2.0)]))
    assert result.held == []
    assert position(store)["quantity"] == pytest.approx(bought(store) * 2)


def test_el_salto_ambiguo_caduca_y_la_caida_real_salta_por_el_stop(store: SuperbotStore) -> None:
    drop = bar(33, 34, 32, 33, split=2.0)                          # −36 % real con la serie continua
    assert run(store, frame([*rebased(PRE, 2), drop])).held == ["SAP.DE"]
    later = [bar(33, 34, 32, 33)] * SPLIT_WINDOW_BARS
    assert run(store, frame([*rebased(PRE, 2), drop, *later])).held == []
    closed = position(store)
    assert closed["status"] == "CLOSED"
    assert closed["quantity"] == bought(store)
    assert store.fills()[-1]["kind"] == "GAP_STOP"


def test_split_antiguo_fuera_de_la_descarga_no_oculta_el_nuevo(store: SuperbotStore) -> None:
    # 2:1 ya aplicado que sale del histórico; llega otro 2:1 con la serie saltando.
    run(store, frame(PRE))
    run(store, frame([*PRE, bar(51, 52, 50.5, 51.5, split=2.0)]))
    assert position(store)["quantity"] == pytest.approx(bought(store) * 2)
    later = START + timedelta(days=2)
    run(store, frame([bar(51, 52, 50.5, 51.5), bar(25.8, 26, 25.5, 25.8, split=2.0)], start=later))
    assert position(store)["quantity"] == pytest.approx(bought(store) * 4)
    assert position(store)["status"] == "OPEN"


def test_salto_claro_tras_una_semana_sin_ejecutar_sigue_reescalando(store: SuperbotStore) -> None:
    # La descarga conserva el salto y la fecha ex ya queda fuera del final.
    run(store, frame(PRE))
    ex = bar(51.5, 52, 51, 51.5, split=2.0)
    run(store, frame([*PRE, ex, *[bar(51.5, 52, 51, 51.5)] * SPLIT_WINDOW_BARS]))
    held = position(store)
    assert held["quantity"] == pytest.approx(bought(store) * 2)
    assert held["status"] == "OPEN"


def test_salto_ambiguo_fuera_del_final_no_retiene(store: SuperbotStore) -> None:
    run(store, frame(PRE))
    ex = bar(70, 71, 69, 70, split=2.0)
    result = run(store, frame([*PRE, ex, *[bar(70, 71, 69, 70)] * SPLIT_WINDOW_BARS]))
    assert result.held == []
    assert position(store)["quantity"] == bought(store)


def test_retener_un_simbolo_deshace_lo_procesado_y_bloquea_entradas(store: SuperbotStore) -> None:
    # MSFT abriría hoy; el salto ambiguo de SAP.DE aparece después en la misma sesión.
    run(store, frame(PRE))
    data = frame([*PRE, bar(70, 71, 69, 70, split=2.0)])
    index = data["SAP.DE"].frame.index
    other = pd.DataFrame([bar(99, 101, 98, 100, BUY) for _ in index], index=index)
    data["ALV.DE"] = BarSeries(symbol="ALV.DE", name="Allianz", currency="EUR", frame=other, market="XETRA")
    result = run(store, data)
    assert result.held == ["SAP.DE"]
    conn = store.connect()
    assert conn.execute("SELECT COUNT(*) FROM orders WHERE symbol = 'ALV.DE'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM signals WHERE symbol = 'ALV.DE'").fetchone()[0] == 0
    assert "ALV.DE" not in store.last_bar_dates()


def test_split_antiguo_de_la_descarga_no_se_toma_por_un_salto_de_serie(store: SuperbotStore) -> None:
    # Réplica: 2:1 con una caída real del 45 %, sesiones después. Solo el final de
    # una descarga puede estar sin ajustar, así que esto es una caída de verdad.
    old = bar(28, 29, 27, 28, split=2.0)
    later = [bar(28, 29, 27, 28)] * SPLIT_WINDOW_BARS
    run(store, frame([*rebased(PRE, 2), old, *later]))
    closed = position(store)
    assert closed["quantity"] == bought(store)
    assert closed["status"] == "CLOSED"


@pytest.mark.parametrize("drop", [0.31, 0.45])
def test_caida_real_en_una_posicion_nacida_en_esta_descarga_no_se_toma_por_un_split(
    store: SuperbotStore, drop: float
) -> None:
    # Réplica reciente: la posición nace y llega a la fecha ex en la misma ejecución.
    opening = 51.5 * (1 - drop)
    ex = bar(opening, opening * 1.01, opening * 0.99, opening, split=2.0)
    assert run(store, frame([*rebased(PRE, 2), ex])).held == ["SAP.DE"]
    assert store.open_positions() == []
    later = [bar(opening, opening * 1.01, opening * 0.99, opening)] * SPLIT_WINDOW_BARS
    run(store, frame([*rebased(PRE, 2), ex, *later]))
    closed = position(store)
    assert closed["quantity"] == bought(store)
    assert closed["status"] == "CLOSED"
