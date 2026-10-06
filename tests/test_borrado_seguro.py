"""Guarda de borrado de deploy/t024 y red de seguridad de los tests (incidente 2026-10-06).

En los casos de denegación, el `shutil` del módulo se sustituye por un registrador: si la guarda fallara,
el test no podría borrar nada real.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.conftest import BorradoProhibidoEnTests, envolver_borrado, ruta_prohibida

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bs = _load("t024_borrado_seguro_test", "deploy/t024/borrado_seguro.py")


@pytest.fixture
def registrador(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    llamadas: list[Path] = []

    def rmtree(ruta: Any) -> None:
        llamadas.append(Path(ruta))

    # Con el atributo: la denegación tiene que venir de la validación de la ruta, no de esta comprobación.
    rmtree.avoids_symlink_attacks = True  # type: ignore[attr-defined]
    monkeypatch.setattr(bs, "shutil", SimpleNamespace(rmtree=rmtree))
    return llamadas


def _staging(base: Path, etiqueta: str = "x") -> Path:
    ruta = base / bs.nombre_staging(etiqueta)
    ruta.mkdir(parents=True)
    (ruta / "dato.csv").write_text("1\n", encoding="utf-8")
    return ruta


@pytest.mark.parametrize("ruta", [Path(), ".", "..", "", Path("."), Path("..")])
def test_rechaza_directorio_actual_y_padre(ruta: Any, tmp_path: Path, registrador: list[Path]) -> None:
    with pytest.raises(bs.BorradoDenegado):
        bs.borrar_staging(ruta, base=tmp_path)
    assert registrador == []


def test_rechaza_raiz_del_repo_home_tmp_y_raiz(tmp_path: Path, registrador: list[Path]) -> None:
    for ruta in (ROOT, Path.home(), Path("/tmp"), Path("/"), ROOT / "data", ROOT / "evidence", ROOT / ".git"):
        with pytest.raises(bs.BorradoDenegado):
            bs.borrar_staging(ruta, base=ruta.parent if ruta != Path("/") else ruta)
    assert registrador == []


def test_rechaza_padre_del_staging_y_staging_bajo_otra_base(tmp_path: Path, registrador: list[Path]) -> None:
    base = tmp_path / "base"
    staging = _staging(base)
    with pytest.raises(bs.BorradoDenegado):
        bs.borrar_staging(base, base=tmp_path)
    with pytest.raises(bs.BorradoDenegado):
        bs.borrar_staging(staging, base=tmp_path)
    anidado = _staging(staging, "anidado")
    with pytest.raises(bs.BorradoDenegado):
        bs.borrar_staging(anidado, base=base)
    assert registrador == []


def test_rechaza_prefijo_incorrecto_inexistente_enlace_y_fichero(tmp_path: Path, registrador: list[Path]) -> None:
    otro = tmp_path / "t024-staging-sin-punto"
    otro.mkdir()
    solo_prefijo = tmp_path / bs.PREFIJO_STAGING
    solo_prefijo.mkdir()
    enlace = tmp_path / bs.nombre_staging("enlace")
    enlace.symlink_to(_staging(tmp_path / "real"))
    fichero = tmp_path / bs.nombre_staging("fichero")
    fichero.write_text("x", encoding="utf-8")
    for ruta in (otro, solo_prefijo, tmp_path / bs.nombre_staging("no-existe"), enlace, fichero):
        with pytest.raises(bs.BorradoDenegado):
            bs.borrar_staging(ruta, base=tmp_path)
    assert registrador == []


def test_rechaza_staging_con_git_o_sqlite(tmp_path: Path, registrador: list[Path]) -> None:
    con_git = _staging(tmp_path, "git")
    (con_git / ".git").mkdir()
    con_db = _staging(tmp_path, "db")
    (con_db / "sub").mkdir()
    (con_db / "sub" / "intradia.db.bak-1").write_text("x", encoding="utf-8")
    for ruta in (con_git, con_db):
        with pytest.raises(bs.BorradoDenegado):
            bs.borrar_staging(ruta, base=tmp_path)
    assert registrador == []


def test_rechaza_staging_que_contiene_el_directorio_actual(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registrador: list[Path]) -> None:
    staging = _staging(tmp_path, "cwd")
    dentro = staging / "trabajo"
    dentro.mkdir()
    monkeypatch.chdir(dentro)
    with pytest.raises(bs.BorradoDenegado):
        bs.borrar_staging(staging, base=tmp_path)
    assert registrador == []


def test_staging_correcto_se_borra_y_solo_el(tmp_path: Path) -> None:
    vecino = tmp_path / "vecino.csv"
    vecino.write_text("conservar\n", encoding="utf-8")
    staging = _staging(tmp_path, "ok")
    bs.borrar_staging(staging, base=tmp_path)
    assert not staging.exists()
    assert vecino.read_text(encoding="utf-8") == "conservar\n"


def test_nombre_staging_no_admite_separadores() -> None:
    for etiqueta in ("", ".", "..", "a/b", f"a{os.sep}b"):
        with pytest.raises(bs.BorradoDenegado):
            bs.nombre_staging(etiqueta)


def test_deploy_t024_solo_borra_a_traves_de_la_guarda() -> None:
    for fichero in sorted((ROOT / "deploy" / "t024").glob("*.py")):
        if fichero.name == "borrado_seguro.py":
            continue
        texto = fichero.read_text(encoding="utf-8")
        patron = r"\brmtree\b|os\.remove|os\.rmdir|removedirs|\.unlink\(|os\.unlink|\.rmdir\(|shutil\.move|[\"']rm[\"']|rm -"
        assert re.search(patron, texto) is None, fichero.name
    for fichero in sorted((ROOT / "deploy" / "t024").glob("*.sh")):
        texto = fichero.read_text(encoding="utf-8")
        assert [linea.strip() for linea in texto.splitlines() if "rm -" in linea] == [
            '/*/t024-staging-*) rm -rf -- "${tmpdir:?}" ;;'
        ]


# ---------------------------------------------------------------------------
# Red de seguridad de conftest: se prueba con una función original falsa, nunca con rutas reales.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "objetivo",
    [
        ROOT,
        ROOT.parent,
        Path.home(),
        Path("/"),
        ROOT / "data",
        ROOT / "data" / "vintages" / "x" / "AAPL.csv",
        ROOT / "evidence",
        ROOT / "evidence" / "algo" / "README.md",
        ROOT / ".git",
        ROOT / ".git" / "index",
        ROOT / "intradia.db",
        ROOT / "intradia.db.bak-20260902",
        ROOT / "intradia.db-wal",
        Path(),
        ".",
    ],
)
def test_red_de_tests_niega_rutas_protegidas(objetivo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    llamadas: list[Any] = []
    guardada = envolver_borrado(lambda ruta, *a, **k: llamadas.append(ruta), "prueba")
    assert ruta_prohibida(objetivo) is not None
    with pytest.raises(BorradoProhibidoEnTests):
        guardada(objetivo)
    assert llamadas == []


def test_red_de_tests_permite_temporales(tmp_path: Path) -> None:
    llamadas: list[Any] = []
    guardada = envolver_borrado(lambda ruta, *a, **k: llamadas.append(ruta), "prueba")
    guardada(tmp_path / "x")
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        guardada("relativo", dir_fd=fd)
    finally:
        os.close(fd)
    assert llamadas == [tmp_path / "x", "relativo"]


def test_red_de_tests_esta_activa_en_la_sesion() -> None:
    import shutil
    import subprocess

    from tests.conftest import PopenGuardado

    for funcion in (shutil.rmtree, os.remove, os.unlink, os.rmdir, os.removedirs, os.rename, os.replace):
        assert funcion.__name__ == "guardada"
    assert subprocess.Popen is PopenGuardado



# ---------------------------------------------------------------------------
# Revisión Codex (borrado): la lógica de rutas protegidas actúa por sí misma, no solo el prefijo
# ---------------------------------------------------------------------------


def test_protegidas_actuan_aunque_el_nombre_sea_de_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registrador: list[Path]) -> None:
    staging = _staging(tmp_path, "repo-falso")
    monkeypatch.setattr(bs, "REPO", staging)
    with pytest.raises(bs.BorradoDenegado, match="protegida"):
        bs.borrar_staging(staging, base=tmp_path)
    monkeypatch.setattr(bs, "REPO", staging / "dentro" / "repo")
    with pytest.raises(bs.BorradoDenegado, match="protegida"):
        bs.borrar_staging(staging, base=tmp_path)
    monkeypatch.setattr(bs, "REPO", ROOT)
    monkeypatch.setattr(bs.Path, "home", classmethod(lambda cls: staging))
    with pytest.raises(bs.BorradoDenegado, match="protegida"):
        bs.borrar_staging(staging, base=tmp_path)
    assert registrador == []


def test_borrado_exige_rmtree_resistente_a_enlaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    staging = _staging(tmp_path, "sin-proteccion")
    monkeypatch.setattr(bs, "shutil", SimpleNamespace(rmtree=lambda ruta: None))
    with pytest.raises(bs.BorradoDenegado, match="enlaces"):
        bs.borrar_staging(staging, base=tmp_path)
    assert staging.exists()


def test_borrado_no_deja_lapidas(tmp_path: Path) -> None:
    staging = _staging(tmp_path, "lapida")
    bs.borrar_staging(staging, base=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_promover_sin_pisar_no_sobrescribe_ni_un_directorio_vacio(tmp_path: Path) -> None:
    staging = _staging(tmp_path, "promo")
    destino = tmp_path / "destino"
    destino.mkdir()
    with pytest.raises(FileExistsError):
        bs.promover_sin_pisar(staging, destino)
    assert list(destino.iterdir()) == [] and (staging / "dato.csv").exists()
    nuevo = tmp_path / "nuevo"
    bs.promover_sin_pisar(staging, nuevo)
    assert (nuevo / "dato.csv").read_text(encoding="utf-8") == "1\n"


def test_promover_sin_pisar_rechaza_enlaces(tmp_path: Path) -> None:
    staging = _staging(tmp_path, "enlaces")
    (staging / "enlace.csv").symlink_to(staging / "dato.csv")
    with pytest.raises(bs.BorradoDenegado):
        bs.promover_sin_pisar(staging, tmp_path / "destino")
    assert not (tmp_path / "destino").exists()


# ---------------------------------------------------------------------------
# Red de conftest: rutas protegidas INEXISTENTES (si la red fallara, no habría nada que borrar)
# ---------------------------------------------------------------------------

NO_EXISTE = "t024-no-existe-nunca-7f3a"


def test_red_cubre_path_unlink_rmdir_removedirs_rename_y_replace(tmp_path: Path) -> None:
    fichero_evidence = ROOT / "evidence" / f"{NO_EXISTE}.txt"
    dir_data = ROOT / "data" / NO_EXISTE
    assert not fichero_evidence.exists() and not dir_data.exists()
    with pytest.raises(BorradoProhibidoEnTests):
        fichero_evidence.unlink()
    with pytest.raises(BorradoProhibidoEnTests):
        dir_data.rmdir()
    with pytest.raises(BorradoProhibidoEnTests):
        os.removedirs(dir_data)
    origen = tmp_path / "x.txt"
    origen.write_text("x", encoding="utf-8")
    with pytest.raises(BorradoProhibidoEnTests):
        os.rename(origen, fichero_evidence)
    with pytest.raises(BorradoProhibidoEnTests):
        origen.replace(ROOT / ".git" / NO_EXISTE)
    with pytest.raises(BorradoProhibidoEnTests):
        os.replace(ROOT / "evidence" / NO_EXISTE, tmp_path / "y")
    assert origen.exists() and not fichero_evidence.exists()


@pytest.mark.parametrize(
    "orden,shell",
    [
        (["rm", "-rf", "objetivo"], False),
        (["/bin/rm", "objetivo"], False),
        (["rmdir", "objetivo"], False),
        (["git", "clean", "-fdx"], False),
        (["find", ".", "-name", "objetivo", "-delete"], False),
        (["bash", "-c", "rm -rf objetivo"], False),
        ("rm -rf objetivo", True),
        ("true && rm objetivo", True),
    ],
)
def test_red_cubre_borrados_por_subprocess(orden: Any, shell: bool, tmp_path: Path) -> None:
    import subprocess

    objetivo = tmp_path / "objetivo"
    objetivo.mkdir()
    with pytest.raises(BorradoProhibidoEnTests):
        subprocess.run(orden, shell=shell, cwd=tmp_path, check=False)
    assert objetivo.exists()


def test_red_no_bloquea_subprocess_normales(tmp_path: Path) -> None:
    import subprocess

    assert subprocess.run(["git", "--version"], capture_output=True, check=False).returncode == 0
    assert subprocess.run("echo hola", shell=True, capture_output=True, text=True, check=False).stdout == "hola\n"



def test_red_resuelve_dir_fd_hacia_rutas_protegidas(tmp_path: Path) -> None:
    fd = os.open(ROOT / "evidence", os.O_RDONLY)
    try:
        with pytest.raises(BorradoProhibidoEnTests):
            os.unlink(f"{NO_EXISTE}.txt", dir_fd=fd)
        with pytest.raises(BorradoProhibidoEnTests):
            os.rmdir(NO_EXISTE, dir_fd=fd)
        origen = tmp_path / "x.txt"
        origen.write_text("x", encoding="utf-8")
        with pytest.raises(BorradoProhibidoEnTests):
            os.replace(origen, f"{NO_EXISTE}.txt", dst_dir_fd=fd)
        with pytest.raises(BorradoProhibidoEnTests):
            os.rename(f"{NO_EXISTE}.txt", origen, src_dir_fd=fd)
        assert origen.exists()
    finally:
        os.close(fd)


def test_red_con_dir_fd_en_temporales_funciona(tmp_path: Path) -> None:
    (tmp_path / "borrable.txt").write_text("x", encoding="utf-8")
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        os.unlink("borrable.txt", dir_fd=fd)
    finally:
        os.close(fd)
    assert not (tmp_path / "borrable.txt").exists()


def test_promover_sin_pisar_es_todo_o_nada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    staging = _staging(tmp_path, "parcial")
    (staging / "otro.csv").write_text("2\n", encoding="utf-8")
    enlazados: list[Any] = []
    link_real = os.link

    def link_que_falla(origen: Any, destino: Any) -> None:
        if enlazados:
            raise OSError("fallo simulado a mitad de la promoción")
        enlazados.append(destino)
        link_real(origen, destino)

    monkeypatch.setattr(bs.os, "link", link_que_falla)
    with pytest.raises(OSError, match="a mitad"):
        bs.promover_sin_pisar(staging, tmp_path / "destino")
    assert not (tmp_path / "destino").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [staging.name]
    assert sorted(p.name for p in staging.iterdir()) == ["dato.csv", "otro.csv"]



@pytest.mark.parametrize(
    "orden",
    [
        ["/usr/bin/env", "rm", "-rf", "objetivo"],
        ["find", ".", "-name", "objetivo", "-exec", "rm", "-rf", "{}", ";"],
        ["xargs", "rm", "-rf"],
        ["git", "-C", ".", "clean", "-fdx"],
    ],
)
def test_red_ve_borrados_envueltos_en_otras_ordenes(orden: list[str], tmp_path: Path) -> None:
    import subprocess

    objetivo = tmp_path / "objetivo"
    objetivo.mkdir()
    with pytest.raises(BorradoProhibidoEnTests):
        subprocess.run(orden, cwd=tmp_path, check=False, input=b"")
    assert objetivo.exists()


def test_red_cubre_os_system_y_spawn(tmp_path: Path) -> None:
    objetivo = tmp_path / "objetivo"
    objetivo.mkdir()
    with pytest.raises(BorradoProhibidoEnTests):
        os.system(f"rm -rf {objetivo}")
    with pytest.raises(BorradoProhibidoEnTests):
        os.spawnvp(os.P_WAIT, "rm", ["rm", "-rf", str(objetivo)])
    if hasattr(os, "posix_spawnp"):
        with pytest.raises(BorradoProhibidoEnTests):
            os.posix_spawnp("rm", ["rm", "-rf", str(objetivo)], dict(os.environ))
    assert objetivo.exists()


def test_interprete_hijo_hereda_la_red(tmp_path: Path) -> None:
    import subprocess

    protegido = ROOT / "evidence" / NO_EXISTE
    codigo = f"import shutil; shutil.rmtree({str(protegido)!r})"
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=False, cwd=tmp_path)
    # Sin red, el hijo fallaría con FileNotFoundError (la ruta no existe); con red, con BorradoProhibidoEnTests.
    assert resultado.returncode != 0
    assert "BorradoProhibidoEnTests" in resultado.stderr, resultado.stderr
    permitido = tmp_path / "borrable"
    permitido.mkdir()
    ok = subprocess.run([sys.executable, "-c", f"import shutil; shutil.rmtree({str(permitido)!r})"], check=False)
    assert ok.returncode == 0 and not permitido.exists()



# ---------------------------------------------------------------------------
# Revisión del revisor (ronda sobre 8c5ba1f)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flags", [["-I"], ["-E"], ["-S"], ["-IS"], ["-u", "-E"]])
def test_interprete_hijo_con_flags_que_anulan_la_red_se_niega(flags: list[str], tmp_path: Path) -> None:
    import subprocess

    with pytest.raises(BorradoProhibidoEnTests):
        subprocess.run([sys.executable, *flags, "-c", "pass"], cwd=tmp_path, check=False)


def test_interprete_hijo_con_env_explicito_sigue_con_red(tmp_path: Path) -> None:
    import subprocess

    protegido = ROOT / "evidence" / NO_EXISTE
    codigo = f"import shutil; shutil.rmtree({str(protegido)!r})"
    entorno = {"PATH": os.environ.get("PATH", "")}
    resultado = subprocess.run([sys.executable, "-c", codigo], env=entorno, capture_output=True, text=True, check=False, cwd=tmp_path)
    assert resultado.returncode != 0 and "BorradoProhibidoEnTests" in resultado.stderr, resultado.stderr


@pytest.mark.parametrize(
    "orden",
    [
        ["mv", "data", "fuera"],
        "mv data fuera",
        ["git", "reset", "--hard"],
        ["git", "checkout", "--", "."],
        ["git", "restore", "evidence"],
        ["git", "stash", "-u"],
        ["git", "rm", "-r", "evidence"],
        ["rsync", "-a", "--delete", "a/", "data/"],
        "find . -name x -delete;",
    ],
)
def test_red_ve_mas_ordenes_destructivas(orden: Any) -> None:
    from tests.red_borrado import orden_de_borrado

    assert orden_de_borrado(orden, shell=isinstance(orden, str)) is not None


@pytest.mark.parametrize("orden", [["git", "checkout", "-q", "-b", "rama"], ["git", "status"], ["git", "commit", "-m", "x"], ["echo", "mvp"]])
def test_red_no_marca_ordenes_inocuas(orden: list[str]) -> None:
    from tests.red_borrado import orden_de_borrado

    assert orden_de_borrado(orden) is None


def test_red_protege_data_aunque_sea_un_enlace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    externo = tmp_path / "externo"
    (externo / "vintages").mkdir(parents=True)
    (repo / "data").symlink_to(externo)
    llamadas: list[Any] = []
    guardada = envolver_borrado(lambda ruta, *a, **k: llamadas.append(ruta), "prueba", repo=repo)
    with pytest.raises(BorradoProhibidoEnTests):
        guardada(repo / "data" / "vintages")
    assert llamadas == [] and (externo / "vintages").is_dir()
