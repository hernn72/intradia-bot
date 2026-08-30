"""Calendario de eventos: macro curado y resultados del proveedor."""

from __future__ import annotations

from datetime import date
from typing import Optional

import pytest

from advisor.events.calendar import EventCalendar, load_macro_events
from advisor.events.models import (
    ALCANCE_ACTIVO,
    ALCANCE_GLOBAL,
    TIPO_BANCO_CENTRAL,
    TIPO_RESULTADOS,
    MarketEvent,
)

HOY = date(2026, 8, 29)


def macro(*fechas: date) -> list:
    return [
        MarketEvent(
            fecha=f, tipo=TIPO_BANCO_CENTRAL, alcance=ALCANCE_GLOBAL,
            titulo="Decisión de tipos", fuente="banco central",
        )
        for f in fechas
    ]


class FuenteFalsa:
    """Fuente de resultados con una fecha fija, sin red."""

    def __init__(self, fecha: Optional[date]) -> None:
        self._fecha = fecha
        self.consultas = 0

    def next_earnings(self, symbol: str) -> Optional[MarketEvent]:
        self.consultas += 1
        if self._fecha is None:
            return None
        return MarketEvent(
            fecha=self._fecha, tipo=TIPO_RESULTADOS, alcance=ALCANCE_ACTIVO,
            titulo="Publicación de resultados", fuente="proveedor",
            simbolo=symbol, confirmada=False,
        )


class TestCargaDelCalendarioMacro:
    def test_carga_el_calendario_real_del_proyecto(self) -> None:
        eventos = load_macro_events("events.yaml")
        assert eventos
        assert all(e.tipo == TIPO_BANCO_CENTRAL for e in eventos)
        assert all(e.alcance == ALCANCE_GLOBAL for e in eventos)
        # La fuente declarada debe llegar hasta el evento, para que el informe
        # pueda decir de dónde sale la fecha.
        assert all(e.fuente.startswith("http") for e in eventos)

    def test_fichero_inexistente(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_macro_events(tmp_path / "no-existe.yaml")

    def test_evento_sin_fecha_valida_falla(self, tmp_path) -> None:
        ruta = tmp_path / "events.yaml"
        ruta.write_text("eventos:\n  - fecha: 'mañana'\n    institucion: Fed\n    titulo: x\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no es una fecha válida"):
            load_macro_events(ruta)

    def test_eventos_desordenados_fallan(self, tmp_path) -> None:
        ruta = tmp_path / "events.yaml"
        ruta.write_text(
            "eventos:\n"
            "  - {fecha: 2027-01-01, institucion: Fed, titulo: b}\n"
            "  - {fecha: 2026-01-01, institucion: Fed, titulo: a}\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="ordenados"):
            load_macro_events(ruta)

    def test_calendario_vacio_falla(self, tmp_path) -> None:
        ruta = tmp_path / "events.yaml"
        ruta.write_text("eventos: []\n", encoding="utf-8")
        with pytest.raises(ValueError, match="ningún evento"):
            load_macro_events(ruta)


class TestEventCalendar:
    def test_solo_devuelve_lo_que_cae_en_la_ventana(self) -> None:
        cal = EventCalendar(macro(date(2026, 8, 20), date(2026, 9, 5), date(2026, 12, 1)))
        fechas = [e.fecha for e in cal.proximos(dias=14, hoy=HOY)]
        # El del 20 de agosto ya pasó y el de diciembre queda lejos.
        assert fechas == [date(2026, 9, 5)]

    def test_los_resultados_solo_aparecen_si_se_pide_el_activo(self) -> None:
        fuente = FuenteFalsa(date(2026, 9, 3))
        cal = EventCalendar(macro(date(2026, 9, 5)), fuente)

        assert len(cal.proximos(dias=14, hoy=HOY)) == 1
        assert fuente.consultas == 0

        con_activo = cal.proximos("SAP.DE", dias=14, hoy=HOY)
        assert [e.tipo for e in con_activo] == [TIPO_RESULTADOS, TIPO_BANCO_CENTRAL]

    def test_una_fecha_de_resultados_caducada_no_es_un_evento(self) -> None:
        """El proveedor devuelve a veces la última publicación en vez de la
        siguiente; presentarla como próxima sería mentir con un dato real."""
        cal = EventCalendar(macro(date(2026, 9, 5)), FuenteFalsa(date(2026, 7, 27)))
        assert all(e.tipo == TIPO_BANCO_CENTRAL for e in cal.proximos("MC.PA", dias=30, hoy=HOY))

    def test_activo_sin_resultados_no_rompe(self) -> None:
        cal = EventCalendar(macro(date(2026, 9, 5)), FuenteFalsa(None))
        assert len(cal.proximos("EUNL.DE", dias=14, hoy=HOY)) == 1

    def test_ventana_negativa_falla(self) -> None:
        cal = EventCalendar(macro(date(2026, 9, 5)))
        with pytest.raises(ValueError, match="dias debe ser"):
            cal.proximos(dias=-1, hoy=HOY)

    def test_avisa_cuando_el_calendario_se_agota(self) -> None:
        """Un calendario agotado no da error: deja de ver eventos, que es la
        forma más silenciosa de fallar."""
        cal = EventCalendar(macro(date(2026, 9, 5)))
        assert "actualiza events.yaml" in cal.avisar_si_se_agota(HOY)
        assert EventCalendar(macro(date(2027, 12, 16))).avisar_si_se_agota(HOY) is None

    def test_alarmas_declaran_calendario_sin_futuro_y_reutilizan_cobertura(self) -> None:
        cal = EventCalendar(macro(date(2026, 8, 1)))

        alarmas = cal.alarmas_salud(HOY)

        assert any("ningún evento macro futuro" in alarma for alarma in alarmas)
        assert any("actualiza events.yaml" in alarma for alarma in alarmas)

    def test_la_fecha_estimada_se_declara_como_tal(self) -> None:
        estimada = FuenteFalsa(date(2026, 9, 3)).next_earnings("SAP.DE")
        assert "estimada" in estimada.etiqueta_fuente
        confirmada = macro(date(2026, 9, 5))[0]
        assert "estimada" not in confirmada.etiqueta_fuente

    def test_dias_hasta(self) -> None:
        evento = macro(date(2026, 9, 5))[0]
        assert evento.dias_hasta(HOY) == 7
        assert evento.dias_hasta(date(2026, 9, 12)) == -7
