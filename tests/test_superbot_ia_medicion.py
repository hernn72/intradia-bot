"""Medición y coste de Superbot IA: valor a mercado, referencia, costes estimados, tope de gasto
opcional con cambio de política auditado, y las dos llamadas al modelo que ya no se pagan."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from superbot.ia import __main__ as cli
from superbot.ia import asesores, dashboard, datos, medicion
from superbot.ia.asesores import OK, OPORTUNIDAD, RIESGO, validar_dictamen
from superbot.ia.cartera import CarteraIA, construir_estado_cartera, valorar_abiertas
from superbot.ia.politica import PoliticaIA
from superbot.ia.registro import PoliticaDistinta, PresupuestoAgotado, RegistroIA, migrar_politica
from tests.test_superbot_ia import (
    POLITICA,
    ClienteFalso,
    T,
    _analisis,
    _pasada,
    compra_ok,
    paquete_compra,
    registro,
)
from tests.test_superbot_ia_cartera import _abrir, _cartera, _proveedor_ohlc

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def _cierre(dia: date, precio: float) -> Tuple[date, datetime, float]:
    return dia, datetime(dia.year, dia.month, dia.day, 16, 35, tzinfo=timezone.utc), precio


# --- tope de gasto y cambio de política ------------------------------------------------


class TestTopeDeGasto:
    def test_por_defecto_no_hay_tope(self, tmp_path: Path) -> None:
        reg = registro(tmp_path)
        assert POLITICA.tope_eur_mes is None
        for _ in range(3):
            reg.reservar("2026-11", 1_000.0)

    def test_sin_tope_el_gasto_se_sigue_registrando(self, tmp_path: Path) -> None:
        reg = registro(tmp_path)
        reg.reservar("2026-11", 2.0)
        reg.conciliar("2026-11", 2.0, 0.5)
        assert reg.gasto("2026-11") == pytest.approx(0.5)

    def test_un_tope_explicito_sigue_bloqueando(self, tmp_path: Path) -> None:
        reg = registro(tmp_path, PoliticaIA(tope_eur_mes=1.0))
        with pytest.raises(PresupuestoAgotado):
            reg.reservar("2026-11", 1.5)


class TestMigrarPolitica:
    ANTIGUA = PoliticaIA(tope_eur_mes=5.0)

    def test_sin_migrar_la_base_antigua_no_se_abre(self, tmp_path: Path) -> None:
        registro(tmp_path, self.ANTIGUA).close()
        with pytest.raises(PoliticaDistinta, match="migrar-politica"):
            registro(tmp_path)

    def test_migra_deja_constancia_y_la_base_se_abre(self, tmp_path: Path) -> None:
        registro(tmp_path, self.ANTIGUA).close()

        cambios = migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope de gasto")

        assert cambios == {"tope_eur_mes": {"antes": 5.0, "despues": None}}
        reg = registro(tmp_path)
        fila = reg.conn.execute("SELECT anterior, nueva, motivo FROM ia_politica_cambio").fetchone()
        assert json.loads(fila["anterior"])["params"]["tope_eur_mes"] == 5.0
        assert json.loads(fila["nueva"])["params"]["tope_eur_mes"] is None
        assert fila["motivo"] == "sin tope de gasto"

    def test_migrar_dos_veces_no_duplica(self, tmp_path: Path) -> None:
        registro(tmp_path, self.ANTIGUA).close()
        migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope")

        assert migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope") is None
        reg = registro(tmp_path)
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_politica_cambio").fetchone()[0] == 1

    def test_no_se_migra_con_una_pasada_en_curso(self, tmp_path: Path) -> None:
        reg = registro(tmp_path, self.ANTIGUA)
        with reg.exclusivo() as libre:
            assert libre
            with pytest.raises(RuntimeError, match="pasada en curso"):
                migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope")
        assert json.loads(reg.conn.execute("SELECT value FROM ia_meta").fetchone()[0])["params"]["tope_eur_mes"] == 5.0

    def test_exige_motivo_y_una_base_que_exista(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope")
        assert not (tmp_path / "ia.db").exists()
        registro(tmp_path, self.ANTIGUA).close()
        with pytest.raises(ValueError):
            migrar_politica(tmp_path / "ia.db", POLITICA, "  ")

    def test_una_base_ajena_se_rechaza_sin_dejarle_ninguna_tabla(self, tmp_path: Path) -> None:
        ajena = sqlite3.connect(tmp_path / "ia.db")
        ajena.execute("CREATE TABLE ajena (x)")
        ajena.commit()

        with pytest.raises(PoliticaDistinta, match="no es una base de Superbot IA"):
            migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope")

        assert [f[0] for f in ajena.execute("SELECT name FROM sqlite_master")] == ["ajena"]

    def test_no_adopta_una_base_de_otra_politica(self, tmp_path: Path) -> None:
        reg = registro(tmp_path, self.ANTIGUA)
        reg.conn.execute("UPDATE ia_meta SET value = ? WHERE key = 'politica'", (json.dumps({"id": "otra", "params": {}}),))
        reg.close()
        with pytest.raises(PoliticaDistinta):
            migrar_politica(tmp_path / "ia.db", POLITICA, "sin tope")

    def test_el_cli_migra_antes_de_abrir_el_registro(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        registro(tmp_path, self.ANTIGUA).close()

        assert cli.main(["--db", str(tmp_path / "ia.db"), "migrar-politica", "--motivo", "sin tope"]) == 0

        assert json.loads(capsys.readouterr().out)["cambios"]["tope_eur_mes"] == {"antes": 5.0, "despues": None}
        registro(tmp_path).close()


# --- llamadas que ya no se pagan ---------------------------------------------------------


class TestValoresConDigitos:
    def _paquete_con_cartera(self) -> Any:
        base = paquete_compra()
        datos = json.loads(json.dumps(base.datos))
        datos["cartera"]["posiciones"] = [{"valor": "MUV2.DE", "exposicion_pct": 10.0, "resultado_pct": 1.0}]
        return replace(base, datos=datos)

    def test_nombrar_una_posicion_con_digitos_no_es_una_cifra(self) -> None:
        texto = json.dumps(compra_ok(riesgos=["Se suma a MUV2.DE y concentra la exposición al euro."]))
        assert validar_dictamen(texto, self._paquete_con_cartera(), "end_turn")[0] == OK

    @pytest.mark.parametrize("frase", [
        "Se suma a MUV2.DE con un 10 de exposición", "Se suma a MUV22.DE", "Se suma a XMUV2.DE", "Se suma a ABC3.DE",
    ])
    def test_cualquier_otro_digito_sigue_invalidando(self, frase: str) -> None:
        texto = json.dumps(compra_ok(riesgos=[frase]))
        assert validar_dictamen(texto, self._paquete_con_cartera(), "end_turn")[0] == asesores.CIFRA_AJENA

    def test_un_valor_que_no_esta_en_el_paquete_no_se_admite(self) -> None:
        texto = json.dumps(compra_ok(riesgos=["Se suma a MUV2.DE"]))
        assert validar_dictamen(texto, paquete_compra(), "end_turn")[0] == asesores.CIFRA_AJENA


class TestRiesgoSoloSiPuedeCambiarElResultado:
    def test_un_descarte_de_oportunidad_no_consulta_a_riesgo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cliente = ClienteFalso([compra_ok(decision="DESCARTAR", prioridad="BAJA")])

        resultado, reg = _pasada(tmp_path, monkeypatch, [_analisis("A")], cliente)

        assert cliente.llamadas == 1 and resultado.compras == [] and resultado.incidencias == []
        fila = reg.decisiones()[0]
        assert fila["resolucion"] == "DESCARTAR" and fila["motivo"] == "RECHAZADA_POR_ASESOR"
        assert set(json.loads(fila["votos"])) == {OPORTUNIDAD}
        assert [f["asesor"] for f in reg.llamadas(resultado.pasada_id)] == [OPORTUNIDAD]

    def test_una_compra_sigue_exigiendo_a_los_dos(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cliente = ClienteFalso(por_defecto=compra_ok())

        resultado, reg = _pasada(tmp_path, monkeypatch, [_analisis("A")], cliente)

        assert cliente.llamadas == 2 and resultado.compras == ["A"]
        assert set(json.loads(reg.decisiones()[0]["votos"])) == {OPORTUNIDAD, RIESGO}

    def test_si_oportunidad_falla_no_hay_decision_ni_se_paga_a_riesgo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cliente = ClienteFalso([TimeoutError("x")])

        resultado, reg = _pasada(tmp_path, monkeypatch, [_analisis("A")], cliente)

        assert cliente.llamadas == 1 and reg.decisiones() == [] and resultado.incidencias


# --- referencia e índice de rentabilidad ------------------------------------------------


class TestValorReferencia:
    CIERRES = (_cierre(date(2026, 11, 2), 100.0), _cierre(date(2026, 11, 3), 100.0), _cierre(date(2026, 11, 4), 110.0))

    def test_el_flujo_entra_al_primer_cierre_posterior_pagando_costes(self) -> None:
        coste = medicion.coste_orden_eur(1_000.0)

        valor = medicion.valor_referencia([(T_ACTIVACION, 1_000.0)], self.CIERRES)

        assert coste == pytest.approx(2.0)
        assert valor is not None and valor[1] == date(2026, 11, 4)
        assert valor[0] == pytest.approx((1_000.0 - coste) / 100.0 * 110.0)

    def test_un_flujo_sin_cierre_todavia_cuenta_como_efectivo(self) -> None:
        tarde = datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc)

        valor = medicion.valor_referencia([(T_ACTIVACION, 1_000.0), (tarde, 500.0)], self.CIERRES)

        assert valor is not None
        assert valor[0] == pytest.approx((1_000.0 - 2.0) / 100.0 * 110.0 + 500.0)

    def test_una_retirada_vende_lo_retirado_mas_su_coste(self) -> None:
        retirada = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)

        valor = medicion.valor_referencia([(T_ACTIVACION, 1_000.0), (retirada, -110.0)], self.CIERRES)

        unidades = (1_000.0 - 2.0) / 100.0 - (110.0 + medicion.coste_orden_eur(110.0)) / 110.0
        assert valor is not None and valor[0] == pytest.approx(unidades * 110.0)

    def test_una_serie_que_empieza_despues_del_dinero_no_da_cifra(self) -> None:
        antes = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
        assert medicion.valor_referencia([(antes, 1_000.0)], self.CIERRES) is None

    @pytest.mark.parametrize("flujos, cierres", [([], CIERRES), ([(T_ACTIVACION, 1_000.0)], ())])
    def test_sin_flujos_o_sin_serie_no_hay_referencia(self, flujos: List[Any], cierres: List[Any]) -> None:
        assert medicion.valor_referencia(flujos, cierres) is None


class TestPeriodoDeLaReferencia:
    @pytest.mark.parametrize("dias, periodo", [(4, "2y"), (549, "2y"), (550, "5y"), (1_700, "10y"), (4_000, "max")])
    def test_alcanza_siempre_al_flujo_mas_antiguo(self, dias: int, periodo: str) -> None:
        flujos = [(T - timedelta(days=dias), 1_000.0), (T - timedelta(days=1), 50.0)]
        assert medicion.periodo_para(flujos, T) == periodo

    def test_sin_flujos_pide_el_periodo_corto(self) -> None:
        assert medicion.periodo_para([], T) == "2y"


class TestIndice:
    def test_una_retirada_tampoco(self) -> None:
        indice = medicion._indice([(1_000.0, 1_000.0), (1_100.0, 1_000.0), (600.0, 500.0)])
        assert indice == pytest.approx([1.0, 1.1, 1.1])

    def test_una_aportacion_no_es_rentabilidad(self) -> None:
        indice = medicion._indice([(1_000.0, 1_000.0), (1_100.0, 1_000.0), (1_600.0, 1_500.0)])
        assert indice == pytest.approx([1.0, 1.1, 1.1])

    def test_la_primera_foto_se_mide_contra_su_capital(self) -> None:
        assert medicion._indice([(950.0, 1_000.0)]) == pytest.approx([0.95])

    def test_la_caida_cuenta_desde_el_capital_inicial(self) -> None:
        assert medicion._caida_maxima([0.95, 1.10, 0.99]) == pytest.approx(0.99 / 1.10 - 1.0)
        assert medicion._caida_maxima([0.95]) == pytest.approx(-0.05)
        assert medicion._caida_maxima([]) is None


# --- valoración de posiciones --------------------------------------------------------


class TestValorarAbiertas:
    def test_valora_al_cierre_analizado(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)

        (valor,) = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))

        assert valor.valorada and valor.session == date(2026, 11, 5)
        assert valor.valor_eur == pytest.approx(1_040.0) and valor.coste_eur == pytest.approx(1_000.0)

    def test_un_cierre_anterior_a_la_compra_no_cuenta_como_resultado(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, entry_session=date(2026, 11, 6))

        (valor,) = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))

        assert valor.valorada and valor.valor_eur == pytest.approx(1_000.0) and valor.session is None

    def test_la_ia_ve_resultado_cero_en_una_posicion_aun_sin_cierre_propio(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, entry_session=date(2026, 11, 6))

        estado, incidencias = construir_estado_cartera(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))

        assert incidencias == {} and estado.equity_eur == pytest.approx(10_000.0)
        assert estado.posiciones[0].pnl_pct == pytest.approx(0.0)
        assert estado.posiciones[0].exposicion_pct == pytest.approx(10.0)

    def test_sin_analisis_cuenta_a_coste_y_lo_dice(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)

        (valor,) = valorar_abiertas(cartera_ia, {}, _proveedor_ohlc({}))

        assert not valor.valorada and valor.valor_eur == pytest.approx(1_000.0)


# --- foto por pasada y dashboard --------------------------------------------------------


def _con_posicion(tmp_path: Path, capital: float = 10_000.0) -> Tuple[CarteraIA, RegistroIA]:
    """Cartera con 1.000 EUR en ``A`` (10 a 100) y un fill de compra, como si se hubiera ejecutado."""

    cartera_ia, reg = _cartera(tmp_path)
    cartera_ia.activar(T_ACTIVACION, capital)
    # ``activar`` fecha el movimiento con el reloj real; la referencia necesita el instante simulado.
    reg.conn.execute("UPDATE ia_movimiento SET created_at = ?", (T_ACTIVACION.isoformat(),))
    _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
    return cartera_ia, reg


def _referencia(*cierres: Tuple[date, float]) -> Any:
    return _proveedor_ohlc({medicion.REFERENCIA: {dia: (precio, precio, precio) for dia, precio in cierres}})


def _crudo(proveedor: Any) -> datos.ProveedorCrudo:
    """Como en la pasada real: la medición recibe el proveedor de barras sin ajustar."""

    return datos.ProveedorCrudo(proveedor, lambda: T)


class TestFotoPorPasada:
    def test_la_pasada_activa_guarda_valor_a_mercado_y_referencia(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        proveedor = _referencia((date(2026, 11, 2), 100.0), (date(2026, 11, 3), 100.0), (date(2026, 11, 5), 102.0))

        _pasada(
            tmp_path, monkeypatch, [_analisis("A", close=104.0, score=40.0)], ClienteFalso(),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
        )

        medida = medicion.leer_medicion(reg.conn)
        assert medida is not None and medida.fotos == 1 and medida.sin_valorar == 0
        assert medida.equity_eur == pytest.approx(10_040.0)
        assert medida.rentabilidad == pytest.approx(0.004)
        assert medida.referencia_session == "2026-11-05"
        assert medida.referencia_eur == pytest.approx((10_000.0 - medicion.coste_orden_eur(10_000.0)) * 1.02)
        assert medida.referencia_eur is not None
        assert medida.rentabilidad_referencia == pytest.approx(medida.referencia_eur / 10_000.0 - 1.0)
        assert medida.posiciones[0]["symbol"] == "A" and medida.posiciones[0]["valor_eur"] == pytest.approx(1_040.0)

    def test_sin_referencia_la_foto_se_guarda_con_ese_hueco(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)

        resultado, _reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A", close=104.0, score=40.0)], ClienteFalso(),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=_proveedor_ohlc({}),
        )

        medida = medicion.leer_medicion(reg.conn)
        assert resultado.status == "OK"
        assert medida is not None and medida.equity_eur == pytest.approx(10_040.0)
        assert medida.referencia_eur is None and medida.rentabilidad_referencia is None

    def test_una_aportacion_durante_la_descarga_no_parte_la_foto(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        pasada_id = reg.abrir_pasada(T, "activo", "sha")
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=100.0)}, _proveedor_ohlc({}))

        class _AportaAlDescargar:
            def get_history(self, *_a: Any, **_k: Any) -> Any:
                otra = RegistroIA(tmp_path / "ia.db", POLITICA)
                CarteraIA(otra.conn).aportar(importe_eur=5_000.0, motivo="prueba", actor="t")
                otra.close()
                raise RuntimeError("sin datos")

        medicion.registrar_valoracion(reg, cartera_ia, valores, _AportaAlDescargar(), pasada_id, T, 0)

        medida = medicion.leer_medicion(reg.conn)
        assert medida is not None
        assert medida.equity_eur == pytest.approx(15_000.0) and medida.capital_neto_eur == pytest.approx(15_000.0)
        # La única caída es el coste estimado del fill de la posición, no los 5.000 EUR aportados.
        assert medida.rentabilidad == pytest.approx(0.0)
        assert medida.caida_maxima == pytest.approx(-medicion.coste_orden_eur(1_000.0) / 15_000.0)

    def test_un_fallo_real_dentro_de_la_foto_no_deja_transaccion_abierta(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))

        with pytest.raises(sqlite3.IntegrityError):  # ``pasada_id`` inexistente: viola la clave ajena
            medicion.registrar_valoracion(reg, cartera_ia, valores, _crudo(_proveedor_ohlc({})), 999, T, 0)

        assert not reg.conn.in_transaction and medicion.leer_medicion(reg.conn) is None

    def test_un_fallo_al_guardar_la_foto_no_detiene_la_pasada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)

        def roto(*_a: Any, **_k: Any) -> None:
            raise RuntimeError("disco lleno")

        monkeypatch.setattr(medicion, "registrar_valoracion", roto)
        resultado, _reg = _pasada(
            tmp_path, monkeypatch, [_analisis("A"), _analisis("B")], ClienteFalso(por_defecto=compra_ok()),
            cartera_ia=cartera_ia, registro_existente=reg, proveedor=_proveedor_ohlc({}),
        )

        assert resultado.status == "OK" and resultado.compras == ["B"] and resultado.incidencias == []

    def test_en_modo_registro_no_hay_foto(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _resultado, reg = _pasada(tmp_path, monkeypatch, [_analisis("A")], ClienteFalso(por_defecto=compra_ok()))
        assert medicion.leer_medicion(reg.conn) is None

    def test_los_costes_estimados_bajan_la_rentabilidad_neta(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        pasada_id = reg.abrir_pasada(T, "activo", "sha")
        reg.guardar_paquete(paquete_compra())
        # Una llamada anterior a la activación (9 €) no es gasto de esta cartera; la posterior (3 €) sí.
        for coste, cuando in ((9.0, T_ACTIVACION - timedelta(hours=1)), (3.0, T_ACTIVACION + timedelta(hours=1))):
            reg.guardar_llamada(
                pasada_id=pasada_id, asesor=OPORTUNIDAD, provider="anthropic", prompt_version="v", schema_version="1",
                input_hash=paquete_compra().input_hash, input_source_ids="[]", observaciones="[]",
                analysis_timestamp=T.isoformat(), estado=OK, coste_eur=coste,
                created_at=cuando.isoformat(timespec="seconds"),
            )
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))

        medicion.registrar_valoracion(reg, cartera_ia, valores, _crudo(_proveedor_ohlc({})), pasada_id, T, 0)

        medida = medicion.leer_medicion(reg.conn)
        assert medida is not None
        assert medida.costes_ejecucion_eur == pytest.approx(2.0) and medida.gasto_api_eur == pytest.approx(3.0)
        assert medida.equity_neta_eur == pytest.approx(10_035.0)
        assert medida.rentabilidad == pytest.approx(0.004) and medida.rentabilidad_neta == pytest.approx(0.0035)

    def test_un_reinicio_empieza_una_serie_nueva(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        pasada_id = reg.abrir_pasada(T, "activo", "sha")
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))
        medicion.registrar_valoracion(reg, cartera_ia, valores, _crudo(_proveedor_ohlc({})), pasada_id, T, 0)

        cartera_ia.reiniciar_cartera(capital_inicial_eur=5_000.0, motivo="prueba", actor="t", instante=T)

        assert medicion.leer_medicion(reg.conn) is None
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_valoracion").fetchone()[0] == 1


class TestDashboard:
    def test_muestra_la_medicion_y_el_valor_de_cada_posicion(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        pasada_id = reg.abrir_pasada(T, "activo", "sha")
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))
        medicion.registrar_valoracion(
            reg, cartera_ia, valores, _crudo(_referencia((date(2026, 11, 3), 100.0), (date(2026, 11, 5), 102.0))),
            pasada_id, T, 0,
        )

        pagina = dashboard.render_html(cartera_ia, reg, "ahora")

        assert "Medición a mercado" in pagina and "10.040,00 EUR" in pagina
        assert f"{medicion.REFERENCIA} con el mismo capital" in pagina
        assert "1.040,00 EUR" in pagina and "4,00 %" in pagina

    def test_sin_fotos_lo_dice_y_no_inventa_valores(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)

        pagina = dashboard.render_html(cartera_ia, reg, "ahora")

        assert "Todavía no hay ninguna valoración a mercado" in pagina

    def test_una_posicion_posterior_a_la_foto_no_hereda_cifras_ajenas(self, tmp_path: Path) -> None:
        cartera_ia, reg = _con_posicion(tmp_path)
        pasada_id = reg.abrir_pasada(T, "activo", "sha")
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))
        medicion.registrar_valoracion(reg, cartera_ia, valores, _crudo(_proveedor_ohlc({})), pasada_id, T, 0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=104.0, exit_price_eur=104.0, exit_session=date(2026, 11, 6),
            origen="STOP_OBLIGATORIO", motivo="STOP_TOCADO",
        )
        _abrir(cartera_ia, symbol="A", entry_price=50.0, units=3.0, entry_session=date(2026, 11, 7))

        tabla = dashboard._posiciones_abiertas_table(cartera_ia, medicion.leer_medicion(reg.conn))

        assert "1.040,00 EUR" not in tabla and "N/D" in tabla

    def test_una_posicion_a_coste_lo_dice_en_vez_de_inventar_un_cierre(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, entry_session=date(2026, 11, 6))
        pasada_id = reg.abrir_pasada(T, "activo", "sha")
        valores = valorar_abiertas(cartera_ia, {"A": _analisis("A", close=104.0)}, _proveedor_ohlc({}))
        medicion.registrar_valoracion(reg, cartera_ia, valores, _crudo(_proveedor_ohlc({})), pasada_id, T, 0)

        tabla = dashboard._posiciones_abiertas_table(cartera_ia, medicion.leer_medicion(reg.conn))

        assert "a coste: aún sin cierre propio" in tabla and "0,00 %" in tabla

    def test_los_fills_muestran_el_precio_en_euros(self) -> None:
        tabla = dashboard._fills_table([{
            "session": "2026-11-10", "symbol": "VRTX", "lado": "COMPRA", "units": 0.7888, "precio": 546.97,
            "precio_eur": 489.87, "importe_eur": 386.41,
        }])
        assert "489,87 EUR" in tabla and "546,97" not in tabla
