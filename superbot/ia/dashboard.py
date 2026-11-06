"""Dashboard HTML de Superbot IA: la cartera paper real, las decisiones de los asesores y la
gestión administrativa de capital — nunca mezclado con el Superbot antiguo ni con T-024/T-025.

Mismo estilo visual que ``superbot/dashboard.py`` (autocontenido, sin dependencias de frontend),
pero leyendo ``CarteraIA``/``RegistroIA`` en vez de ``SuperbotStore``. Las acciones administrativas
(aportar, retirar, reiniciar) exigen HTTP Basic Auth; la lectura es abierta en la LAN, igual que el
dashboard existente.
"""

from __future__ import annotations

import base64
import hmac
import html
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

from superbot.ia.cartera import CarteraIA, CarteraInactiva, EfectivoInsuficiente
from superbot.ia.registro import RegistroIA

USUARIO_ENV = "SUPERBOT_IA_DASHBOARD_USUARIO"
CLAVE_ENV = "SUPERBOT_IA_DASHBOARD_CLAVE"
CONFIRMACION_REINICIO = "SI"


# --- formato ------------------------------------------------------------------------


def _text(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "N/D"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    return f"{_num(value)} EUR"


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    return f"{_num(value * 100)} %"


def _signed_class(value: Optional[float]) -> str:
    if value is None or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"


def _kpi(label: str, value: str, css_class: str = "neutral") -> str:
    return f'<div class="kpi"><span>{_text(label)}</span><strong class="{css_class}">{_text(value)}</strong></div>'


def _td(value: object, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"<td{class_attr}>{_text(value)}</td>"


def _table(headers: List[str], rows: List[List[str]], empty: str = "Sin datos") -> str:
    head = "".join(f"<th>{_text(header)}</th>" for header in headers)
    if not rows:
        return f'<table><thead><tr>{head}</tr></thead><tbody><tr><td colspan="{len(headers)}">{_text(empty)}</td></tr></tbody></table>'
    body = "".join("<tr>" + "".join(cell for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


# --- datos ---------------------------------------------------------------------


def build_stats(cartera_ia: CarteraIA) -> Dict[str, Any]:
    """Resumen de capital. Valorado a COSTE (cash + coste de entrada de lo abierto), nunca a
    mercado: este dashboard no consulta cotizaciones en vivo (evita depender de un proveedor
    externo, con su límite de peticiones, en cada carga de página). Como las posiciones abiertas
    se valoran siempre a su propio coste, aquí nunca hay P&L NO realizado: todo el resultado real
    es ``pnl_realizado_eur``.

    La rentabilidad se mide como ``pnl_realizado_eur / capital_inicial_eur`` — los dos términos son
    invariantes a cualquier ``aportar``/``retirar`` posterior a la activación (segundo hallazgo de
    Codex: dividir por el capital NETO, que SÍ cambia con cada flujo, seguía haciendo que la misma
    ganancia pareciera un porcentaje distinto según cuándo se aportara o retirase). Esto resuelve
    exactamente el caso que reprodujo (una ganancia fija, flujos de capital antes y después, sin
    ninguna operación nueva entre medias); una rentabilidad perfectamente invariante también
    cuando SÍ hay operaciones nuevas entre flujos de capital exigiría una rentabilidad ponderada
    por tiempo (TWR / Dietz modificado), que considero fuera del alcance de un panel de paper
    trading salvo que el propietario la pida explícitamente — queda como limitación conocida.
    """

    if not cartera_ia.activa():
        return {"activa": False}
    cash = cartera_ia.cash_eur()
    abiertas = cartera_ia.posiciones_abiertas()
    coste_abierto = sum(p.units * p.entry_price_eur for p in abiertas)
    equity = cash + coste_abierto
    fila = cartera_ia.conn.execute("SELECT capital_inicial_eur FROM ia_cartera WHERE id = 1").fetchone()
    capital_inicial = float(fila["capital_inicial_eur"]) if fila is not None else 0.0
    capital_neto = cartera_ia.capital_neto_aportado_eur()
    num_cerradas, realizado = cartera_ia.resumen_cerradas()
    return {
        "activa": True,
        "capital_inicial_eur": capital_inicial,
        "capital_neto_aportado_eur": capital_neto,
        "cash_eur": cash,
        "coste_abierto_eur": coste_abierto,
        "equity_contable_eur": equity,
        "rentabilidad_contable_pct": (realizado / capital_inicial) if capital_inicial else 0.0,
        "pnl_realizado_eur": realizado,
        "num_abiertas": len(abiertas),
        "num_cerradas": num_cerradas,
    }


def _posiciones_abiertas_table(cartera_ia: CarteraIA) -> str:
    body = [
        [
            _td(p.symbol), _td(p.entry_session.isoformat()), _td(_num(p.units, 4), "num"),
            _td(f"{_num(p.entry_price)} {p.currency}", "num"), _td(f"{_num(p.stop)} {p.currency}", "num"),
            _td(_eur(p.units * p.entry_price_eur), "num"),
        ]
        for p in cartera_ia.posiciones_abiertas()
    ]
    return _table(["Símbolo", "Entrada", "Unidades", "Precio entrada", "Stop vigente", "Coste EUR"], body)


def _posiciones_cerradas_table(cartera_ia: CarteraIA) -> str:
    body = []
    for p in cartera_ia.posiciones_cerradas(limite=100):
        pnl = p["pnl_eur"]
        body.append([
            _td(p["symbol"]), _td(p["entry_session"]), _td(p.get("exit_session")),
            _td(_num(p["units"], 4), "num"), _td(p.get("motivo_cierre")),
            _td(_eur(pnl), f"num {_signed_class(pnl)}"),
        ])
    return _table(["Símbolo", "Entrada", "Salida", "Unidades", "Motivo", "P&L EUR"], body)


_PROPOSITO_LABEL = {"ENTRY": "COMPRA", "EXIT_IA": "VENTA IA", "STOP": "STOP"}


def _ordenes_table(ordenes: Sequence[Mapping[str, Any]]) -> str:
    body = [
        [
            _td(o["created_at"]), _td(o["symbol"]), _td(_PROPOSITO_LABEL.get(o["proposito"], o["proposito"])),
            _td(o["origen"]), _td(o["estado"]), _td(o.get("target_session")), _td(o.get("motivo")),
        ]
        for o in ordenes
    ]
    return _table(["Creada", "Símbolo", "Tipo", "Origen", "Estado", "Sesión objetivo", "Motivo"], body)


def _fills_table(fills: Sequence[Mapping[str, Any]]) -> str:
    body = [
        [
            _td(f["session"]), _td(f["symbol"]), _td(f["lado"]), _td(_num(f["units"], 4), "num"),
            _td(f"{_num(f['precio'])} EUR", "num"), _td(_eur(f["importe_eur"]), "num"),
        ]
        for f in fills
    ]
    return _table(["Sesión", "Símbolo", "Lado", "Unidades", "Precio EUR", "Importe EUR"], body)


def _resumen_votos(votos_json: str) -> str:
    """Un resumen por asesor (decisión de su dictamen), nunca solo la resolución final del comité
    (hallazgo de Codex: "votos y resolución" pedía los dos, no uno en vez del otro)."""

    try:
        datos = json.loads(votos_json)
    except (TypeError, ValueError):
        return "—"
    if not isinstance(datos, dict) or not datos:
        return "—"
    partes = []
    for asesor in sorted(datos):
        dictamen = datos[asesor]
        if not isinstance(dictamen, dict):
            partes.append(f"{asesor}: sin dictamen")
        else:
            partes.append(f"{asesor}: {dictamen.get('decision', '?')}")
    return "; ".join(partes)


def _decisiones_table(decisiones: Sequence[Mapping[str, Any]]) -> str:
    body = [
        [
            _td(d["decision_ts"]), _td(d["symbol"]), _td(d["tipo"]), _td(_resumen_votos(d["votos"])),
            _td(d["resolucion"]), _td(d["motivo"]), _td(d.get("causa")), _td("sí" if d["aplicada"] else "no"),
        ]
        for d in decisiones
    ]
    return _table(
        ["Instante", "Símbolo", "Tipo", "Votos", "Resolución", "Motivo", "Causa", "Aplicada"], body
    )


def _pasadas_table(pasadas: Sequence[Mapping[str, Any]]) -> str:
    body = [
        [
            _td(p["started_at"]), _td(p.get("finished_at")), _td(p["modo"]), _td(p["status"]),
            _td(p.get("detail") or ""),
        ]
        for p in pasadas
    ]
    return _table(["Inicio", "Fin", "Modo", "Estado", "Detalle"], body)


def _eventos_table(eventos: Sequence[Mapping[str, Any]]) -> str:
    body = [
        [_td(e["created_at"]), _td(e["tipo"]), _td(e.get("symbol")), _td(e["payload"])]
        for e in eventos
    ]
    return _table(["Instante", "Tipo", "Símbolo", "Detalle"], body)


def _generaciones_table(cartera_ia: CarteraIA) -> str:
    body = [
        [
            _td(g["archivada_at"]), _td(g["id"]), _td(_eur(g["capital_inicial_eur"]), "num"),
            _td(_eur(g["coste_mas_cash_eur"]), "num"), _td(g.get("actor")), _td(g.get("motivo")),
        ]
        for g in cartera_ia.generaciones_archivadas()
    ]
    return _table(["Archivada", "ID", "Capital inicial", "Coste + caja final", "Actor", "Motivo"], body)


# --- página --------------------------------------------------------------------


_ESTILO = """
:root {
  color-scheme: light dark;
  --bg: #f5f7fb; --panel: #ffffff; --text: #18202f; --muted: #647084; --line: #d9e0eb;
  --red: #b42318; --green: #067647; --bad: #d92d20; --blue: #175cd3;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #101319; --panel: #171b24; --text: #edf1f7; --muted: #9aa4b2; --line: #2a3342; }
}
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
main { width: min(1280px, 100%); margin: 0 auto; padding: 24px; }
h1 { margin: 0 0 6px; font-size: clamp(1.6rem, 3vw, 2.4rem); }
h2 { margin: 0 0 14px; font-size: 1.05rem; }
.top { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 16px; flex-wrap: wrap; }
.muted { color: var(--muted); }
.banner { margin: 0 0 12px; padding: 14px 16px; border-radius: 8px; background: var(--red); color: white; font-weight: 800; letter-spacing: .02em; }
.banner.inactiva { background: #7a271a; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 18px 0; }
.kpi, section { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
.kpi { padding: 14px; min-height: 92px; }
.kpi span { display: block; color: var(--muted); font-size: .86rem; }
.kpi strong { display: block; margin-top: 10px; font-size: 1.35rem; }
section { margin-top: 16px; padding: 16px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 640px; }
th, td { padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
td.num, th.num { text-align: right; white-space: nowrap; }
.positive { color: var(--green); }
.negative { color: var(--bad); }
.neutral { color: var(--text); }
form.admin { display: flex; gap: 10px; flex-wrap: wrap; align-items: end; margin-top: 10px; }
form.admin label { display: flex; flex-direction: column; font-size: .8rem; color: var(--muted); gap: 4px; }
form.admin input { padding: 7px 9px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--text); }
form.admin button { padding: 8px 14px; border-radius: 6px; border: 1px solid var(--line); background: var(--blue); color: white; cursor: pointer; font-weight: 600; }
form.reiniciar button { background: var(--red); }
.aviso { padding: 10px; border-radius: 6px; margin-top: 10px; background: var(--line); font-size: .9rem; }
@media (max-width: 720px) { main { padding: 14px; } .top { display: block; } table { min-width: 560px; } }
"""


def render_html(cartera_ia: CarteraIA, registro: RegistroIA, now_label: str, mensaje: str = "") -> str:
    stats = build_stats(cartera_ia)
    gasto_total = registro.gasto_total()
    if not stats["activa"]:
        banner = '<div class="banner inactiva">CARTERA INACTIVA — Superbot IA no ha activado todavía ninguna cartera paper</div>'
        kpis = ""
    else:
        banner = '<div class="banner">SUPERBOT IA — PAPER, NO VALIDADA PARA CAPITAL REAL</div>'
        kpis = "".join([
            _kpi("Capital inicial", _eur(stats["capital_inicial_eur"])),
            _kpi("Capital neto aportado", _eur(stats["capital_neto_aportado_eur"])),
            _kpi("Cash", _eur(stats["cash_eur"])),
            _kpi("Equity (a coste)", _eur(stats["equity_contable_eur"]), _signed_class(stats["rentabilidad_contable_pct"])),
            _kpi("Rentabilidad (a coste)", _pct(stats["rentabilidad_contable_pct"]), _signed_class(stats["rentabilidad_contable_pct"])),
            _kpi("P&L realizado", _eur(stats["pnl_realizado_eur"]), _signed_class(stats["pnl_realizado_eur"])),
            _kpi("Posiciones abiertas", str(stats["num_abiertas"])),
            _kpi("Gasto API acumulado", _eur(gasto_total)),
        ])
    # El límite se aplica DENTRO de cada estado (hallazgo de Codex): 100 EJECUTADA recientes nunca
    # deben poder ocultar una PENDIENTE o RECHAZADA más antigua.
    pendientes = cartera_ia.ordenes_recientes(100, estado="PENDIENTE") if stats["activa"] else ()
    ejecutadas = cartera_ia.ordenes_recientes(100, estado="EJECUTADA") if stats["activa"] else ()
    rechazadas = cartera_ia.ordenes_recientes(100, estado="RECHAZADA") if stats["activa"] else ()
    aviso_html = f'<div class="aviso">{_text(mensaje)}</div>' if mensaje else ""
    admin_forms = "" if not stats["activa"] else f"""
    <section>
      <h2>Gestión de capital (requiere autenticación)</h2>
      <form class="admin" method="post" action="/aportar">
        <label>Importe EUR<input type="number" name="importe_eur" step="0.01" min="0.01" required></label>
        <label>Motivo<input type="text" name="motivo" required></label>
        <button type="submit">Aportar</button>
      </form>
      <form class="admin" method="post" action="/retirar">
        <label>Importe EUR<input type="number" name="importe_eur" step="0.01" min="0.01" required></label>
        <label>Motivo<input type="text" name="motivo" required></label>
        <button type="submit">Retirar</button>
      </form>
      <form class="admin reiniciar" method="post" action="/reiniciar">
        <label>Capital inicial nuevo EUR<input type="number" name="capital_inicial_eur" step="0.01" min="0.01" required></label>
        <label>Motivo<input type="text" name="motivo" required></label>
        <label>Escribe "{CONFIRMACION_REINICIO}" para confirmar<input type="text" name="confirmar" required></label>
        <button type="submit">Reiniciar cartera (archiva todo lo actual)</button>
      </form>
    </section>
    """
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="300">
  <title>Superbot IA</title>
  <style>{_ESTILO}</style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>Superbot IA</h1>
        <div class="muted">Actualizado: {_text(now_label)}</div>
      </div>
    </div>
    {banner}
    {aviso_html}
    <div class="kpis">{kpis}</div>
    {admin_forms}
    <section><h2>Posiciones abiertas</h2>{_posiciones_abiertas_table(cartera_ia)}</section>
    <section><h2>Posiciones cerradas</h2>{_posiciones_cerradas_table(cartera_ia)}</section>
    <section><h2>Órdenes pendientes</h2>{_ordenes_table(pendientes)}</section>
    <section><h2>Órdenes ejecutadas</h2>{_ordenes_table(ejecutadas)}</section>
    <section><h2>Órdenes rechazadas (incluye las canceladas por un reinicio de cartera)</h2>{_ordenes_table(rechazadas)}</section>
    <section><h2>Fills (compras y ventas ejecutadas)</h2>{_fills_table(cartera_ia.fills_recientes(100))}</section>
    <section><h2>Decisiones de los asesores IA</h2>{_decisiones_table(registro.decisiones_recientes(200))}</section>
    <section><h2>Pasadas — estado operativo y errores</h2>{_pasadas_table(registro.pasadas(50))}</section>
    <section><h2>Auditoría (incluidas las acciones administrativas)</h2>{_eventos_table(cartera_ia.eventos_recientes(100) if stats["activa"] else ())}</section>
    <section><h2>Carteras anteriores (archivadas)</h2>{_generaciones_table(cartera_ia)}</section>
  </main>
</body>
</html>
"""


# --- autenticación y acciones administrativas -----------------------------------


def _credenciales_configuradas() -> Optional[Tuple[str, str]]:
    usuario = os.getenv(USUARIO_ENV, "").strip()
    clave = os.getenv(CLAVE_ENV, "").strip()
    return (usuario, clave) if usuario and clave else None


def _autenticado(header_autorizacion: Optional[str]) -> Optional[str]:
    """``None`` si no autentica; si autentica, el nombre de usuario (para auditar ``actor``)."""

    credenciales = _credenciales_configuradas()
    if credenciales is None:
        return None  # sin usuario/clave configurados, las acciones administrativas quedan cerradas
    if not header_autorizacion or not header_autorizacion.startswith("Basic "):
        return None
    try:
        decodificado = base64.b64decode(header_autorizacion[len("Basic "):]).decode("utf-8")
        usuario, _, clave = decodificado.partition(":")
    except Exception:
        return None
    usuario_ok, clave_ok = credenciales
    # ``hmac.compare_digest``, no ``==`` (hallazgo de Codex): tiempo constante, para que una
    # comparación de credenciales nunca filtre por temporización cuánto coincide con lo correcto.
    if hmac.compare_digest(usuario, usuario_ok) and hmac.compare_digest(clave, clave_ok):
        return usuario
    return None


# --- servidor -------------------------------------------------------------------


def serve(db_path: str | Path, politica: Any, host: str = "127.0.0.1", port: int = 8766) -> None:
    """Sirve el dashboard de Superbot IA en HTTP, refrescando desde SQLite en cada petición."""

    db = Path(db_path)

    class Handler(BaseHTTPRequestHandler):
        def _render(self, mensaje: str = "") -> bytes:
            registro = RegistroIA(db, politica)
            try:
                cartera_ia = CarteraIA(registro.conn)
                pagina = render_html(cartera_ia, registro, datetime.now().isoformat(timespec="seconds"), mensaje)
            finally:
                registro.close()
            return pagina.encode("utf-8")

        def _responder_html(self, payload: bytes, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _origen_valido(self) -> bool:
            """Defensa CSRF ligera (hallazgo de Codex): un navegador que recuerde la sesión de
            Basic Auth podría enviar un formulario cruzado desde otro origen. Sin cabecera
            ``Origin`` (curl, la mayoría de clientes que no son un navegador) no se bloquea; CON
            ella, debe coincidir con el ``Host`` al que se dirige la petición."""

            origen = self.headers.get("Origin")
            if origen is None:
                return True
            destino = self.headers.get("Host", "")
            return origen in (f"http://{destino}", f"https://{destino}")

        def _exigir_autenticacion(self) -> Optional[str]:
            actor = _autenticado(self.headers.get("Authorization"))
            if actor is None:
                self.send_response(401)
                # Latin-1 solo (lo exige http.server para las cabeceras): nunca una raya ni tildes.
                self.send_header("WWW-Authenticate", 'Basic realm="Superbot IA - administracion"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            return actor

        def do_GET(self) -> None:
            ruta = urlparse(self.path)
            if ruta.path == "/healthz":
                payload = b"ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if ruta.path != "/":
                self.send_error(404)
                return
            mensaje = parse_qs(ruta.query).get("mensaje", [""])[0]
            self._responder_html(self._render(mensaje))

        def _leer_formulario(self) -> Dict[str, str]:
            largo = int(self.headers.get("Content-Length", "0"))
            cuerpo = self.rfile.read(largo).decode("utf-8") if largo else ""
            analizado = parse_qs(cuerpo)
            return {clave: valores[0] for clave, valores in analizado.items() if valores}

        def _redirigir_con_mensaje(self, mensaje: str) -> None:
            # POST-Redirect-GET (hallazgo de Codex): tras aplicar la acción, SIEMPRE se redirige a
            # un GET — nunca se responde el resultado directamente sobre la URL del POST, para que
            # recargar la página (o un reenvío accidental del formulario) jamás repita la
            # aportación, la retirada o el reinicio ya aplicados.
            destino = "/?" + urlencode({"mensaje": mensaje})
            self.send_response(303)
            self.send_header("Location", destino)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _accion_admin(self, accion: Callable[[CarteraIA, Dict[str, str], str], str]) -> None:
            if not self._origen_valido():
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            actor = self._exigir_autenticacion()
            if actor is None:
                return
            campos = self._leer_formulario()
            registro = RegistroIA(db, politica)
            try:
                cartera_ia = CarteraIA(registro.conn)
                try:
                    mensaje = accion(cartera_ia, campos, actor)
                except (ValueError, CarteraInactiva, EfectivoInsuficiente) as exc:
                    mensaje = f"No se pudo completar: {exc}"
            finally:
                registro.close()
            self._redirigir_con_mensaje(mensaje)

        def do_POST(self) -> None:
            if self.path == "/aportar":
                self._accion_admin(_accion_aportar)
            elif self.path == "/retirar":
                self._accion_admin(_accion_retirar)
            elif self.path == "/reiniciar":
                self._accion_admin(_accion_reiniciar)
            else:
                self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _accion_aportar(cartera_ia: CarteraIA, campos: Dict[str, str], actor: str) -> str:
    importe = float(campos.get("importe_eur", ""))
    motivo = campos.get("motivo", "").strip()
    if not motivo:
        raise ValueError("falta el motivo")
    cartera_ia.aportar(importe_eur=importe, motivo=motivo, actor=actor)
    return f"Aportación de {_eur(importe)} registrada por {actor}."


def _accion_retirar(cartera_ia: CarteraIA, campos: Dict[str, str], actor: str) -> str:
    importe = float(campos.get("importe_eur", ""))
    motivo = campos.get("motivo", "").strip()
    if not motivo:
        raise ValueError("falta el motivo")
    cartera_ia.retirar(importe_eur=importe, motivo=motivo, actor=actor)
    return f"Retirada de {_eur(importe)} registrada por {actor}."


def _accion_reiniciar(cartera_ia: CarteraIA, campos: Dict[str, str], actor: str) -> str:
    if campos.get("confirmar", "").strip().upper() != CONFIRMACION_REINICIO:
        raise ValueError(f'hay que escribir "{CONFIRMACION_REINICIO}" para confirmar el reinicio')
    capital = float(campos.get("capital_inicial_eur", ""))
    motivo = campos.get("motivo", "").strip()
    if not motivo:
        raise ValueError("falta el motivo")
    generacion_id = cartera_ia.reiniciar_cartera(
        capital_inicial_eur=capital, motivo=motivo, actor=actor, instante=datetime.now(timezone.utc),
    )
    return f"Cartera reiniciada por {actor}: generación {generacion_id} archivada, nuevo capital {_eur(capital)}."


__all__ = ["build_stats", "render_html", "serve"]
