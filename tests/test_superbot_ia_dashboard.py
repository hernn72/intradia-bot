"""Dashboard de Superbot IA: resumen de capital, renderizado HTML, autenticación y acciones
administrativas (aportar, retirar, reiniciar) por fuera de cualquier servidor HTTP real."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from superbot.ia.cartera import CarteraIA
from superbot.ia.dashboard import (
    ACTOR_SIN_AUTENTICAR,
    CLAVE_ENV,
    USUARIO_ENV,
    _accion_aportar,
    _accion_reiniciar,
    _accion_retirar,
    _autenticado,
    build_stats,
    render_html,
)
from tests.test_superbot_ia_cartera import _abrir, _cartera
from tests.test_superbot_ia_fase2 import SESION_OBJETIVO

T_ACTIVACION = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


class TestBuildStats:
    def test_cartera_inactiva(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        assert build_stats(cartera_ia) == {"activa": False}

    def test_cartera_activa_vacia(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        stats = build_stats(cartera_ia)

        assert stats["activa"] is True
        assert stats["capital_inicial_eur"] == pytest.approx(10_000.0)
        assert stats["cash_eur"] == pytest.approx(10_000.0)
        assert stats["equity_contable_eur"] == pytest.approx(10_000.0)
        assert stats["rentabilidad_contable_pct"] == pytest.approx(0.0)
        assert stats["num_abiertas"] == 0 and stats["num_cerradas"] == 0

    def test_con_posiciones_abiertas_y_cerradas(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)  # 1.000 EUR de coste
        _abrir(cartera_ia, symbol="B", entry_price=50.0, units=4.0)  # 200 EUR de coste
        posicion_b = next(p for p in cartera_ia.posiciones_abiertas() if p.symbol == "B")
        cartera_ia.cerrar_posicion(
            posicion_b, exit_price=60.0, exit_price_eur=60.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="STOP_TOCADO",
        )

        stats = build_stats(cartera_ia)

        assert stats["num_abiertas"] == 1 and stats["num_cerradas"] == 1
        assert stats["coste_abierto_eur"] == pytest.approx(1_000.0)  # solo A, B ya cerrada
        # Caja: 10.000 - 1.000 (A) - 200 (B) + 240 (venta de B a 60 x 4) = 9.040.
        assert stats["cash_eur"] == pytest.approx(9_040.0)
        assert stats["equity_contable_eur"] == pytest.approx(9_040.0 + 1_000.0)
        assert stats["pnl_realizado_eur"] == pytest.approx(40.0)  # 240 - 200

    def test_una_aportacion_nunca_se_muestra_como_rentabilidad(self, tmp_path: Path) -> None:
        """Hallazgo de Codex: antes, la rentabilidad se medía contra ``capital_inicial_eur`` a
        secas; una aportación posterior a la activación inflaba la equity sin inflar esa base,
        pareciendo una ganancia del 50 % que nunca existió."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        cartera_ia.aportar(importe_eur=5_000.0, motivo="refuerzo", actor="propietario")
        stats = build_stats(cartera_ia)
        assert stats["capital_neto_aportado_eur"] == pytest.approx(15_000.0)
        assert stats["equity_contable_eur"] == pytest.approx(15_000.0)
        assert stats["rentabilidad_contable_pct"] == pytest.approx(0.0)  # no un +50 %

        cartera_ia.retirar(importe_eur=3_000.0, motivo="viaje", actor="propietario")
        stats = build_stats(cartera_ia)
        assert stats["capital_neto_aportado_eur"] == pytest.approx(12_000.0)
        assert stats["rentabilidad_contable_pct"] == pytest.approx(0.0)  # tampoco una pérdida

    def test_una_ganancia_real_si_se_refleja_en_la_rentabilidad(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 1_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=1.0)  # 100 EUR de coste
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=150.0, exit_price_eur=150.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="m",
        )  # +50 EUR reales

        stats = build_stats(cartera_ia)

        assert stats["capital_neto_aportado_eur"] == pytest.approx(1_000.0)  # sin aportar/retirar
        assert stats["equity_contable_eur"] == pytest.approx(1_050.0)
        assert stats["rentabilidad_contable_pct"] == pytest.approx(0.05)

    def test_la_rentabilidad_no_cambia_con_flujos_de_capital_posteriores_a_una_ganancia(
        self, tmp_path: Path,
    ) -> None:
        """Segundo hallazgo de Codex: dividir por ``capital_neto_aportado_eur`` (que SÍ cambia con
        cada flujo) seguía haciendo que la misma ganancia de 50 EUR pareciera 5 %, luego 2,5 % al
        aportar 1.000, luego 10 % al retirar 1.500 — sin que el P&L real cambiara en ningún
        momento. Dividiendo por ``capital_inicial_eur`` (fijo, nunca lo tocan aportar/retirar),
        el porcentaje debe permanecer exactamente igual durante toda la secuencia."""

        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 1_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=1.0)
        posicion = cartera_ia.posiciones_abiertas()[0]
        cartera_ia.cerrar_posicion(
            posicion, exit_price=150.0, exit_price_eur=150.0, exit_session=SESION_OBJETIVO,
            origen="STOP_OBLIGATORIO", motivo="m",
        )  # +50 EUR reales, sobre 1.000 -> 5 %
        assert build_stats(cartera_ia)["rentabilidad_contable_pct"] == pytest.approx(0.05)

        cartera_ia.aportar(importe_eur=1_000.0, motivo="refuerzo", actor="propietario")
        assert build_stats(cartera_ia)["rentabilidad_contable_pct"] == pytest.approx(0.05)  # sigue 5 %

        cartera_ia.retirar(importe_eur=1_500.0, motivo="retirada", actor="propietario")
        assert build_stats(cartera_ia)["rentabilidad_contable_pct"] == pytest.approx(0.05)  # sigue 5 %
        assert build_stats(cartera_ia)["pnl_realizado_eur"] == pytest.approx(50.0)  # el P&L real, intacto


