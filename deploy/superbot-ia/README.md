# Superbot IA — pegamento de despliegue en Raspberry Pi

**PAPER OPERACIONAL / NO VALIDADA PARA CAPITAL REAL.** Este directorio contiene
las plantillas systemd y los wrappers del despliegue de `superbot.ia`. Es una
instalación separada del Superbot técnico antiguo, de T-024 y de T-025.

La instalación usa el checkout y el entorno propios de la Pi:

- checkout: `/home/fer/superbot-ia-forward`
- venv: `/home/fer/superbot-ia-venv`
- base nueva y separada: `/home/fer/superbot-ia-forward/datos/superbot_ia.db`
- logs: `/home/fer/superbot-ia-forward/logs/`

| Unidad | Qué hace |
|---|---|
| `superbot-ia-pasada.timer` → `superbot-ia-pasada.service` | Ejecuta `python -m superbot.ia ... pasada` lun-vie a las 07:00, 08:30, 14:30 y 21:00 `Europe/London`. |
| `superbot-ia-telegram.timer` → `superbot-ia-telegram.service` | Vacía la cola de avisos pendientes cada 10 minutos. |
| `superbot-ia-dashboard.service` | Sirve el dashboard en `192.168.1.113:8766` (la LAN de la Pi, nunca `0.0.0.0`); sin `SUPERBOT_IA_DASHBOARD_USUARIO`/`CLAVE` en el `.env`, sus acciones administrativas quedan abiertas sin autenticación (decisión del propietario, 2026-11-08). |

La pasada no lleva `SuccessExitStatus=2`: si el candado está ocupado devuelve
el fallo normal de `ejecutar_pasada` y queda registrado en el journal/log; el
siguiente disparo del timer lo reintentará.

## Secretos y clave de Anthropic

Copiar `superbot-ia.env.example` en la Pi como
`/home/fer/superbot-ia-forward/superbot-ia.env`, rellenarlo y dejarlo en
`0600`. `SUPERBOT_IA_TELEGRAM_BOT_TOKEN`/`CHAT_ID` son del bot propio y
exclusivo de Superbot IA (el bot del Superbot antiguo tenía el token
revocado cuando se intentó reutilizar, 2026-11-08). Dejar
`SUPERBOT_IA_DASHBOARD_USUARIO`/`CLAVE` en blanco a propósito: así el
dashboard queda abierto, sin contraseña, para cualquier dispositivo de la
LAN — ver la sección "Dashboard" más abajo.

El wrapper `bin/pasada.sh` lee `ANTHROPIC_API_KEY` de
`/home/fer/intradia-bot/.env` y la reexporta como `SUPERBOT_IA_API_KEY` solo al
proceso de la pasada. No se duplica la clave en `superbot-ia.env`.

## Instalación manual

Con el checkout y el venv ya preparados en la Pi, ejecutar desde la raíz de
este repositorio:

```bash
sudo install -d -m 0755 -o fer -g fer /home/fer/superbot-ia-forward/bin
sudo install -d -m 0755 -o fer -g fer /home/fer/superbot-ia-forward/datos
sudo install -d -m 0755 -o fer -g fer /home/fer/superbot-ia-forward/logs
sudo install -m 0755 -o fer -g fer deploy/superbot-ia/bin/pasada.sh /home/fer/superbot-ia-forward/bin/pasada.sh
sudo install -m 0755 -o fer -g fer deploy/superbot-ia/bin/telegram-flush.sh /home/fer/superbot-ia-forward/bin/telegram-flush.sh
sudo install -m 0600 -o fer -g fer deploy/superbot-ia/superbot-ia.env.example /home/fer/superbot-ia-forward/superbot-ia.env
sudo install -m 0644 deploy/superbot-ia/systemd/superbot-ia-pasada.service /etc/systemd/system/
sudo install -m 0644 deploy/superbot-ia/systemd/superbot-ia-pasada.timer /etc/systemd/system/
sudo install -m 0644 deploy/superbot-ia/systemd/superbot-ia-dashboard.service /etc/systemd/system/
sudo install -m 0644 deploy/superbot-ia/systemd/superbot-ia-telegram.service /etc/systemd/system/
sudo install -m 0644 deploy/superbot-ia/systemd/superbot-ia-telegram.timer /etc/systemd/system/
sudoedit /home/fer/superbot-ia-forward/superbot-ia.env
sudo systemctl daemon-reload
sudo systemctl enable --now superbot-ia-dashboard.service
sudo systemctl enable --now superbot-ia-pasada.timer superbot-ia-telegram.timer
systemctl list-timers superbot-ia-pasada.timer superbot-ia-telegram.timer
```

