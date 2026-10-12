"""Contrato de las cohortes de T-025 (ficha §0, §6, §13; D-75).

B2 y S2 tal como están en ``politicas-finales.json``, C0 como control y BH como benchmark, sobre el
contrato de sistema de P6 (100.000 EUR por libro, 0,5 % de riesgo, 10 % máximo, 0,10 % + 5 pb, rechazo sin
cash). Los hashes de política se **regeneran** desde ``advisor`` y la cohorte no se crea ni se procesa si no
coinciden byte a byte con los congelados (§6).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from paper import ENGINE_VERSION, LABEL, T025_PREREG_SHA
from paper.engine_v1 import KIND_BENCHMARK, KIND_POLICY, EngineSpec
from paper.store import canonical, sha256_text

POLICIES = ("B2", "S2", "C0")
BENCHMARK = "BH"
COHORT_POLICIES = (*POLICIES, BENCHMARK)
EMBARGOED = ("B2", "S2", "C0")  # D-75: C0 sellado como B2 y S2 mientras T-024 no se resuelva
CAPITAL_EUR = 100_000.0
SYSTEM_HASHES = Path("evidence/2026-10-03-T-022-p6/preflight/system-hashes.json")
P6_RUNS = {"B2": "B2_primaria_5pb", "S2": "S2_primaria_5pb", "C0": "C0_primaria_5pb", "BH": "benchmark_5pb"}

# Adaptaciones en vivo de §8 y reglas de T-025 que forman parte de la identidad del sistema (§13).
T025_ADAPTATIONS = (
    "senal_vinculante_ultima_pasada_antes_de_apertura",
    "reejecucion_de_pasada_fallida",
    "signal_not_evaluated_sin_relleno",
    "barra_entrada_ausente_5_sesiones_salto_p6",
    "plazos_solo_provider_data_missing",
    "dividendo_tardio_late",
    "split_adjust_solo_split_observado",
    "scale_mismatch_como_dato_ausente",
    "data_loss_suspended_sin_venta_sintetica_20_sesiones",
    "exit_corporate_action_terminal_verificable",
    "exit_cohort_closed_apertura_siguiente",
    "engine_unrunnable_sin_salidas",
    "environment_epoch_equivalencia_byte_a_byte",
)


class ContractError(RuntimeError):
    """El contrato congelado de una cohorte no se reproduce: no se procesa."""


@dataclass(frozen=True)
class CohortContract:
    policy_id: str
    kind: str
    policy_sha256: str
    advisor_config_hash: str
    p6_system_sha256: str
    capital_inicial_eur: float
    risk_pct: float
    max_position_pct: float
    fee_rate: float
    slippage_bps: float
    min_rr: float
    max_hold_bars: int
    asset_list_sha256: str
    universe_vintage_id: str
    universe_size: int
    start_date: str
    t025_code_sha: str
    engine_version: str = ENGINE_VERSION
    t025_prereg_sha: str = T025_PREREG_SHA
    base_currency: str = "EUR"
    seal_rule: str = "EMBARGO_T024_HASTA_RESULTADO_B2_Y_S2;P7_WINDOWS"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def t025_system_sha256(self) -> str:
        envelope = {
            "schema": "intradia.t025.system.v1",
            "p6_system_sha256": self.p6_system_sha256,
            "engine_version": self.engine_version,
            "adaptaciones": list(T025_ADAPTATIONS),
            "capital_inicial_eur": self.capital_inicial_eur,
            "seal_rule": self.seal_rule,
            "kind": self.kind,
        }
        return sha256_text(canonical(envelope))

    @property
    def cohort_id(self) -> str:
        return sha256_text(canonical({"contract": self.as_dict(), "t025_system_sha256": self.t025_system_sha256}))

    def engine_spec(self) -> EngineSpec:
        return EngineSpec(
            policy_id=self.policy_id, system_sha256=self.t025_system_sha256, kind=self.kind,
            capital=self.capital_inicial_eur, risk_pct=self.risk_pct, max_position_pct=self.max_position_pct,
            fee_rate=self.fee_rate, slippage_bps=self.slippage_bps, min_rr=self.min_rr,
            max_hold_bars=self.max_hold_bars, universe_size=self.universe_size,
        )


def frozen_policy_identities() -> Dict[str, Dict[str, str]]:
    """Regenera los hashes de B2, S2 y C0 desde ``advisor`` y los compara con los congelados de P6."""

    from advisor.research import p6

    config, _universe = p6._sources()
    regenerated = p6.policy_identities(config)
    for policy, (policy_sha, config_hash) in p6.POLICY_HASHES.items():
        got = regenerated[policy]
        if (got["policy_sha256"], got["advisor_config_hash"]) != (policy_sha, config_hash):
            raise ContractError(f"{policy}: hashes de política distintos de los congelados (§6): {got}")
    return regenerated


def p6_system_hashes(path: Path = SYSTEM_HASHES) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for policy, run in P6_RUNS.items():
        entry = data["hashes"][run]
        out[policy] = str(entry.get("system_sha256") or entry["benchmark_sha256"])
    return out


def build_contracts(start: date, t025_code_sha: str, *, identities: Optional[Mapping[str, Mapping[str, str]]] = None,
                    system_hashes: Optional[Mapping[str, str]] = None, asset_list_sha256: Optional[str] = None,
                    universe_vintage_id: Optional[str] = None, universe_size: Optional[int] = None) -> List[CohortContract]:
    """Las cuatro cohortes de la primera versión, con los parámetros económicos de P6 (D-74 §5, D-75)."""

    from advisor.research import p6

    ids = identities if identities is not None else frozen_policy_identities()
    systems = system_hashes if system_hashes is not None else p6_system_hashes()
    alsha = asset_list_sha256 or p6.ASSET_LIST_SHA256
    uvid = universe_vintage_id or p6.UNIVERSE_VINTAGE_ID
    size = universe_size if universe_size is not None else len(p6.asset_list())
    contracts = []
    for policy in COHORT_POLICIES:
        identity = ids.get(policy, {"policy_sha256": "", "advisor_config_hash": ""})
        contracts.append(
            CohortContract(
                policy_id=policy, kind=KIND_BENCHMARK if policy == BENCHMARK else KIND_POLICY,
                policy_sha256=identity["policy_sha256"], advisor_config_hash=identity["advisor_config_hash"],
                p6_system_sha256=systems[policy], capital_inicial_eur=CAPITAL_EUR, risk_pct=0.5, max_position_pct=10.0,
                fee_rate=0.001, slippage_bps=p6.SLIPPAGE_PRIMARY_BPS, min_rr=1.5, max_hold_bars=40,
                asset_list_sha256=alsha, universe_vintage_id=uvid, universe_size=size, start_date=start.isoformat(),
                t025_code_sha=t025_code_sha,
            )
        )
    return contracts


def cohort_row(contract: CohortContract, created_at: str) -> Dict[str, Any]:
    return {
        "cohort_id": contract.cohort_id,
        "book_kind": "PAPER",
        "kind": contract.kind,
        "policy_id": contract.policy_id,
        "policy_sha256": contract.policy_sha256,
        "advisor_config_hash": contract.advisor_config_hash,
        "p6_system_sha256": contract.p6_system_sha256,
        "t025_system_sha256": contract.t025_system_sha256,
        "engine_version": contract.engine_version,
        "t025_prereg_sha": contract.t025_prereg_sha,
        "t025_code_sha": contract.t025_code_sha,
        "capital_inicial_eur": contract.capital_inicial_eur,
        "base_currency": contract.base_currency,
        "asset_list_sha256": contract.asset_list_sha256,
        "universe_vintage_id": contract.universe_vintage_id,
        "start_date": contract.start_date,
        "seal_rule": contract.seal_rule,
        "label": LABEL,
        "contract_json": canonical(contract.as_dict()),
        "created_at": created_at,
    }


def contract_from_row(row: Mapping[str, Any]) -> CohortContract:
    contract = CohortContract(**json.loads(row["contract_json"]))
    if contract.cohort_id != row["cohort_id"]:
        raise ContractError(f"{row['cohort_id']}: el contrato guardado no reproduce su cohort_id")
    return contract
