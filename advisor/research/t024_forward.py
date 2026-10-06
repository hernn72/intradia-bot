"""Captura forward de T-024: petición exacta, cosecha apta, registro forward y salida de conteos.

T-024 §7 (D-72): en cada checkpoint mensual (primer día hábil del mes) se congela una cosecha con
`freeze_vintage` y una petición exacta `start`/`end`; quedan fuera las sesiones de los últimos 5 días
hábiles anteriores al checkpoint. Solo una cosecha completa entra en el registro forward, y la captura
de un checkpoint emite únicamente los conteos de §6.3. Nada de este módulo abre desenlaces: no importa
ninguna función de salida, ventana, retorno ni bootstrap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from advisor.research import t024_comun as comun
from advisor.research.t024_captura import ResultadoCaptura, _barras_ciegas, calidad_barras, capturar
from advisor.research.t024_comun import DEV_VINTAGE_ID, POLITICAS_DECISORIAS, POLITICAS_DESCRIPTIVAS
from advisor.research.vintage import (
    PROVIDER,
    VintageLoad,
    _verified_manifest,
    freeze_vintage,
    hash_symbol_list,
    load_vintage,
)

FORWARD_START = date(2021, 8, 30)
FORWARD_INTERVAL = "1d"
DIAS_HABILES_RETRASO = 5
PRIMER_CHECKPOINT = date(2026, 11, 3)
# Lista derivada del manifiesto de la cosecha consumida (`DEV_VINTAGE_ID`): sus 126 símbolos ordenados.
# Cubre activos, benchmarks y contexto; no se reconstruye desde el universo del día.
SIMBOLOS_FORWARD_SHA256 = "c7a896ab921a27dce3e6ea268187ff03ce77954dd67298ac2b62d7c4017b50b5"
N_SIMBOLOS_FORWARD = 126
# Universo congelado de P6 (T-024 §6.2), el mismo `UNIVERSE_VINTAGE_ID` de p4/p5.
UNIVERSE_VINTAGE_ID = "237b0056f0b2ce6cfa0bc1cc64a475585c938a178e61ad23863b37c3ac565d19"
ZONA_CHECKPOINT = "Atlantic/Canary"
POLITICAS = (*POLITICAS_DECISORIAS, *POLITICAS_DESCRIPTIVAS)

REGISTRO_SCHEMA = "t024-registro-forward"
REGISTRO_SCHEMA_VERSION = 1
CLAVES_REGISTRO = frozenset({"schema", "schema_version", "cosechas", "sha256", "entradas_sha256"})
# Lista cerrada: una entrada con cualquier otra clave (salidas, R, D1/D2, P&L…) no es un registro válido.
CLAVES_ENTRADA = frozenset(
    {
        "checkpoint",
        "data_vintage_id",
        "manifest_hash",
        "manifest_file_sha256",
        "requested_start",
        "requested_end",
        "end_exclusive",
        "interval",
        "auto_adjust",
        "actions",
        "symbols_sha256",
        "n_symbols",
        "festivos",
        "universe_vintage_id",
        "provider",
        "provider_version",
        "T024_PREREG_SHA",
        "T024_CODE_SHA",
    }
)
CLAVES_SALIDA = frozenset(
    {"checkpoint", "c_e", "data_vintage_id", "previa_data_vintage_id", "politicas", "barras_nuevas", "barras_revisadas"}
)
CLAVES_CONTEO_POLITICA = frozenset({"senales_operar", "ejecutables", "rechazos", "q_p", "w_p", "exclusiones"})
T024_FORWARD_IMPORTED_CALLABLES = (
    "advisor.research.t024_captura._barras_ciegas",
    "advisor.research.t024_captura.calidad_barras",
    "advisor.research.t024_captura.capturar",
    "advisor.research.t024_decision.cargar_registro_forward",
    "advisor.research.t024_decision.verificar_identidad",
    "advisor.research.vintage._verified_manifest",
    "advisor.research.vintage.freeze_vintage",
    "advisor.research.vintage.hash_symbol_list",
    "advisor.research.vintage.load_vintage",
)
_SHA_GIT = re.compile(r"[0-9a-f]{40}")


class T024ForwardError(RuntimeError):
    """La captura forward violaría el contrato de T-024 §7."""


# ---------------------------------------------------------------------------
# Petición exacta
# ---------------------------------------------------------------------------


def simbolos_forward(root_dir: str | Path = "data/vintages") -> tuple[str, ...]:
    """Símbolos de toda cosecha forward: los de la cosecha consumida, ordenados y con hash verificado."""

    _vintage_dir, manifest = _verified_manifest(DEV_VINTAGE_ID, root_dir)
    if manifest.get("failed"):
        raise T024ForwardError("la cosecha consumida declara símbolos fallidos: la lista no es derivable")
    symbols = tuple(sorted(str(asset["symbol"]) for asset in manifest["assets"]))
    if len(symbols) != N_SIMBOLOS_FORWARD or hash_symbol_list(symbols) != SIMBOLOS_FORWARD_SHA256:
        raise T024ForwardError(f"lista de símbolos forward distinta de la congelada ({hash_symbol_list(symbols)})")
    return symbols


def es_dia_habil(dia: date, festivos: Iterable[date]) -> bool:
    return dia.weekday() < 5 and dia not in set(festivos)


def primer_dia_habil(anio: int, mes: int, festivos: Iterable[date]) -> date:
    fijos = tuple(festivos)
    dia = date(anio, mes, 1)
    while not es_dia_habil(dia, fijos):
        dia += timedelta(days=1)
    return dia


def end_exclusivo(checkpoint: date, festivos: Iterable[date]) -> date:
    """`end` exclusivo del checkpoint: el quinto día hábil anterior a él.

    Las sesiones de ese día y posteriores quedan fuera (T-024 §7, retraso europeo). Día hábil = lunes a
    viernes menos los festivos declarados para ese checkpoint, que viajan en la petición y en el registro.
    """

    fijos = _festivos(festivos)
    if checkpoint != primer_dia_habil(checkpoint.year, checkpoint.month, fijos):
        raise T024ForwardError(f"{checkpoint} no es el primer día hábil de su mes con festivos {[d.isoformat() for d in fijos]}")
    dia = checkpoint
    vistos = 0
    while vistos < DIAS_HABILES_RETRASO:
        dia -= timedelta(days=1)
        if es_dia_habil(dia, fijos):
            vistos += 1
    return dia


def _festivos(festivos: Iterable[date]) -> tuple[date, ...]:
    fijos = tuple(festivos)
    if any(not isinstance(dia, date) or isinstance(dia, datetime) for dia in fijos):
        raise T024ForwardError("los festivos son fechas")
    return tuple(sorted(set(fijos)))


@dataclass(frozen=True)
class PeticionForward:
    checkpoint: date
    start: date
    end: date
    interval: str
    symbols: tuple[str, ...]
    symbols_sha256: str
    festivos: tuple[date, ...]

    def serializable(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint.isoformat(),
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "end_exclusive": True,
            "interval": self.interval,
            "auto_adjust": False,
            "actions": True,
            "symbols": list(self.symbols),
            "symbols_sha256": self.symbols_sha256,
            "n_symbols": len(self.symbols),
            "festivos": [dia.isoformat() for dia in self.festivos],
        }


def peticion_checkpoint(
    checkpoint: date, festivos: Iterable[date], *, simbolos_root: str | Path = "data/vintages"
) -> PeticionForward:
    """Petición exacta de un checkpoint. Solo calcula: no descarga nada."""

    if checkpoint < PRIMER_CHECKPOINT:
        raise T024ForwardError(f"checkpoint {checkpoint} anterior al primero previsto ({PRIMER_CHECKPOINT})")
    fijos = _festivos(festivos)
    end = end_exclusivo(checkpoint, fijos)
    symbols = simbolos_forward(simbolos_root)
    return PeticionForward(checkpoint, FORWARD_START, end, FORWARD_INTERVAL, symbols, hash_symbol_list(symbols), fijos)


# ---------------------------------------------------------------------------
# Congelación y aptitud de la cosecha
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CosechaForward:
    peticion: PeticionForward
    data_vintage_id: Optional[str]
    apta: bool
    motivos: tuple[str, ...]
    succeeded: tuple[str, ...]
    failed: Mapping[str, str]

    def serializable(self) -> dict[str, object]:
        return {
            "peticion": self.peticion.serializable(),
            "data_vintage_id": self.data_vintage_id,
            "apta": self.apta,
            "motivos": list(self.motivos),
            "succeeded": len(self.succeeded),
            "failed": dict(sorted(self.failed.items())),
        }


def hoy_checkpoint() -> date:
    return datetime.now(ZoneInfo(ZONA_CHECKPOINT)).date()


def congelar_checkpoint(
    peticion: PeticionForward,
    provider: Any,
    *,
    root_dir: str | Path = "data/vintages",
    universe_vintage: str,
    hoy: Optional[date] = None,
    downloaded_at: Optional[datetime] = None,
) -> CosechaForward:
    """Congela la cosecha del checkpoint y dice si es apta. Una cosecha no apta no se registra.

    Sin sustituir símbolos, sin otra fuente y sin rellenar barras: un símbolo fallido deja la cosecha no
    apta, aunque sus ficheros queden en disco como evidencia del intento.
    """

    dia = hoy if hoy is not None else hoy_checkpoint()
    if dia < peticion.checkpoint:
        raise T024ForwardError(f"hoy ({dia}) es anterior al checkpoint {peticion.checkpoint}: no se captura antes de tiempo")
    if universe_vintage != UNIVERSE_VINTAGE_ID:
        raise T024ForwardError(f"universo {universe_vintage} distinto del congelado de P6")
    try:
        result = freeze_vintage(
            peticion.symbols,
            provider,
            interval=peticion.interval,
            start=peticion.start.isoformat(),
            end=peticion.end.isoformat(),
            root_dir=root_dir,
            downloaded_at=downloaded_at,
            universe_vintage=universe_vintage,
        )
    except ValueError as exc:
        return CosechaForward(peticion, None, False, (f"congelación fallida: {exc}",), (), {})
    motivos = verificar_cosecha_forward(result.data_vintage_id, peticion, root_dir=root_dir)
    return CosechaForward(
        peticion, result.data_vintage_id, not motivos, motivos, tuple(result.succeeded), dict(result.failed)
    )


def verificar_cosecha_forward(
    data_vintage_id: str, peticion: PeticionForward, *, root_dir: str | Path = "data/vintages"
) -> tuple[str, ...]:
    """Motivos por los que la cosecha no es apta para el registro; vacío si lo es."""

    try:
        _vintage_dir, manifest = _verified_manifest(data_vintage_id, root_dir)
    except (OSError, ValueError) as exc:
        return (f"manifiesto no verificable: {exc}",)
    motivos: list[str] = []
    request = manifest.get("request")
    esperado = {
        "symbols": list(peticion.symbols),
        "symbols_sha256": peticion.symbols_sha256,
        "start": peticion.start.isoformat(),
        "end": peticion.end.isoformat(),
        "end_exclusive": True,
        "interval": peticion.interval,
        "auto_adjust": False,
        "actions": True,
        "provider": PROVIDER,
    }
    if manifest.get("schema_version") != 2 or not isinstance(request, dict):
        motivos.append("el manifiesto no es de petición exacta (schema_version 2)")
    else:
        for key, value in esperado.items():
            if request.get(key) != value:
                motivos.append(f"petición del manifiesto distinta en {key}")
    if peticion.symbols_sha256 != SIMBOLOS_FORWARD_SHA256 or len(peticion.symbols) != N_SIMBOLOS_FORWARD:
        motivos.append("la petición no usa la lista de símbolos congelada")
    if manifest.get("failed"):
        motivos.append(f"símbolos fallidos: {sorted(item['symbol'] for item in manifest['failed'])}")
    congelados = sorted(str(asset["symbol"]) for asset in manifest.get("assets", []))
    if congelados != sorted(peticion.symbols):
        motivos.append("los símbolos congelados no son exactamente los pedidos")
    if manifest.get("universe_vintage_id") != UNIVERSE_VINTAGE_ID:
        motivos.append("universe_vintage_id distinto del congelado de P6")
    if not motivos:
        try:
            load_vintage(data_vintage_id, root_dir=root_dir)
        except (OSError, ValueError, KeyError) as exc:
            motivos.append(f"cosecha no verificable: {exc}")
    return tuple(motivos)


# ---------------------------------------------------------------------------
# Registro forward
# ---------------------------------------------------------------------------


def entrada_registro(
    data_vintage_id: str,
    peticion: PeticionForward,
    *,
    t024_code_sha: str,
    root_dir: str | Path = "data/vintages",
) -> dict[str, object]:
    """Entrada canónica del registro para una cosecha apta. Solo identidad y petición: ningún desenlace."""

    motivos = verificar_cosecha_forward(data_vintage_id, peticion, root_dir=root_dir)
    if motivos:
        raise T024ForwardError(f"cosecha {data_vintage_id} no apta para el registro: {list(motivos)}")
    if not _SHA_GIT.fullmatch(t024_code_sha):
        raise T024ForwardError("T024_CODE_SHA con formato inválido")
    vintage_dir, manifest = _verified_manifest(data_vintage_id, root_dir)
    return {
        "checkpoint": peticion.checkpoint.isoformat(),
        "data_vintage_id": data_vintage_id,
        "manifest_hash": manifest["manifest_hash"],
        "manifest_file_sha256": hashlib.sha256((vintage_dir / "manifest.json").read_bytes()).hexdigest(),
        "requested_start": peticion.start.isoformat(),
        "requested_end": peticion.end.isoformat(),
        "end_exclusive": True,
        "interval": peticion.interval,
        "auto_adjust": False,
        "actions": True,
        "symbols_sha256": peticion.symbols_sha256,
        "n_symbols": len(peticion.symbols),
        "festivos": [dia.isoformat() for dia in peticion.festivos],
        "universe_vintage_id": manifest["universe_vintage_id"],
        "provider": PROVIDER,
        "provider_version": manifest["request"]["provider_version"],
        "T024_PREREG_SHA": comun.T024_PREREG_SHA,
        "T024_CODE_SHA": t024_code_sha,
    }


def _sha256_compatible(cosechas: Sequence[Mapping[str, object]]) -> str:
    """El hash que recalcula `t024_decision.cargar_registro_forward`: solo `data_vintage_id` y `checkpoint`."""

    encoded = json.dumps(
        {"cosechas": [{"data_vintage_id": item["data_vintage_id"], "checkpoint": item["checkpoint"]} for item in cosechas]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_entradas(cosechas: Sequence[Mapping[str, object]]) -> str:
    encoded = json.dumps(list(cosechas), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _registro(cosechas: Sequence[Mapping[str, object]]) -> dict[str, object]:
    items = [dict(item) for item in cosechas]
    return {
        "schema": REGISTRO_SCHEMA,
        "schema_version": REGISTRO_SCHEMA_VERSION,
        "cosechas": items,
        "sha256": _sha256_compatible(items),
        "entradas_sha256": _sha256_entradas(items),
    }


def registro_vacio() -> dict[str, object]:
    return _registro([])


def validar_registro(data: Mapping[str, object]) -> None:
    if set(data) != CLAVES_REGISTRO:
        raise T024ForwardError(f"claves del registro forward inválidas: {sorted(set(data) ^ CLAVES_REGISTRO)}")
    if data["schema"] != REGISTRO_SCHEMA or data["schema_version"] != REGISTRO_SCHEMA_VERSION:
        raise T024ForwardError("esquema del registro forward desconocido")
    cosechas = data["cosechas"]
    if not isinstance(cosechas, list):
        raise T024ForwardError("cosechas del registro forward no es una lista")
    previo: Optional[date] = None
    vistos: set[str] = set()
    for item in cosechas:
        _validar_entrada(item)
        checkpoint = date.fromisoformat(str(item["checkpoint"]))
        if previo is not None and checkpoint <= previo:
            raise T024ForwardError("registro forward no ordenado por checkpoint estrictamente creciente")
        if item["data_vintage_id"] in vistos:
            raise T024ForwardError("data_vintage_id repetido en el registro forward")
        previo = checkpoint
        vistos.add(str(item["data_vintage_id"]))
    if data["sha256"] != _sha256_compatible(cosechas) or data["entradas_sha256"] != _sha256_entradas(cosechas):
        raise T024ForwardError("hash del registro forward no cuadra")


def _validar_entrada(item: object) -> None:
    if not isinstance(item, dict) or set(item) != CLAVES_ENTRADA:
        claves = set(item) if isinstance(item, dict) else set()
        raise T024ForwardError(f"entrada del registro forward con claves inválidas: {sorted(claves ^ CLAVES_ENTRADA)}")
    if item["T024_PREREG_SHA"] != comun.T024_PREREG_SHA:
        raise T024ForwardError("entrada con un T024_PREREG_SHA distinto del congelado")
    if not _SHA_GIT.fullmatch(str(item["T024_CODE_SHA"])):
        raise T024ForwardError("entrada con T024_CODE_SHA inválido")
    if item["symbols_sha256"] != SIMBOLOS_FORWARD_SHA256 or item["universe_vintage_id"] != UNIVERSE_VINTAGE_ID:
        raise T024ForwardError("entrada con símbolos o universo distintos de los congelados")
    if item["requested_start"] != FORWARD_START.isoformat() or item["interval"] != FORWARD_INTERVAL:
        raise T024ForwardError("entrada con start o interval distintos de los congelados")
    if item["end_exclusive"] is not True or item["auto_adjust"] is not False or item["actions"] is not True:
        raise T024ForwardError("entrada con una petición distinta de auto_adjust=False, actions=True y end exclusivo")
    if item["manifest_hash"] != item["data_vintage_id"]:
        raise T024ForwardError("entrada con manifest_hash distinto de su data_vintage_id")
    if date.fromisoformat(str(item["checkpoint"])) < PRIMER_CHECKPOINT:
        raise T024ForwardError(f"checkpoint anterior al primero previsto ({PRIMER_CHECKPOINT})")
    if not isinstance(item["festivos"], list):
        raise T024ForwardError("festivos de la entrada no es una lista")
    festivos = tuple(date.fromisoformat(str(dia)) for dia in item["festivos"])
    if end_exclusivo(date.fromisoformat(str(item["checkpoint"])), festivos).isoformat() != item["requested_end"]:
        raise T024ForwardError("entrada cuyo end no sale de la regla de los 5 días hábiles")


def _cosechas(registro: Mapping[str, object]) -> list[Mapping[str, object]]:
    cosechas = registro["cosechas"]
    if not isinstance(cosechas, list):
        raise T024ForwardError("cosechas del registro forward no es una lista")
    return [item for item in cosechas if isinstance(item, dict)]


def anadir_entrada(registro: Mapping[str, object], entrada: Mapping[str, object]) -> dict[str, object]:
    """Registro nuevo con `entrada` al final. No modifica el recibido."""

    validar_registro(registro)
    nuevo = _registro([*_cosechas(registro), dict(entrada)])
    validar_registro(nuevo)
    return nuevo


def serializar_registro(registro: Mapping[str, object]) -> str:
    validar_registro(registro)
    return json.dumps(registro, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def leer_registro(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validar_registro(data)
    return data


def escribir_registro(path: Path, registro: Mapping[str, object]) -> None:
    texto = serializar_registro(registro)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, path)


def entrada_de(registro: Mapping[str, object], data_vintage_id: str) -> tuple[Mapping[str, object], Optional[str]]:
    """Entrada de la cosecha y el `data_vintage_id` de la inmediatamente anterior (None en la primera)."""

    validar_registro(registro)
    cosechas = _cosechas(registro)
    for posicion, item in enumerate(cosechas):
        if item["data_vintage_id"] == data_vintage_id:
            previa = str(cosechas[posicion - 1]["data_vintage_id"]) if posicion > 0 else None
            return item, previa
    raise T024ForwardError(f"cosecha {data_vintage_id} ausente del registro forward")


def peticion_de_entrada(entrada: Mapping[str, object], *, simbolos_root: str | Path = "data/vintages") -> PeticionForward:
    festivos_raw = entrada["festivos"]
    if not isinstance(festivos_raw, list):
        raise T024ForwardError("festivos de la entrada no es una lista")
    festivos = tuple(date.fromisoformat(str(dia)) for dia in festivos_raw)
    return peticion_checkpoint(date.fromisoformat(str(entrada["checkpoint"])), festivos, simbolos_root=simbolos_root)


# ---------------------------------------------------------------------------
# Captura del checkpoint: solo conteos (T-024 §6.3)
# ---------------------------------------------------------------------------


def calidad_cosechas(
    actual: VintageLoad, previa: Optional[VintageLoad], universe: Any, *, c_e: date
) -> tuple[Optional[int], Optional[int]]:
    """Barras nuevas y revisadas frente a la cosecha inmediatamente anterior; (None, None) sin previa.

    Revisada = barra ya vista en la previa cuyo OHLCV cambia, o que desaparece de la actual.
    """

    if previa is None:
        return None, None
    actuales = {}
    previas = {}
    for symbol in sorted(set(actual.by_symbol) | set(previa.by_symbol)):
        asset = universe.get(symbol)
        if asset is None:
            continue
        actuales[symbol] = _barras_ciegas(actual, symbol, asset.timezone, c_e) if symbol in actual.by_symbol else ()
        previas[symbol] = _barras_ciegas(previa, symbol, asset.timezone, c_e) if symbol in previa.by_symbol else ()
    nuevas, revisadas = calidad_barras(actuales, previas)
    desaparecidas = sum(
        len({row.session for row in previas[symbol]} - {row.session for row in actuales[symbol]}) for symbol in previas
    )
    return nuevas, revisadas + desaparecidas


def salida_captura(
    resultado: ResultadoCaptura,
    *,
    checkpoint: date,
    data_vintage_id: str,
    previa_data_vintage_id: Optional[str],
    barras_nuevas: Optional[int],
    barras_revisadas: Optional[int],
) -> dict[str, object]:
    """Salida canónica: conteos B2/S2/C0, Q_p, W_p, ejecutables, rechazos previos a la entrada, calidad y
    exclusiones. Nada más."""

    exclusiones: dict[str, dict[str, int]] = defaultdict(dict)
    for key, value in resultado.exclusiones.items():
        policy, _sep, motivo = key.partition(":")
        exclusiones[policy][motivo] = int(value)
    politicas: dict[str, dict[str, object]] = {}
    for policy in POLITICAS:
        conteo = resultado.conteos.get(policy)
        politicas[policy] = {
            "senales_operar": conteo.senales_operar if conteo else 0,
            "ejecutables": conteo.ejecutables if conteo else 0,
            "rechazos": dict(sorted(conteo.rechazos.items())) if conteo else {},
            "q_p": conteo.q_p if conteo else 0,
            "w_p": conteo.w_p if conteo else 0,
            "exclusiones": dict(sorted(exclusiones.get(policy, {}).items())),
        }
    return {
        "checkpoint": checkpoint.isoformat(),
        "c_e": checkpoint.isoformat(),
        "data_vintage_id": data_vintage_id,
        "previa_data_vintage_id": previa_data_vintage_id,
        "politicas": politicas,
        "barras_nuevas": barras_nuevas,
        "barras_revisadas": barras_revisadas,
    }


def capturar_checkpoint(
    config: Any,
    universe: Any,
    *,
    data_vintage_id: str,
    registro_path: Path,
    root_dir: str | Path = "data/vintages",
) -> dict[str, object]:
    """Conteos de un checkpoint registrado. `c_e` = checkpoint; la previa solo sirve para la calidad."""

    from advisor.research.t024_decision import cargar_registro_forward, verificar_identidad

    code_sha = verificar_identidad()
    registro = leer_registro(registro_path)
    cargar_registro_forward(registro_path, data_vintage_id)
    entrada, previa_id = entrada_de(registro, data_vintage_id)
    if entrada["T024_CODE_SHA"] != code_sha:
        raise T024ForwardError("la cosecha se registró con otro T024_CODE_SHA")
    peticion = peticion_de_entrada(entrada)
    if entrada_registro(data_vintage_id, peticion, t024_code_sha=code_sha, root_dir=root_dir) != dict(entrada):
        raise T024ForwardError("la entrada del registro no se reproduce desde la cosecha y la petición")
    checkpoint = peticion.checkpoint
    vintage = load_vintage(data_vintage_id, root_dir=root_dir)
    previa = load_vintage(previa_id, root_dir=root_dir) if previa_id is not None else None
    resultado = capturar(config, universe, vintage, c_e=checkpoint, desarrollo=False)
    nuevas, revisadas = calidad_cosechas(vintage, previa, universe, c_e=checkpoint)
    salida = salida_captura(
        resultado,
        checkpoint=checkpoint,
        data_vintage_id=data_vintage_id,
        previa_data_vintage_id=previa_id,
        barras_nuevas=nuevas,
        barras_revisadas=revisadas,
    )
    validar_salida(salida)
    return salida


def validar_salida(salida: Mapping[str, object]) -> None:
    if set(salida) != CLAVES_SALIDA:
        raise T024ForwardError("salida de captura con claves fuera del contrato")
    politicas = salida["politicas"]
    if not isinstance(politicas, dict) or set(politicas) != set(POLITICAS):
        raise T024ForwardError("salida de captura sin exactamente B2, S2 y C0")
    for bloque in politicas.values():
        if set(bloque) != CLAVES_CONTEO_POLITICA:
            raise T024ForwardError("conteo de política con claves fuera del contrato")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# CLI del runbook (docs/tareas/T-024: runbook del checkpoint)
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m advisor.research.t024_forward")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("peticion", "congelar"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--checkpoint", required=True, type=date.fromisoformat)
        cmd.add_argument("--festivo", action="append", default=[], type=date.fromisoformat)
    sub.choices["congelar"].add_argument("--data-dir", default="data/vintages")
    registrar = sub.add_parser("registrar")
    registrar.add_argument("--data-vintage-id", required=True)
    registrar.add_argument("--checkpoint", required=True, type=date.fromisoformat)
    registrar.add_argument("--festivo", action="append", default=[], type=date.fromisoformat)
    registrar.add_argument("--registro", required=True, type=Path)
    registrar.add_argument("--data-dir", default="data/vintages")
    captura = sub.add_parser("capturar")
    captura.add_argument("--data-vintage-id", required=True)
    captura.add_argument("--registro", required=True, type=Path)
    captura.add_argument("--data-dir", default="data/vintages")
    args = parser.parse_args(argv)

    if args.cmd == "peticion":
        sys.stdout.write(_json(peticion_checkpoint(args.checkpoint, args.festivo).serializable()))
        return 0
    if args.cmd == "congelar":
        from advisor.config import load_config
        from advisor.data.market_data import MarketDataProvider
        from advisor.universe.loader import load_universe
        from advisor.universe.vintage import universe_vintage_id

        peticion = peticion_checkpoint(args.checkpoint, args.festivo)
        config = load_config("config.yaml")
        universe = load_universe(config.universe_path)
        cosecha = congelar_checkpoint(
            peticion,
            MarketDataProvider(config.request_min_interval_seconds),
            root_dir=args.data_dir,
            universe_vintage=universe_vintage_id(universe),
        )
        sys.stdout.write(_json(cosecha.serializable()))
        return 0 if cosecha.apta else 2
    if args.cmd == "registrar":
        from advisor.research.t024_decision import verificar_identidad

        code_sha = verificar_identidad()
        peticion = peticion_checkpoint(args.checkpoint, args.festivo)
        entrada = entrada_registro(args.data_vintage_id, peticion, t024_code_sha=code_sha, root_dir=args.data_dir)
        registro = leer_registro(args.registro) if args.registro.exists() else registro_vacio()
        nuevo = anadir_entrada(registro, entrada)
        escribir_registro(args.registro, nuevo)
        sys.stdout.write(_json(entrada))
        return 0
    from advisor.config import load_config
    from advisor.universe.loader import load_universe

    config = load_config("config.yaml")
    universe = load_universe(config.universe_path)
    salida = capturar_checkpoint(
        config, universe, data_vintage_id=args.data_vintage_id, registro_path=args.registro, root_dir=args.data_dir
    )
    sys.stdout.write(_json(salida))
    return 0


if __name__ == "__main__":  # pragma: no cover - entrada del runbook
    raise SystemExit(main())
