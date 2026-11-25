"""Contrafactual sobre sesiones oficiales (D-90): ni un hueco ni una barra de más cambian el día de un desenlace."""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
import pytest

from advisor.data.calendars import expected_sessions
from superbot.ia import contrafactual as cf
from superbot.ia import madurez
from superbot.ia.registro import RegistroIA
from superbot_lab import evaluacion
from tests.test_superbot_ia_madurez import NIVELES, SESIONES, _base, _decision, _tras

H, ESPERA = cf.HORIZONTE_SESIONES, cf.SESIONES_DE_ESPERA
NAN = float("nan")
SANA = (98.0, 97.0, 99.0)
TOCA = (98.0, 94.0, 96.0)
PLAZAS = ("XETRA", "NASDAQ", "NYSE", "JPX", "HKG", "LSE", "KSC", "CRYPTO")
Fila = Tuple[float, float, float]


def _sesiones(market: str, n: int = 40) -> List[date]:
    return expected_sessions(market, date(2026, 11, 25), date(2027, 6, 30))[:n]


def _serie(sesiones: Sequence[date], stop_en: Optional[int] = None) -> List[cf.Barra]:
    """Una cotización distinta por sesión, para que desplazarse un día cambie el resultado."""

    return [
        (s, *(TOCA if i == stop_en else (98.0, 97.0, 98.0 + i / 10))) for i, s in enumerate(sesiones)
    ]


def _sim(barras: Sequence[cf.Barra], cerradas: Sequence[date], splits: Sequence[date] = ()) -> cf.Desenlace:
    return cf.simular_en_calendario(NIVELES, barras, cerradas[0], cerradas, splits)


class TestSesionesOficiales:
    @pytest.mark.parametrize("market", PLAZAS)
    def test_el_horizonte_es_la_vigesima_sesion_de_su_plaza(self, market: str) -> None:
        sesiones = _sesiones(market)
        barras = _serie(sesiones)
        antes = _sim(barras[:H - 1], sesiones[:H - 1])
        assert (antes.estado, antes.final, antes.sesiones) == (cf.ABIERTA, False, H - 1)
        d = _sim(barras, sesiones)
        assert (d.estado, d.final, d.sesiones, d.hasta_session) == (cf.HORIZONTE, True, H, sesiones[H - 1])
        assert d.salida == barras[H - 1][3] and d == cf.simular(NIVELES, barras, sesiones[0])

    def test_los_festivos_de_cada_plaza_no_cuentan(self) -> None:
        """Acción de Gracias, Navidad y fin de año caen dentro; cada plaza acaba en su propio día."""

        def vigesima(market: str) -> date:
            sesiones = expected_sessions(market, date(2026, 12, 10), date(2027, 3, 1))[:30]
            fin = _sim(_serie(sesiones), sesiones).hasta_session
            assert fin is not None
            return fin

        fines = {m: vigesima(m) for m in ("XETRA", "NASDAQ", "JPX", "CRYPTO")}
        assert fines["CRYPTO"] == date(2026, 12, 29)
        assert len(set(fines.values())) >= 3
        assert date(2026, 11, 26) not in expected_sessions("NASDAQ", date(2026, 11, 25), date(2026, 11, 27))

    @pytest.mark.parametrize("market", ["XETRA", "NASDAQ", "JPX"])
    @pytest.mark.parametrize("stop_en", [None, 12])
    def test_una_barra_de_un_dia_sin_sesion_se_descarta(self, market: str, stop_en: Optional[int]) -> None:
        sesiones = _sesiones(market)
        barras = _serie(sesiones, stop_en)
        ajenos = [
            sesiones[0] + timedelta(days=i) for i in range((sesiones[H] - sesiones[0]).days)
            if sesiones[0] + timedelta(days=i) not in sesiones
        ]
        assert ajenos
        sucias = sorted([*barras, *((dia, *TOCA) for dia in ajenos)])
        assert _sim(sucias, sesiones) == _sim(barras, sesiones)

    def test_una_barra_en_dia_sin_sesion_no_compensa_un_hueco(self) -> None:
        sesiones = _sesiones("XETRA", ESPERA - 1)
        sabado = next(s for s in sesiones if s.weekday() == 4) + timedelta(days=1)
        barras = sorted([*(b for i, b in enumerate(_serie(sesiones)) if i != 7), (sabado, *SANA)])
        d = _sim(barras, sesiones)
        assert d.estado == cf.DATOS_INCOMPLETOS and not d.final

    def test_un_cierre_extraordinario_declarado_deja_de_ser_hueco(self) -> None:
        """Con la plaza cerrada por sorpresa falta una barra hasta que el calendario lo recoge."""

        sesiones = _sesiones("HKG")
        tifon = sesiones[5]
        barras = [b for b in _serie(sesiones) if b[0] != tifon]
        assert _sim(barras, sesiones[:ESPERA - 1]).estado == cf.DATOS_INCOMPLETOS
        corregidas = [s for s in sesiones if s != tifon]
        d = _sim(barras, corregidas)
        assert (d.estado, d.hasta_session) == (cf.HORIZONTE, corregidas[H - 1])

    def test_si_la_objetivo_deja_de_ser_sesion_no_se_entra_otro_dia(self) -> None:
        sesiones = _sesiones("HKG", 10)
        d = cf.simular_en_calendario(NIVELES, _serie(sesiones), sesiones[0], sesiones[1:])
        assert d.estado == cf.SIN_BARRA_DE_ENTRADA and d.entrada is None and not d.final


