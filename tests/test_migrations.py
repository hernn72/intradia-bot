"""Migraciones SQLite y verificación de backups."""

from __future__ import annotations

import sqlite3

import pytest

from advisor.storage.db import (
    REGISTRO_DESCONOCIDO,
    REGISTRO_EN_LOG,
    AdvisorDB,
    check_backup,
    verify_backup,
)
from advisor.storage.migrations import BACKUP_LOG_STATEMENTS, LATEST_VERSION, table_exists
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

    assert db.schema_version() == LATEST_VERSION
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

    assert db.schema_version() == LATEST_VERSION
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
    assert AdvisorDB(path).schema_version() == LATEST_VERSION


def test_segunda_apertura_es_idempotente(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)

    AdvisorDB(path)
    AdvisorDB(path)

    esperados = LATEST_VERSION - 1  # una copia por migración pendiente: v2, v3, v4, v5
    assert len(list(tmp_path.glob("intradia.db.bak-*"))) == esperados
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
        assert conn.execute("SELECT count(DISTINCT backup_path) FROM backup_log").fetchone()[0] == esperados


def test_migracion_v4_anade_codigos_calidad_y_ventana(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)

    AdvisorDB(path)

    with sqlite3.connect(path) as conn:
        recommendation = {row[1] for row in conn.execute("PRAGMA table_info(recommendation)")}
        freshness = {row[1] for row in conn.execute("PRAGMA table_info(data_freshness_measurement)")}

    assert {
        "discard_code", "execution_code", "quality_freshness", "quality_recent",
        "quality_historical", "execution_ready", "quality_period", "quality_interval",
    } <= recommendation
    assert {
        "quality_freshness", "quality_recent", "quality_historical", "execution_ready",
        "quality_period", "quality_interval",
    } <= freshness


def test_backup_conserva_los_conteos_registrados(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v1_db(path)
    AdvisorDB(path)
    backup = next(tmp_path.glob("intradia.db.bak-*-pre-v2"))

    with sqlite3.connect(path) as conn:
        logged = dict(
            conn.execute("SELECT table_name, row_count FROM backup_log WHERE backup_path = ?", (str(backup),)).fetchall()
        )
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

    # Base v1 sin backup_log: no se puede consultar el registro, y eso se
    # declara como desconocido en vez de tomarse por un defecto de la copia.
    check = check_backup(path, backup)
    assert check.integrity_ok is True
    assert check.registration == REGISTRO_DESCONOCIDO
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert list(tmp_path.glob("intradia.db.bak-*")) == []

    # Ruta inexistente: no se crea nada.
    missing = tmp_path / "no-existe.db"
    assert check_backup(missing, backup).live_reason is not None
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


_ANALYSIS_RUN_V2 = """
CREATE TABLE analysis_run (
    run_id                  TEXT PRIMARY KEY,
    command                 TEXT NOT NULL,
    git_sha                 TEXT NOT NULL,
    git_dirty               INTEGER NOT NULL,
    config_hash             TEXT NOT NULL,
    universe_vintage_id     TEXT NOT NULL,
    data_vintage_id         TEXT,
    score_model_version     TEXT NOT NULL,
    context_model_version   TEXT,
    schema_version          INTEGER NOT NULL,
    analysis_timestamp      TEXT NOT NULL,
    environment             TEXT NOT NULL,
    python_version          TEXT NOT NULL,
    provider_versions       TEXT NOT NULL,
    clock_drift_seconds     REAL,
    clock_status            TEXT NOT NULL
);
"""


def _create_v4_db(path, *, con_backup_log: bool = True, pasadas: int = 2) -> None:
    """Base con la forma que tiene hoy la Pi: esquema v4 y manifiestos guardados."""

    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA_V1)
        conn.executescript(_ANALYSIS_RUN_V2)
        for index in range(pasadas):
            conn.execute(
                """
                INSERT INTO analysis_run (
                    run_id, command, git_sha, git_dirty, config_hash, universe_vintage_id,
                    data_vintage_id, score_model_version, context_model_version, schema_version,
                    analysis_timestamp, environment, python_version, provider_versions,
                    clock_drift_seconds, clock_status
                ) VALUES (?, 'analizar', 'ae39c6c', ?, ?, 'universo-103', NULL, 'v3', NULL, 4,
                    ?, 'pi', '3.11.2', '{"yfinance": "0.2.65"}', 0.001, 'CLOCK_OK')
                """,
                (f"run-{index}", index % 2, f"hash-viejo-{index}", f"2026-09-1{index}T09:00:00+00:00"),
            )
        if con_backup_log:
            for statement in BACKUP_LOG_STATEMENTS:
                conn.execute(statement)
        conn.execute("PRAGMA user_version = 4")


