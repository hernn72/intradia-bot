"""Sondeo del plan gratuito de EODHD para OD-01 (D-39).

No integra nada: descarga el JSON de fundamentales de uno o dos valores europeos,
lo guarda crudo y dice qué campos de los que exige el proyecto están presentes.
La conclusión que importa es `filing_date`: sin fecha de publicación por línea no
hay point-in-time y los fundamentales no pueden entrar en un backtest (GATE B0).

Uso:

    export EODHD_API_KEY=...          # o ponerla en .env como EODHD_API_KEY
    .venv/bin/python evidence/2026-09-20-OD-01-eodhd-free/sondeo_eodhd.py

La clave nunca se imprime ni se guarda: la URL se registra con la clave recortada.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AQUI = Path(__file__).resolve().parent

# Dos valores europeos de nuestro universo, en la notación de EODHD.
SIMBOLOS = ["SAP.XETRA", "ASML.AS"]

# Qué se busca y dónde suele vivir en la respuesta de EODHD. La ruta es
# orientativa: si no está donde se espera, el sondeo la busca por todo el árbol
# y dice dónde apareció, porque el objetivo es saber si el dato existe.
CAMPOS_EXIGIDOS: List[Tuple[str, str]] = [
    ("filing_date", "fecha de publicación por línea — sin esto no hay point-in-time"),
    ("ISIN", "identidad del instrumento, para cruzar con universe.yaml"),
    ("Balance_Sheet", "estados financieros: balance"),
    ("Income_Statement", "estados financieros: cuenta de resultados"),
    ("Cash_Flow", "estados financieros: flujo de caja"),
    ("earningsShare", "EPS"),
    ("totalDebt", "deuda"),
    ("freeCashFlow", "flujo de caja libre"),
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


def url_recortada(url: str, clave: str) -> str:
    return url.replace(clave, f"{clave[:4]}…{clave[-2:]}") if clave else url


def descargar(simbolo: str, clave: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Devuelve (json, diagnóstico). El diagnóstico distingue el plan del proveedor."""
    url = f"https://eodhd.com/api/fundamentals/{simbolo}?api_token={clave}&fmt=json"
    peticion = urllib.request.Request(url, headers={"User-Agent": "intradia-bot/sondeo-OD-01"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            return json.loads(respuesta.read().decode("utf-8")), "OK"
    except urllib.error.HTTPError as error:
        cuerpo = error.read().decode("utf-8", errors="replace")[:300]
        if error.code in (401, 403):
            return None, f"HTTP {error.code}: clave rechazada o símbolo fuera del plan — {cuerpo}"
        if error.code == 402:
            return None, f"HTTP 402: LO RESTRINGE EL PLAN, no es que el proveedor no lo dé — {cuerpo}"
        if error.code == 429:
            return None, f"HTTP 429: cuota diaria del plan gratuito agotada — {cuerpo}"
        return None, f"HTTP {error.code}: {cuerpo}"
    except urllib.error.URLError as error:
        return None, f"sin respuesta: {error.reason}"


def buscar_clave(nodo: Any, buscada: str, ruta: str = "") -> List[str]:
    """Todas las rutas donde aparece `buscada`, para no fiarse de dónde debería estar."""
    encontradas: List[str] = []
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            hijo = f"{ruta}.{clave}" if ruta else str(clave)
            if clave.lower() == buscada.lower():
                encontradas.append(hijo)
            encontradas.extend(buscar_clave(valor, buscada, hijo))
    elif isinstance(nodo, list) and nodo:
        # Solo el primer elemento: las series de EODHD son homogéneas y
        # recorrerlas enteras multiplica la salida sin añadir información.
        encontradas.extend(buscar_clave(nodo[0], buscada, f"{ruta}[0]"))
    return encontradas


def informar(simbolo: str, datos: Dict[str, Any]) -> List[str]:
    lineas = [f"## {simbolo}", ""]
    for campo, para_que in CAMPOS_EXIGIDOS:
        rutas = buscar_clave(datos, campo)
        if rutas:
            muestra = ", ".join(rutas[:3])
            resto = f" (+{len(rutas) - 3} más)" if len(rutas) > 3 else ""
            lineas.append(f"- **{campo}**: PRESENTE en {muestra}{resto} — {para_que}")
        else:
            lineas.append(f"- **{campo}**: AUSENTE de la respuesta — {para_que}")
    lineas.append("")
    return lineas


def main() -> int:
    cargar_env()
    clave = os.environ.get("EODHD_API_KEY", "").strip()
    if not clave:
        print(
            "Falta EODHD_API_KEY. Créala en el plan gratuito de EODHD y ponla en .env\n"
            "como EODHD_API_KEY=... (el fichero .env no se sube al repositorio).",
            file=sys.stderr,
        )
        return 2

    salida: List[str] = [
        "# Sondeo del plan gratuito de EODHD — OD-01 / D-39",
        "",
        "Generado por `sondeo_eodhd.py`. Comprueba presencia de campos sobre el JSON",
        "crudo, no sobre la documentación del proveedor.",
        "",
    ]
    fallos = 0
    for simbolo in SIMBOLOS:
        url = f"https://eodhd.com/api/fundamentals/{simbolo}?api_token={clave}&fmt=json"
        salida.append(f"Petición: `{url_recortada(url, clave)}`")
        salida.append("")
        datos, diagnostico = descargar(simbolo, clave)
        if datos is None:
            fallos += 1
            salida.extend([f"## {simbolo}", "", f"- **sin datos** — {diagnostico}", ""])
            continue
        crudo = AQUI / f"crudo-{simbolo.replace('.', '-')}.json"
        crudo.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
        salida.append(f"JSON crudo guardado en `{crudo.name}` ({crudo.stat().st_size // 1024} KB).")
        salida.append("")
        salida.extend(informar(simbolo, datos))

    destino = AQUI / "resultado.md"
    destino.write_text("\n".join(salida) + "\n", encoding="utf-8")
    print("\n".join(salida))
    print(f"\nEscrito en {destino}")
    return 1 if fallos == len(SIMBOLOS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
