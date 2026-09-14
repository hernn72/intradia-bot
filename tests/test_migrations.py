"""Migraciones SQLite y verificación de backups."""

from __future__ import annotations

import sqlite3

import pytest

from advisor.storage.db import AdvisorDB, verify_backup
from advisor.storage.migrations import MIGRATIONS as _REAL_MIGRATIONS

_SCHEMA_V1 = """
CREATE TABLE recommendation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    name            TEXT NOT NULL,
    isin            TEXT,
    trade_republic  TEXT NOT NULL,
    currency        TEXT NOT NULL,
    horizonte       TEXT NOT NULL,
    radar           TEXT NOT NULL,
    accion          TEXT NOT NULL,
    score           REAL NOT NULL,
    evaluable_max   REAL NOT NULL,
    price           REAL NOT NULL,
    price_eur       REAL,
    entry_max       REAL NOT NULL,
    entry_max_eur   REAL,
    stop            REAL NOT NULL,
    stop_eur        REAL,
    target2         REAL NOT NULL,
    target2_eur     REAL,
    risk_pct        REAL NOT NULL,
    reward_pct      REAL NOT NULL,
    rr_ratio        REAL NOT NULL,
    reasons         TEXT
);

CREATE TABLE data_freshness_measurement (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    measured_at                     TEXT NOT NULL,
    symbol                          TEXT NOT NULL,
    data_symbol                     TEXT NOT NULL,
    market                          TEXT NOT NULL,
    benchmark_symbol                TEXT,
    last_bar_date                   TEXT,
    natural_days                    INTEGER,
    sessions_approx                INTEGER,
    may_be_partial_current_session  INTEGER NOT NULL,
    absent_reference_sessions       TEXT NOT NULL,
    absent_recent_sessions          TEXT NOT NULL,
    reference_sessions_checked      INTEGER NOT NULL,
    veto_window_sessions            INTEGER NOT NULL,
    quality                         TEXT NOT NULL,
    error                           TEXT
);
"""


def _create_v1_db(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA_V1)
        for index in range(3):
            conn.execute(
                """
                INSERT INTO recommendation (
                    created_at, symbol, name, trade_republic, currency, horizonte,
                    radar, accion, score, evaluable_max, price, entry_max, stop,
                    target2, risk_pct, reward_pct, rr_ratio, reasons
                ) VALUES (?, ?, 'SAP', 'unknown', 'EUR', 'swing', 'OPERAR',
                    'COMPRAR', 78, 80, 240, 243, 232, 252, 3.3, 5.0, 1.5, '[]')
                """,
                (f"2026-08-27T09:3{index}:00+00:00", f"SAP{index}.DE"),
            )


def test_migrations_base_nueva_llega_a_ultima_version() -> None:
    db = AdvisorDB(":memory:")

    assert db.schema_version() == 2
    with db._connect() as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert {"analysis_run", "recommendation", "data_freshness_measurement"} <= tables


def test_migrations_base_v1_existente_se_marca_y_migra(tmp_path) -> None:
    path = tmp_path / "v1.db"
    _create_v1_db(path)

    db = AdvisorDB(path)

    assert db.schema_version() == 2
    with db._connect() as conn:
        assert conn.execute("SELECT count(*) FROM recommendation").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM recommendation WHERE run_id IS NULL").fetchone()[0] == 3


def test_backup_antes_de_migrar(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)

    AdvisorDB(path)
    backups = list(tmp_path.glob("intradia.db.bak-*-pre-v2"))

    assert len(backups) == 1
    assert verify_backup(path, backups[0])


def test_backup_corrupto_falla(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)
    AdvisorDB(path)
    backup = next(tmp_path.glob("intradia.db.bak-*-pre-v2"))
    backup.write_bytes(b"no es sqlite")

    assert verify_backup(path, backup) is False


