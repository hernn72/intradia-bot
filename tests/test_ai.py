"""Capa IA: mensaje al agente, parseo de la respuesta y degradación."""

from __future__ import annotations

import json

from advisor.ai.agents import _call, build_user_message
from advisor.ai.narrator import enrich_with_narrative, extract_json, parse_narrative
from advisor.analysis.levels import compute_levels
from advisor.analysis.opportunity import build_opportunity
from advisor.analysis.scoring import compute_score
from advisor.config import AiConfig, LevelsConfig, RiskConfig, ScoringConfig
from tests.test_analysis import make_snapshot

_RESPUESTA = {
    "tesis": "Estructura alcista con volumen por encima de la media.",
    "catalizador": "Ruptura del máximo de la ventana con volumen doble.",
    "escenario_alcista": "Continuación hasta el objetivo 3.",
    "escenario_base": "Avance hacia el objetivo 2.",
    "escenario_bajista": "Pérdida del soporte y activación del stop.",
    "que_podria_salir_mal": ["Fallo de la ruptura", "Repunte del VIX"],
}


def _opportunity(asset, context):
    snapshot = make_snapshot()
    levels = compute_levels(snapshot, LevelsConfig())
    score = compute_score(snapshot, levels, context, ScoringConfig(), 250)
    return build_opportunity(
        asset=asset, horizonte="swing", snapshot=snapshot, levels=levels,
        score=score, context=context, scoring=ScoringConfig(), risk=RiskConfig(),
    )


class TestExtractJson:
    def test_json_limpio(self) -> None:
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_envuelto_en_texto(self) -> None:
        assert extract_json('Claro:\n```json\n{"a": 1}\n```\nEso es todo.') == {"a": 1}

    def test_sin_json(self) -> None:
        assert extract_json("no hay nada aquí") is None

    def test_cadena_vacia(self) -> None:
        assert extract_json("") is None

    def test_json_que_no_es_objeto(self) -> None:
        assert extract_json("[1, 2, 3]") is None


class TestParseNarrative:
    def test_respuesta_completa(self) -> None:
        narrative = parse_narrative(json.dumps(_RESPUESTA))
        assert narrative.tesis.startswith("Estructura alcista")
        assert len(narrative.que_podria_salir_mal) == 2

    def test_campos_ausentes_quedan_vacios(self) -> None:
        narrative = parse_narrative('{"tesis": "Solo la tesis"}')
        assert narrative.tesis == "Solo la tesis"
        assert narrative.catalizador == ""
        assert narrative.que_podria_salir_mal == []

    def test_riesgos_como_cadena_se_normalizan_a_lista(self) -> None:
        narrative = parse_narrative('{"que_podria_salir_mal": "un solo riesgo"}')
        assert narrative.que_podria_salir_mal == ["un solo riesgo"]

    def test_respuesta_no_json_devuelve_none(self) -> None:
        assert parse_narrative("el modelo se puso a charlar") is None

    def test_conserva_la_respuesta_cruda(self) -> None:
        raw = json.dumps(_RESPUESTA)
        assert parse_narrative(raw).raw == raw


class TestBuildUserMessage:
    def test_incluye_los_niveles_ya_fijados(self, asset_eur, benign_context) -> None:
        mensaje = build_user_message(_opportunity(asset_eur, benign_context))
        assert "NIVELES YA FIJADOS (no los modifiques)" in mensaje
        assert "Ratio beneficio/riesgo" in mensaje

    def test_declara_las_dimensiones_sin_datos(self, asset_eur, benign_context) -> None:
        mensaje = build_user_message(_opportunity(asset_eur, benign_context))
        assert "Dimensiones sin datos: fundamental" in mensaje

    def test_incluye_la_decision_del_sistema(self, asset_eur, benign_context) -> None:
        opportunity = _opportunity(asset_eur, benign_context)
        assert f"Decisión del sistema: {opportunity.accion}" in build_user_message(opportunity)


class TestEnrichWithNarrative:
    def test_ia_desactivada_devuelve_las_oportunidades_intactas(self, asset_eur, benign_context) -> None:
        opportunities = [_opportunity(asset_eur, benign_context)]
        assert enrich_with_narrative(opportunities, AiConfig(enabled=False)) is opportunities

    def test_lista_vacia(self) -> None:
        assert enrich_with_narrative([], AiConfig(enabled=True)) == []

    def test_sin_clave_api_no_falla(self, asset_eur, benign_context, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        opportunities = [_opportunity(asset_eur, benign_context)]
        resultado = enrich_with_narrative(opportunities, AiConfig(enabled=True))
        assert resultado is opportunities
        assert resultado[0].narrative is None


class _Block:
    """Bloque de contenido de una respuesta, como los que devuelve el SDK."""

    def __init__(self, tipo: str, text=None) -> None:
        self.type = tipo
        if text is not None:
            self.text = text


class _FakeMessage:
    def __init__(self, content, stop_reason="end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


class _FakeClient:
    """Cliente mínimo: registra la llamada y devuelve la respuesta preparada."""

    def __init__(self, message) -> None:
        self._message = message
        self.kwargs = None
        self.messages = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self._message


class TestCall:
    def test_ignora_los_bloques_de_razonamiento(self) -> None:
        """El texto no tiene por qué ser el primer bloque de la respuesta."""

        client = _FakeClient(_FakeMessage([
            _Block("thinking", ""),
            _Block("text", '  {"tesis": "vale"}  '),
        ]))
        assert _call(client, "modelo", "system", "user") == '{"tesis": "vale"}'

    def test_sin_bloque_de_texto_falla_con_los_tipos_recibidos(self) -> None:
        client = _FakeClient(_FakeMessage([_Block("thinking", "")]))
        try:
            _call(client, "modelo", "system", "user")
        except RuntimeError as exc:
            assert "thinking" in str(exc)
        else:
            raise AssertionError("debería haber lanzado RuntimeError")

    def test_avisa_cuando_la_respuesta_se_trunca(self, caplog) -> None:
        client = _FakeClient(_FakeMessage([_Block("text", '{"tesis": "a med')], stop_reason="max_tokens"))
        with caplog.at_level("WARNING"):
            _call(client, "modelo", "system", "user")
        assert "truncada" in caplog.text

    def test_pide_margen_suficiente_de_tokens(self) -> None:
        """Un techo ajustado corta el JSON y pierde la narrativa en silencio."""

        client = _FakeClient(_FakeMessage([_Block("text", "{}")]))
        _call(client, "modelo", "system", "user")
        assert client.kwargs["max_tokens"] >= 2000