class TestHuecos:
    @pytest.mark.parametrize("hueco", range(1, H))
    def test_un_hueco_se_reintenta_hasta_la_espera_y_si_llega_da_lo_mismo_que_sin_hueco(self, hueco: int) -> None:
        sesiones = _sesiones("XETRA")
        barras = _serie(sesiones)
        con_hueco = [b for i, b in enumerate(barras) if i != hueco]
        for n in (hueco + 2, ESPERA - 1, ESPERA):
            d = _sim(con_hueco[:n - 1], sesiones[:n])
            assert (d.estado, d.final) == (cf.DATOS_INCOMPLETOS, n == ESPERA)
            assert d.salida is None and d.retorno_pct is None and d.retorno_r is None and d.entrada == 98.0
            assert (d.sesiones, d.hasta_session) == (hueco + 1, sesiones[hueco])
            assert (d.retorno_corto_pct is not None) == (hueco >= cf.HORIZONTE_CORTO)
        assert _sim(barras, sesiones[:ESPERA]) == _sim(barras[:H], sesiones[:H])

    @pytest.mark.parametrize("vacia", [
        (NAN, NAN, NAN), (NAN, 97.0, 99.0), (98.0, NAN, 99.0), (98.0, 97.0, NAN), (0.0, 0.0, 0.0), (98.0, -1.0, 99.0),
        (math.inf, 97.0, 99.0),
    ])
    @pytest.mark.parametrize("donde", [0, 3, H - 1])
    def test_una_sesion_sin_cotizacion_valida_es_un_hueco(self, vacia: Fila, donde: int) -> None:
        sesiones = _sesiones("XETRA", ESPERA - 1)
        barras = _serie(sesiones)
        barras[donde] = (sesiones[donde], *vacia)
        d = _sim(barras, sesiones)
        assert d.estado == (cf.DATOS_INCOMPLETOS if donde else cf.SIN_BARRA_DE_ENTRADA)
        assert not d.final and d.motivo_gate is None and d.salida is None

    def test_un_hueco_posterior_al_desenlace_no_importa(self) -> None:
        sesiones = _sesiones("XETRA")
        assert _sim([b for i, b in enumerate(_serie(sesiones)) if i != H], sesiones).estado == cf.HORIZONTE
        paradas = [b for i, b in enumerate(_serie(sesiones, 4)) if i != 5]
        assert _sim(paradas, sesiones) == _sim(_serie(sesiones, 4), sesiones)

    @pytest.mark.parametrize("entra", [(), ((98.0, NAN, NAN),), (SANA, (98.5, 97.0, 99.0))])
    def test_sin_apertura_fiable_no_hay_entrada_ni_rechazo_y_se_espera(self, entra: Tuple[Fila, ...]) -> None:
        sesiones = _sesiones("XETRA")
        barras = [*((sesiones[0], *fila) for fila in entra), *_serie(sesiones)[1:]]
        for n in (6, ESPERA - 1, ESPERA):
            d = _sim([b for b in barras if b[0] <= sesiones[n - 1]], sesiones[:n])
            assert (d.estado, d.final, d.entrada) == (cf.SIN_BARRA_DE_ENTRADA, n == ESPERA, None)

    def test_un_dato_que_no_llega_a_la_objetivo_sigue_pendiente(self) -> None:
        sesiones = _sesiones("XETRA")
        previa = (sesiones[0] - timedelta(days=1), *SANA)
        assert _sim([previa], sesiones) == cf.Desenlace(cf.PENDIENTE)
        assert cf.simular_en_calendario(NIVELES, [previa], sesiones[0], []) == cf.Desenlace(cf.PENDIENTE)

    def test_los_niveles_incompletos_y_el_gate_siguen_igual(self) -> None:
        sesiones = _sesiones("XETRA", 5)
        barras = _serie(sesiones)
        d = cf.simular_en_calendario({"stop": 95.0}, barras, sesiones[0], sesiones)
        assert d.estado == cf.DATOS_INCOMPLETOS and d.final
        cara = [(sesiones[0], 102.0, 101.0, 104.0), *barras[1:]]
        rechazo = _sim(cara, sesiones)
        assert (rechazo.estado, rechazo.motivo_gate, rechazo.final) == (cf.NO_EJECUTABLE, "ABOVE_MAX_ENTRY", True)