class TestRenderHtml:
    def test_cartera_inactiva_no_lanza_y_lo_dice(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)

        pagina = render_html(cartera_ia, reg, "2026-11-06T12:00:00")

        assert "CARTERA INACTIVA" in pagina
        assert "<form" not in pagina  # sin cartera activa, no se ofrece ninguna acción administrativa

    def test_cartera_activa_con_datos_completos_no_lanza(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)
        _abrir(cartera_ia, symbol="A", entry_price=100.0, units=10.0)
        cartera_ia.posiciones_abiertas()[0]
        reg.conn.execute("INSERT INTO ia_paquete (input_hash, tipo, symbol, contenido) VALUES ('h','COMPRA','A','{}')")
        pasada_id = reg.abrir_pasada(T_ACTIVACION, "activo", "sha")
        votos = '{"OPORTUNIDAD": {"decision": "COMPRAR"}, "RIESGO": {"decision": "COMPRAR"}}'
        reg.guardar_decision(
            clave="A|2026-11-05|2026-11-06|x", pasada_id=pasada_id, symbol="A", market="NYSE", tipo="COMPRA",
            signal_session="2026-11-05", target_session="2026-11-06", target_open=SESION_OBJETIVO.isoformat(),
            decision_ts=T_ACTIVACION.isoformat(), input_hash="h", cuantitativo="{}", votos=votos, predicados=None,
            resolucion="COMPRAR", motivo="APROBADA_POR_AMBOS", prioridad="ALTA", causa=None,
        )
        cartera_ia.reiniciar_cartera(capital_inicial_eur=5_000.0, motivo="prueba", actor="test", instante=T_ACTIVACION)

        pagina = render_html(cartera_ia, reg, "2026-11-06T12:00:00")

        assert "SUPERBOT IA" in pagina
        assert "A" in pagina  # el símbolo aparece en alguna tabla
        assert "OPORTUNIDAD: COMPRAR" in pagina  # hallazgo de Codex: los votos, no solo la resolución
        assert "RIESGO: COMPRAR" in pagina
        # Solo la acción y la clase, no el atributo onsubmit completo (hallazgo de Codex de la
        # confirmación del navegador añadida junto con el acceso sin autenticación en LAN).
        assert 'class="admin" method="post" action="/aportar"' in pagina
        assert 'class="admin" method="post" action="/retirar"' in pagina
        assert 'class="admin reiniciar" method="post" action="/reiniciar"' in pagina
        # La auditoría (reinicio, aportación inicial) aparece en el propio dashboard.
        assert "CARTERA_REINICIADA" in pagina

    def test_un_mensaje_se_muestra_escapado(self, tmp_path: Path) -> None:
        cartera_ia, reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        pagina = render_html(cartera_ia, reg, "2026-11-06T12:00:00", mensaje="<script>alert(1)</script>")

        assert "<script>" not in pagina
        assert "&lt;script&gt;" in pagina