Antes de activar la cartera, comprobar que el checkout, el venv, la
configuración y la base apuntan a este despliegue y revisar los logs. Para
vaciar manualmente la cola de Telegram, si se desea:

```bash
sudo systemctl start superbot-ia-telegram.service
```

Para enviar el mensaje de prueba del CLI (`telegram --test`), cargar el mismo
fichero de entorno y ejecutar:

```bash
sudo -u fer bash -lc 'set -a; source /home/fer/superbot-ia-forward/superbot-ia.env; set +a; exec /home/fer/superbot-ia-venv/bin/python -B -m superbot.ia --db /home/fer/superbot-ia-forward/datos/superbot_ia.db telegram --test'
```

## Comando de Telegram `/dashboard`

Si `SUPERBOT_IA_DASHBOARD_URL` está rellenado en el `.env`, cada vez que
corre `superbot-ia-telegram.timer` (cada 10 min) también atiende los mensajes
pendientes del chat configurado: si alguno es `/dashboard`, responde con esa
URL. Cualquier mensaje de un chat distinto al configurado se ignora sin
respuesta. No hace falta ningún comando nuevo para probarlo: basta con
escribirle `/dashboard` al bot y esperar al siguiente disparo del timer (o
lanzarlo a mano con `sudo systemctl start superbot-ia-telegram.service`).

No activar ni reactivar `superbot-paper.timer`. Tampoco tocar
`intradia-t024-checkpoint`, `intradia-t025-paper`, `intradia-bot`,
`intradia-bot-event` ni `superbot-dashboard`: son unidades de otros despliegues.

## Dashboard

El puerto de Superbot IA es **8766**, nunca 8765 (8765 pertenece al Superbot
técnico antiguo). Decisión del propietario (2026-11-08): el servicio escucha
directamente en `192.168.1.113` (la LAN de la Pi), nunca en `0.0.0.0`, así
que no es alcanzable desde Internet salvo que el router tenga ese puerto
reenviado (revisarlo aparte, no hay forma de comprobarlo desde la Pi misma).
Sin `SUPERBOT_IA_DASHBOARD_USUARIO`/`CLAVE`, no pide usuario ni contraseña:
se abre directamente desde cualquier dispositivo de la LAN en

```
http://192.168.1.113:8766
```

Las acciones que tocan capital (aportar, retirar, reiniciar) piden
confirmación en el propio navegador antes de enviarse (además de la
confirmación escrita "SI" que ya exige el reinicio en el servidor); la
defensa contra peticiones cruzadas desde otra página (`Origin`) sigue activa
igual que antes. Volver a exigir usuario/contraseña es tan simple como
rellenar `SUPERBOT_IA_DASHBOARD_USUARIO`/`CLAVE` en el `.env` y reiniciar el
servicio.

## Activación explícita de la cartera

La cartera nace inactiva. Ni `pasada` ni el dashboard llaman a
`CarteraIA.activar(...)`; el CLI y el dashboard no tienen wiring para hacerlo.
Tras el preflight, si se autoriza ponerla en PAPER, ejecutar una sola vez este
snippet en la Pi. El capital inicial autorizado por defecto es **10.000 EUR**:

```bash
cd /home/fer/superbot-ia-forward
/home/fer/superbot-ia-venv/bin/python - <<'PY'
from datetime import datetime, timezone

from superbot.ia.cartera import CarteraIA
from superbot.ia.politica import PoliticaIA
from superbot.ia.registro import RegistroIA

db = "/home/fer/superbot-ia-forward/datos/superbot_ia.db"
politica = PoliticaIA()
registro = RegistroIA(db, politica)
try:
    cartera_ia = CarteraIA(registro.conn)
    cartera_ia.activar(instante=datetime.now(timezone.utc), capital_inicial_eur=10_000.0)
finally:
    registro.close()
PY
```

`activar` es idempotente respecto de una cartera ya activa; no ejecutar el
snippet para cambiarle el capital. La base de este despliegue es nueva y no se
debe sustituir por ninguna base existente.
