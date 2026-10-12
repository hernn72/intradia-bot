"""Telegram del asesor: un único aviso corto con las OPERAR, nunca el informe.

El informe completo se partía en 7 mensajes. Telegram es ahora una vista de
operación (ticker, entrada máxima, stop, objetivo 2, RR y tamaño) y el informe
sigue saliendo entero por la salida estándar y la base de datos.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import List

import pytest

from advisor.analysis.analyzer import AnalysisResult
from advisor.analysis.opportunity import RADAR_DESCARTAR, RADAR_OPERAR, RADAR_VIGILAR
from advisor.config import AdvisorConfig
from advisor.data.freshness import DataFreshness
from advisor.data.fx import FxConverter
from advisor.events.models import ALCANCE_GLOBAL, TIPO_BANCO_CENTRAL, MarketEvent
from advisor.report.formatter import format_report, format_telegram_opportunities
from advisor.telegram.notifier import TELEGRAM_MAX_CHARS
from tests.conftest import FakeProvider
from tests.test_report import _opportunity as _opportunity_sin_frescura

GENERATED_AT = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)

# Lo que el informe completo lleva y el aviso de Telegram no debe llevar.
_SECCIONES_DEL_INFORME = ["SITUACIÓN GLOBAL", "RADAR", "DESCARTADOS", "caché", "Tesis", "Score"]


@pytest.fixture
def fx() -> FxConverter:
    return FxConverter(FakeProvider(closes={"EURUSD=X": 1.25}), "EUR")


@pytest.fixture
def config() -> AdvisorConfig:
    return AdvisorConfig(horizontes={"swing": {"interval": "1d", "period": "1y", "min_bars": 120}})


def _frescura(quality: str = "OK") -> DataFreshness:
    return DataFreshness(
        last_bar_date=date(2026, 10, 9),
        natural_days=3,
        sessions_approx=0,
        label="al día",
        calendar="XETR",
        quality=quality,
    )


def _opportunity(asset, context, quality: str = "OK"):
    """Oportunidad con su frescura medida, como en la pasada real.

    Sin frescura, la ficha y el aviso la recalculan desde la fecha de la barra
    sin calendario y sale DEGRADADO: no es el caso que se quiere probar aquí.
    """

    return replace(_opportunity_sin_frescura(asset, context), data_freshness=_frescura(quality))


def _result(opportunities, context) -> AnalysisResult:
    return AnalysisResult(
        generated_at=GENERATED_AT,
        horizonte="swing",
        interval="1d",
        context=context,
        opportunities=opportunities,
        overview=[],
    )


def _mezcla(asset_eur, asset_usd, context) -> List:
    """Dos OPERAR, una en vigilancia y una descartada."""

    operar_eur = _opportunity(asset_eur, context)
    operar_usd = _opportunity(asset_usd, context)
    assert operar_eur.radar == RADAR_OPERAR and operar_usd.radar == RADAR_OPERAR
    vigilada = replace(_opportunity(asset_eur, context), radar=RADAR_VIGILAR)
    descartada = replace(_opportunity(asset_usd, context), radar=RADAR_DESCARTAR)
    return [operar_eur, operar_usd, vigilada, descartada]


class TestFormatoTelegram:
    def test_varias_oportunidades_en_un_unico_mensaje_compacto(
        self, asset_eur, asset_usd, benign_context, fx, config
    ) -> None:
        result = _result(_mezcla(asset_eur, asset_usd, benign_context), benign_context)
        aviso = format_telegram_opportunities(result, config, fx)

        assert aviso is not None
        assert aviso.startswith("📊 ASESOR — OPORTUNIDADES\n")
        assert aviso.count("🟢 ") == 2
        assert "🟢 SAP.DE" in aviso and "🟢 AAPL" in aviso
        assert aviso.endswith("2 oportunidades detectadas.")
        assert len(aviso) <= TELEGRAM_MAX_CHARS

    def test_cada_ficha_lleva_solo_los_seis_datos_operativos(self, asset_eur, benign_context, fx, config) -> None:
        operar = _opportunity(asset_eur, benign_context)
        aviso = format_telegram_opportunities(_result([operar], benign_context), config, fx)

        assert aviso is not None
        ficha = aviso.split("🟢 SAP.DE\n", 1)[1].split("\n\n", 1)[0].splitlines()
        assert [linea.split(":", 1)[0] for linea in ficha] == [
            "Entrada máx.", "Stop", "Objetivo", "RR a 100,00 €", "Tamaño sugerido",
        ]
        levels = operar.levels

        def coma(value: float) -> str:
            return f"{value:.2f}".replace(".", ",")

        assert ficha[0] == f"Entrada máx.: {coma(levels.entry_max)} €"
        assert ficha[1] == f"Stop: {coma(levels.stop)} €"
        assert ficha[2] == f"Objetivo: {coma(levels.target2)} €"
        assert ficha[3] == f"RR a {coma(operar.execution.entry_price)} €: {coma(operar.execution.rr)}"
        assert aviso.endswith("1 oportunidad detectada.")

    def test_rr_indica_el_precio_al_que_se_calcula(self, asset_eur, benign_context, fx, config) -> None:
        """El RR es al precio de referencia; si no se dice, parece el de la entrada máxima."""

        base = _opportunity(asset_eur, benign_context)
        por_debajo = replace(base, execution=replace(base.execution, entry_price=97.5, rr=2.13))
        assert por_debajo.execution.entry_price < por_debajo.levels.entry_max
        aviso = format_telegram_opportunities(_result([por_debajo], benign_context), config, fx)

        assert aviso is not None
        assert "RR a 97,50 €: 2,13" in aviso
        assert "Entrada máx.: 100,00 €" in aviso

    def test_sin_avisos_si_no_hay_extension_ni_dato_degradado(self, asset_eur, benign_context, fx, config) -> None:
        operar = _opportunity(asset_eur, benign_context)
        assert operar.levels.chase is False
        aviso = format_telegram_opportunities(_result([operar], benign_context), config, fx)

        assert aviso is not None
        assert "⚠️" not in aviso

    def test_avisos_operativos_de_extension_y_dato_degradado(self, asset_eur, benign_context, fx, config) -> None:
        base = _opportunity(asset_eur, benign_context)
        extendida = replace(base, levels=replace(base.levels, chase=True))
        degradada = _opportunity(asset_eur, benign_context, quality="DEGRADADO")
        incompleta = _opportunity(asset_eur, benign_context, quality="INCOMPLETO")

        def ficha(opportunity) -> str:
            aviso = format_telegram_opportunities(_result([opportunity], benign_context), config, fx)
            assert aviso is not None
            return aviso.split("Tamaño sugerido: ", 1)[1].split("\n\n", 1)[0]

        assert ficha(extendida).split("\n")[1:] == ["⚠️ Esperar pullback / no perseguir"]
        assert ficha(degradada).split("\n")[1:] == ["⚠️ Dato degradado"]
        assert ficha(incompleta).split("\n")[1:] == ["⚠️ Dato degradado"]
        ambas = replace(degradada, levels=replace(degradada.levels, chase=True))
        assert ficha(ambas).split("\n")[1:] == ["⚠️ Esperar pullback / no perseguir", "⚠️ Dato degradado"]

    def test_tamano_sin_decimal_sobrante(self, asset_eur, benign_context, fx, config) -> None:
        base = _opportunity(asset_eur, benign_context)
        diez = replace(base, sizing=replace(base.sizing, position_pct=10.0))
        nueve = replace(base, sizing=replace(base.sizing, position_pct=8.94))
        aviso = format_telegram_opportunities(_result([diez, nueve], benign_context), config, fx)

        assert aviso is not None
        assert "Tamaño sugerido: 10 %" in aviso
        assert "Tamaño sugerido: 8,9 %" in aviso

    def test_activo_en_dolares_muestra_tambien_euros(self, asset_usd, benign_context, fx, config) -> None:
        aviso = format_telegram_opportunities(
            _result([_opportunity(asset_usd, benign_context)], benign_context), config, fx
        )
        assert aviso is not None
        assert "USD (≈ " in aviso and " €)" in aviso

    def test_cero_oportunidades_no_hay_mensaje(self, asset_eur, asset_usd, benign_context, fx, config) -> None:
        sin_operar = [o for o in _mezcla(asset_eur, asset_usd, benign_context) if o.radar != RADAR_OPERAR]
        assert format_telegram_opportunities(_result(sin_operar, benign_context), config, fx) is None
        assert format_telegram_opportunities(_result([], benign_context), config, fx) is None

    def test_no_lleva_secciones_del_informe(self, asset_eur, asset_usd, benign_context, fx, config) -> None:
        result = _result(_mezcla(asset_eur, asset_usd, benign_context), benign_context)
        informe = format_report(result, config, fx)
        aviso = format_telegram_opportunities(result, config, fx)

        assert aviso is not None
        for texto in _SECCIONES_DEL_INFORME:
            assert texto not in aviso, texto
        # Comprobación de que la lista no es vacua: el informe sí lleva lo que el aviso calla.
        for texto in ["SITUACIÓN GLOBAL", "RADAR", "DESCARTADOS", "Tesis", "Score"]:
            assert texto in informe, texto

    def test_respeta_el_tope_top_n_del_informe(self, asset_eur, benign_context, fx, config) -> None:
        config = config.model_copy(update={"report": config.report.model_copy(update={"top_n": 2})})
        operar = [_opportunity(asset_eur, benign_context) for _ in range(3)]
        aviso = format_telegram_opportunities(_result(operar, benign_context), config, fx)

        assert aviso is not None
        assert aviso.count("🟢 ") == 2
        assert aviso.endswith("3 oportunidades detectadas. Se muestran las 2 primeras.")


class _NotificadorEspia:
    def __init__(self) -> None:
        self.mensajes: List[str] = []
        self.largos: List[str] = []

    def send_message(self, text: str) -> bool:
        self.mensajes.append(text)
        return True

    def send_long_message(self, text: str) -> bool:
        self.largos.append(text)
        return True


class TestAnalizarConTelegram:
    def _ejecutar(self, tmp_path, monkeypatch, opportunities, context) -> _NotificadorEspia:
        import advisor.main as main
        import advisor.run.manifest as manifest
        from advisor.config import load_config
        from advisor.universe.loader import load_universe

        resultado = _result(opportunities, context)
        espia = _NotificadorEspia()
        config = load_config("config.yaml").model_copy(update={"db_path": str(tmp_path / "pasada.db")})

        monkeypatch.setattr(main, "run_analysis", lambda *a, **k: resultado)
        monkeypatch.setattr(main, "_build_calendar", lambda *a, **k: None)
        monkeypatch.setattr(main, "_build_notifier", lambda: espia)
        # La medición del reloj sale a la red (NTP) cuando no hay timedatectl.
        monkeypatch.setattr(manifest, "measure_clock_drift_seconds", lambda: None)

        args = argparse.Namespace(grupos=None, horizonte="swing", sin_ia=True, sin_guardar=False, telegram=True)
        assert main.cmd_analizar(args, config, load_universe("universe.yaml")) == 0
        self.db_path = config.db_path
        return espia

    def test_varias_oportunidades_un_solo_mensaje_y_el_informe_sigue_fuera(
        self, tmp_path, monkeypatch, capsys, asset_eur, asset_usd, benign_context
    ) -> None:
        from advisor.storage.db import AdvisorDB

        espia = self._ejecutar(tmp_path, monkeypatch, _mezcla(asset_eur, asset_usd, benign_context), benign_context)

        assert espia.largos == []
        assert len(espia.mensajes) == 1
        aviso = espia.mensajes[0]
        assert aviso.startswith("📊 ASESOR — OPORTUNIDADES")
        for texto in _SECCIONES_DEL_INFORME:
            assert texto not in aviso, texto

        informe = capsys.readouterr().out
        for seccion in ["🌍 SITUACIÓN GLOBAL", "🔥 OPORTUNIDADES DETECTADAS", "👀 RADAR", "🔴 DESCARTADOS"]:
            assert seccion in informe
        assert {row["symbol"] for row in AdvisorDB(self.db_path).get_recent_recommendations()} == {"SAP.DE", "AAPL"}

    def test_sin_operar_no_se_envia_nada_pero_hay_informe(
        self, tmp_path, monkeypatch, capsys, asset_eur, asset_usd, benign_context
    ) -> None:
        sin_operar = [o for o in _mezcla(asset_eur, asset_usd, benign_context) if o.radar != RADAR_OPERAR]
        espia = self._ejecutar(tmp_path, monkeypatch, sin_operar, benign_context)

        assert espia.mensajes == [] and espia.largos == []
        assert "NO OPERAR / MANTENER LIQUIDEZ" in capsys.readouterr().out


class _NotificadorQueFalla(_NotificadorEspia):
    def send_message(self, text: str) -> bool:
        self.mensajes.append(text)
        return False


class TestPasadaEventoConTelegram:
    """`pasada-evento` manda el mismo aviso compacto y solo marca SENT si se envió.

    SENT es lo único que deduplica (`claim_event_passes`); CLAIMED es un intento
    que se puede repetir. Sin OPERAR no hay mensaje, así que no hay nada que
    deduplicar y los eventos no pueden quedar SENT.
    """

    HOY = date(2026, 10, 12)

    def _evento(self) -> MarketEvent:
        return MarketEvent(
            fecha=self.HOY,
            tipo=TIPO_BANCO_CENTRAL,
            alcance=ALCANCE_GLOBAL,
            titulo="Decisión de tipos del BCE",
            fuente="banco central",
        )

    def _ejecutar(self, tmp_path, monkeypatch, opportunities, context, notifier):
        import advisor.main as main
        import advisor.run.manifest as manifest
        from advisor.config import load_config
        from advisor.events.calendar import EventCalendar
        from advisor.events.passes import deterministic_event_pass_id
        from advisor.storage.db import AdvisorDB
        from advisor.universe.loader import load_universe

        config = load_config("config.yaml").model_copy(update={"db_path": str(tmp_path / "pasada.db")})
        assert config.events.enabled, "el test cubre la pasada con el calendario activado, como en la Pi"
        resultado = _result(opportunities, context)

        monkeypatch.setattr(main, "YahooEarningsSource", lambda *a, **k: None)
        monkeypatch.setattr(main.EventCalendar, "load", classmethod(lambda cls, *a, **k: EventCalendar([self._evento()])))
        monkeypatch.setattr(main, "run_analysis", lambda *a, **k: resultado)
        monkeypatch.setattr(main, "_build_notifier", lambda: notifier)
        monkeypatch.setattr(manifest, "measure_clock_drift_seconds", lambda: None)

        args = argparse.Namespace(horizonte="swing", fecha=self.HOY.isoformat(), sin_ia=True)
        assert main.cmd_pasada_evento(args, config, load_universe("universe.yaml")) == 0
        event_id = deterministic_event_pass_id(self._evento(), "swing", "evento")
        return AdvisorDB(config.db_path), event_id

    def test_con_operar_un_mensaje_compacto_con_el_evento_y_queda_sent(
        self, tmp_path, monkeypatch, capsys, asset_eur, asset_usd, benign_context
    ) -> None:
        espia = _NotificadorEspia()
        db, event_id = self._ejecutar(
            tmp_path, monkeypatch, _mezcla(asset_eur, asset_usd, benign_context), benign_context, espia
        )

        assert espia.largos == []
        assert len(espia.mensajes) == 1
        primera, resto = espia.mensajes[0].split("\n", 1)
        assert primera.startswith("Pasada por evento: 2026-10-12 Decisión de tipos del BCE")
        assert resto.startswith("\n📊 ASESOR — OPORTUNIDADES")
        for texto in _SECCIONES_DEL_INFORME:
            assert texto not in espia.mensajes[0], texto
        assert db.get_event_pass(event_id)["status"] == "SENT"

        informe = capsys.readouterr().out
        assert informe.startswith("Pasada por evento: ")
        for seccion in ["🌍 SITUACIÓN GLOBAL", "👀 RADAR", "🔴 DESCARTADOS"]:
            assert seccion in informe
        assert {row["symbol"] for row in db.get_recent_recommendations()} == {"SAP.DE", "AAPL"}

    def test_envio_fallido_deja_claimed(self, tmp_path, monkeypatch, asset_eur, benign_context) -> None:
        falla = _NotificadorQueFalla()
        db, event_id = self._ejecutar(
            tmp_path, monkeypatch, [_opportunity(asset_eur, benign_context)], benign_context, falla
        )

        assert len(falla.mensajes) == 1
        assert db.get_event_pass(event_id)["status"] == "CLAIMED"

    def test_sin_operar_no_hay_mensaje_ni_sent_y_el_evento_sigue_reintentable(
        self, tmp_path, monkeypatch, capsys, asset_eur, asset_usd, benign_context
    ) -> None:
        from advisor.events.calendar import EventCalendar
        from advisor.events.passes import decide_event_pass

        espia = _NotificadorEspia()
        sin_operar = [o for o in _mezcla(asset_eur, asset_usd, benign_context) if o.radar != RADAR_OPERAR]
        db, event_id = self._ejecutar(tmp_path, monkeypatch, sin_operar, benign_context, espia)

        assert espia.mensajes == [] and espia.largos == []
        assert db.get_event_pass(event_id)["status"] == "CLAIMED"
        assert "NO OPERAR / MANTENER LIQUIDEZ" in capsys.readouterr().out
        # Las recomendaciones (VIGILAR/DESCARTAR) se persisten igual que antes.
        assert {row["symbol"] for row in db.get_recent_recommendations()} == {"SAP.DE", "AAPL"}
        repeticion = decide_event_pass(
            EventCalendar([self._evento()]), [asset_eur], db, horizonte="swing", today=self.HOY
        )
        assert repeticion.claimed_event_ids == [event_id]


def test_linea_de_evento_larga_no_hace_que_telegram_rechace_el_aviso() -> None:
    from advisor.main import _event_telegram
    from advisor.telegram.notifier import TELEGRAM_MAX_CHARS

    aviso = "📊 ASESOR — OPORTUNIDADES\n\n🟢 SAP.DE\n\n1 oportunidad detectada."
    pocos = [MarketEvent(fecha=date(2026, 10, 12), tipo=TIPO_BANCO_CENTRAL, alcance=ALCANCE_GLOBAL,
                         titulo="Decisión de tipos del BCE", fuente="banco central")]
    assert _event_telegram(pocos, aviso).startswith("Pasada por evento: 2026-10-12 Decisión de tipos del BCE")

    muchos = [replace(pocos[0], titulo=f"Evento {i} " + "x" * 120) for i in range(60)]
    texto = _event_telegram(muchos, aviso)
    assert len(texto) <= TELEGRAM_MAX_CHARS
    assert texto == f"Pasada por evento: 60 eventos hoy (detalle en el informe)\n\n{aviso}"
