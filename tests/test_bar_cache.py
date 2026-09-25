"""Caché local de barras de sesión cerrada ya validadas (T-018, C-09, D-41).

Los números están escritos en cada test a propósito: el caso que originó la
tarea es concreto —`SAP.DE` el 2026-09-14 a las 20:02 tiene la barra del 14, y
a las 06:02 del 15 el proveedor ha vuelto a la del 11— y un test que se apoyara
en «la última barra» no distinguiría la barra correcta de la reaparecida.
"""

from __future__ import annotations

import collections
import json
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd
import pytest

from advisor.data.bar_cache import (
    KIND_READJUSTMENT,
    KIND_REVISION,
    STATUS_DISABLED,
    STATUS_LIVE,
    STATUS_PINNED,
    STATUS_REANCHORED,
    STATUS_SERVED,
    CachedBarProvider,
    build_market_resolver,
)
from advisor.data.calendars import expected_sessions
from advisor.storage.db import AdvisorDB
from advisor.storage.migrations import LATEST_VERSION

SESIONES = expected_sessions("XETRA", date(2026, 3, 2), date(2026, 9, 14))
"""Sesiones reales de XETRA, no días naturales: la caché se mide en sesiones."""

TARDE_DEL_14 = datetime(2026, 9, 14, 20, 2, tzinfo=timezone.utc)
MANANA_DEL_15 = datetime(2026, 9, 15, 6, 2, tzinfo=timezone.utc)


def serie(sessions: List[date], start: float = 100.0, factor: float = 1.0) -> pd.DataFrame:
    """OHLCV determinista fechado en la zona de XETRA.

    ``factor`` multiplica toda la serie, que es exactamente lo que hace el
    proveedor cuando reajusta por un dividendo o un split.
    """

    index = pd.DatetimeIndex([pd.Timestamp(value, tz="Europe/Berlin") for value in sessions])
    closes = [(start + 0.5 * position) * factor for position in range(len(sessions))]
    return pd.DataFrame(
        {
            "Open": [close * 0.995 for close in closes],
            "High": [close * 1.01 for close in closes],
            "Low": [close * 0.99 for close in closes],
            "Close": closes,
            "Volume": [1_000_000.0] * len(sessions),
        },
        index=index,
    )


class ProveedorDeUniverso:
    """Proveedor con una serie por símbolo, como la pasada real."""

    def __init__(self, histories: dict) -> None:
        self.histories = histories

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        if symbol not in self.histories:
            raise ValueError(f"sin datos para '{symbol}'")
        return self.histories[symbol]

    def get_raw_history(
        self, symbol: str, period: str = "1y", interval: str = "1d", *, drop_na: bool = True
    ) -> pd.DataFrame:
        return self.get_history(symbol, period=period, interval=interval)

    def get_last_close(self, symbol: str, period: str = "5d", interval: str = "1d"):
        if symbol not in self.histories:
            return None, None
        history = self.histories[symbol]
        return float(history["Close"].iloc[-1]), history.index[-1]


class ProveedorDeSerie:
    """Proveedor que sirve exactamente la serie que se le da."""

    def __init__(self, history: pd.DataFrame) -> None:
        self.history = history
        self.calls: List[str] = []

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        self.calls.append(symbol)
        return self.history

    def get_raw_history(
        self, symbol: str, period: str = "1y", interval: str = "1d", *, drop_na: bool = True
    ) -> pd.DataFrame:
        return self.history


def cache(
    provider: ProveedorDeSerie,
    db: Optional[AdvisorDB],
    reference: datetime,
    *,
    window_sessions: int = 30,
    market: Optional[str] = "XETRA",
) -> CachedBarProvider:
    return CachedBarProvider(
        provider,
        store=db,
        resolve_market=lambda symbol: market,
        reference=reference,
        settlement_minutes=20,
        window_sessions=window_sessions,
        readjustment_tolerance=1e-4,
    )


def guardar(db: AdvisorDB, provider: CachedBarProvider) -> int:
    """Persiste lo que la pasada dejó pendiente, en el orden de `insert_analysis_result`.

    El reanclaje borra **antes** de insertar. Al revés, el `DELETE` se llevaría
    las barras nuevas y la caché quedaría vacía tras cada dividendo.
    """

    for symbol in provider.report.reanchored_symbols:
        db.delete_validated_bars(symbol)
    guardadas = db.insert_validated_bars(provider.report.bars_to_store)
    db.insert_bar_revisions(provider.report.revisions_to_store)
    return guardadas


@pytest.fixture
def db(tmp_path) -> AdvisorDB:
    return AdvisorDB(tmp_path / "cache.db")


def _cierres_por_sesion(df: pd.DataFrame) -> dict:
    return {
        pd.Timestamp(label).tz_convert("Europe/Berlin").date(): float(df["Close"].iloc[position])
        for position, label in enumerate(df.index)
    }