class TestDuplicadas:
    @pytest.mark.parametrize("donde", [0, 6, H - 1])
    def test_una_barra_repetida_identica_se_unifica(self, donde: int) -> None:
        sesiones = _sesiones("XETRA")
        barras = _serie(sesiones)
        assert _sim([*barras[:donde + 1], *barras[donde:]], sesiones) == _sim(barras, sesiones)

    def test_una_vacia_junto_a_una_valida_no_estorba(self) -> None:
        sesiones = _sesiones("XETRA")
        barras = _serie(sesiones)
        sucias = sorted([*barras, (sesiones[0], NAN, NAN, NAN), (sesiones[6], NAN, 97.0, NAN)], key=lambda b: b[0])
        assert _sim(sucias, sesiones) == _sim(barras, sesiones)

    @pytest.mark.parametrize("otra", [(98.0, 97.0, 120.0), TOCA, (90.0, 89.0, 91.0), (98.0, 96.0, NAN)])
    @pytest.mark.parametrize("donde", [0, 6, H - 1])
    @pytest.mark.parametrize("primero", [True, False])
    def test_dos_precios_para_una_sesion_no_se_eligen(self, otra: Fila, donde: int, primero: bool) -> None:
        sesiones = _sesiones("XETRA", ESPERA - 1)
        barras = _serie(sesiones)
        barras.insert(donde + (0 if primero else 1), (sesiones[donde], *otra))
        d = _sim(barras, sesiones)
        assert d.estado == (cf.DATOS_INCOMPLETOS if donde else cf.SIN_BARRA_DE_ENTRADA)
        assert not d.final and d.salida is None

    def test_una_duplicada_no_compensa_un_hueco(self) -> None:
        sesiones = _sesiones("XETRA", ESPERA - 1)
        barras = _serie(sesiones)
        d = _sim([*barras[:7], barras[6], *barras[8:]], sesiones)
        assert d.estado == cf.DATOS_INCOMPLETOS and not d.final

    def test_el_orden_de_las_barras_no_cambia_nada(self) -> None:
        sesiones = _sesiones("XETRA")
        for stop_en in (None, 9):
            barras = _serie(sesiones, stop_en)
            assert _sim(barras[::-1], sesiones) == _sim(barras, sesiones)


class TestStops:
    @pytest.mark.parametrize("stop_en", range(H))
    def test_el_stop_cierra_en_su_sesion(self, stop_en: int) -> None:
        sesiones = _sesiones("XETRA")
        d = _sim(_serie(sesiones, stop_en), sesiones)
        assert (d.estado, d.final, d.salida) == (cf.STOP, True, 95.0)
        assert (d.sesiones, d.hasta_session) == (stop_en + 1, sesiones[stop_en])

    def test_un_stop_tras_el_horizonte_no_existe(self) -> None:
        sesiones = _sesiones("XETRA")
        assert _sim(_serie(sesiones, H), sesiones).estado == cf.HORIZONTE

    @pytest.mark.parametrize("hueco,stop_en", [(2, 5), (1, 2), (18, 19), (5, 5)])
    def test_un_stop_detras_de_un_hueco_no_se_da_por_bueno(self, hueco: int, stop_en: int) -> None:
        sesiones = _sesiones("XETRA")
        barras = _serie(sesiones, stop_en)
        for n in (ESPERA - 1, ESPERA):
            d = _sim([b for i, b in enumerate(barras[:n]) if i != hueco], sesiones[:n])
            assert (d.estado, d.final, d.salida) == (cf.DATOS_INCOMPLETOS, n == ESPERA, None)
        assert _sim(barras, sesiones).hasta_session == sesiones[stop_en]

    def test_un_hueco_bajista_se_ejecuta_a_la_apertura(self) -> None:
        sesiones = _sesiones("XETRA")
        barras = _serie(sesiones)
        barras[6] = (sesiones[6], 93.0, 92.0, 94.0)
        d = _sim(barras, sesiones)
        assert (d.estado, d.salida, d.hasta_session) == (cf.STOP, 93.0, sesiones[6])


