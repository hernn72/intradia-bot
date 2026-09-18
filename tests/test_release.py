"""Release por tag: qué código corre esta máquina y si su copia es restaurable."""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from advisor.config import load_config
from advisor.deploy.release import (
    DESCONOCIDO,
    EN_TAG,
    FUERA_DE_TAG,
    ORIGIN_COINCIDE,
    ORIGIN_DESCONOCIDO,
    evaluate_release,
    format_release_status,
)
from advisor.run import manifest as manifest_module
from advisor.run.git import git_dirty
from advisor.run.manifest import build_run_manifest
from advisor.storage.db import (
    REGISTRO_COPIA_MANUAL,
    REGISTRO_EN_LOG,
    AdvisorDB,
    check_backup,
)
from advisor.universe.loader import load_universe


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo_con_tag(tmp_path: Path, *, tag: str = "v0.1.0", con_origin: bool = True) -> Path:
    """Repositorio de trabajo con un tag y, si se pide, un `origin` que lo publica.

    El `origin` es un repositorio local: la prueba no toca la red, pero
    `ls-remote` es el de verdad, no un doble.
    """

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "codigo.py").write_text("uno\n", encoding="utf-8")
    _git(repo, "add", "codigo.py")
    _git(repo, "commit", "-q", "-m", "primer commit")
    _git(repo, "tag", tag)
    if con_origin:
        origin = tmp_path / "origin.git"
        _git(repo, "init", "-q", "--bare", str(origin))
        _git(repo, "remote", "add", "origin", str(origin))
        _git(repo, "push", "-q", "origin", "HEAD", "--tags")
    return repo


def test_verificar_release_en_tag_exacto(tmp_path) -> None:
    repo = _repo_con_tag(tmp_path)

    status = evaluate_release(repo)

    assert status.verdict == EN_TAG
    assert status.tag == "v0.1.0"
    assert status.head_sha == _git(repo, "rev-parse", "HEAD")
    assert status.local_tag_sha == status.head_sha
    assert status.origin_state == ORIGIN_COINCIDE
    assert status.exit_code == 0


def test_verificar_release_por_delante_del_tag(tmp_path) -> None:
    repo = _repo_con_tag(tmp_path)
    for numero in ("dos", "tres"):
        (repo / "codigo.py").write_text(f"{numero}\n", encoding="utf-8")
        _git(repo, "commit", "-q", "-am", f"commit {numero}")

    status = evaluate_release(repo)

    assert status.verdict == FUERA_DE_TAG
    assert status.tag is None
    assert status.nearest_tag == "v0.1.0"
    assert status.commits_ahead == 2
    assert status.exit_code == 1
    assert "2 commits por delante de v0.1.0" in format_release_status(status)


def test_verificar_release_con_arbol_sucio(tmp_path) -> None:
    """El SHA coincide con el tag y el código en ejecución no: HEAD no ve los cambios."""

    repo = _repo_con_tag(tmp_path)
    (repo / "codigo.py").write_text("modificado sin commitear\n", encoding="utf-8")

    status = evaluate_release(repo)

    assert status.head_sha == _git(repo, "rev-parse", "v0.1.0")
    assert status.dirty.value is True
    assert status.verdict == FUERA_DE_TAG
    assert status.exit_code == 1


def test_verificar_release_sin_red_declara_desconocido(tmp_path) -> None:
    """Sin poder preguntar a `origin` no se asume que coincide (INV-16)."""

    repo = _repo_con_tag(tmp_path, con_origin=False)

    status = evaluate_release(repo)

    assert status.tag == "v0.1.0"
    assert status.dirty.value is False
    assert status.origin_state == ORIGIN_DESCONOCIDO
    assert status.origin_tag_sha is None
    assert status.verdict == DESCONOCIDO
    assert status.exit_code == 1


