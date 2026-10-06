"""Copia y verificación local de una cosecha forward T-024."""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SHA64 = re.compile(r"[0-9a-f]{64}")


def _cargar_hermano(nombre: str) -> Any:
    """Carga un módulo de deploy/t024 por ruta: funciona como script y desde los tests."""

    import importlib.util
    import sys

    ruta = Path(__file__).resolve().with_name(f"{nombre}.py")
    clave = f"_t024_deploy_{nombre}"
    if clave in sys.modules:
        return sys.modules[clave]
    spec = importlib.util.spec_from_file_location(clave, ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[clave] = modulo
    spec.loader.exec_module(modulo)
    return modulo


borrado_seguro = _cargar_hermano("borrado_seguro")
CODE_SHA_SIDECAR = Path("evidence/2026-10-05-T-024-code-lock/T024_CODE_SHA.txt")
Runner = Callable[[list[str]], None]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _calendario(path: Path, checkpoint: str) -> Mapping[str, Any]:
    data = _load_json(path)
    for item in data["checkpoints"]:
        if item["checkpoint"] == checkpoint:
            return item
    raise ValueError(f"checkpoint no declarado en calendario: {checkpoint}")


def _paths_for_sum(artefactos: Path, vintage_dir: Path, rel: str) -> Path:
    if rel.startswith("vintage/"):
        parts = rel.split("/")
        if len(parts) < 3:
            raise ValueError(f"ruta vintage inválida en SHA256SUMS: {rel}")
        return vintage_dir / "/".join(parts[2:])
    return artefactos / rel


def _rel_files(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def _vintage_rel_from_sum(rel: str) -> str | None:
    if not rel.startswith("vintage/"):
        return None
    parts = rel.split("/")
    if len(parts) < 3:
        raise ValueError(f"ruta vintage inválida en SHA256SUMS: {rel}")
    return "/".join(parts[2:])


def _verificar_sha256s(artefactos: Path, vintage_dir: Path) -> list[str]:
    errores: list[str] = []
    sums = artefactos / "SHA256SUMS"
    if not sums.is_file():
        return ["falta SHA256SUMS"]
    listados_vintage: set[str] = set()
    listados_artefactos: set[str] = set()
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if sep != "  " or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errores.append(f"línea SHA256SUMS inválida: {line}")
            continue
        rel_vintage = _vintage_rel_from_sum(rel)
        if rel_vintage is not None:
            listados_vintage.add(rel_vintage)
        else:
            listados_artefactos.add(rel)
        path = _paths_for_sum(artefactos, vintage_dir, rel)
        if not path.is_file():
            errores.append(f"falta fichero listado: {rel}")
        elif _sha256(path) != digest:
            errores.append(f"hash distinto: {rel}")
    existentes_artefactos = _rel_files(artefactos) if artefactos.is_dir() else set()
    esperados_artefactos = {"SHA256SUMS", *listados_artefactos}
    if existentes_artefactos != esperados_artefactos:
        faltan = sorted(esperados_artefactos - existentes_artefactos)
        sobran = sorted(existentes_artefactos - esperados_artefactos)
        if faltan:
            errores.append(f"ficheros de artefactos ausentes: {faltan}")
        if sobran:
            errores.append(f"ficheros de artefactos sin listar: {sobran}")
    existentes_vintage = _rel_files(vintage_dir) if vintage_dir.is_dir() else set()
    if listados_vintage != existentes_vintage:
        faltan = sorted(existentes_vintage - listados_vintage)
        sobran = sorted(listados_vintage - existentes_vintage)
        if faltan:
            errores.append(f"ficheros vintage sin listar: {faltan}")
        if sobran:
            errores.append(f"ficheros vintage listados ausentes: {sobran}")
    return errores


def verificar(
    *,
    checkpoint: str,
    artefactos: Path,
    vintage_dir: Path,
    calendario: Path | None = None,
    code_sha_esperado: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    repo = _repo_root()
    calendario = calendario or (repo / "deploy" / "t024" / "calendario-checkpoints.json")
    esperado = _calendario(calendario, checkpoint)
    estado = _load_json(artefactos / "estado.json")
    congelacion = _load_json(artefactos / "congelacion.json")
    peticion = _load_json(artefactos / "peticion.json")
    vintage_id = vintage_dir.name
    errores: list[str] = []
    if not SHA64.fullmatch(vintage_id):
        errores.append("vintage-dir no termina en un data_vintage_id de 64 hex")
    errores.extend(_verificar_sha256s(artefactos, vintage_dir))
    if code_sha_esperado is None:
        code_sha_esperado = (repo / CODE_SHA_SIDECAR).read_text(encoding="utf-8").strip()
    try:
        identidad = (artefactos / "identidad.txt").read_text(encoding="utf-8").strip()
        if identidad != code_sha_esperado:
            errores.append("identidad.txt distinto del T024_CODE_SHA esperado")
    except OSError as exc:
        errores.append(f"identidad.txt no verificable: {exc}")
    if isinstance(congelacion.get("peticion"), dict):
        peticion_congelacion = congelacion["peticion"]
        if peticion_congelacion.get("end") != peticion.get("end"):
            errores.append("congelacion.json peticion.end distinta de peticion.json")
        if peticion_congelacion.get("checkpoint") != peticion.get("checkpoint"):
            errores.append("congelacion.json peticion.checkpoint distinta de peticion.json")
    else:
        errores.append("congelacion.json no contiene peticion")
    try:
        from advisor.research import t024_comun
        from advisor.research.vintage import load_vintage

        loaded = load_vintage(vintage_id, root_dir=vintage_dir.parent)
        manifest = loaded.manifest
        request = manifest.get("request")
        if loaded.data_vintage_id != vintage_id:
            errores.append("load_vintage devolvió otro data_vintage_id")
        if manifest.get("schema_version") != 2:
            errores.append("schema_version distinto de 2")
        if len(manifest.get("assets", [])) != 126 or len(loaded.by_symbol) != 126:
            errores.append("la cosecha no tiene 126 activos")
        if manifest.get("failed") != []:
            errores.append("failed no está vacío")
        if not isinstance(request, dict):
            errores.append("request ausente o inválida")
        else:
            campos = ("start", "end", "interval", "auto_adjust", "actions", "symbols", "symbols_sha256")
            if {key: request.get(key) for key in campos} != {key: peticion.get(key) for key in campos}:
                errores.append("request del manifiesto distinta de peticion.json")
            if request.get("end") != esperado["requested_end"]:
                errores.append("end no coincide con requested_end del calendario")
            context = request.get("context")
            if not isinstance(context, dict):
                errores.append("request.context ausente")
            else:
                if context.get("checkpoint") != checkpoint or context.get("festivos") != esperado["festivos"]:
                    errores.append("contexto de checkpoint/festivos distinto del calendario")
                if context.get("T024_PREREG_SHA") != t024_comun.T024_PREREG_SHA:
                    errores.append("T024_PREREG_SHA distinto")
                if context.get("T024_CODE_SHA") != code_sha_esperado:
                    errores.append("T024_CODE_SHA distinto del sidecar")
    except Exception as exc:
        errores.append(f"load_vintage falló: {exc}")
    if estado.get("estado") != "APTA" or estado.get("apta") is not True:
        errores.append("estado.json no declara APTA")
    if congelacion.get("data_vintage_id") != vintage_id:
        errores.append("congelacion.json apunta a otro data_vintage_id")
    if congelacion.get("apta") is not True:
        errores.append("congelacion.json no declara apta true")
    informe = {
        "checkpoint": checkpoint,
        "data_vintage_id": vintage_id,
        "artefactos": str(artefactos),
        "vintage_dir": str(vintage_dir),
        "ok": not errores,
        "errores": errores,
    }
    return not errores, informe


def _rsync_args(ssh_key: str | None) -> list[str]:
    if ssh_key is None:
        return ["rsync", "-a"]
    return ["rsync", "-a", "-e", f"ssh -i {ssh_key}"]


def _run_subprocess(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _dirs_byte_iguales(left: Path, right: Path) -> bool:
    if _rel_files(left) != _rel_files(right):
        return False
    return all(filecmp.cmp(left / rel, right / rel, shallow=False) for rel in sorted(_rel_files(left)))


def copiar(args: argparse.Namespace, runner: Runner = _run_subprocess) -> int:
    """Trae artefactos y vintage de la Pi a staging, verifica y solo entonces promueve.

    Todo borrado pasa por `borrado_seguro.borrar_staging`. La promoción no pisa nada y es todo o nada
    (`promover_sin_pisar`). Si falla la de los artefactos después de promover el vintage en esta misma
    ejecución, ese vintage recién creado se renombra a un staging nuevo y se borra por la guarda. Nunca se
    borra un destino que existiera antes.
    """

    destino = args.destino_artefactos
    destino.parent.mkdir(parents=True, exist_ok=True)
    base_artefactos = destino.parent
    staging_artefactos = base_artefactos / borrado_seguro.nombre_staging(f"artefactos-{args.checkpoint}-{os.getpid()}")
    if staging_artefactos.exists():
        borrado_seguro.borrar_staging(staging_artefactos, base=base_artefactos)
    staging_artefactos.mkdir()
    base_vintage = args.data_dir.parent
    staging_parent: Path | None = None
    remote_cp = f"{args.pi}:{args.pi_artefactos}/checkpoints/{args.checkpoint}/"
    try:
        runner([*_rsync_args(args.ssh_key), remote_cp, str(staging_artefactos) + "/"])
        estado = _load_json(staging_artefactos / "estado.json")
        if estado.get("estado") != "APTA" or not SHA64.fullmatch(str(estado.get("data_vintage_id", ""))):
            raise SystemExit("estado remoto no es APTA")
        vintage_id = str(estado["data_vintage_id"])
        base_vintage.mkdir(parents=True, exist_ok=True)
        staging_parent = base_vintage / borrado_seguro.nombre_staging(f"{vintage_id}-{os.getpid()}")
        if staging_parent.exists():
            borrado_seguro.borrar_staging(staging_parent, base=base_vintage)
        staging = staging_parent / vintage_id
        staging.mkdir(parents=True)
        runner([*_rsync_args(args.ssh_key), f"{args.pi}:{args.pi_data_dir}/{vintage_id}/", str(staging) + "/"])
        ok, informe = verificar(checkpoint=args.checkpoint, artefactos=staging_artefactos, vintage_dir=staging)
        print(json.dumps(informe, sort_keys=True, indent=2, ensure_ascii=False))
        if not ok:
            return 1
        final = args.data_dir / vintage_id
        if final.exists() and not _dirs_byte_iguales(staging, final):
            raise SystemExit(f"ya existe {final}, pero no es byte a byte igual")
        if destino.exists() and not _dirs_byte_iguales(staging_artefactos, destino):
            raise SystemExit(f"ya existe {destino}, pero no es byte a byte igual")
        args.data_dir.mkdir(parents=True, exist_ok=True)
        creados: list[Path] = []

        def retirar_creados() -> None:
            # Solo lo creado en esta ejecución: vuelve a un staging nuevo y se borra por la guarda.
            for creado in reversed(creados):
                retirada = creado.parent / borrado_seguro.nombre_staging(f"retirada-{creado.name}-{os.getpid()}")
                os.rename(creado, retirada)
                borrado_seguro.borrar_staging(retirada, base=creado.parent)

        try:
            if not final.exists():
                borrado_seguro.promover_sin_pisar(staging, final)
                creados.append(final)
            if not destino.exists():
                borrado_seguro.promover_sin_pisar(staging_artefactos, destino)
                creados.append(destino)
        except Exception:
            retirar_creados()
            raise
        # Lo promovido se verifica otra vez donde queda: un cambio en staging entre la primera verificación y
        # la promoción no puede colarse.
        ok_final, informe_final = verificar(checkpoint=args.checkpoint, artefactos=destino, vintage_dir=final)
        if not ok_final:
            print(json.dumps(informe_final, sort_keys=True, indent=2, ensure_ascii=False))
            retirar_creados()
            return 1
        return 0
    finally:
        if staging_artefactos.exists():
            borrado_seguro.borrar_staging(staging_artefactos, base=base_artefactos)
        if staging_parent is not None and staging_parent.exists():
            borrado_seguro.borrar_staging(staging_parent, base=base_vintage)


def verificar_cmd(args: argparse.Namespace) -> int:
    ok, informe = verificar(
        checkpoint=args.checkpoint,
        artefactos=args.artefactos,
        vintage_dir=args.vintage_dir,
        calendario=args.calendario,
    )
    print(json.dumps(informe, sort_keys=True, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python deploy/t024/traer_cosecha.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("copiar")
    cp.add_argument("--pi", default="fer@192.168.1.113")
    cp.add_argument("--pi-artefactos", default="/home/fer/t024-forward")
    cp.add_argument("--pi-data-dir", default="/home/fer/intradia-bot/data/vintages")
    cp.add_argument("--ssh-key")
    cp.add_argument("--checkpoint", required=True)
    cp.add_argument("--destino-artefactos", required=True, type=Path)
    cp.add_argument("--data-dir", default=Path("data/vintages"), type=Path)
    vf = sub.add_parser("verificar")
    vf.add_argument("--checkpoint", required=True)
    vf.add_argument("--artefactos", required=True, type=Path)
    vf.add_argument("--vintage-dir", required=True, type=Path)
    vf.add_argument("--calendario", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "copiar":
        return copiar(args)
    return verificar_cmd(args)


if __name__ == "__main__":
    raise SystemExit(main())