class TestExclusionDeCotizacion:
    @pytest.mark.parametrize("ultimas", [1, 5, H - 1])
    @pytest.mark.parametrize("cerradas", [H, ESPERA, 40])
    def test_un_valor_que_deja_de_cotizar_ni_llega_al_horizonte_ni_se_cierra(self, ultimas: int, cerradas: int) -> None:
        sesiones = _sesiones("XETRA")
        d = _sim(_serie(sesiones)[:ultimas], sesiones[:cerradas])
        assert (d.estado, d.final, d.sesiones) == (cf.ABIERTA, False, ultimas)
        assert d.hasta_session == sesiones[ultimas - 1]

    def test_una_suspension_se_completa_si_el_proveedor_recupera_las_barras(self) -> None:
        sesiones = _sesiones("XETRA")
        barras = _serie(sesiones)
        suspendido = [b for i, b in enumerate(barras) if not 5 <= i < 9]
        assert _sim(suspendido[:12], sesiones[:16]).estado == cf.DATOS_INCOMPLETOS
        assert _sim(barras, sesiones).estado == cf.HORIZONTE

    def test_excluido_tras_un_stop_conserva_el_stop(self) -> None:
        sesiones = _sesiones("XETRA")
        assert _sim(_serie(sesiones, 4)[:6], sesiones).estado == cf.STOP

    @pytest.mark.parametrize("dias,excluye", [(-1, False), (0, True), (3, True)])
    def test_un_split_excluye_como_siempre(self, dias: int, excluye: bool) -> None:
        sesiones = _sesiones("XETRA")
        d = _sim(_serie(sesiones), sesiones, [sesiones[0] + timedelta(days=dias)])
        assert d.estado == (cf.SPLIT_POSTERIOR if excluye else cf.HORIZONTE) and d.final


@pytest.mark.parametrize("market", ["XETRA", "NASDAQ", "JPX"])
def test_ninguna_averia_del_proveedor_cambia_un_desenlace_definitivo(market: str) -> None:
    """Con huecos, vacías, repetidas, contradictorias, barras de festivo y desorden: el mismo desenlace o ninguno."""

    azar, vistos, sesiones = random.Random(20261125), set(), _sesiones(market)
    for _ in range(400):
        n = azar.randint(1, len(sesiones))
        limpias = _serie(sesiones, azar.choice([None, *range(H)]))[:n]
        sucias: List[cf.Barra] = []
        rotas = set(azar.sample(range(n), min(n, azar.randint(0, 4))))
        for i, barra in enumerate(limpias):  # a lo sumo una avería por sesión: con dos, la buena podría no verse nunca
            tipo = azar.choice(("falta", "vacia", "repetida", "contraria")) if i in rotas else "sana"
            if tipo == "vacia":
                sucias.append((barra[0], *azar.choice([(NAN, NAN, NAN), (98.0, NAN, 99.0), (98.0, 97.0, NAN)])))
            elif tipo != "falta":
                sucias.append(barra)
            if tipo == "repetida":
                sucias.append(barra)
            elif tipo == "contraria":
                sucias.append((barra[0], *azar.choice([TOCA, (98.0, 97.5, 140.0)])))
        for _ in range(azar.randint(0, 3)):
            dia = sesiones[0] + timedelta(days=azar.randrange(60))
            if dia not in sesiones:
                sucias.append((dia, *TOCA))
        if azar.random() < 0.3:
            azar.shuffle(sucias)
        limpio, d = _sim(limpias, sesiones[:n]), _sim(sucias, sesiones[:n])
        if d.estado in (cf.STOP, cf.HORIZONTE):
            assert d == limpio and d.hasta_session is not None
            assert evaluacion._sin_huecos(market, sesiones[0], d.estado, d.hasta_session.isoformat(), d.sesiones)
            vistos.add("definitivo")
        else:
            assert not d.final or n >= ESPERA
            vistos.add(d.estado)
    assert vistos >= {"definitivo", cf.DATOS_INCOMPLETOS, cf.SIN_BARRA_DE_ENTRADA, cf.ABIERTA}


