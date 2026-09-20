"""Sondeo del plan gratuito de EODHD para OD-01 (D-39).

No integra nada. Pregunta una sola cosa y la contesta contra el JSON crudo, no
contra la documentación del proveedor: **si los fundamentales traen
`filing_date`**, es decir fecha de publicación por línea. Sin eso no hay
point-in-time y los fundamentales no pueden entrar en un backtest (GATE B0).

La secuencia está diseñada para que un campo ausente no se pueda confundir con
un plan restringido, que son dos conclusiones opuestas:

1. fundamentales de dos valores europeos con la clave del propietario;
2. fundamentales de un valor de EE. UU. con la misma clave — si también falla,
   el límite es del plan y no de la plaza;
3. EOD de un valor europeo con la misma clave — si funciona, la clave es válida
   y lo que falta es el producto, no el acceso;
4. fundamentales del valor de demostración con el token público `demo`, que sí
   los sirve: es la única forma de ver la forma real del JSON sin pagar;
5. fundamentales de un europeo con `demo`, para dejar dicho hasta dónde llega.

Uso:

    .venv/bin/python evidence/2026-09-20-OD-01-eodhd-free/sondeo_eodhd.py

`EODHD_API_KEY` se lee de `.env` o del entorno. Si falta, los pasos 1-3 se
declaran no ejecutados y el resto corre igual, porque `demo` es público. La
clave nunca se imprime ni se guarda: las URL se registran recortadas.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AQUI = Path(__file__).resolve().parent

EUROPEOS = ["SAP.XETRA", "ASML.AS"]
DEMO = "AAPL.US"

# Qué hace falta y para qué. El sondeo busca cada nombre por todo el árbol en vez
# de mirar donde "debería" estar, porque lo que importa es si el dato existe.
CAMPOS_EXIGIDOS: List[Tuple[str, str]] = [
    ("filing_date", "fecha de publicación por línea — sin esto no hay point-in-time"),
    ("ISIN", "identidad del instrumento, para cruzar con universe.yaml"),
    ("Balance_Sheet", "estados financieros: balance"),
    ("Income_Statement", "estados financieros: cuenta de resultados"),
    ("Cash_Flow", "estados financieros: flujo de caja"),
    ("EarningsShare", "EPS (instantánea, sin fecha de publicación)"),
    ("epsActual", "EPS publicado, con `reportDate` al lado"),
    ("netDebt", "deuda neta"),
    ("longTermDebt", "deuda a largo plazo"),
    ("shortTermDebt", "deuda a corto plazo"),
    ("freeCashFlow", "flujo de caja libre"),
    ("totalDebt", "deuda total en una sola línea (se espera ausente: se deriva)"),
]


def cargar_env() -> None:
    """Lee `.env` sin depender de python-dotenv, que puede no estar instalado."""
    env = Path.cwd() / ".env"
    if not env.is_file():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip())


def recortar(texto: str, clave: str) -> str:
    return texto.replace(clave, f"{clave[:4]}…{clave[-2:]}") if clave else texto


def pedir(url: str) -> Tuple[Optional[Any], str]:
    """Devuelve (json, diagnóstico). El diagnóstico separa el plan del proveedor."""
    peticion = urllib.request.Request(url, headers={"User-Agent": "intradia-bot/sondeo-OD-01"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return json.loads(respuesta.read().decode("utf-8")), "OK"
    except urllib.error.HTTPError as error:
        cuerpo = error.read().decode("utf-8", errors="replace").strip()[:200]
        etiqueta = {
            401: "clave rechazada",
            402: "LO RESTRINGE EL PLAN, no es que el proveedor no lo dé",
            403: "prohibido: el plan no incluye este producto, o el token no cubre ese símbolo",
            429: "cuota diaria agotada",
        }.get(error.code, "error del servidor")
        return None, f"HTTP {error.code} — {etiqueta}: {cuerpo}"
    except urllib.error.URLError as error:
        return None, f"sin respuesta: {error.reason}"


def rutas_de(nodo: Any, buscada: str, ruta: str = "", acc: Optional[List[str]] = None) -> List[str]:
    """Todas las rutas donde aparece `buscada`. En listas mira solo el primer elemento:
    las series de EODHD son homogéneas y recorrerlas enteras no añade información."""
    acc = [] if acc is None else acc
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            hijo = f"{ruta}.{clave}" if ruta else str(clave)
            if clave.lower() == buscada.lower():
                acc.append(hijo)
            rutas_de(valor, buscada, hijo, acc)
    elif isinstance(nodo, list) and nodo:
        rutas_de(nodo[0], buscada, f"{ruta}[0]", acc)
    return acc


def inventario(datos: Any) -> List[str]:
    lineas: List[str] = []
    for campo, para_que in CAMPOS_EXIGIDOS:
        rutas = rutas_de(datos, campo)
        if rutas:
            resto = f" (+{len(rutas) - 2} más)" if len(rutas) > 2 else ""
            lineas.append(f"- **{campo}**: PRESENTE, {len(rutas)} apariciones — `{rutas[0]}`{resto} · {para_que}")
        else:
            lineas.append(f"- **{campo}**: AUSENTE · {para_que}")
    return lineas


def extracto(datos: Dict[str, Any], periodos: int = 2) -> Dict[str, Any]:
    """Recorte publicable: el JSON completo pasa del megabyte y se regenera con el script."""
    salida: Dict[str, Any] = {
        "_nota": "Extracto generado por sondeo_eodhd.py. El JSON completo se descarga con el script.",
        "General": datos.get("General", {}),
        "Highlights": datos.get("Highlights", {}),
        "Financials": {},
        "Earnings": {"History": {}},
    }
    for estado, contenido in datos.get("Financials", {}).items():
        salida["Financials"][estado] = {}
        for periodicidad, series in contenido.items():
            if isinstance(series, dict):
                salida["Financials"][estado][periodicidad] = dict(list(series.items())[:periodos])
            else:
                salida["Financials"][estado][periodicidad] = series
    historia = datos.get("Earnings", {}).get("History", {})
    if isinstance(historia, dict):
        salida["Earnings"]["History"] = dict(list(historia.items())[:4])
    return salida


def main() -> int:
    cargar_env()
    clave = os.environ.get("EODHD_API_KEY", "").strip()

    salida: List[str] = [
        "# Sondeo del plan gratuito de EODHD — OD-01 / D-39",
        "",
        "Salida literal de `sondeo_eodhd.py`. Se comprueba contra el JSON crudo.",
        "",
        "## Qué responde cada petición",
        "",
    ]

    pruebas: List[Tuple[str, str, str]] = []
    if clave:
        for simbolo in EUROPEOS:
            pruebas.append(
                (
                    f"fundamentales de {simbolo} con la clave del propietario",
                    f"https://eodhd.com/api/fundamentals/{simbolo}?api_token={clave}&fmt=json",
                    "",
                )
            )
        pruebas.append(
            (
                f"fundamentales de {DEMO} con la clave del propietario (¿es la plaza o el plan?)",
                f"https://eodhd.com/api/fundamentals/{DEMO}?api_token={clave}&fmt=json",
                "",
            )
        )
        pruebas.append(
            (
                f"EOD de {EUROPEOS[0]} con la clave del propietario (¿la clave vale?)",
                f"https://eodhd.com/api/eod/{EUROPEOS[0]}?api_token={clave}&fmt=json&from=2026-09-14",
                "",
            )
        )
    else:
        salida.append("- **Pasos con la clave del propietario: NO EJECUTADOS**, falta `EODHD_API_KEY`.")
        salida.append("")

    pruebas.append(
        (
            f"fundamentales de {DEMO} con el token público `demo`",
            f"https://eodhd.com/api/fundamentals/{DEMO}?api_token=demo&fmt=json",
            "inventario",
        )
    )
    pruebas.append(
        (
            f"fundamentales de {EUROPEOS[0]} con el token público `demo`",
            f"https://eodhd.com/api/fundamentals/{EUROPEOS[0]}?api_token=demo&fmt=json",
            "",
        )
    )

    crudos = Path(tempfile.gettempdir()) / "sondeo-eodhd"
    crudos.mkdir(exist_ok=True)
    inventarios: List[str] = []

    for etiqueta, url, papel in pruebas:
        datos, diagnostico = pedir(url)
        salida.append(f"### {etiqueta}")
        salida.append("")
        salida.append(f"`{recortar(url, clave)}`")
        salida.append("")
        if datos is None:
            salida.append(f"- **sin datos** — {diagnostico}")
            salida.append("")
            continue
        tamano = len(json.dumps(datos))
        medida = f"{tamano // 1024} KB" if tamano >= 1024 else f"{tamano} bytes"
        salida.append(f"- **respuesta OK**, {medida} de JSON.")
        salida.append("")
        if papel == "inventario" and isinstance(datos, dict):
            destino = AQUI / f"extracto-{DEMO.replace('.', '-')}.json"
            destino.write_text(json.dumps(extracto(datos), indent=2, ensure_ascii=False), encoding="utf-8")
            (crudos / f"crudo-{DEMO.replace('.', '-')}.json").write_text(json.dumps(datos), encoding="utf-8")
            inventarios = [
                "## Inventario de campos sobre ese JSON",
                "",
                f"Fuente: `{DEMO}` con el token `demo`. Extracto publicable en `{destino.name}`;",
                f"el JSON completo ({tamano // 1024} KB) se regenera ejecutando este script.",
                "",
                *inventario(datos),
                "",
            ]

    salida.extend(inventarios)
    destino = AQUI / "resultado.md"
    destino.write_text("\n".join(salida) + "\n", encoding="utf-8")
    print("\n".join(salida))
    print(f"\nEscrito en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
