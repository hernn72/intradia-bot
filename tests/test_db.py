"""Persistencia: recomendaciones, posiciones y revisiones."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from advisor.storage.db import AdvisorDB


@pytest.fixture
def db(tmp_path) -> AdvisorDB:
    return AdvisorDB(tmp_path / "test.db")


def _recommendation(symbol: str = "SAP.DE") -> dict:
    return {
        "created_at": "2026-08-27T09:30:00+00:00",
        "symbol": symbol,
        "name": "SAP",
        "isin": None,
        "trade_republic": "unknown",
        "currency": "EUR",
        "horizonte": "swing",
        "radar": "OPERAR",
        "accion": "COMPRAR",
        "score": 78.0,
        "evaluable_max": 80.0,
        "price": 240.0,
        "price_eur": 240.0,
        "entry_max": 243.0,
        "entry_max_eur": 243.0,
        "stop": 232.0,
        "stop_eur": 232.0,
        "target2": 252.0,
        "target2_eur": 252.0,
        "risk_pct": 3.3,
        "reward_pct": 5.0,
        "rr_ratio": 1.5,
        "reasons": "[]",
        "run_id": "test-run",
    }


class TestRecommendations:
    def test_guarda_y_recupera(self, db: AdvisorDB) -> None:
        assert db.insert_recommendations([_recommendation(), _recommendation("SIE.DE")]) == 2
        assert len(db.get_recent_recommendations()) == 2

    def test_lista_vacia_no_hace_nada(self, db: AdvisorDB) -> None:
        assert db.insert_recommendations([]) == 0

    def test_filtra_por_simbolo(self, db: AdvisorDB) -> None:
        db.insert_recommendations([_recommendation(), _recommendation("SIE.DE")])
        filas = db.get_recent_recommendations(symbol="sie.de")
        assert len(filas) == 1
        assert filas[0]["symbol"] == "SIE.DE"


class TestFreshnessMeasurements:
    def _row(self, symbol: str = "SAP.DE") -> dict:
        return {
            "measured_at": "2026-09-02T08:30:00+00:00",
            "symbol": symbol,
            "data_symbol": symbol,
            "market": "XETRA",
            "benchmark_symbol": "^STOXX",
            "last_bar_date": "2026-08-31",
            "natural_days": 0,
            "sessions_approx": 0,
            "may_be_partial_current_session": True,
            "absent_reference_sessions": ["2026-08-28"],
            "absent_recent_sessions": ["2026-08-28"],
            "reference_sessions_checked": 10,
            "veto_window_sessions": 20,
            "quality": "INCOMPLETO",
            "error": None,
            "run_id": "test-run",
        }

    def test_guarda_y_recupera_mediciones(self, db: AdvisorDB) -> None:
        assert db.insert_freshness_measurements([self._row(), self._row("SIE.DE")]) == 2
        rows = db.get_recent_freshness_measurements(symbol="sap.de")

        assert len(rows) == 1
        assert rows[0]["symbol"] == "SAP.DE"
        assert rows[0]["may_be_partial_current_session"] == 1
        assert rows[0]["absent_reference_sessions"] == '["2026-08-28"]'
        assert rows[0]["absent_recent_sessions"] == '["2026-08-28"]'
        assert rows[0]["quality"] == "INCOMPLETO"
        assert rows[0]["veto_window_sessions"] == 20

    def test_guarda_errores_de_descarga(self, db: AdvisorDB) -> None:
        row = self._row("ERR.DE")
        row.update(
            benchmark_symbol=None,
            last_bar_date=None,
            natural_days=None,
            sessions_approx=None,
            may_be_partial_current_session=False,
            absent_reference_sessions=[],
            reference_sessions_checked=0,
            error="sin datos",
        )

        db.insert_freshness_measurements([row])
        stored = db.get_recent_freshness_measurements()[0]

        assert stored["last_bar_date"] is None
        assert stored["error"] == "sin datos"


class TestEventPasses:
    def _event_row(self, event_id: str = "2026-09-10|banco_central|global|-|swing|evento") -> dict:
        return {
            "event_id": event_id,
            "event_date": "2026-09-10",
            "event_type": "banco_central",
            "event_scope": "global",
            "symbol": None,
            "horizonte": "swing",
            "pass_kind": "evento",
            "title": "Decisión de tipos del BCE",
        }

    def test_claimed_es_reintentable(self, db: AdvisorDB) -> None:
        row = self._event_row()

        assert db.claim_event_passes([row]) == [row["event_id"]]
        assert db.claim_event_passes([row]) == [row["event_id"]]
        assert db.get_event_pass(row["event_id"])["status"] == "CLAIMED"

    def test_marca_eventos_como_enviados(self, db: AdvisorDB) -> None:
        row = self._event_row()
        db.claim_event_passes([row])

        db.mark_event_passes_sent([row["event_id"]])

        assert db.get_event_pass(row["event_id"])["status"] == "SENT"
        assert db.claim_event_passes([row]) == []


class TestPositions:
    def _abrir(self, db: AdvisorDB, symbol: str = "SAP.DE") -> int:
        return db.open_position(
            symbol=symbol, name="SAP", entry_price=240.0, currency="EUR", quantity=4,
            thesis="Ruptura con volumen", horizonte="swing", invested_eur=960.0,
            target=252.0, stop=232.0,
        )

    def test_abrir_y_listar(self, db: AdvisorDB) -> None:
        position_id = self._abrir(db)
        abiertas = db.list_open_positions()
        assert len(abiertas) == 1
        assert abiertas[0]["id"] == position_id
        assert abiertas[0]["status"] == "OPEN"

    def test_normaliza_el_simbolo(self, db: AdvisorDB) -> None:
        self._abrir(db, "sap.de")
        assert db.get_open_position("SAP.DE") is not None

    def test_no_permite_dos_posiciones_abiertas_del_mismo_activo(self, db: AdvisorDB) -> None:
        self._abrir(db)
        with pytest.raises(ValueError, match="ya existe una posición abierta"):
            self._abrir(db)

    def test_rechaza_precio_o_cantidad_invalidos(self, db: AdvisorDB) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            db.open_position(symbol="X", name="X", entry_price=0, currency="EUR", quantity=1,
                             thesis="t", horizonte="swing")
        with pytest.raises(ValueError, match="quantity"):
            db.open_position(symbol="X", name="X", entry_price=1, currency="EUR", quantity=0,
                             thesis="t", horizonte="swing")

    def test_exige_tesis(self, db: AdvisorDB) -> None:
        with pytest.raises(ValueError, match="thesis"):
            db.open_position(symbol="X", name="X", entry_price=1, currency="EUR", quantity=1,
                             thesis="   ", horizonte="swing")

    def test_cerrar_libera_el_simbolo(self, db: AdvisorDB) -> None:
        self._abrir(db)
        db.close_position("SAP.DE", 252.0, "objetivo 2 alcanzado")
        assert db.list_open_positions() == []
        self._abrir(db)  # ahora se puede volver a abrir

    def test_cerrar_una_posicion_inexistente(self, db: AdvisorDB) -> None:
        with pytest.raises(ValueError, match="no hay ninguna posición abierta"):
            db.close_position("SAP.DE", 100.0, "motivo")

    def test_cerrar_con_precio_invalido(self, db: AdvisorDB) -> None:
        self._abrir(db)
        with pytest.raises(ValueError, match="exit_price"):
            db.close_position("SAP.DE", -1.0, "motivo")


class TestReviews:
    def test_guarda_revision(self, db: AdvisorDB) -> None:
        position_id = db.open_position(
            symbol="SAP.DE", name="SAP", entry_price=240.0, currency="EUR", quantity=4,
            thesis="t", horizonte="swing",
        )
        db.insert_review(
            position_id=position_id, price=248.0, pnl_pct=3.3, verdict="REFUERZA",
            score=81.0, note="la tesis se mantiene",
            created_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        )
        revisiones = db.get_reviews(position_id)
        assert len(revisiones) == 1
        assert revisiones[0]["verdict"] == "REFUERZA"

    def test_rechaza_veredicto_invalido(self, db: AdvisorDB) -> None:
        with pytest.raises(ValueError, match="verdict inválido"):
            db.insert_review(position_id=1, price=1.0, pnl_pct=0.0, verdict="QUIZÁS")

    def test_el_esquema_se_crea_una_sola_vez(self, tmp_path) -> None:
        path = tmp_path / "test.db"
        AdvisorDB(path).insert_recommendations([_recommendation()])
        # Reabrir no debe borrar ni duplicar nada.
        assert len(AdvisorDB(path).get_recent_recommendations()) == 1


class TestRunIdObligatorio:
    """Criterio de rechazo de T-002: ninguna fila nueva sin `run_id`."""

    @pytest.mark.parametrize("run_id", [None, ""])
    def test_recomendacion_sin_run_id_se_rechaza(self, db: AdvisorDB, run_id) -> None:
        row = _recommendation()
        row["run_id"] = run_id
        with pytest.raises(ValueError, match="run_id"):
            db.insert_recommendations([row])

    def test_recomendacion_sin_clave_run_id_se_rechaza(self, db: AdvisorDB) -> None:
        row = _recommendation()
        del row["run_id"]
        with pytest.raises(ValueError, match="run_id"):
            db.insert_recommendations([row])

    @pytest.mark.parametrize("run_id", [None, ""])
    def test_medicion_sin_run_id_se_rechaza(self, db: AdvisorDB, run_id) -> None:
        row = TestFreshnessMeasurements._row(TestFreshnessMeasurements(), "SAP.DE")
        row["run_id"] = run_id
        with pytest.raises(ValueError, match="run_id"):
            db.insert_freshness_measurements([row])