class _Proveedor:
    """Sirve las filas tal cual, con sus repeticiones y sus huecos."""

    def __init__(self, filas: Sequence[cf.Barra]) -> None:
        self.filas = filas

    def get_history(self, *_args: Any, **_kwargs: Any) -> pd.DataFrame:
        return pd.DataFrame(
            {"Open": [f[1] for f in self.filas], "Low": [f[2] for f in self.filas], "Close": [f[3] for f in self.filas]},
            index=pd.DatetimeIndex([f[0] for f in self.filas]),
        )


def _actualizar(reg: RegistroIA, filas: Sequence[cf.Barra], sesion: date) -> int:
    return cf.actualizar(
        reg.conn, _Proveedor(filas), SimpleNamespace(get=lambda _s: None), _tras(sesion), "1y", "1d", 0,
    )


def _fila(reg: RegistroIA) -> Dict[str, Any]:
    cursor = reg.conn.execute("SELECT * FROM ia_contrafactual")
    return dict(zip([c[0] for c in cursor.description], cursor.fetchone()))


def _entradas(reg: RegistroIA) -> List[Any]:
    return [tuple(f) for f in reg.conn.execute("SELECT * FROM ia_contrafactual_entrada")]


class TestActualizar:
    def test_el_hueco_espera_y_el_caso_se_salva_si_la_barra_llega(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        barras = _serie(SESIONES[:40])
        _actualizar(reg, [b for i, b in enumerate(barras) if i != 7], SESIONES[ESPERA - 2])
        fila = _fila(reg)
        assert (fila["estado"], fila["final"], fila["salida"]) == (cf.DATOS_INCOMPLETOS, 0, None)
        assert len(_entradas(reg)) == 1
        _actualizar(reg, barras, SESIONES[ESPERA - 1])
        fila = _fila(reg)
        assert (fila["estado"], fila["final"], fila["sesiones"]) == (cf.HORIZONTE, 1, H)
        assert fila["hasta_session"] == SESIONES[H - 1].isoformat()

    def test_pasada_la_espera_es_definitivo_y_ya_no_cambia(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        barras = _serie(SESIONES[:40])
        _actualizar(reg, [b for i, b in enumerate(barras) if i != 7], SESIONES[ESPERA - 1])
        antes = _fila(reg)
        assert (antes["estado"], antes["final"]) == (cf.DATOS_INCOMPLETOS, 1)
        assert _actualizar(reg, barras, SESIONES[ESPERA]) == 0 and _fila(reg) == antes

    @pytest.mark.parametrize("entra", [[(NAN, NAN, NAN)], [], [SANA, (103.0, 102.0, 104.0)]])
    def test_sin_apertura_fiable_no_se_escribe_la_entrada(self, tmp_path: Path, entra: List[Fila]) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        barras = _serie(SESIONES[:10])
        _actualizar(reg, [*((SESIONES[0], *f) for f in entra), *barras[1:]], SESIONES[9])
        assert _fila(reg)["estado"] == cf.SIN_BARRA_DE_ENTRADA and _fila(reg)["final"] == 0 and _entradas(reg) == []
        assert madurez.contar(reg.conn, _tras(SESIONES[9])).sin_resolver == 1
        _actualizar(reg, barras, SESIONES[9])
        assert _entradas(reg)[0][1] == 1 and _fila(reg)["estado"] == cf.ABIERTA

    @pytest.mark.parametrize("estado", [cf.STOP, cf.HORIZONTE, cf.NO_EJECUTABLE, cf.SIN_BARRA_DE_ENTRADA, cf.SPLIT_POSTERIOR])
    @pytest.mark.parametrize("cuando", [madurez.CORTE - timedelta(days=3), madurez.CORTE + timedelta(hours=5)])
    def test_lo_definitivo_y_las_entradas_no_se_tocan(self, tmp_path: Path, estado: str, cuando: datetime) -> None:
        """También lo que la regla nueva resolvería de otra forma: no se recalcula nada histórico."""

        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=0, cuando=cuando)
        reg.conn.execute(
            "INSERT INTO ia_contrafactual VALUES (1, 'A', 'COMPRAR', ?, ?, 'g', 1, 2, 3, '2026-12-01', 4, 5, 6, 1, 'antes')",
            (SESIONES[0].isoformat(), estado),
        )
        antes, entradas = _fila(reg), _entradas(reg)
        assert _actualizar(reg, _serie(SESIONES[:40]), SESIONES[39]) == 0
        # Sin su entrada se completa, como hasta ahora, y el desenlace sigue igual.
        reg.conn.execute("DELETE FROM ia_contrafactual_entrada")
        assert _actualizar(reg, _serie(SESIONES[:40]), SESIONES[39]) == 0
        assert _fila(reg) == antes and entradas[0][1] == 0 and _entradas(reg)[0][1] == 1

    @pytest.mark.parametrize("segundos,nueva", [(-1, False), (0, True), (0.5, True)])
    @pytest.mark.parametrize("averia", ["hueco", "duplicada", "ajena"])
    def test_las_anteriores_al_corte_siguen_con_su_regla(
        self, tmp_path: Path, averia: str, segundos: float, nueva: bool,
    ) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None, cuando=madurez.CORTE + timedelta(seconds=segundos))
        barras = _serie(SESIONES[:24])
        if averia == "hueco":
            sucias = [b for i, b in enumerate(barras) if i != 7]
        elif averia == "duplicada":
            sucias = [*barras[:8], *barras[7:]]
        else:
            sabado = next(s for s in SESIONES if s.weekday() == 4) + timedelta(days=1)
            sucias = sorted([*barras, (sabado, *SANA)])
        _actualizar(reg, sucias, SESIONES[23])
        fila = _fila(reg)
        if not nueva:
            viejo = cf.simular(NIVELES, sucias, SESIONES[0])
            assert (fila["estado"], fila["hasta_session"]) == (viejo.estado, str(viejo.hasta_session))
            assert fila["hasta_session"] == SESIONES[H if averia == "hueco" else H - 2].isoformat() and fila["final"] == 1
        elif averia == "hueco":
            assert (fila["estado"], fila["final"]) == (cf.DATOS_INCOMPLETOS, 0)
        else:
            assert (fila["estado"], fila["hasta_session"]) == (cf.HORIZONTE, SESIONES[H - 1].isoformat())

    def test_el_corte_es_el_mismo_que_cuenta_la_madurez(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None, cuando=madurez.CORTE - timedelta(seconds=1))
        _actualizar(reg, _serie(SESIONES[:3]), SESIONES[2])
        assert len(_entradas(reg)) == 1
        assert madurez.contar(reg.conn, _tras(SESIONES[2])).aprobadas == madurez.GrupoMadurez(0, 0, 0, 0)

    def test_el_dia_de_la_objetivo_sin_cerrar_sigue_pendiente(self, tmp_path: Path) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        antes_del_cierre = datetime.combine(SESIONES[0], datetime.min.time(), timezone.utc) + timedelta(hours=12)
        cf.actualizar(
            reg.conn, _Proveedor([(SESIONES[0], *TOCA)]), SimpleNamespace(get=lambda _s: None), antes_del_cierre,
            "1y", "1d", 20,
        )
        assert _fila(reg)["estado"] == cf.PENDIENTE and _entradas(reg) == []

    def test_sin_saber_que_sesiones_han_cerrado_no_se_escribe_nada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reg = _base(tmp_path)
        _decision(reg, "A", SESIONES[0], ejecutable=None)
        monkeypatch.setattr(cf, "latest_expected_closed_session", lambda *_a, **_k: None)
        assert _actualizar(reg, _serie(SESIONES[:10]), SESIONES[9]) == 0
        assert reg.conn.execute("SELECT COUNT(*) FROM ia_contrafactual").fetchone()[0] == 0 and _entradas(reg) == []


def test_la_espera_es_la_del_evaluador() -> None:
    assert ESPERA == evaluacion.SESIONES_DE_ESPERA