def test_verificar_release_con_tag_que_origin_no_publica(tmp_path) -> None:
    """Un tag local que nadie ha empujado no prueba que la Pi corra lo acordado."""

    repo = _repo_con_tag(tmp_path)
    (repo / "codigo.py").write_text("dos\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "segundo commit")
    _git(repo, "tag", "v0.2.0")

    status = evaluate_release(repo)

    assert status.tag == "v0.2.0"
    assert status.origin_state == "AUSENTE"
    assert status.verdict == FUERA_DE_TAG
    assert any("no existe en origin" in reason for reason in status.reasons)


def test_verificar_release_ignora_un_tag_que_no_es_release(tmp_path) -> None:
    """`release-test` no es una versión publicada: la CI solo construye `vX.Y.Z`."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "codigo.py").write_text("uno\n", encoding="utf-8")
    _git(repo, "add", "codigo.py")
    _git(repo, "commit", "-q", "-m", "primer commit")
    _git(repo, "tag", "release-test")
    origin = tmp_path / "origin.git"
    _git(repo, "init", "-q", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "HEAD", "--tags")

    status = evaluate_release(repo)

    assert status.tag is None
    assert status.verdict != EN_TAG
    assert status.exit_code == 1


def test_verificar_release_elige_el_release_mayor_entre_varios_tags(tmp_path) -> None:
    """Con varios tags en el mismo commit no puede decidir `git describe` por su cuenta."""

    repo = _repo_con_tag(tmp_path, tag="v0.1.0")
    _git(repo, "tag", "antes-de-tocar")
    _git(repo, "tag", "v0.2.0")
    _git(repo, "push", "-q", "origin", "--tags")

    status = evaluate_release(repo)

    assert status.tag == "v0.2.0"
    assert status.verdict == EN_TAG


def test_verificar_release_sin_git_declara_desconocido(tmp_path) -> None:
    sin_repo = tmp_path / "carpeta"
    sin_repo.mkdir()

    status = evaluate_release(sin_repo)

    assert status.head_sha == "unknown"
    assert status.verdict == DESCONOCIDO
    assert git_dirty(sin_repo).value is None


def test_manifiesto_guarda_release_tag_o_null(tmp_path, monkeypatch) -> None:
    """El tag viaja en el manifiesto; si HEAD no está en uno, es NULL, no una cadena."""

    monkeypatch.setattr(manifest_module, "measure_clock_drift_seconds", lambda: None)
    config = load_config("config.yaml")
    universe = load_universe("universe.yaml")
    db = AdvisorDB(tmp_path / "pasada.db")

    monkeypatch.setattr(manifest_module, "exact_release_tag", lambda *a, **k: "v0.2.0")
    con_tag = build_run_manifest(
        command="analizar",
        config=config,
        universe=universe,
        schema_version=db.schema_version(),
        timestamp=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(manifest_module, "exact_release_tag", lambda *a, **k: None)
    sin_tag = build_run_manifest(
        command="analizar",
        config=config,
        universe=universe,
        schema_version=db.schema_version(),
        timestamp=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    assert con_tag.release_tag == "v0.2.0"
    assert sin_tag.release_tag is None

    db.insert_analysis_run(con_tag)
    db.insert_analysis_run(sin_tag)
    guardados = {
        row["run_id"]: row["release_tag"]
        for row in [db.get_analysis_run(con_tag.run_id), db.get_analysis_run(sin_tag.run_id)]
    }
    assert guardados[con_tag.run_id] == "v0.2.0"
    assert guardados[sin_tag.run_id] is None


def test_verificar_backup_acepta_una_copia_manual_integra(tmp_path) -> None:
    """Una copia hecha con `cp` no está en `backup_log` y es restaurable igual.

    El 2026-09-18 el comando la llamó «inválida» en pleno despliegue: solo
    validaba contra el registro, donde una copia manual nunca aparece.
    """

    viva = tmp_path / "intradia.db"
    db = AdvisorDB(viva)
    db.insert_recommendations([_recomendacion()])
    copia = tmp_path / "intradia.db.bak-manual"
    copia.write_bytes(viva.read_bytes())

    check = check_backup(viva, copia)

    assert check.restorable is True
    assert check.integrity_ok is True
    assert check.registration == REGISTRO_COPIA_MANUAL
    assert check.schema_version == db.schema_version()
    assert check.counts["recommendation"] == 1
    assert check.live_counts is not None and check.live_counts["recommendation"] == 1


def test_verificar_backup_rechaza_una_base_sin_las_tablas_del_asesor(tmp_path) -> None:
    """Un SQLite íntegro pero vacío pasa `integrity_check` y no restaura nada."""

    viva = tmp_path / "intradia.db"
    AdvisorDB(viva)
    vacia = tmp_path / "vacia.db"
    with sqlite3.connect(vacia) as conn:
        conn.execute("CREATE TABLE cualquiera (id INTEGER)")

    check = check_backup(viva, vacia)

    assert check.integrity_ok is True
    assert check.restorable is False
    assert any("no es una base del asesor" in reason for reason in check.reasons)


def test_verificar_backup_avisa_si_la_copia_cambio_desde_que_se_registro(tmp_path) -> None:
    """Más filas que el registro no impide restaurar, pero ya no es la copia registrada."""

    from tests.test_migrations import _create_v4_db

    path = tmp_path / "intradia.db"
    _create_v4_db(path)
    AdvisorDB(path)
    copia = next(tmp_path.glob("intradia.db.bak-*-pre-v5"))
    with sqlite3.connect(copia) as conn:
        conn.execute(
            """INSERT INTO recommendation (created_at, symbol, name, trade_republic, currency,
                 horizonte, radar, accion, score, evaluable_max, price, entry_max, stop, target2,
                 risk_pct, reward_pct, rr_ratio, reasons)
               VALUES ('2026-09-18T10:00:00+00:00', 'NUEVA.DE', 'x', 'unknown', 'EUR', 'swing',
                 'OPERAR', 'COMPRAR', 1, 1, 1, 1, 1, 1, 1, 1, 1, '[]')"""
        )

    check = check_backup(path, copia)

    assert check.restorable is True
    assert any("ha cambiado desde que se registró" in reason for reason in check.reasons)


def test_verificar_backup_rechaza_un_fichero_corrupto(tmp_path) -> None:
    viva = tmp_path / "intradia.db"
    AdvisorDB(viva)
    corrupto = tmp_path / "intradia.db.bak-corrupto"
    corrupto.write_bytes(b"esto no es una base SQLite")

    check = check_backup(viva, corrupto)

    assert check.restorable is False
    assert check.integrity_ok is False
    assert check.registration != REGISTRO_EN_LOG
    assert check.reasons


def test_verificar_backup_rechaza_una_copia_truncada(tmp_path) -> None:
    """Un fichero SQLite legible pero con páginas rotas no es restaurable."""

    viva = tmp_path / "intradia.db"
    db = AdvisorDB(viva)
    db.insert_recommendations([dict(_recomendacion(), symbol=f"SAP{i}.DE") for i in range(400)])
    copia = tmp_path / "intradia.db.bak-truncada"
    datos = bytearray(viva.read_bytes())
    # Se rompe una página de datos, no la cabecera: el fichero sigue abriéndose
    # como base SQLite y es `integrity_check` quien lo caza.
    for offset in range(4096, len(datos)):
        datos[offset] = 0xFF
    copia.write_bytes(bytes(datos))

    check = check_backup(viva, copia)

    assert check.restorable is False
    assert any("integrity_check" in reason or "SQLite" in reason for reason in check.reasons)


def _recomendacion() -> dict:
    return {
        "run_id": "run-de-prueba",
        "created_at": "2026-09-18T09:00:00+00:00",
        "symbol": "SAP.DE",
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
    }


def test_sqlite_de_la_copia_manual_se_abre(tmp_path) -> None:
    """Guarda de la propia prueba: la copia manual es una base abrible de verdad."""

    viva = tmp_path / "intradia.db"
    AdvisorDB(viva)
    copia = tmp_path / "copia.db"
    copia.write_bytes(viva.read_bytes())
    with sqlite3.connect(f"file:{copia}?mode=ro", uri=True) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
