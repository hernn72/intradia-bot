"""Épocas de entorno de una cohorte (``environment_epoch``, D-78 / OD-T25-11; ficha §13).

Una cohorte solo corre con el entorno de su época vigente. Si una dependencia o el entorno tienen que cambiar:

1. ``ENVIRONMENT_INVESTIGATION``: la cohorte no corre (sus pasadas son ``ENGINE_DOWNTIME``).
2. Prueba de equivalencia con el entorno nuevo, sin descargas para el replay: el código económico y los
   hashes de política no cambian y la reconstrucción reproduce **byte a byte** todo lo escrito.
3. Si todo coincide, una D-nn abre la época ``n + 1`` (tramo causal nuevo, etiquetado).
4. Si algo falla, ``ENGINE_UNRUNNABLE`` desde el último evento válido: órdenes canceladas, posiciones
   ``NO_EVALUABLE``, sin salidas ni P&L inventado, y una cohorte nueva con el entorno nuevo.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from paper.store import PaperStore, canonical, sha256_text


@dataclass(frozen=True)
class Environment:
    python_version: str
    packages: Tuple[str, ...]
    requirements_sha256: str

    @property
    def packages_sha256(self) -> str:
        return sha256_text("\n".join(self.packages))


def current_environment(requirements: Path = Path("requirements.txt")) -> Environment:
    packages = sorted(
        f"{dist.metadata['Name'].lower()}=={dist.version}" for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    )
    req = hashlib.sha256(requirements.read_bytes()).hexdigest() if requirements.exists() else ""
    return Environment(platform.python_version(), tuple(packages), req)


def latest_epoch(store: PaperStore, cohort_id: str) -> Optional[Any]:
    return store.one("SELECT * FROM paper_environment_epoch WHERE cohort_id = ? ORDER BY epoch_no DESC LIMIT 1", (cohort_id,))


def record_epoch(store: PaperStore, cohort_id: str, env: Environment, *, code_sha: str, now: datetime,
                 first_scheduled_pass: str, decision_ref: str = "", equivalence_commitment: str = "") -> int:
    last = latest_epoch(store, cohort_id)
    epoch_no = int(last["epoch_no"]) + 1 if last else 1
    if epoch_no > 1 and not decision_ref:
        raise ValueError("una época nueva exige una D-nn (D-78)")
    store.insert("paper_environment_epoch", {
        "cohort_id": cohort_id, "epoch_no": epoch_no, "epoch_code_sha": code_sha, "python_version": env.python_version,
        "installed_packages_sha256": env.packages_sha256, "packages_json": canonical(list(env.packages)),
        "requirements_sha256": env.requirements_sha256, "started_at": now.isoformat(),
        "first_scheduled_pass": first_scheduled_pass, "decision_ref": decision_ref,
        "equivalence_commitment": equivalence_commitment,
    }, ("cohort_id", "epoch_no"))
    return epoch_no


def environment_matches(store: PaperStore, cohort_id: str, env: Environment) -> bool:
    last = latest_epoch(store, cohort_id)
    return (last is not None and last["installed_packages_sha256"] == env.packages_sha256
            and last["python_version"] == env.python_version and last["requirements_sha256"] == env.requirements_sha256)


def cohort_state(store: PaperStore, cohort_id: str) -> str:
    row = store.one(
        "SELECT state FROM paper_cohort_event WHERE cohort_id = ? ORDER BY event_ts_utc DESC, created_at DESC LIMIT 1",
        (cohort_id,),
    )
    return str(row["state"]) if row else "ACTIVE"


def set_state(store: PaperStore, cohort_id: str, state: str, *, at: datetime, reason: str, decision_ref: str = "") -> None:
    store.check_reference("cohort_state", state)
    store.insert("paper_cohort_event", {
        "cohort_id": cohort_id, "state": state, "event_ts_utc": at.isoformat(), "reason": reason,
        "decision_ref": decision_ref, "created_at": at.isoformat(),
    }, ("cohort_id", "state", "event_ts_utc"))


@dataclass(frozen=True)
class EquivalenceResult:
    passed: bool
    checks: Dict[str, bool]
    commitment: str
    detail_sealed: Dict[str, Any]


def equivalence_check(store: PaperStore, universe: Any, cohort_id: str, *, contract_ok: bool,
                      interpretation_ok: bool, envs: Optional[Mapping[str, Any]] = None,
                      evaluator: Any = None) -> EquivalenceResult:
    """Prueba de equivalencia previa a reanudar con un entorno nuevo (D-78). Con el entorno actual y sin
    descargas: el replay regenera byte a byte ledger, eventos, instantáneas y desenlaces, y las evaluaciones de
    cada pasada (señales, niveles, contexto) se recalculan e igualan. El resultado visible es ``PASS``/``FAIL``
    y un compromiso con nonce (el detalle depende de los libros y queda sellado)."""

    from paper.audit import replay, replay_evaluations

    report = replay(store, universe, cohort_id)
    is_policy = store.one("SELECT kind FROM paper_cohort WHERE cohort_id = ?", (cohort_id,))["kind"] == "POLICY"  # type: ignore[index]
    evaluations_ok = True
    eval_detail: Dict[str, Any] = {}
    if is_policy:
        if envs is None:
            raise ValueError("la equivalencia de una cohorte de política exige recalcular sus evaluaciones (envs)")
        evals = replay_evaluations(store, universe, envs, cohort_id, evaluator=evaluator)
        evaluations_ok = evals.match
        eval_detail = evals.__dict__
    checks = {"codigo_y_hashes_de_politica": contract_ok, "replay_byte_a_byte": report.match,
              "evaluaciones_identicas": evaluations_ok, "interpretacion_del_proveedor": interpretation_ok}
    detail = {"replay": report.as_dict(), "evaluaciones": eval_detail}
    nonce = secrets.token_hex(32)
    commitment = sha256_text(nonce + canonical(detail))
    return EquivalenceResult(all(checks.values()), checks, commitment, {"nonce": nonce, **detail})


REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits")


def interpretation_check(store: PaperStore, provider: Any, universe: Any, now: datetime, *, sessions_back: int = 20,
                         provisional_markets: Tuple[str, ...] = ("XETRA", "PAR", "AMS", "MCE", "MIL")) -> Tuple[bool, Dict[str, int]]:
    """Invariantes de interpretación del proveedor con el entorno nuevo (D-78, criterio fijado antes).

    Vuelve a pedir el tramo reciente ya guardado de todo el universo y comprueba columnas, zona horaria y
    asignación de sesiones, y que las barras coincidan salvo diferencias **aisladas y explicadas**: el ratio de
    un split observado, la barra provisional de D-21 (dos últimas sesiones europeas) o una acción corporativa
    nueva que el motor registraría como ``late``. Cualquier otra diferencia es ``FAIL``.
    (Si el entorno anterior todavía funciona, la comparación se hace normalizando una misma respuesta cruda
    con los dos entornos, fuera de este proceso.)
    """

    from datetime import timedelta

    import pandas as pd

    from paper.ingest import _session_of, fetch
    from paper.inputs import _splits, ts

    counts = {"objetos": 0, "barras": 0, "explicadas": 0, "fallos": 0}
    for asset in universe.assets:
        stored = {r["session_date"]: r for r in store.rows(
            "SELECT session_date, close, observed_at FROM paper_bar_observation WHERE data_symbol = ? AND scale_doubtful = 0 "
            "ORDER BY session_date DESC, observed_at LIMIT ?", (asset.data_symbol, sessions_back * 2))}
        if not stored:
            continue
        first = min(stored)
        frame = fetch(provider, asset.data_symbol, datetime.fromisoformat(first).date(), now.date() + timedelta(days=1))
        counts["objetos"] += 1
        if any(column not in frame.columns for column in REQUIRED_COLUMNS) or getattr(frame.index, "tz", None) is None:
            counts["fallos"] += 1
            continue
        splits = {d.isoformat(): r for d, r, _o in _splits(store, asset.data_symbol, now)}
        recent = sorted(stored)[-2:]
        for stamp, bar in frame.iterrows():
            day = _session_of(pd.Timestamp(stamp), asset.market).isoformat()
            old = stored.get(day)
            if old is None:
                continue
            counts["barras"] += 1
            ratio = float(old["close"]) / float(bar["Close"]) if float(bar["Close"]) else float("inf")
            if abs(ratio - 1.0) <= 1e-9:
                continue
            explained = any(abs(ratio - r) <= 1e-4 * r for r in splits.values()) or (
                asset.market in provisional_markets and day in recent) or float(bar.get("Dividends", 0.0) or 0.0) > 0
            if explained:
                counts["explicadas"] += 1
            else:
                counts["fallos"] += 1
        _ = ts  # mantiene el import explícito de la misma regla temporal que inputs
    return counts["fallos"] == 0, counts


def resolve_investigation(store: PaperStore, cohort_id: str, env: Environment, *, passed: bool, decision_ref: str,
                          code_sha: str, now: datetime, first_scheduled_pass: str, commitment: str) -> str:
    """Cierra ``ENVIRONMENT_INVESTIGATION`` con una D-nn: época nueva si la equivalencia pasó (tramo causal
    nuevo) o ``ENGINE_UNRUNNABLE`` si falló (fallback obligatorio, D-78)."""

    if not decision_ref:
        raise ValueError("la transición de entorno exige una D-nn (D-78)")
    with store.transaction():
        if passed:
            record_epoch(store, cohort_id, env, code_sha=code_sha, now=now, first_scheduled_pass=first_scheduled_pass,
                         decision_ref=decision_ref, equivalence_commitment=commitment)
            set_state(store, cohort_id, "ACTIVE", at=now, reason="época de entorno nueva tras equivalencia", decision_ref=decision_ref)
            return "ACTIVE"
        set_state(store, cohort_id, "ENGINE_UNRUNNABLE", at=now, reason="equivalencia fallida (D-78)", decision_ref=decision_ref)
        return "ENGINE_UNRUNNABLE"