class TestReglaUnoLaBarraNoDesaparece:
    def test_barra_validada_sobrevive_a_que_el_proveedor_deje_de_servirla(self, db) -> None:
        """Regla 1: el caso real de `SAP.DE` entre el 14 por la tarde y el 15 por la mañana."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE", period="1y")
        assert guardar(db, tarde) > 0

        # A las 06:02 del 15 el proveedor ha retirado el 14 y ha vuelto al 11.
        retirada = SESIONES[:-1]
        assert retirada[-1] == date(2026, 9, 11)
        manana = cache(ProveedorDeSerie(serie(retirada)), db, MANANA_DEL_15)
        merged = manana.get_history("SAP.DE", period="1y")

        cierres = _cierres_por_sesion(merged)
        assert date(2026, 9, 14) in cierres
        assert cierres[date(2026, 9, 14)] == pytest.approx(_cierres_por_sesion(serie(SESIONES))[date(2026, 9, 14)])
        uso = manana.report.usage["SAP.DE"]
        assert uso.served_from_cache == (date(2026, 9, 14),)
        assert uso.status == STATUS_SERVED

    def test_la_serie_reinyectada_queda_ordenada_y_sin_duplicar_la_sesion(self, db) -> None:
        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        manana = cache(ProveedorDeSerie(serie(SESIONES[:-1])), db, MANANA_DEL_15)
        merged = manana.get_history("SAP.DE")

        fechas = [pd.Timestamp(label).tz_convert("Europe/Berlin").date() for label in merged.index]
        assert fechas == sorted(fechas)
        assert len(fechas) == len(set(fechas))
        assert fechas[-1] == date(2026, 9, 14)

    def test_sin_base_de_datos_la_cache_no_actua_y_no_revienta(self) -> None:
        provider = ProveedorDeSerie(serie(SESIONES))
        sin_cache = cache(provider, None, TARDE_DEL_14)

        merged = sin_cache.get_history("SAP.DE")

        assert merged is provider.history
        assert sin_cache.report.enabled is False


class TestReglaDosYTresNoSeInventaNada:
    def test_la_cache_no_inventa_una_sesion_nunca_observada(self, db) -> None:
        """Regla 2 y 3: la sesión del 15, exigible y jamás recibida, no se fabrica."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        # El 16 a las 06:02 la sesión del 15 ya es exigible, y nadie la ha visto.
        provider = ProveedorDeSerie(serie(SESIONES))
        despues = cache(provider, db, datetime(2026, 9, 16, 6, 2, tzinfo=timezone.utc))
        merged = despues.get_history("SAP.DE")

        cierres = _cierres_por_sesion(merged)
        assert date(2026, 9, 15) not in cierres
        uso = despues.report.usage["SAP.DE"]
        assert date(2026, 9, 15) in uso.sessions_never_observed
        assert uso.served_from_cache == ()

    def test_contador_de_valor_marginal_solo_cuenta_lo_nunca_observado(self, db) -> None:
        """Regla 6: una sesión que sí se vio antes no suma al valor marginal."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        # El 16 por la mañana: el proveedor ha retirado el 14 (ya observado) y
        # nunca ha entregado el 15 (exigible desde anoche).
        manana = cache(ProveedorDeSerie(serie(SESIONES[:-1])), db, datetime(2026, 9, 16, 6, 2, tzinfo=timezone.utc))
        manana.get_history("SAP.DE")

        uso = manana.report.usage["SAP.DE"]
        assert uso.served_from_cache == (date(2026, 9, 14),)
        assert uso.sessions_never_observed == (date(2026, 9, 15),)
        assert manana.report.never_observed_count == 1

    def test_no_cuenta_sesiones_anteriores_a_la_primera_barra_del_activo(self, db) -> None:
        """Una cotización que empieza el 2026-09-07 no reclama las sesiones de antes."""

        recientes = [value for value in SESIONES if value >= date(2026, 9, 7)]
        provider = ProveedorDeSerie(serie(recientes))
        reciente = cache(provider, db, TARDE_DEL_14)

        reciente.get_history("NUEVA.DE")

        uso = reciente.report.usage["NUEVA.DE"]
        assert uso.sessions_never_observed == ()
        assert uso.status == STATUS_LIVE


class TestReglaCuatroRevisiones:
    def test_revision_de_barra_no_sobrescribe_en_silencio(self, db) -> None:
        """Regla 4: quedan las dos versiones, con instante y proveedor."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)
        original = _cierres_por_sesion(serie(SESIONES))[date(2026, 9, 14)]

        revisada = serie(SESIONES)
        revisada.iloc[-1, revisada.columns.get_loc("Close")] = original + 0.5
        siguiente = cache(ProveedorDeSerie(revisada), db, MANANA_DEL_15)
        merged = siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        # Manda la primera validada: el análisis sigue viendo el cierre original.
        assert _cierres_por_sesion(merged)[date(2026, 9, 14)] == pytest.approx(original)
        uso = siguiente.report.usage["SAP.DE"]
        assert uso.pinned_revisions == (date(2026, 9, 14),)
        assert uso.status == STATUS_PINNED

        revisiones = db.get_bar_revisions("SAP.DE")
        assert len(revisiones) == 1
        fila = revisiones[0]
        assert fila["kind"] == KIND_REVISION
        assert fila["previous_close"] == pytest.approx(original)
        assert fila["new_close"] == pytest.approx(original + 0.5)
        assert fila["applied"] == 0
        assert fila["provider"] == "yfinance"
        assert fila["observed_at"] == MANANA_DEL_15.isoformat()
        assert fila["previous_observed_at"] == TARDE_DEL_14.isoformat()

    def test_la_barra_guardada_no_se_sobrescribe_en_la_tabla(self, db) -> None:
        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)
        original = _cierres_por_sesion(serie(SESIONES))[date(2026, 9, 14)]

        revisada = serie(SESIONES)
        revisada.iloc[-1, revisada.columns.get_loc("Close")] = original + 0.5
        siguiente = cache(ProveedorDeSerie(revisada), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        guardadas = {
            row["session_date"]: row["close"] for row in db.get_validated_bars("SAP.DE")
        }
        assert guardadas["2026-09-14"] == pytest.approx(original)

    def test_una_sola_barra_solapada_no_se_declara_reajuste(self, db) -> None:
        """Sin dos barras solapadas no se puede distinguir reajuste de revisión.

        La lectura conservadora es la del propietario: manda la primera validada
        y la diferencia queda registrada como revisión, no como reajuste.
        """

        tarde = cache(ProveedorDeSerie(serie(SESIONES[-1:])), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        siguiente = cache(ProveedorDeSerie(serie(SESIONES[-1:], factor=1.02)), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        assert siguiente.report.usage["SAP.DE"].status == STATUS_PINNED
        assert [row["kind"] for row in db.get_bar_revisions("SAP.DE")] == [KIND_REVISION]


class TestReajusteDeLaSerie:
    def test_reajuste_uniforme_se_adopta_y_no_deja_dos_bases(self, db) -> None:
        """Un dividendo reescribe toda la serie por un factor: se adopta la base nueva."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        ajustada = serie(SESIONES, factor=0.99)
        siguiente = cache(ProveedorDeSerie(ajustada), db, MANANA_DEL_15)
        merged = siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        uso = siguiente.report.usage["SAP.DE"]
        assert uso.status == STATUS_REANCHORED
        assert uso.readjustment_factor == pytest.approx(0.99, abs=1e-6)
        assert uso.pinned_revisions == ()
        # La serie que ve el análisis es la viva entera, en una sola base.
        assert _cierres_por_sesion(merged) == pytest.approx(_cierres_por_sesion(ajustada))
        # Y lo guardado también: nada sobrevive en la base vieja.
        guardadas = {row["session_date"]: row["close"] for row in db.get_validated_bars("SAP.DE")}
        esperadas = _cierres_por_sesion(ajustada)
        assert guardadas["2026-09-14"] == pytest.approx(esperadas[date(2026, 9, 14)])
        assert all(
            valor == pytest.approx(esperadas[date.fromisoformat(fecha)])
            for fecha, valor in guardadas.items()
        )
        revisiones = db.get_bar_revisions("SAP.DE")
        assert revisiones
        assert {row["kind"] for row in revisiones} == {KIND_READJUSTMENT}
        assert all(row["applied"] == 1 for row in revisiones)
        assert all(row["factor"] == pytest.approx(0.99, abs=1e-6) for row in revisiones)

    def test_el_reanclaje_declara_la_barra_que_se_pierde(self, db) -> None:
        """Coste declarado: escalar la barra ausente daría un valor no observado."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        ajustada_sin_el_14 = serie(SESIONES, factor=0.99).iloc[:-1]
        siguiente = cache(ProveedorDeSerie(ajustada_sin_el_14), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")

        uso = siguiente.report.usage["SAP.DE"]
        assert uso.status == STATUS_REANCHORED
        assert "2026-09-14" in uso.detail
        assert "se pierden" in uso.detail

    def test_una_diferencia_de_redondeo_no_es_revision(self, db) -> None:
        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        casi_igual = serie(SESIONES, factor=1 + 1e-6)
        siguiente = cache(ProveedorDeSerie(casi_igual), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")

        assert siguiente.report.usage["SAP.DE"].status == STATUS_LIVE
        assert db.get_bar_revisions("SAP.DE") == []


class TestBarraEnCursoYPlaza:
    def test_una_barra_de_sesion_no_cerrada_no_entra_en_la_cache(self, db) -> None:
        """D-37: una barra en curso no es un dato, así que no se guarda."""

        con_el_15_en_curso = serie([*SESIONES, date(2026, 9, 15)])
        provider = cache(ProveedorDeSerie(con_el_15_en_curso), db, MANANA_DEL_15)
        provider.get_history("SAP.DE")
        guardar(db, provider)

        fechas = {row["session_date"] for row in db.get_validated_bars("SAP.DE")}
        assert "2026-09-15" not in fechas
        assert "2026-09-14" in fechas

    def test_simbolo_sin_plaza_declarada_no_usa_cache_y_lo_declara(self, db) -> None:
        """INV-16: sin plaza no se supone ninguna; la caché se aparta y lo dice."""

        provider = ProveedorDeSerie(serie(SESIONES))
        sin_plaza = cache(provider, db, TARDE_DEL_14, market=None)

        merged = sin_plaza.get_history("RARO.XX")

        assert merged is provider.history
        uso = sin_plaza.report.usage["RARO.XX"]
        assert uso.status == STATUS_DISABLED
        assert db.get_validated_bars("RARO.XX") == []

    def test_intervalo_no_diario_pasa_de_largo(self, db) -> None:
        provider = ProveedorDeSerie(serie(SESIONES))
        intradia = cache(provider, db, TARDE_DEL_14)

        merged = intradia.get_history("SAP.DE", period="60d", interval="15m")

        assert merged is provider.history
        assert intradia.report.usage == {}

    def test_la_ventana_limita_lo_que_se_guarda(self, db) -> None:
        corta = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14, window_sessions=5)
        corta.get_history("SAP.DE")
        guardar(db, corta)

        fechas = sorted(row["session_date"] for row in db.get_validated_bars("SAP.DE"))
        assert len(fechas) == 5
        assert fechas[-1] == "2026-09-14"
        assert fechas[0] == "2026-09-08"

    def test_un_fallo_de_la_cache_no_tumba_la_pasada_y_se_declara(self, db) -> None:
        class BaseQueFalla:
            def get_validated_bars(self, data_symbol, since=None):
                raise RuntimeError("base bloqueada")

        provider = ProveedorDeSerie(serie(SESIONES))
        rota = CachedBarProvider(
            provider,
            store=BaseQueFalla(),
            resolve_market=lambda symbol: "XETRA",
            reference=TARDE_DEL_14,
            settlement_minutes=20,
            window_sessions=30,
            readjustment_tolerance=1e-4,
        )

        merged = rota.get_history("SAP.DE")

        assert merged is provider.history
        uso = rota.report.usage["SAP.DE"]
        assert uso.status == "CACHE_NO_APLICADA"
        assert "base bloqueada" in uso.detail


class TestResolverDePlaza:
    def test_usa_la_plaza_declarada_en_el_universo(self, universe) -> None:
        resolve = build_market_resolver(universe)

        assert resolve("SAP.DE") == "XETRA"
        assert resolve("AAPL") == "NASDAQ"

    def test_un_indice_de_contexto_se_resuelve_por_su_simbolo(self, universe) -> None:
        resolve = build_market_resolver(universe)

        assert resolve("^STOXX50E") == "XETRA"
        assert resolve("^VIX") == "NYSE"

    def test_lo_que_no_se_puede_resolver_devuelve_none(self, universe) -> None:
        assert build_market_resolver(universe)("EURUSD=X") is None


class TestEsquema:
    def test_la_migracion_v6_crea_las_tablas_de_la_cache(self, tmp_path) -> None:
        db = AdvisorDB(tmp_path / "nueva.db")

        assert db.schema_version() == LATEST_VERSION
        with db._connect() as conn:
            tablas = {
                row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            frescura = {row[1] for row in conn.execute("PRAGMA table_info(data_freshness_measurement)")}

        assert {"validated_bar", "validated_bar_revision"} <= tablas
        assert {
            "bars_served_from_cache",
            "bars_pinned_revisions",
            "sessions_never_observed",
            "bar_cache_status",
        } <= frescura

    def test_una_sesion_solo_puede_tener_una_barra_guardada(self, db) -> None:
        fila = {
            "data_symbol": "SAP.DE",
            "market": "XETRA",
            "session_date": "2026-09-14",
            "bar_timestamp": "2026-09-14T00:00:00+02:00",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 10.0,
            "observed_at": TARDE_DEL_14.isoformat(),
            "provider": "yfinance",
            "run_id": None,
        }

        assert db.insert_validated_bars([fila]) == 1
        assert db.insert_validated_bars([dict(fila, close=9.9)]) == 0
        assert [row["close"] for row in db.get_validated_bars("SAP.DE")] == [1.5]

    def test_get_validated_bars_recorta_por_fecha(self, db) -> None:
        filas = [
            {
                "data_symbol": "SAP.DE",
                "market": "XETRA",
                "session_date": value.isoformat(),
                "bar_timestamp": f"{value.isoformat()}T00:00:00+02:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": None,
                "observed_at": TARDE_DEL_14.isoformat(),
                "provider": "yfinance",
                "run_id": None,
            }
            for value in (date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 14))
        ]
        db.insert_validated_bars(filas)

        recortadas = db.get_validated_bars("SAP.DE", date(2026, 9, 11))

        assert [row["session_date"] for row in recortadas] == ["2026-09-11", "2026-09-14"]


class TestVentanaDeCalendario:
    def test_un_cierre_largo_no_deja_la_ventana_corta(self, db) -> None:
        """La ventana se pide en sesiones, no en días naturales.

        Si se pidieran 30 días naturales, un puente o unas vacaciones dejarían
        la ventana con menos sesiones sin que nadie se enterara.
        """

        provider = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14, window_sessions=30)
        provider.get_history("SAP.DE")
        guardar(db, provider)

        fechas = sorted(date.fromisoformat(row["session_date"]) for row in db.get_validated_bars("SAP.DE"))
        assert len(fechas) == 30
        assert (fechas[-1] - fechas[0]) > timedelta(days=30)


class TestPasadaCompleta:
    """Integración: la pasada entera, con la caché puesta y persistiendo.

    Es donde se comprueba lo que la ficha pide de verdad: que las
    recomendaciones no cambien porque el proveedor haya retirado una barra, y
    que la medición de esa pasada lo declare (INV-21).
    """

    def _provider(self, sap: pd.DataFrame) -> ProveedorDeUniverso:
        return ProveedorDeUniverso(
            {
                "SAP.DE": sap,
                "AAPL": serie(SESIONES, start=180.0),
                "^STOXX50E": serie(SESIONES, start=5000.0),
                "^GSPC": serie(SESIONES, start=5500.0),
            }
        )

    def _pasada(self, config, universe, db, provider, reference):
        from advisor.analysis.analyzer import run_analysis
        from advisor.data.fx import FxConverter
        from advisor.main import _persist
        from advisor.run.manifest import build_run_manifest

        cached = CachedBarProvider(
            provider,
            store=db,
            resolve_market=build_market_resolver(universe),
            reference=reference,
            settlement_minutes=20,
            window_sessions=30,
            readjustment_tolerance=1e-4,
        )
        manifest = build_run_manifest(
            command="analizar",
            config=config,
            universe=universe,
            schema_version=db.schema_version(),
            timestamp=reference,
        )
        result = run_analysis(config, universe, cached, horizonte="swing", now=reference)
        _persist(result, FxConverter(cached, config.base_currency), db, manifest)
        return result

    def test_una_barra_retirada_no_cambia_la_recomendacion_y_queda_declarada(
        self, config, universe, db
    ) -> None:
        primera = self._pasada(
            config, universe, db, self._provider(serie(SESIONES)), TARDE_DEL_14
        )
        sap_antes = next(o for o in primera.opportunities if o.asset.symbol == "SAP.DE")

        # El proveedor retira la barra del 14 en la pasada de la mañana.
        segunda = self._pasada(
            config, universe, db, self._provider(serie(SESIONES[:-1])), MANANA_DEL_15
        )
        sap_despues = next(o for o in segunda.opportunities if o.asset.symbol == "SAP.DE")

        assert sap_despues.levels.price == pytest.approx(sap_antes.levels.price)
        assert sap_despues.score.value == pytest.approx(sap_antes.score.value)
        assert sap_despues.accion == sap_antes.accion
        assert sap_despues.data_freshness.last_bar_date == date(2026, 9, 14)
        assert sap_despues.data_freshness.sessions_approx == 0

        assert segunda.bar_cache is not None
        assert segunda.bar_cache.usage["SAP.DE"].served_from_cache == (date(2026, 9, 14),)

    def test_sin_cache_la_misma_retirada_si_movería_la_recomendacion(
        self, config, universe, db
    ) -> None:
        """Contraprueba: si la caché no actuara, el precio sí cambiaría.

        Sin esto, el test de arriba pasaría igual con una caché que no hiciera
        nada, porque no distinguiría «la barra volvió» de «nunca se fue».
        """

        from advisor.analysis.analyzer import run_analysis

        completa = run_analysis(
            config, universe, self._provider(serie(SESIONES)), horizonte="swing", now=TARDE_DEL_14
        )
        recortada = run_analysis(
            config, universe, self._provider(serie(SESIONES[:-1])), horizonte="swing", now=MANANA_DEL_15
        )

        antes = next(o for o in completa.opportunities if o.asset.symbol == "SAP.DE")
        despues = next(o for o in recortada.opportunities if o.asset.symbol == "SAP.DE")
        assert despues.levels.price != pytest.approx(antes.levels.price)
        assert despues.data_freshness.last_bar_date == date(2026, 9, 11)

    def test_la_medicion_persistida_declara_la_barra_servida_por_cache(
        self, config, universe, db
    ) -> None:
        self._pasada(config, universe, db, self._provider(serie(SESIONES)), TARDE_DEL_14)
        self._pasada(config, universe, db, self._provider(serie(SESIONES[:-1])), MANANA_DEL_15)

        filas = [
            row
            for row in db.get_recent_freshness_measurements("SAP.DE")
            if row["measured_at"] == MANANA_DEL_15.isoformat()
        ]
        assert len(filas) == 1
        fila = filas[0]
        assert json.loads(fila["bars_served_from_cache"]) == ["2026-09-14"]
        assert fila["bar_cache_status"] == STATUS_SERVED
        assert json.loads(fila["bars_pinned_revisions"]) == []

    def test_las_barras_y_el_manifiesto_entran_con_el_mismo_run_id(
        self, config, universe, db
    ) -> None:
        """INV-18: nada persiste sin el `run_id` de un manifiesto que existe."""

        self._pasada(config, universe, db, self._provider(serie(SESIONES)), TARDE_DEL_14)

        barras = db.get_validated_bars("SAP.DE")
        assert barras
        run_ids = {row["run_id"] for row in barras}
        assert None not in run_ids
        for run_id in run_ids:
            assert db.get_analysis_run(run_id) is not None

    def test_el_informe_declara_lo_que_hizo_la_cache(self, config, universe, db) -> None:
        from advisor.data.fx import FxConverter
        from advisor.report.formatter import format_report

        self._pasada(config, universe, db, self._provider(serie(SESIONES)), TARDE_DEL_14)
        provider = self._provider(serie(SESIONES[:-1]))
        segunda = self._pasada(config, universe, db, provider, MANANA_DEL_15)

        informe = format_report(segunda, config, FxConverter(provider, config.base_currency))

        assert "Caché de barras validadas" in informe
        assert "2026-09-14" in informe
        assert "valor marginal de una segunda fuente" in informe

    def test_el_acumulado_del_historico_no_cuenta_dos_veces_la_misma_sesion(
        self, config, universe, db
    ) -> None:
        """D-40: el mismo par activo-sesión aparece en varias pasadas y cuenta una vez."""

        from advisor.freshness_history import summarize_freshness_history

        self._pasada(config, universe, db, self._provider(serie(SESIONES)), TARDE_DEL_14)
        # Dos mañanas seguidas con la misma barra retirada: dos filas, un par.
        self._pasada(config, universe, db, self._provider(serie(SESIONES[:-1])), MANANA_DEL_15)
        self._pasada(
            config,
            universe,
            db,
            self._provider(serie(SESIONES[:-1])),
            datetime(2026, 9, 15, 6, 32, tzinfo=timezone.utc),
        )

        resumen = summarize_freshness_history(db.get_all_freshness_measurements(), universe)

        assert resumen.bar_cache.served_pairs == 1
        assert resumen.bar_cache.served_symbols == 1
        assert resumen.bar_cache.passes_with_cache == 3


class TestHallazgosDeLaRevisionIndependiente:
    """Los cuatro defectos que la revisión independiente midió, y su guarda.

    Cada test lleva escrito el valor que daba **antes** de la corrección: sin
    eso, un test que pase no distingue una corrección que funciona de una
    comprobación que no comprueba nada.
    """

    def test_la_reinyeccion_conserva_el_indice_y_la_fortaleza_relativa(self, db) -> None:
        """Antes: el índice degradaba a `object` y `relative_strength` daba None.

        Las marcas se guardan en ISO con su desfase, así que al releerlas salen
        con zona de desfase fijo y no con `Europe/Berlin`. Concatenar las dos
        degradaba el índice, y con un índice `object` la fortaleza relativa no
        puede alinear sesiones: devolvía `None` —el factor desaparecía del
        reparto— justo en los activos que la caché rescata.
        """

        from advisor.indicators.technical import relative_strength

        completa = serie(SESIONES)
        tarde = cache(ProveedorDeSerie(completa), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        manana = cache(ProveedorDeSerie(serie(SESIONES[:-1])), db, MANANA_DEL_15)
        merged = manana.get_history("SAP.DE")

        assert isinstance(merged.index, pd.DatetimeIndex)
        assert str(merged.index.tz) == str(completa.index.tz)

        benchmark = serie(SESIONES, start=5000.0)["Close"]
        esperada = relative_strength(completa["Close"], benchmark, 20)
        assert esperada is not None
        assert relative_strength(merged["Close"], benchmark, 20) == pytest.approx(esperada)

    def test_una_barra_sin_volumen_conocido_no_entra_en_la_cache(self, db) -> None:
        """Antes: se guardaba con volumen NULL y al reinyectarla entraba un NaN.

        `build_snapshot` descarta los nulos antes de leer el último volumen, así
        que el análisis habría usado el volumen de la sesión anterior como si
        fuera el de esta barra, sin declararlo.
        """

        sin_volumen = serie(SESIONES)
        sin_volumen.iloc[-1, sin_volumen.columns.get_loc("Volume")] = float("nan")
        provider = cache(ProveedorDeSerie(sin_volumen), db, TARDE_DEL_14)
        provider.get_history("SAP.DE")
        guardar(db, provider)

        fechas = {row["session_date"] for row in db.get_validated_bars("SAP.DE")}
        assert "2026-09-14" not in fechas
        assert "2026-09-11" in fechas

    def test_una_serie_sin_columna_de_volumen_si_se_cachea(self, db) -> None:
        """La guarda es por volumen desconocido, no por ausencia de la columna."""

        sin_columna = serie(SESIONES).drop(columns=["Volume"])
        provider = cache(ProveedorDeSerie(sin_columna), db, TARDE_DEL_14)
        provider.get_history("SAP.DE")
        guardar(db, provider)

        guardadas = db.get_validated_bars("SAP.DE")
        assert {row["session_date"] for row in guardadas} >= {"2026-09-14"}
        assert all(row["volume"] is None for row in guardadas)

    def test_una_revision_solo_de_volumen_se_registra_y_no_manda(self, db) -> None:
        """Antes: estado FUENTE_VIVA, 0 revisiones, y el análisis usaba el volumen nuevo.

        El volumen alimenta el catalizador, así que una revisión que solo lo toca
        cambiaba un insumo del análisis sin que nadie la registrara.
        """

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        revisada = serie(SESIONES)
        revisada.iloc[-1, revisada.columns.get_loc("Volume")] = 2_000_000.0
        siguiente = cache(ProveedorDeSerie(revisada), db, MANANA_DEL_15)
        merged = siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        assert siguiente.report.usage["SAP.DE"].status == STATUS_PINNED
        assert float(merged["Volume"].iloc[-1]) == pytest.approx(1_000_000.0)
        revisiones = db.get_bar_revisions("SAP.DE")
        assert [row["kind"] for row in revisiones] == [KIND_REVISION]
        assert revisiones[0]["previous_volume"] == pytest.approx(1_000_000.0)
        assert revisiones[0]["new_volume"] == pytest.approx(2_000_000.0)
        assert revisiones[0]["applied"] == 0

    def test_una_diferencia_de_volumen_por_debajo_de_la_tolerancia_no_es_revision(self, db) -> None:
        """La tolerancia es relativa y vale igual para el volumen: 1e-6 es ruido."""

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        casi_igual = serie(SESIONES)
        casi_igual.iloc[-1, casi_igual.columns.get_loc("Volume")] = 999_999.0
        siguiente = cache(ProveedorDeSerie(casi_igual), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")

        assert siguiente.report.usage["SAP.DE"].status == STATUS_LIVE
        assert db.get_bar_revisions("SAP.DE") == []

    def test_un_split_con_una_revision_puntual_se_reancla_igual(self, db) -> None:
        """Antes: no se reanclaba y el análisis veía la base entera anterior.

        Medido sobre este mismo caso: el último cierre que llegaba al análisis
        era 168,5 mientras el proveedor ya servía 85,09. Un solo dato revisado no
        puede decidir sobre la escala de toda la serie.
        """

        tarde = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        split = serie(SESIONES, factor=0.5)
        posicion = split.columns.get_loc("Close")
        split.iloc[-1, posicion] = float(split["Close"].iloc[-1]) * 1.01
        siguiente = cache(ProveedorDeSerie(split), db, MANANA_DEL_15)
        merged = siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        uso = siguiente.report.usage["SAP.DE"]
        assert uso.status == STATUS_REANCHORED
        assert uso.readjustment_factor == pytest.approx(0.5, abs=1e-6)
        assert uso.pinned_revisions == ()
        assert float(merged["Close"].iloc[-1]) == pytest.approx(float(split["Close"].iloc[-1]))
        assert "2026-09-14" in uso.detail

        kinds = collections.Counter(row["kind"] for row in db.get_bar_revisions("SAP.DE"))
        assert kinds[KIND_REVISION] == 1
        assert kinds[KIND_READJUSTMENT] >= 2
        assert all(row["applied"] == 1 for row in db.get_bar_revisions("SAP.DE"))

    def test_el_reanclaje_por_el_camino_real_no_vacia_la_cache(self, config, universe, db) -> None:
        """La transacción real borra y luego inserta, en ese orden.

        Los tests de reajuste usaban un helper del propio fichero, así que
        invertir el orden dentro de `insert_analysis_result` habría sobrevivido a
        todos ellos. Esto pasa por el camino que usa producción.
        """

        from advisor.run.manifest import build_run_manifest

        db.insert_validated_bars(
            [
                {
                    "data_symbol": "SAP.DE",
                    "market": "XETRA",
                    "session_date": "2026-09-11",
                    "bar_timestamp": "2026-09-11T00:00:00+02:00",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1.0,
                    "observed_at": TARDE_DEL_14.isoformat(),
                    "provider": "yfinance",
                }
            ]
        )
        manifest = build_run_manifest(
            command="analizar",
            config=config,
            universe=universe,
            schema_version=db.schema_version(),
            timestamp=MANANA_DEL_15,
        )

        db.insert_analysis_result(
            manifest,
            [],
            [],
            validated_bars=[
                {
                    "data_symbol": "SAP.DE",
                    "market": "XETRA",
                    "session_date": "2026-09-14",
                    "bar_timestamp": "2026-09-14T00:00:00+02:00",
                    "open": 50.0,
                    "high": 50.5,
                    "low": 49.5,
                    "close": 50.0,
                    "volume": 2.0,
                    "observed_at": MANANA_DEL_15.isoformat(),
                    "provider": "yfinance",
                }
            ],
            bar_revisions=[],
            reanchored_symbols=["SAP.DE"],
        )

        guardadas = {row["session_date"]: row["close"] for row in db.get_validated_bars("SAP.DE")}
        assert guardadas == {"2026-09-14": 50.0}


class TestLaCacheNoAlargaLaVentanaPedida:
    """La caché repone lo retirado; no extiende la serie hacia atrás.

    Medido en una pasada real: el contexto pide `^VIX` con `period="5d"` y la
    caché le inyectaba 19 barras guardadas por la llamada del mismo símbolo con
    `2y`. Eran barras reales, pero nadie las había pedido, y la cifra de barras
    rescatadas que lee el propietario salía inflada: 74 barras en 19 símbolos
    cuando solo 12 habían sido retiradas de verdad.
    """

    def test_una_llamada_con_periodo_corto_no_recibe_barras_mas_viejas(self, db) -> None:
        larga = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        larga.get_history("^STOXX50E", period="2y")
        guardar(db, larga)

        cortas = SESIONES[-4:]
        corta = cache(ProveedorDeSerie(serie(cortas)), db, TARDE_DEL_14)
        merged = corta.get_history("^STOXX50E", period="5d")

        fechas = [pd.Timestamp(label).tz_convert("Europe/Berlin").date() for label in merged.index]
        assert fechas == cortas
        assert corta.report.usage["^STOXX50E"].served_from_cache == ()

    def test_pero_si_le_retiran_la_ultima_barra_la_recupera_igual(self, db) -> None:
        """La cola sí se repone: es justo el fallo que la tarea viene a arreglar."""

        larga = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        larga.get_history("^STOXX50E", period="2y")
        guardar(db, larga)

        corta_sin_cola = SESIONES[-4:-1]
        corta = cache(ProveedorDeSerie(serie(corta_sin_cola)), db, TARDE_DEL_14)
        merged = corta.get_history("^STOXX50E", period="5d")

        fechas = [pd.Timestamp(label).tz_convert("Europe/Berlin").date() for label in merged.index]
        assert fechas == SESIONES[-4:]
        assert corta.report.usage["^STOXX50E"].served_from_cache == (date(2026, 9, 14),)

    def test_un_hueco_interior_dentro_del_rango_vivo_si_se_repone(self, db) -> None:
        larga = cache(ProveedorDeSerie(serie(SESIONES)), db, TARDE_DEL_14)
        larga.get_history("SAP.DE")
        guardar(db, larga)

        con_hueco = serie(SESIONES).drop(index=pd.Timestamp(date(2026, 9, 10), tz="Europe/Berlin"))
        siguiente = cache(ProveedorDeSerie(con_hueco), db, MANANA_DEL_15)
        merged = siguiente.get_history("SAP.DE")

        fechas = [pd.Timestamp(label).tz_convert("Europe/Berlin").date() for label in merged.index]
        assert date(2026, 9, 10) in fechas
        assert siguiente.report.usage["SAP.DE"].served_from_cache == (date(2026, 9, 10),)


class TestSegundaRondaDeRevision:
    """Los tres agujeros que la segunda vuelta de revisión encontró.

    Los dos primeros los abrieron las correcciones de la primera vuelta, que es
    justo por lo que hay una segunda.
    """

    def test_un_empate_de_factores_no_se_declara_reajuste(self, db) -> None:
        """Antes: con 2 barras a 0,5 y 2 a 0,8 reanclaba a 0,5 por llegar antes.

        Elegir la escala de una serie por orden temporal es elegirla por sorteo.
        Un empate no es mayoría, así que la lectura conservadora manda: revisiones
        fijadas y ningún reanclaje.
        """

        cuatro = SESIONES[-4:]
        tarde = cache(ProveedorDeSerie(serie(cuatro)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        mezclada = serie(cuatro)
        for posicion, factor in enumerate((0.5, 0.5, 0.8, 0.8)):
            for columna in ("Open", "High", "Low", "Close"):
                indice = mezclada.columns.get_loc(columna)
                mezclada.iloc[posicion, indice] = float(mezclada.iloc[posicion, indice]) * factor
        siguiente = cache(ProveedorDeSerie(mezclada), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")
        guardar(db, siguiente)

        uso = siguiente.report.usage["SAP.DE"]
        assert uso.status == STATUS_PINNED
        assert uso.readjustment_factor is None
        assert siguiente.report.reanchored_symbols == []
        assert {row["kind"] for row in db.get_bar_revisions("SAP.DE")} == {KIND_REVISION}

    def test_un_reajuste_con_mayoria_estricta_si_se_adopta(self, db) -> None:
        """La guarda del empate no puede haberse llevado el caso normal."""

        cuatro = SESIONES[-4:]
        tarde = cache(ProveedorDeSerie(serie(cuatro)), db, TARDE_DEL_14)
        tarde.get_history("SAP.DE")
        guardar(db, tarde)

        casi_toda = serie(cuatro, factor=0.5)
        indice = casi_toda.columns.get_loc("Close")
        casi_toda.iloc[0, indice] = float(casi_toda.iloc[0, indice]) * 1.02
        siguiente = cache(ProveedorDeSerie(casi_toda), db, MANANA_DEL_15)
        siguiente.get_history("SAP.DE")

        uso = siguiente.report.usage["SAP.DE"]
        assert uso.status == STATUS_REANCHORED
        assert uso.readjustment_factor == pytest.approx(0.5, abs=1e-6)

    def test_una_peticion_corta_no_borra_el_contador_de_la_larga(self, db) -> None:
        """Antes: la intersección dejaba el contador de OD-02 bis en cero.

        El mismo símbolo se pide dos veces en una pasada con ventanas distintas.
        La larga ve una sesión exigible que nadie ha servido nunca; la corta
        empieza después de esa fecha, así que su propio conjunto sale vacío.
        Intersecar borraba la sesión, y con ella la cifra que decide si hay que
        pagar una segunda fuente.
        """

        hueco = date(2026, 9, 1)
        assert hueco in SESIONES
        larga = serie([value for value in SESIONES if value != hueco])
        corta = serie([value for value in SESIONES if value >= date(2026, 9, 7)])

        class ProveedorPorPeriodo:
            def get_history(self, symbol, period="1y", interval="1d"):
                return corta if period == "1mo" else larga

            def get_raw_history(self, symbol, period="1y", interval="1d", *, drop_na=True):
                return larga

        provider = cache(ProveedorPorPeriodo(), db, TARDE_DEL_14)
        provider.get_history("^STOXX50E", period="2y")
        assert provider.report.usage["^STOXX50E"].sessions_never_observed == (hueco,)

        provider.get_history("^STOXX50E", period="1mo")

        assert provider.report.usage["^STOXX50E"].sessions_never_observed == (hueco,)
        assert provider.report.never_observed_count == 1

    def test_una_sesion_entregada_por_otra_peticion_deja_de_contar(self, db) -> None:
        """La contraprueba: lo que alguna petición entrega no es valor marginal."""

        hueco = date(2026, 9, 1)
        corta = serie([value for value in SESIONES if value >= date(2026, 9, 7)])
        completa = serie(SESIONES)

        class ProveedorPorPeriodo:
            def get_history(self, symbol, period="1y", interval="1d"):
                return corta if period == "1mo" else completa

            def get_raw_history(self, symbol, period="1y", interval="1d", *, drop_na=True):
                return completa

        provider = cache(ProveedorPorPeriodo(), db, TARDE_DEL_14)
        provider.get_history("^STOXX50E", period="1mo")
        provider.get_history("^STOXX50E", period="2y")

        uso = provider.report.usage["^STOXX50E"]
        assert hueco not in uso.sessions_never_observed
        assert provider.report.never_observed_count == 0

    def test_una_marca_que_no_vuelve_a_fechar_en_su_sesion_no_se_reinyecta(self, db) -> None:
        """Releer una marca en otra zona puede moverla de sesión: no se reinyecta.

        Con el cambio de horario, una marca de medianoche con un desfase que no
        corresponde a esa fecha retrocede un día. Antes se reinyectaba y la barra
        cambiaba de sesión; ahora se valida y se declara.
        """

        db.insert_validated_bars(
            [
                {
                    "data_symbol": "SAP.DE",
                    "market": "XETRA",
                    "session_date": "2026-09-14",
                    # 20:00 UTC son las 22:00 de Berlín del día 13: esta marca no
                    # vuelve a fechar en la sesión con la que se guardó.
                    "bar_timestamp": "2026-09-13T20:00:00+00:00",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1.0,
                    "observed_at": TARDE_DEL_14.isoformat(),
                    "provider": "yfinance",
                }
            ]
        )

        provider = cache(ProveedorDeSerie(serie(SESIONES[:-1])), db, MANANA_DEL_15)
        merged = provider.get_history("SAP.DE")

        fechas = [pd.Timestamp(label).tz_convert("Europe/Berlin").date() for label in merged.index]
        assert date(2026, 9, 14) not in fechas
        assert provider.report.usage["SAP.DE"].served_from_cache == ()
        # La barra sigue guardada: lo que no se puede es reinyectarla a ciegas.
        assert {row["session_date"] for row in db.get_validated_bars("SAP.DE")} == {"2026-09-14"}