def test_migracion_que_falla_a_mitad_no_deja_esquema_a_medias(tmp_path, monkeypatch) -> None:
    """Un corte entre dos ALTER TABLE no puede dejar `run_id` puesto y la versión antigua.

    Antes, `executescript` ejecutaba cada sentencia en autocommit: la primera
    ALTER quedaba, `user_version` seguía en 1 y toda apertura posterior
    reventaba con `duplicate column name: run_id`, creando un backup más cada vez.
    """

    import advisor.storage.db as db_module
    from advisor.storage import migrations

    path = tmp_path / "intradia.db"
    _create_v1_db(path)

    def migracion_rota(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE recommendation ADD COLUMN run_id TEXT")
        raise sqlite3.OperationalError("corte simulado entre sentencias")

    monkeypatch.setattr(db_module, "MIGRATIONS", [(2, "rota", migracion_rota)])
    monkeypatch.setattr(migrations, "MIGRATIONS", [(2, "rota", migracion_rota)])

    with pytest.raises(sqlite3.OperationalError):
        AdvisorDB(path)

    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        columns = [row[1] for row in conn.execute("PRAGMA table_info(recommendation)")]
        assert "run_id" not in columns
    assert len(list(tmp_path.glob("intradia.db.bak-*"))) == 1

    # Con la migración buena, la misma base abre y migra sin tropezar con restos.
    monkeypatch.setattr(db_module, "MIGRATIONS", _REAL_MIGRATIONS)
    monkeypatch.setattr(migrations, "MIGRATIONS", _REAL_MIGRATIONS)
    assert AdvisorDB(path).schema_version() == 2


def test_segunda_apertura_es_idempotente(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)

    AdvisorDB(path)
    AdvisorDB(path)

    assert len(list(tmp_path.glob("intradia.db.bak-*"))) == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT count(DISTINCT backup_path) FROM backup_log").fetchone()[0] == 1


def test_backup_conserva_los_conteos_registrados(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)
    AdvisorDB(path)
    backup = next(tmp_path.glob("intradia.db.bak-*-pre-v2"))

    with sqlite3.connect(path) as conn:
        logged = dict(conn.execute("SELECT table_name, row_count FROM backup_log").fetchall())
    with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as copy:
        assert copy.execute("PRAGMA user_version").fetchone()[0] == 1
        for table, count in logged.items():
            assert copy.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == count
    assert logged["recommendation"] == 3


def test_verify_backup_acepta_ruta_relativa_y_absoluta(tmp_path, monkeypatch) -> None:
    """`db_path: intradia.db` registra el backup relativo al cwd; el operador
    lo pasa como lo lee en `ls -la`, que es absoluto. Ambas formas valen."""

    monkeypatch.chdir(tmp_path)
    _create_v1_db("intradia.db")
    AdvisorDB("intradia.db")
    backup = next(tmp_path.glob("intradia.db.bak-*-pre-v2"))

    assert verify_backup("intradia.db", backup.name) is True
    assert verify_backup("intradia.db", backup.resolve()) is True
    assert verify_backup(tmp_path / "intradia.db", backup.name) is True


def test_verify_backup_no_escribe_en_la_base_viva(tmp_path) -> None:
    """Verificar no puede migrar producción ni fabricar una base vacía."""

    path = tmp_path / "intradia.db"
    _create_v1_db(path)
    migrated = tmp_path / "migrada.db"
    _create_v1_db(migrated)
    AdvisorDB(migrated)
    backup = next(tmp_path.glob("migrada.db.bak-*-pre-v2"))

    # Base v1 sin backup_log: la verificación falla, pero no la toca.
    assert verify_backup(path, backup) is False
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert list(tmp_path.glob("intradia.db.bak-*")) == []

    # Ruta inexistente: no se crea nada.
    missing = tmp_path / "no-existe.db"
    assert verify_backup(missing, backup) is False
    assert not missing.exists()


def test_backup_con_menos_filas_que_el_registro_falla(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)
    AdvisorDB(path)
    backup = next(tmp_path.glob("intradia.db.bak-*-pre-v2"))
    with sqlite3.connect(backup) as copy:
        copy.execute("DELETE FROM recommendation WHERE symbol = 'SAP0.DE'")

    assert verify_backup(path, backup) is False


def test_readonly_no_crea_ni_migra(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)

    db = AdvisorDB(path, readonly=True)
    with db._connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    with pytest.raises(FileNotFoundError):
        AdvisorDB(tmp_path / "no-existe.db", readonly=True)
    assert not (tmp_path / "no-existe.db").exists()
