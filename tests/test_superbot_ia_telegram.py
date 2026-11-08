"""Avisos de Telegram de Superbot IA: solo operaciones realmente ejecutadas (incluidos los
stops), nunca una decisión del comité todavía sin ejecutar ni un activo descartado; sin
duplicados; recuperación frente a un fallo de envío; resumen periódico acotado en el tiempo.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

from superbot.ia import telegram
from superbot.ia.cartera import RECLAMO_NOTIFICACION_EXPIRA, CarteraIA
from superbot.ia.pasada import ResultadoPasada
from tests.test_superbot_ia import APERTURA, ClienteFalso, _analisis, _pasada, compra_ok, registro
from tests.test_superbot_ia_cartera import _abrir, _cartera, _proveedor_ohlc
from tests.test_superbot_ia_fase2 import SESION_OBJETIVO

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


class _NotifierFalso:
    def __init__(self, enabled: bool = True, falla: bool = False) -> None:
        self.enabled = enabled
        self.falla = falla
        self.enviados: List[str] = []
        self.bot_token: str | None = None
        self.chat_id: str | None = None

    def send_message(self, texto: str) -> bool:
        if self.falla:
            return False
        self.enviados.append(texto)
        return True

    def send_long_message(self, texto: str) -> bool:
        if self.falla:
            return False
        self.enviados.append(texto)
        return True


class TestEncolarResumenPasada:
    def test_sin_ninguna_operacion_real_no_encola_nada(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        resultado = ResultadoPasada(pasada_id=1, status="OK")  # compras/ventas decididas, nada ejecutado
        resultado.compras.append("A")  # el comité decidió, pero no es una ejecución real
        resultado.ventas.append("B")

        encolado = telegram.encolar_resumen_pasada(cartera_ia, resultado)

        assert encolado is False
        assert cartera_ia.notificaciones_pendientes() == ()

    def test_una_compra_ejecutada_encola_un_aviso_con_los_datos_de_la_posicion(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=90.0)
        resultado = ResultadoPasada(pasada_id=1, status="OK")
        resultado.aperturas.append("A")

        encolado = telegram.encolar_resumen_pasada(cartera_ia, resultado)

        assert encolado is True
        pendientes = cartera_ia.notificaciones_pendientes()
        assert len(pendientes) == 1 and pendientes[0]["tipo"] == "OPERACIONES"
        assert "COMPRA ejecutada" in pendientes[0]["texto"]
        assert "A" in pendientes[0]["texto"]
        assert "1.000,00 EUR" in pendientes[0]["texto"]  # coste: 10 x 100

    def test_una_venta_por_stop_encola_el_resultado_de_la_operacion(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=90.0, exit_price_eur=90.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="STOP_TOCADO",
        )  # -100 EUR
        resultado = ResultadoPasada(pasada_id=1, status="OK")
        resultado.cerradas_stop.append("A")

        telegram.encolar_resumen_pasada(cartera_ia, resultado)

        texto = cartera_ia.notificaciones_pendientes()[0]["texto"]
        assert "VENTA ejecutada" in texto and "STOP obligatorio" in texto
        assert "-100,00 EUR" in texto

    def test_una_venta_de_la_ia_se_distingue_del_stop(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=110.0, exit_price_eur=110.0, exit_session=SESION_OBJETIVO,
            origen="DECISION_IA", motivo="CIERRE_BAJO_SMA",
        )
        resultado = ResultadoPasada(pasada_id=1, status="OK")
        resultado.salidas_ia.append("A")

        telegram.encolar_resumen_pasada(cartera_ia, resultado)

        texto = cartera_ia.notificaciones_pendientes()[0]["texto"]
        assert "venta de la IA" in texto

    def test_una_compra_cerrada_en_la_misma_pasada_sigue_notificando_la_compra(self, tmp_path: Path) -> None:
        """Hallazgo de Codex: una posición que abre y toca el stop dentro de la MISMA llamada a
        ``procesar_pendientes`` ya no está ``ABIERTA`` cuando se construye el aviso — el bloque de
        COMPRA debe seguir mostrándose, con los datos de la entrada ya cerrada."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0, stop=90.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=85.0, exit_price_eur=85.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="GAP_BAJO_STOP",
        )  # ya CERRADA antes de construir el aviso, como si hubiera pasado en la misma llamada
        resultado = ResultadoPasada(pasada_id=1, status="OK")
        resultado.aperturas.append("A")
        resultado.cerradas_stop.append("A")

        telegram.encolar_resumen_pasada(cartera_ia, resultado)

        texto = cartera_ia.notificaciones_pendientes()[0]["texto"]
        assert "COMPRA ejecutada" in texto and "1.000,00 EUR" in texto  # coste de la entrada: 10 x 100
        assert "VENTA ejecutada" in texto and "-150,00 EUR" in texto  # 850 - 1.000

    def test_una_venta_no_se_pierde_aunque_otros_200_cierres_sean_mas_recientes(self, tmp_path: Path) -> None:
        """Hallazgo de Codex: el límite global de ``posiciones_cerradas`` podía dejar fuera el
        cierre real de un símbolo si otros 200 símbolos se habían cerrado más tarde."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 50_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=1.0, entry_session=date(2026, 11, 2))
        posicion_a = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion_a, exit_price=110.0, exit_price_eur=110.0, exit_session=date(2026, 11, 3),
            origen="STOP_OBLIGATORIO", motivo="m",
        )
        # 200 cierres de otros símbolos, todos con exit_session POSTERIOR al de A.
        for n in range(200):
            simbolo = f"X{n}"
            _abrir(cartera_ia, symbol=simbolo, entry_price=10.0, units=1.0, entry_session=date(2026, 11, 2))
            posicion = next(p for p in cartera_ia.posiciones_abiertas() if p.symbol == simbolo)
            cartera_ia.cerrar_posicion(
                posicion, exit_price=10.0, exit_price_eur=10.0, exit_session=date(2026, 11, 10),
                origen="STOP_OBLIGATORIO", motivo="m",
            )
        resultado = ResultadoPasada(pasada_id=1, status="OK")
        resultado.cerradas_stop.append("A")

        encolado = telegram.encolar_resumen_pasada(cartera_ia, resultado)

        assert encolado is True
        texto = cartera_ia.notificaciones_pendientes()[0]["texto"]
        assert "VENTA ejecutada" in texto and "+10,00 EUR" in texto  # la de A, no la de un X cualquiera

    def test_repetir_la_misma_pasada_nunca_duplica_el_aviso(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        resultado = ResultadoPasada(pasada_id=7, status="OK")
        resultado.aperturas.append("A")

        primero = telegram.encolar_resumen_pasada(cartera_ia, resultado)
        segundo = telegram.encolar_resumen_pasada(cartera_ia, resultado)

        assert primero is True and segundo is False
        assert len(cartera_ia.notificaciones_pendientes()) == 1

    def test_un_simbolo_sin_posicion_real_no_rompe_el_encolado(self, tmp_path: Path) -> None:
        """Defensa en profundidad: si por cualquier motivo la posición ya no estuviera donde se
        espera, no debe lanzar una excepción ni bloquear el resto de la pasada."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        resultado = ResultadoPasada(pasada_id=1, status="OK")
        resultado.aperturas.append("FANTASMA")  # no existe ninguna posición con ese símbolo

        encolado = telegram.encolar_resumen_pasada(cartera_ia, resultado)

        assert encolado is False  # ningún bloque real que avisar
        assert cartera_ia.notificaciones_pendientes() == ()