class TestAutenticacion:
    def test_sin_credenciales_configuradas_autentica_siempre_sin_auth(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Decisión del propietario (2026-11-08): sin usuario/clave configurados, el dashboard
        queda abierto en su LAN — con o sin cabecera ``Authorization``."""

        monkeypatch.delenv(USUARIO_ENV, raising=False)
        monkeypatch.delenv(CLAVE_ENV, raising=False)
        assert _autenticado("Basic " + _b64("usuario:clave")) == ACTOR_SIN_AUTENTICAR
        assert _autenticado(None) == ACTOR_SIN_AUTENTICAR

    def test_credenciales_correctas_autentican_con_el_usuario(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USUARIO_ENV, "propietario")
        monkeypatch.setenv(CLAVE_ENV, "secreta")
        assert _autenticado("Basic " + _b64("propietario:secreta")) == "propietario"

    def test_credenciales_incorrectas_no_autentican(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USUARIO_ENV, "propietario")
        monkeypatch.setenv(CLAVE_ENV, "secreta")
        assert _autenticado("Basic " + _b64("propietario:mal")) is None

    def test_sin_cabecera_no_autentica(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USUARIO_ENV, "propietario")
        monkeypatch.setenv(CLAVE_ENV, "secreta")
        assert _autenticado(None) is None

    def test_cabecera_mal_formada_no_autentica(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USUARIO_ENV, "propietario")
        monkeypatch.setenv(CLAVE_ENV, "secreta")
        assert _autenticado("Bearer algo") is None
        assert _autenticado("Basic no-es-base64-valido!!") is None


def _b64(texto: str) -> str:
    import base64
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


class TestAccionesAdministrativas:
    def test_aportar_actualiza_caja_y_devuelve_un_mensaje(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        mensaje = _accion_aportar(cartera_ia, {"importe_eur": "500", "motivo": "refuerzo"}, "propietario")

        assert cartera_ia.cash_eur() == pytest.approx(10_500.0)
        assert "propietario" in mensaje

    def test_aportar_sin_motivo_no_hace_nada(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        with pytest.raises(ValueError):
            _accion_aportar(cartera_ia, {"importe_eur": "500", "motivo": ""}, "propietario")
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0)

    def test_retirar_actualiza_caja(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        _accion_retirar(cartera_ia, {"importe_eur": "1000", "motivo": "viaje"}, "propietario")

        assert cartera_ia.cash_eur() == pytest.approx(9_000.0)

    def test_reiniciar_sin_confirmar_no_hace_nada(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        with pytest.raises(ValueError):
            _accion_reiniciar(
                cartera_ia, {"capital_inicial_eur": "5000", "motivo": "x", "confirmar": "no"}, "propietario",
            )
        assert cartera_ia.cash_eur() == pytest.approx(10_000.0)
        assert cartera_ia.generaciones_archivadas() == ()

    def test_reiniciar_confirmado_archiva_y_activa_el_capital_nuevo(self, tmp_path: Path) -> None:
        cartera_ia, _reg = _cartera(tmp_path)
        cartera_ia.activar(T_ACTIVACION, 10_000.0)

        mensaje = _accion_reiniciar(
            cartera_ia, {"capital_inicial_eur": "5000", "motivo": "nueva estrategia", "confirmar": "SI"},
            "propietario",
        )

        assert cartera_ia.cash_eur() == pytest.approx(5_000.0)
        assert len(cartera_ia.generaciones_archivadas()) == 1
        assert "propietario" in mensaje


class TestServidorHttpReal:
    """Levanta el servidor de verdad, en un hilo, sobre un puerto efímero: las pruebas de más
    arriba ejercitan la lógica sin pasar por ``http.server``, y un fallo real (como el hallado
    manualmente: una cabecera HTTP con un carácter fuera de latin-1 tumbaba la petición entera con
    un ``UnicodeEncodeError``, sin que ninguna prueba unitaria lo viera) solo se detecta así."""

    def test_get_post_sin_auth_y_post_con_auth_responden_correctamente(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import http.client
        import socket
        import threading

        from superbot.ia import dashboard as dashboard_mod
        from superbot.ia.politica import PoliticaIA
        from superbot.ia.registro import RegistroIA

        db = tmp_path / "servidor.db"
        politica = PoliticaIA()
        reg = RegistroIA(db, politica)
        CarteraIA(reg.conn).activar(T_ACTIVACION, 10_000.0)
        reg.close()

        monkeypatch.setenv(USUARIO_ENV, "propietario")
        monkeypatch.setenv(CLAVE_ENV, "secreta123")

        with socket.socket() as sonda:  # puerto libre real, sin coordinarlo a mano
            sonda.bind(("127.0.0.1", 0))
            puerto = sonda.getsockname()[1]

        hilo = threading.Thread(
            target=dashboard_mod.serve, args=(db, politica, "127.0.0.1", puerto), daemon=True,
        )
        hilo.start()
        try:
            conexion = None
            for _ in range(50):
                try:
                    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=1)
                    conexion.request("GET", "/healthz")
                    conexion.getresponse().read()
                    break
                except (ConnectionRefusedError, OSError):
                    conexion = None
                    import time as _time
                    _time.sleep(0.05)
            assert conexion is not None, "el servidor no llegó a arrancar"

            conexion.request("GET", "/")
            respuesta = conexion.getresponse()
            assert respuesta.status == 200
            cuerpo = respuesta.read().decode("utf-8")
            assert "SUPERBOT IA" in cuerpo

            conexion.request("POST", "/aportar", body="importe_eur=100&motivo=x")
            respuesta = conexion.getresponse()
            respuesta.read()
            assert respuesta.status == 401  # nunca un crash silencioso ni una respuesta vacía
            assert respuesta.getheader("WWW-Authenticate") is not None

            import base64
            credenciales = base64.b64encode(b"propietario:secreta123").decode("ascii")
            conexion.request(
                "POST", "/aportar", body="importe_eur=100&motivo=refuerzo",
                headers={"Authorization": f"Basic {credenciales}"},
            )
            respuesta = conexion.getresponse()
            respuesta.read()
            # POST-Redirect-GET (hallazgo de Codex): nunca se responde el resultado directamente
            # sobre la URL del POST — así una recarga de la página jamás repite la aportación.
            assert respuesta.status == 303
            ubicacion = respuesta.getheader("Location")
            assert ubicacion is not None and ubicacion.startswith("/?mensaje=")

            conexion.request("GET", ubicacion)
            respuesta = conexion.getresponse()
            cuerpo = respuesta.read().decode("utf-8")
            assert respuesta.status == 200
            assert "Aportación de 100,00 EUR registrada por propietario" in cuerpo

            # Defensa CSRF (hallazgo de Codex): un ``Origin`` que no coincide con el ``Host`` de
            # destino se rechaza, aunque las credenciales sean correctas.
            conexion.request(
                "POST", "/aportar", body="importe_eur=100&motivo=cruzado",
                headers={"Authorization": f"Basic {credenciales}", "Origin": "http://atacante.ejemplo"},
            )
            respuesta = conexion.getresponse()
            respuesta.read()
            assert respuesta.status == 403
        finally:
            conexion is not None and conexion.close()

    def test_sin_credenciales_configuradas_las_acciones_admin_funcionan_sin_auth(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Decisión del propietario (2026-11-08): sin ``SUPERBOT_IA_DASHBOARD_USUARIO``/``CLAVE``
        configurados, una acción administrativa real (``/aportar``) funciona sin cabecera
        ``Authorization`` — la defensa CSRF por ``Origin`` sigue activa."""

        import http.client
        import socket
        import threading

        from superbot.ia import dashboard as dashboard_mod
        from superbot.ia.politica import PoliticaIA
        from superbot.ia.registro import RegistroIA

        db = tmp_path / "servidor_sin_auth.db"
        politica = PoliticaIA()
        reg = RegistroIA(db, politica)
        CarteraIA(reg.conn).activar(T_ACTIVACION, 10_000.0)
        reg.close()

        monkeypatch.delenv(USUARIO_ENV, raising=False)
        monkeypatch.delenv(CLAVE_ENV, raising=False)

        with socket.socket() as sonda:
            sonda.bind(("127.0.0.1", 0))
            puerto = sonda.getsockname()[1]

        hilo = threading.Thread(
            target=dashboard_mod.serve, args=(db, politica, "127.0.0.1", puerto), daemon=True,
        )
        hilo.start()
        try:
            conexion = None
            for _ in range(50):
                try:
                    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=1)
                    conexion.request("GET", "/healthz")
                    conexion.getresponse().read()
                    break
                except (ConnectionRefusedError, OSError):
                    conexion = None
                    import time as _time
                    _time.sleep(0.05)
            assert conexion is not None, "el servidor no llegó a arrancar"

            conexion.request("POST", "/aportar", body="importe_eur=100&motivo=sin-auth")
            respuesta = conexion.getresponse()
            respuesta.read()
            assert respuesta.status == 303  # nunca 401: sin credenciales configuradas, se permite

            conexion.request(
                "POST", "/aportar", body="importe_eur=100&motivo=cruzado",
                headers={"Origin": "http://atacante.ejemplo"},
            )
            respuesta = conexion.getresponse()
            respuesta.read()
            assert respuesta.status == 403  # la defensa CSRF no depende de si hay auth
        finally:
            conexion is not None and conexion.close()

    def test_un_reinicio_se_bloquea_mientras_hay_una_pasada_en_curso(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Hallazgo de Codex: un reinicio administrativo que se cruzara con una pasada activa
        podría dejar que una decisión registrada justo después del reinicio se materializara
        contra el capital de la generación nueva. El reinicio debe compartir el mismo candado
        exclusivo que ``pasada.ejecutar_pasada`` y rendirse, sin tocar nada, si lo encuentra
        ocupado — nunca intentarlo de todos modos."""

        import http.client
        import socket
        import threading

        from superbot.ia import dashboard as dashboard_mod
        from superbot.ia.politica import PoliticaIA
        from superbot.ia.registro import RegistroIA

        db = tmp_path / "servidor_reinicio.db"
        politica = PoliticaIA()
        reg = RegistroIA(db, politica)
        CarteraIA(reg.conn).activar(T_ACTIVACION, 10_000.0)

        monkeypatch.setenv(USUARIO_ENV, "propietario")
        monkeypatch.setenv(CLAVE_ENV, "secreta123")

        with socket.socket() as sonda:
            sonda.bind(("127.0.0.1", 0))
            puerto = sonda.getsockname()[1]

        hilo = threading.Thread(
            target=dashboard_mod.serve, args=(db, politica, "127.0.0.1", puerto), daemon=True,
        )
        hilo.start()
        try:
            conexion: Any = None
            for _ in range(50):
                try:
                    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=1)
                    conexion.request("GET", "/healthz")
                    conexion.getresponse().read()
                    break
                except (ConnectionRefusedError, OSError):
                    conexion = None
                    import time as _time
                    _time.sleep(0.05)
            assert conexion is not None, "el servidor no llegó a arrancar"

            import base64
            credenciales = base64.b64encode(b"propietario:secreta123").decode("ascii")
            # Simula una pasada en curso: el mismo candado exclusivo, en otra conexión al mismo
            # fichero, tal como lo tomaría un proceso ``python -m superbot.ia pasada`` real.
            with reg.exclusivo() as libre:
                assert libre
                conexion.request(
                    "POST", "/reiniciar",
                    body="capital_inicial_eur=5000&motivo=prueba&confirmar=SI",
                    headers={"Authorization": f"Basic {credenciales}"},
                )
                respuesta = conexion.getresponse()
                respuesta.read()
                ubicacion = respuesta.getheader("Location")
                assert respuesta.status == 303 and ubicacion is not None
                conexion.request("GET", ubicacion)
                respuesta = conexion.getresponse()
                cuerpo = respuesta.read().decode("utf-8")
                assert "pasada en curso" in cuerpo

            # Nada se tocó: sigue la misma generación, sin archivar, con el capital original.
            cartera_ia = CarteraIA(reg.conn)
            assert cartera_ia.generaciones_archivadas() == ()
            fila = reg.conn.execute("SELECT capital_inicial_eur FROM ia_cartera WHERE id = 1").fetchone()
            assert fila["capital_inicial_eur"] == pytest.approx(10_000.0)

            # Liberado el candado, el reinicio ya se aplica con normalidad.
            conexion.request(
                "POST", "/reiniciar", body="capital_inicial_eur=5000&motivo=prueba&confirmar=SI",
                headers={"Authorization": f"Basic {credenciales}"},
            )
            respuesta = conexion.getresponse()
            respuesta.read()
            ubicacion = respuesta.getheader("Location")
            conexion.request("GET", ubicacion)
            respuesta = conexion.getresponse()
            cuerpo = respuesta.read().decode("utf-8")
            assert "reiniciada" in cuerpo
        finally:
            conexion is not None and conexion.close()
            reg.close()
