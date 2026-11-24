"""Simulador de reglas: gate y stop reales, tope de entrada en toda variante, orden del día y contabilidad."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from superbot.ia.medicion import coste_orden_eur
from superbot.lab import __main__ as cli
from superbot.lab import datos_lab
from superbot.lab.simulador import (
    BASE,
    CAPITAL_EUR,
    VARIANTES,
    Ficha,
    Regla,
    Resultado,
    Serie,
    intervalo_diferencia,
    precio_entrada,
    simular,
)

D0 = date(2025, 1, 1)
FICHA = Ficha(65.0, 100.0, 96.0, 106.0, 100.0, 1.5, 1.5, 2.0, 95.0, 90.0)
PLANA = (100.0, 100.5, 99.5, 100.0)


def _dia(n: int) -> date:
    return D0 + timedelta(days=n)


def _serie(barras: List[Tuple[float, float, float, float]], symbol: str = "A", currency: str = "EUR") -> Serie:
    o, h, low, c = zip(*barras)
    return Serie(symbol, "XETRA", currency, tuple(_dia(i) for i in range(len(barras))), o, h, low, c)


def _simular(
    series: List[Serie], fichas: Dict[str, Dict[int, Ficha]], regla: Regla = BASE, *, fx: Optional[Any] = None,
    ref: Optional[List[float]] = None,
) -> Resultado:
    n = len(series[0].sesiones)
    dias = [_dia(i) for i in range(n)]
    return simular(
        {s.symbol: s for s in series}, {k: {_dia(d): f for d, f in v.items()} for k, v in fichas.items()}, fx or {},
        (dias, ref or [100.0] * n), regla, D0, dias[-1],
    )


class TestPrecioEntrada:
    @pytest.mark.parametrize("apertura, entra", [(100.0, True), (99.0, True), (100.01, False)])
    def test_la_base_es_la_regla_actual(self, apertura: float, entra: bool) -> None:
        assert (precio_entrada(BASE, FICHA, apertura, 95.0)[0] is not None) is entra

    @pytest.mark.parametrize("regla, tope", [("E1_MARGEN_025", 100.5), ("E2_MARGEN_050", 101.0)])
    def test_el_margen_sube_el_tope_y_no_lo_quita(self, regla: str, tope: float) -> None:
        elegida = next(v for v in VARIANTES if v.nombre == regla)
        assert precio_entrada(elegida, FICHA, tope, 99.0)[0] == pytest.approx(tope)
        assert precio_entrada(elegida, FICHA, tope + 0.01, 99.0)[0] is None

    def test_el_limite_nunca_paga_mas_que_el_maximo(self) -> None:
        regla = next(v for v in VARIANTES if v.nombre == "E3_LIMITE_DIA")
        assert precio_entrada(regla, FICHA, 101.0, 99.9) == (100.0, "")
        assert precio_entrada(regla, FICHA, 99.0, 98.5)[0] == 99.0
        assert precio_entrada(regla, FICHA, 101.0, 100.1) == (None, "LIMITE_NO_TOCADO")

    def test_ninguna_variante_entra_por_debajo_del_stop(self) -> None:
        for regla in (BASE, *VARIANTES):
            assert precio_entrada(regla, FICHA, 95.0, 94.0)[0] is None


class TestSimular:
    def test_decide_al_cierre_y_entra_en_la_apertura_siguiente_con_el_tamano_real(self) -> None:
        r = _simular([_serie([PLANA] * 3)], {"A": {0: FICHA}})
        # Riesgo 0,5 % de 5.000 = 25 EUR a 4 por unidad da 625 EUR; manda el 10 %.
        assert r.exposicion == [0.0, pytest.approx(500.0), pytest.approx(500.0)]
        assert r.equity[1] == pytest.approx(CAPITAL_EUR - coste_orden_eur(500.0)) and r.abiertas == 1

    def test_el_stop_cierra_al_stop_y_el_hueco_a_la_apertura(self) -> None:
        for barra, precio in (((99.0, 99.0, 95.0, 97.0), 96.0), ((90.0, 97.0, 90.0, 92.0), 90.0)):
            r = _simular([_serie([PLANA, PLANA, barra])], {"A": {0: FICHA}})
            coste = coste_orden_eur(500.0) + coste_orden_eur(5 * precio)
            assert r.operaciones[0].motivo == "STOP" and r.operaciones[0].pnl_eur == pytest.approx(5 * (precio - 100) - coste)

    def test_el_stop_de_la_sesion_de_entrada_cuenta(self) -> None:
        r = _simular([_serie([PLANA, (100.0, 100.0, 95.0, 97.0)])], {"A": {0: FICHA}})
        assert [o.motivo for o in r.operaciones] == ["STOP"]

    def test_la_venta_por_score_sale_en_la_apertura_siguiente_y_respeta_la_espera(self) -> None:
        fichas = dict.fromkeys(range(9), FICHA)
        fichas[1] = replace(FICHA, score=59.0)
        r = _simular([_serie([PLANA] * 10)], {"A": fichas})
        assert (r.operaciones[0].motivo, r.operaciones[0].salida) == ("PREDICADO_SCORE", _dia(2))
        # Vendida en la sesión 2: hasta la 7 no vuelve a ser candidata, y entra en la 8.
        assert r.candidatas == 2 and r.exposicion[7] == 0.0 and r.exposicion[8] > 0

    def test_la_histeresis_mantiene_lo_que_la_base_vende(self) -> None:
        fichas = {"A": {0: FICHA, 1: replace(FICHA, score=57.0)}}
        h1 = next(v for v in VARIANTES if v.nombre == "H1_60_55")
        assert _simular([_serie([PLANA] * 4)], fichas).operaciones
        assert not _simular([_serie([PLANA] * 4)], fichas, h1).operaciones

    def test_el_objetivo_no_se_cobra_el_dia_de_entrada_y_el_stop_manda(self) -> None:
        x1 = next(v for v in VARIANTES if v.nombre == "X1_OBJETIVO")
        alta = (100.0, 107.0, 99.5, 100.0)
        assert not _simular([_serie([PLANA, alta])], {"A": {0: FICHA}}, x1).operaciones
        assert _simular([_serie([PLANA, PLANA, alta])], {"A": {0: FICHA}}, x1).operaciones[0].motivo == "OBJETIVO"
        ambos = (100.0, 107.0, 95.0, 100.0)
        assert _simular([_serie([PLANA, PLANA, ambos])], {"A": {0: FICHA}}, x1).operaciones[0].motivo == "STOP"

    def test_el_stop_movil_sube_tras_el_cierre_y_nunca_baja(self) -> None:
        x2 = next(v for v in VARIANTES if v.nombre == "X2_STOP_MOVIL")
        barras = [PLANA, PLANA, (100.0, 110.0, 100.0, 110.0), (109.0, 109.0, 105.0, 107.0)]
        r = _simular([_serie(barras)], {"A": {0: FICHA}}, x2)
        assert r.operaciones[0].salida == _dia(3) and not _simular([_serie(barras)], {"A": {0: FICHA}}).operaciones

    def test_la_salida_por_tiempo(self) -> None:
        x3 = next(v for v in VARIANTES if v.nombre == "X3_20_SESIONES")
        r = _simular([_serie([PLANA] * 24)], {"A": {0: FICHA}}, x3)
        assert (r.operaciones[0].motivo, r.operaciones[0].salida) == ("TIEMPO", _dia(21))

    def test_el_efectivo_limita_y_manda_el_score(self) -> None:
        series = [_serie([PLANA] * 4, f"S{i}") for i in range(12)]
        fichas = {f"S{i}": {d: replace(FICHA, score=60.0 + i) for d in range(3)} for i in range(12)}
        r = _simular(series, fichas)
        assert r.rechazadas["SIN_EFECTIVO"] >= 3 and r.abiertas == 9
        assert all(e <= CAPITAL_EUR for e in r.exposicion)

    def test_la_divisa_mueve_el_valor(self) -> None:
        fx = {"USD": ([_dia(0), _dia(2)], [0.9, 0.8])}
        r = _simular([_serie([PLANA] * 3, currency="USD")], {"A": {0: FICHA}}, fx=fx)
        assert r.exposicion[2] == pytest.approx(r.exposicion[1] * 0.8 / 0.9)

    def test_el_exceso_descuenta_la_referencia_con_la_exposicion_y_el_efectivo_no_suma(self) -> None:
        sin_nada = _simular([_serie([PLANA] * 3)], {}, ref=[100.0, 120.0, 90.0])
        assert sin_nada.exceso == [0.0, 0.0, 0.0]
        invertido = _simular([_serie([PLANA] * 3)], {"A": {0: FICHA}}, ref=[100.0, 120.0, 90.0])
        assert invertido.exceso[2] == pytest.approx(500.0 * 0.25)

    def test_no_mira_el_futuro(self) -> None:
        barras = [PLANA] * 5
        corto = _simular([_serie(barras)], {"A": {0: FICHA}})
        largo = _simular([_serie([*barras, (50.0, 50.0, 40.0, 45.0)])], {"A": {0: FICHA}})
        assert largo.equity[:5] == corto.equity


class TestIntervalo:
    def test_es_reproducible_y_contiene_la_diferencia(self) -> None:
        variante, base = [((i * 7) % 11) - 4.5 for i in range(300)], [0.0] * 300
        a = intervalo_diferencia(variante, base, nivel=0.95, replicas=2000)
        assert a == intervalo_diferencia(variante, base, nivel=0.95, replicas=2000)
        assert a[1] < a[0] < a[2] and a[0] == pytest.approx(sum(variante))

    def test_iguales_no_dan_diferencia_y_series_distintas_se_rechazan(self) -> None:
        assert intervalo_diferencia([1.0] * 50, [1.0] * 50, nivel=0.95, replicas=100) == (0.0, 0.0, 0.0)
        with pytest.raises(ValueError):
            intervalo_diferencia([1.0], [1.0, 2.0], nivel=0.95)


class TestGuardas:
    def test_los_datos_acaban_donde_ya_estan_consumidos(self) -> None:
        assert datos_lab.DESCARGA_FIN_EXCLUSIVO == "2026-08-28" and date(2026, 8, 27) == datos_lab.FIN

    def test_sin_el_preregistro_exacto_no_corre(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        salida = tmp_path / "r.json"
        assert cli.main(["correr", "--cosecha", "x", "--prereg-sha256", "0", "--salida", str(salida)]) == 2
        assert not salida.exists()

    def test_produccion_no_importa_el_laboratorio(self) -> None:
        for fichero in Path("superbot/ia").glob("*.py"):
            assert "superbot.lab" not in fichero.read_text(encoding="utf-8"), fichero