class TestEncolarErrorPasada:
    def test_solo_encola_si_la_pasada_entera_fallo(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        resultado_ok = ResultadoPasada(pasada_id=1, status="OK", incidencias=["A: sin tipo de cambio todavía"])

        assert telegram.encolar_error_pasada(cartera_ia, resultado_ok) is False
        assert cartera_ia.notificaciones_pendientes() == ()

    def test_un_error_de_pasada_si_se_notifica(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        resultado = ResultadoPasada(pasada_id=1, status="ERROR", incidencias=["contexto: TimeoutError: x"])

        encolado = telegram.encolar_error_pasada(cartera_ia, resultado)

        assert encolado is True
        texto = cartera_ia.notificaciones_pendientes()[0]["texto"]
        assert "ERROR" in texto and "TimeoutError" in texto


class TestEncolarResumenPeriodico:
    def test_sin_cartera_activa_no_encola(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        assert telegram.encolar_resumen_periodico(cartera_ia, T_ACTIVACION) is False

    def test_el_primero_se_encola_los_siguientes_dentro_del_intervalo_no(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        primero = telegram.encolar_resumen_periodico(cartera_ia, T_ACTIVACION)
        pronto = telegram.encolar_resumen_periodico(cartera_ia, T_ACTIVACION + timedelta(hours=1))

        assert primero is True and pronto is False
        assert len(cartera_ia.notificaciones_pendientes()) == 1

    def test_pasado_el_intervalo_se_encola_otro(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        telegram.encolar_resumen_periodico(cartera_ia, T_ACTIVACION)

        despues = telegram.encolar_resumen_periodico(cartera_ia, T_ACTIVACION + timedelta(days=2))

        assert despues is True
        assert len(cartera_ia.notificaciones_pendientes()) == 2

    def test_el_resumen_incluye_capital_y_posiciones(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)

        telegram.encolar_resumen_periodico(cartera_ia, T_ACTIVACION)

        texto = cartera_ia.notificaciones_pendientes()[0]["texto"]
        assert "RESUMEN DE CARTERA" in texto and "A" in texto


class TestReclamarNotificacion:
    def test_dos_flush_concurrentes_nunca_envian_el_mismo_aviso_dos_veces(self, tmp_path: Path) -> None:
        """Hallazgo de Codex: sin una reclamación atómica, dos ``flush()`` a la vez podían leer la
        misma notificación pendiente y enviarla ambos."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.encolar_notificacion(clave="x", tipo="ERROR", texto="hola")
        notificacion_id = cartera_ia.notificaciones_pendientes()[0]["id"]

        primera_reclamacion = cartera_ia.reclamar_notificacion(notificacion_id)
        segunda_reclamacion = cartera_ia.reclamar_notificacion(notificacion_id)  # "otro flush()" a la vez

        assert primera_reclamacion is True and segunda_reclamacion is False
        # Mientras está ENVIANDO, tampoco vuelve a aparecer como pendiente para un tercer flush().
        assert cartera_ia.notificaciones_pendientes() == ()


class TestFlush:
    def test_envia_lo_pendiente_y_lo_marca_enviada(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.encolar_notificacion(clave="x", tipo="ERROR", texto="hola")
        notifier = _NotifierFalso()

        contadores = telegram.flush(cartera_ia, notifier)

        assert contadores == {"ENVIADA": 1, "FALLIDA": 0, "SIN_CONFIGURAR": 0}
        assert notifier.enviados == ["hola"]
        assert cartera_ia.notificaciones_pendientes() == ()  # ya no vuelve a aparecer

    def test_un_fallo_de_envio_queda_pendiente_de_reintento(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.encolar_notificacion(clave="x", tipo="ERROR", texto="hola")

        contadores_1 = telegram.flush(cartera_ia, _NotifierFalso(falla=True))
        assert contadores_1 == {"ENVIADA": 0, "FALLIDA": 1, "SIN_CONFIGURAR": 0}
        assert len(cartera_ia.notificaciones_pendientes()) == 1  # sigue pendiente de reintento

        contadores_2 = telegram.flush(cartera_ia, _NotifierFalso(falla=False))
        assert contadores_2 == {"ENVIADA": 1, "FALLIDA": 0, "SIN_CONFIGURAR": 0}
        assert cartera_ia.notificaciones_pendientes() == ()

    def test_sin_telegram_configurado_no_se_marca_como_enviada(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.encolar_notificacion(clave="x", tipo="ERROR", texto="hola")

        contadores = telegram.flush(cartera_ia, _NotifierFalso(enabled=False))

        assert contadores == {"ENVIADA": 0, "FALLIDA": 0, "SIN_CONFIGURAR": 1}
        assert len(cartera_ia.notificaciones_pendientes()) == 1  # sigue ahí, listo en cuanto se configure


class TestIntegracionConLaPasada:
    def test_un_descarte_nunca_genera_ningun_aviso(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pedido explícito del propietario: nunca un mensaje por cada activo descartado."""

        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        candidata = _analisis("B", score=72.0)
        rechazo = {
            "decision": "DESCARTAR", "prioridad": "ALTA", "motivos": ["No cumple el riesgo"],
            "riesgos": ["Volatilidad alta"], "datos_citados": ["tecnico.rsi"],
        }
        cliente = ClienteFalso(por_defecto=rechazo)

        _pasada(tmp_path, monkeypatch, [candidata], cliente, cartera_ia=cartera_ia, registro_existente=reg)

        # El primer resumen periódico SÍ se encola (es la primera pasada tras activar): lo que
        # nunca debe aparecer es un aviso de OPERACIONES por un simple descarte.
        assert not any(n["tipo"] == "OPERACIONES" for n in cartera_ia.notificaciones_pendientes())

    def test_un_stop_ejecutado_durante_la_pasada_queda_encolado_para_telegram(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", stop=90.0, entry_price=100.0, units=10.0, entry_session=APERTURA.date() - timedelta(days=3))
        proveedor = _proveedor_ohlc({"A": {(APERTURA.date() - timedelta(days=1)): (85.0, 80.0, 86.0)}})
        cliente = ClienteFalso(respuestas=[Exception("no debería llamarse")])

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [], cliente, cartera_ia=cartera_ia, registro_existente=reg, proveedor=proveedor,
        )

        assert resultado.cerradas_stop == ["A"]
        operaciones = [n for n in cartera_ia.notificaciones_pendientes() if n["tipo"] == "OPERACIONES"]
        assert len(operaciones) == 1
        assert "VENTA ejecutada" in operaciones[0]["texto"] and "A" in operaciones[0]["texto"]

    def test_un_descarte_junto_a_una_compra_real_no_menciona_el_descarte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)  # ya hay una compra ejecutada
        candidata = _analisis("B", score=72.0)
        cliente = ClienteFalso(por_defecto=compra_ok(decision="DESCARTAR", prioridad="BAJA"))

        resultado, _reg2 = _pasada(
            tmp_path, monkeypatch, [candidata], cliente, cartera_ia=cartera_ia, registro_existente=reg,
            proveedor=_proveedor_ohlc({}),
        )

        assert resultado.compras == []
        # No hay ninguna apertura/cierre NUEVO en esta pasada (A se abrió fuera de ella, a mano):
        # ningún aviso de "OPERACIONES" para esta pasada en concreto.
        assert not any(
            n["clave"] == f"pasada:{resultado.pasada_id}" for n in cartera_ia.notificaciones_pendientes()
        )


class TestReclamoAbandonadoSeRecupera:
    """Segundo hallazgo de Codex: sin caducidad, un reclamo (``ENVIANDO``) de un proceso que
    muere antes de resolverlo perdía el aviso para siempre — ningún ``flush()`` posterior lo
    recuperaba, porque ``notificaciones_pendientes()`` nunca devolvía un ``ENVIANDO``."""

    def test_un_reclamo_reciente_no_se_ofrece_de_nuevo(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.encolar_notificacion(clave="x", tipo="ERROR", texto="hola")
        notificacion_id = cartera_ia.notificaciones_pendientes()[0]["id"]
        cartera_ia.reclamar_notificacion(notificacion_id)

        assert cartera_ia.notificaciones_pendientes() == ()
        assert cartera_ia.reclamar_notificacion(notificacion_id) is False  # todavía vigente

    def test_un_reclamo_caducado_vuelve_a_ofrecerse_y_puede_reclamarse_otra_vez(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        cartera_ia.encolar_notificacion(clave="x", tipo="ERROR", texto="hola")
        notificacion_id = cartera_ia.notificaciones_pendientes()[0]["id"]
        cartera_ia.reclamar_notificacion(notificacion_id)
        # Simula un reclamo abandonado: lo retrasamos más allá de la caducidad, directamente en SQL
        # (sin esperar de verdad el intervalo real en la prueba).
        hace_mucho = (datetime.now(timezone.utc) - RECLAMO_NOTIFICACION_EXPIRA - timedelta(minutes=1)).isoformat()
        cartera_ia.conn.execute(
            "UPDATE ia_notificacion SET reclamado_en = ? WHERE id = ?", (hace_mucho, notificacion_id)
        )

        pendientes = cartera_ia.notificaciones_pendientes()

        assert len(pendientes) == 1 and pendientes[0]["id"] == notificacion_id
        assert cartera_ia.reclamar_notificacion(notificacion_id) is True  # se puede reclamar de nuevo


class TestMigracionDeLaTablaDeNotificaciones:
    def test_una_base_con_el_check_antiguo_se_migra_conservando_sus_filas(self, tmp_path: Path) -> None:
        """Hallazgo de Codex: una ``ia_notificacion`` creada antes de añadir 'ENVIANDO' al CHECK
        no se actualiza sola (``CREATE TABLE IF NOT EXISTS`` no toca una tabla ya existente)."""

        reg = registro(tmp_path)
        reg.conn.executescript("""
            CREATE TABLE ia_notificacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL CHECK (tipo IN ('OPERACIONES', 'ERROR', 'RESUMEN')),
                texto TEXT NOT NULL,
                estado TEXT NOT NULL CHECK (estado IN ('PENDIENTE', 'ENVIADA', 'FALLIDA')),
                created_at TEXT NOT NULL,
                enviado_at TEXT
            );
        """)
        reg.conn.execute(
            "INSERT INTO ia_notificacion (clave, tipo, texto, estado, created_at) "
            "VALUES ('vieja', 'ERROR', 'un aviso de antes', 'PENDIENTE', '2026-11-01T00:00:00+00:00')"
        )
        reg.conn.commit()

        cartera_ia = CarteraIA(reg.conn)

        filas = cartera_ia.conn.execute("SELECT * FROM ia_notificacion").fetchall()
        assert len(filas) == 1 and filas[0]["clave"] == "vieja" and filas[0]["texto"] == "un aviso de antes"
        assert cartera_ia.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'ia_notificacion_v1'"
        ).fetchone() is None
        # El CHECK ya admite ENVIANDO: reclamar la fila migrada funciona sin IntegrityError.
        assert cartera_ia.reclamar_notificacion(filas[0]["id"]) is True

    def test_un_esquema_intermedio_con_envianda_pero_sin_columna_tambien_se_repara(self, tmp_path: Path) -> None:
        """Segunda ronda de Codex: una ``ia_notificacion`` cuyo CHECK ya admitía 'ENVIANDO' pero
        sin la columna ``reclamado_en`` no la detectaba la migración completa (que solo mira el
        CHECK) y ``notificaciones_pendientes()`` fallaba con ``OperationalError``. Además, una
        fila YA ``ENVIANDO`` en ese esquema intermedio debe quedar inmediatamente recuperable, no
        con ``reclamado_en`` nulo para siempre."""

        reg = registro(tmp_path)
        reg.conn.executescript("""
            CREATE TABLE ia_notificacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clave TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL CHECK (tipo IN ('OPERACIONES', 'ERROR', 'RESUMEN')),
                texto TEXT NOT NULL,
                estado TEXT NOT NULL CHECK (estado IN ('PENDIENTE', 'ENVIANDO', 'ENVIADA', 'FALLIDA')),
                created_at TEXT NOT NULL,
                enviado_at TEXT
            );
        """)
        reg.conn.execute(
            "INSERT INTO ia_notificacion (clave, tipo, texto, estado, created_at) "
            "VALUES ('atascada', 'ERROR', 'ya reclamada antes de la columna', 'ENVIANDO', '2026-11-01T00:00:00+00:00')"
        )
        reg.conn.commit()

        cartera_ia = CarteraIA(reg.conn)  # no debe lanzar OperationalError

        # Recuperable de inmediato: su reclamo, de antes de que existiera la columna, se trata
        # como ya caducado, no como "nunca caduca".
        pendientes = cartera_ia.notificaciones_pendientes()
        assert len(pendientes) == 1 and pendientes[0]["clave"] == "atascada"
        assert cartera_ia.reclamar_notificacion(pendientes[0]["id"]) is True

    def test_reabrir_una_base_ya_migrada_es_idempotente(self, tmp_path: Path) -> None:
        reg = registro(tmp_path)
        CarteraIA(reg.conn)  # crea el esquema actual directamente, sin nada que migrar

        cartera_otra_vez = CarteraIA(reg.conn)  # como si se reabriera el proceso

        assert cartera_otra_vez.conn.execute("SELECT COUNT(*) FROM ia_notificacion").fetchone()[0] == 0


class _RespuestaFalsa:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class TestAtenderComandos:
    """``/dashboard`` responde con la URL, solo al chat configurado, sin reprocesar mensajes."""

    def test_sin_telegram_configurado_no_hace_ninguna_peticion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reg = registro(tmp_path)
        llamado = False

        def _get(*args: object, **kwargs: object) -> _RespuestaFalsa:
            nonlocal llamado
            llamado = True
            return _RespuestaFalsa({"ok": True, "result": []})

        monkeypatch.setattr(telegram.requests, "get", _get)
        notifier = _NotifierFalso(enabled=False)

        assert telegram.atender_comandos(reg, notifier, "http://192.168.1.113:8766") == 0
        assert llamado is False

    def test_comando_dashboard_del_chat_configurado_responde_con_la_url(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reg = registro(tmp_path)
        notifier = _NotifierFalso()
        notifier.bot_token = "token-falso"
        notifier.chat_id = "5502578663"

        def _get(*args: object, **kwargs: object) -> _RespuestaFalsa:
            return _RespuestaFalsa({
                "ok": True,
                "result": [{
                    "update_id": 10,
                    "message": {"chat": {"id": 5502578663}, "text": "/dashboard"},
                }],
            })

        monkeypatch.setattr(telegram.requests, "get", _get)

        enviados = telegram.atender_comandos(reg, notifier, "http://192.168.1.113:8766")

        assert enviados == 1
        assert notifier.enviados == ["Dashboard de Superbot IA: http://192.168.1.113:8766"]
        assert telegram._offset_guardado(reg) == 11  # nunca reprocesa este update_id

    def test_mensaje_de_otro_chat_se_ignora_sin_responder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        reg = registro(tmp_path)
        notifier = _NotifierFalso()
        notifier.bot_token = "token-falso"
        notifier.chat_id = "5502578663"

        def _get(*args: object, **kwargs: object) -> _RespuestaFalsa:
            return _RespuestaFalsa({
                "ok": True,
                "result": [{
                    "update_id": 20,
                    "message": {"chat": {"id": 999999}, "text": "/dashboard"},
                }],
            })

        monkeypatch.setattr(telegram.requests, "get", _get)

        assert telegram.atender_comandos(reg, notifier, "http://192.168.1.113:8766") == 0
        assert notifier.enviados == []
        assert telegram._offset_guardado(reg) == 21  # el update se consume igual, nunca se reintenta

    def test_un_fallo_de_red_no_lanza_y_devuelve_cero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import requests as requests_mod

        reg = registro(tmp_path)
        notifier = _NotifierFalso()
        notifier.bot_token = "token-falso"
        notifier.chat_id = "5502578663"

        def _get(*args: object, **kwargs: object) -> _RespuestaFalsa:
            raise requests_mod.RequestException("sin red")

        monkeypatch.setattr(telegram.requests, "get", _get)

        assert telegram.atender_comandos(reg, notifier, "http://192.168.1.113:8766") == 0