def test_manifiestos_antiguos_conservan_su_hash_y_su_version(tmp_path) -> None:
    """El hash viejo se calculó con las rutas dentro; recalcularlo sería inventarlo (D-33)."""

    path = tmp_path / "intradia.db"
    _create_v4_db(path)

    db = AdvisorDB(path)

    assert db.schema_version() == LATEST_VERSION
    with db._connect() as conn:
        filas = {row["run_id"]: row for row in conn.execute("SELECT * FROM analysis_run ORDER BY run_id")}
    assert set(filas) == {"run-0", "run-1"}
    assert filas["run-0"]["config_hash"] == "hash-viejo-0"
    assert filas["run-1"]["config_hash"] == "hash-viejo-1"
    assert filas["run-0"]["config_hash_version"] == 1
    assert filas["run-1"]["config_hash_version"] == 1
    # Lo que ya se sabía se conserva; lo que nadie midió entonces queda NULL.
    assert filas["run-0"]["git_dirty"] == 0
    assert filas["run-1"]["git_dirty"] == 1
    assert filas["run-0"]["release_tag"] is None
    assert filas["run-0"]["groups"] is None
    assert filas["run-0"]["git_dirty_reason"] is None
    assert filas["run-0"]["universe_vintage_id"] == "universo-103"


def test_git_dirty_desconocido_se_guarda_como_null(tmp_path) -> None:
    """La columna es nullable para esto: `0` significaría «lo comprobé y estaba limpio»."""

    from datetime import datetime, timezone

    from advisor.run.manifest import RunManifest

    path = tmp_path / "intradia.db"
    db = AdvisorDB(path)
    manifiesto = RunManifest(
        run_id="run-sin-git",
        command="analizar",
        git_sha="unknown",
        git_dirty=None,
        git_dirty_reason="git no está instalado",
        release_tag=None,
        config_hash="hash",
        config_hash_version=2,
        universe_vintage_id="universo-103",
        groups=None,
        data_vintage_id=None,
        score_model_version="v3",
        context_model_version=None,
        schema_version=db.schema_version(),
        analysis_timestamp=datetime(2026, 9, 18, tzinfo=timezone.utc).isoformat(),
        environment="pi",
        python_version="3.11.2",
        provider_versions={},
        clock_drift_seconds=None,
        clock_status="CLOCK_UNKNOWN",
    )

    db.insert_analysis_run(manifiesto)

    fila = db.get_analysis_run("run-sin-git")
    assert fila is not None
    assert fila["git_dirty"] is None
    assert fila["git_dirty_reason"] == "git no está instalado"
    assert fila["config_hash_version"] == 2


def test_backup_log_la_crea_la_migracion_y_es_idempotente(tmp_path) -> None:
    """Deja de crearse en cada apertura: ahora es esquema versionado (INV-17)."""

    path = tmp_path / "intradia.db"
    _create_v4_db(path, con_backup_log=False)

    db = AdvisorDB(path)

    with db._connect() as conn:
        assert table_exists(conn, "backup_log")
    # Segunda apertura: la migración ya está aplicada y no vuelve a intentarse.
    otra = AdvisorDB(path)
    assert otra.schema_version() == LATEST_VERSION
    with otra._connect() as conn:
        assert table_exists(conn, "backup_log")

    # Y una base que ya la tenía migra igual, sin chocar con la tabla existente.
    con_tabla = tmp_path / "con-tabla.db"
    _create_v4_db(con_tabla, con_backup_log=True)
    assert AdvisorDB(con_tabla).schema_version() == LATEST_VERSION


def test_la_migracion_v5_hace_backup_previo(tmp_path) -> None:
    path = tmp_path / "intradia.db"
    _create_v4_db(path)

    AdvisorDB(path)

    copias = list(tmp_path.glob("intradia.db.bak-*-pre-v5"))
    assert len(copias) == 1
    check = check_backup(path, copias[0])
    assert check.restorable is True
    assert check.registration == REGISTRO_EN_LOG
    assert check.schema_version == 4  # la copia es de ANTES de migrar
    assert check.counts["analysis_run"] == 2


def test_el_backup_previo_a_v5_queda_registrado_aunque_no_hubiera_backup_log(tmp_path) -> None:
    """Una base v4 sin `backup_log` migra igual, y su copia previa es trazable.

    Sin esto la copia se hacía pero no se anotaba, y en un rollback nadie podría
    demostrar de qué momento era.
    """

    path = tmp_path / "intradia.db"
    _create_v4_db(path, con_backup_log=False)

    AdvisorDB(path)

    copias = list(tmp_path.glob("intradia.db.bak-*-pre-v5"))
    assert len(copias) == 1
    check = check_backup(path, copias[0])
    assert check.registration == REGISTRO_EN_LOG
    assert check.restorable is True
