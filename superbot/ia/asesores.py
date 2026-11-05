"""Asesores: llamada al modelo y validación estricta de su dictamen.

El esquema no tiene campos de precio, stop, tamaño ni capital, así que el modelo
no puede ordenarlos. La validación corre además aquí: una respuesta dudosa vale
como fallo y nunca como aprobación.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple

from superbot.ia.comite import COMPRAR, DESCARTAR, MANTENER, PRIORIDADES, VENDER, Voto
from superbot.ia.paquete import COMPRA, POSICION, Paquete
from superbot.ia.politica import CAUSAS, PoliticaIA

OPORTUNIDAD = "oportunidad"
RIESGO = "riesgo"

OK = "OK"
JSON_INVALIDO = "JSON_INVALIDO"
ESQUEMA_INVALIDO = "ESQUEMA_INVALIDO"
CITA_INEXISTENTE = "CITA_INEXISTENTE"
CIFRA_AJENA = "CIFRA_AJENA"
DATO_EXTERNO = "DATO_EXTERNO"
CAUSA_NO_CIERTA = "CAUSA_NO_CIERTA"
TRUNCADA = "TRUNCADA"
RECHAZADA = "RECHAZADA"
ERROR_LLAMADA = "ERROR_LLAMADA"
SIN_PRESUPUESTO = "SIN_PRESUPUESTO"
SIN_CLIENTE = "SIN_CLIENTE"

_PROMPTS = Path(__file__).parent / "prompts"

_TEXTOS: Dict[str, Any] = {"type": "array", "items": {"type": "string"}}
_COMUNES: Dict[str, Any] = {"motivos": _TEXTOS, "riesgos": _TEXTOS, "datos_citados": _TEXTOS}

ESQUEMA_COMPRA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": [COMPRAR, DESCARTAR]},
        "prioridad": {"type": "string", "enum": list(PRIORIDADES)},
        **_COMUNES,
    },
    "required": ["decision", "prioridad", "motivos", "riesgos", "datos_citados"],
    "additionalProperties": False,
}
ESQUEMA_POSICION: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": [MANTENER, VENDER]},
        "causa": {"anyOf": [{"type": "string", "enum": list(CAUSAS)}, {"type": "null"}]},
        **_COMUNES,
    },
    "required": ["decision", "causa", "motivos", "riesgos", "datos_citados"],
    "additionalProperties": False,
}

# Lo que delata conocimiento ajeno al paquete. Una coincidencia invalida el dictamen.
_EXTERNO = re.compile(
    r"\b(noticias?|rumor(es)?|titulares?|analistas?|consenso|presentaci[oó]n de resultados|"
    r"resultados (trimestrales|empresariales|del trimestre)|guidance|fed|bce|banco central|"
    r"inflaci[oó]n|tipos de inter[eé]s|aranceles|elecciones|guerra|ceo|adquisici[oó]n|fusi[oó]n)\b",
    re.IGNORECASE,
)
_CIFRA = re.compile(r"(?<![A-Za-zÁÉÍÓÚáéíóúÑñ_\-])\d+(?:[.,]\d+)?(?![A-Za-z_])")


@dataclass(frozen=True)
class RespuestaModelo:
    texto: str
    modelo: str
    stop_reason: Optional[str]
    request_id: Optional[str]
    tokens_entrada: int
    tokens_salida: int


class ClienteIA(Protocol):
    def llamar(self, system: str, mensaje: str, esquema: Mapping[str, Any]) -> RespuestaModelo: ...


class ClienteAnthropic:
    """Llamada real. Sin fallback a otro modelo: una negativa es un fallo y debe constar como tal."""

    def __init__(self, api_key: str, politica: PoliticaIA) -> None:
        from anthropic import Anthropic

        self._client: Any = Anthropic(api_key=api_key, timeout=120.0, max_retries=2)
        self._politica = politica

    def llamar(self, system: str, mensaje: str, esquema: Mapping[str, Any]) -> RespuestaModelo:
        respuesta: Any = self._client.messages.create(
            model=self._politica.modelo,
            max_tokens=self._politica.max_tokens,
            system=system,
            messages=[{"role": "user", "content": mensaje}],
            output_config={
                "effort": self._politica.esfuerzo,
                "format": {"type": "json_schema", "schema": dict(esquema)},
            },
        )
        texto = next((b.text for b in respuesta.content if b.type == "text"), "")
        return RespuestaModelo(
            texto=texto,
            modelo=respuesta.model,
            stop_reason=respuesta.stop_reason,
            request_id=getattr(respuesta, "_request_id", None),
            tokens_entrada=respuesta.usage.input_tokens,
            tokens_salida=respuesta.usage.output_tokens,
        )


def cargar_prompt(asesor: str) -> str:
    return (_PROMPTS / f"{asesor}.md").read_text(encoding="utf-8").strip()


def version_prompt(asesor: str) -> str:
    return hashlib.sha256(cargar_prompt(asesor).encode("utf-8")).hexdigest()


def esquema_de(paquete: Paquete) -> Mapping[str, Any]:
    return ESQUEMA_COMPRA if paquete.tipo == COMPRA else ESQUEMA_POSICION


def _valor_en(datos: Any, ruta: str) -> Any:
    actual = datos
    for parte in ruta.split("."):
        if isinstance(actual, Mapping) and parte in actual:
            actual = actual[parte]
        elif isinstance(actual, list) and parte.isdigit() and int(parte) < len(actual):
            actual = actual[int(parte)]
        else:
            return None
    return actual


def _numeros(value: Any) -> List[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, Mapping):
        return [n for item in value.values() for n in _numeros(item)]
    if isinstance(value, (list, tuple)):
        return [n for item in value for n in _numeros(item)]
    return []


def _cifra_conocida(texto: str, conocidos: List[float]) -> bool:
    numero = float(texto.replace(",", "."))
    decimales = len(texto.replace(",", ".").partition(".")[2])
    return any(round(valor, decimales) == numero or round(abs(valor), decimales) == numero for valor in conocidos)


def _texto_valido(frases: List[str], conocidos: List[float]) -> Optional[str]:
    for frase in frases:
        if _EXTERNO.search(frase):
            return DATO_EXTERNO
        if any(not _cifra_conocida(match.group(0), conocidos) for match in _CIFRA.finditer(frase)):
            return CIFRA_AJENA
    return None


def validar_dictamen(texto: str, paquete: Paquete, stop_reason: Optional[str]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Devuelve el estado y, solo si es ``OK``, el dictamen."""

    if stop_reason == "max_tokens":
        return TRUNCADA, None
    if stop_reason == "refusal":
        return RECHAZADA, None
    try:
        data = json.loads(texto)
    except (TypeError, ValueError):
        return JSON_INVALIDO, None
    if not isinstance(data, dict):
        return JSON_INVALIDO, None

    esquema = esquema_de(paquete)
    if set(data) != set(esquema["properties"]):
        return ESQUEMA_INVALIDO, None
    if data["decision"] not in esquema["properties"]["decision"]["enum"]:
        return ESQUEMA_INVALIDO, None
    for campo in ("motivos", "riesgos", "datos_citados"):
        if not isinstance(data[campo], list) or not all(isinstance(item, str) and item.strip() for item in data[campo]):
            return ESQUEMA_INVALIDO, None
    if not data["motivos"] or not data["datos_citados"]:
        return ESQUEMA_INVALIDO, None

    if paquete.tipo == COMPRA and data["prioridad"] not in PRIORIDADES:
        return ESQUEMA_INVALIDO, None
    if paquete.tipo == POSICION:
        vende = data["decision"] == VENDER
        if vende and data["causa"] not in CAUSAS:
            return ESQUEMA_INVALIDO, None
        if not vende and data["causa"] is not None:
            return ESQUEMA_INVALIDO, None
        if vende and paquete.datos.get("predicados", {}).get(data["causa"]) is not True:
            return CAUSA_NO_CIERTA, None

    if any(_valor_en(paquete.datos, ruta) is None for ruta in data["datos_citados"]):
        return CITA_INEXISTENTE, None
    fallo = _texto_valido(data["motivos"] + data["riesgos"], _numeros(paquete.datos))
    if fallo is not None:
        return fallo, None
    return OK, data


def voto_de(asesor: str, dictamen: Optional[Mapping[str, Any]]) -> Optional[Voto]:
    if dictamen is None:
        return None
    return Voto(asesor, dictamen["decision"], dictamen.get("prioridad"), dictamen.get("causa"))
