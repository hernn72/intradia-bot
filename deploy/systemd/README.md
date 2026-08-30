# Unidades systemd

Estas unidades versionan las decisiones operativas: cuatro pasadas normales
en días laborables (`07:00`, `08:30`, `14:30`, `21:00`), una pasada por evento
autodescartable a la hora configurada en `events.pasada_evento_hora`, `TimeoutStartSec=1800`
y `Persistent=false`.

Las rutas no viven en las unidades versionadas. El instalador lee un fichero
externo, por defecto `/etc/intradia-bot/systemd.env`, con estas variables.

Ese fichero **no contiene secretos**: solo rutas, el usuario y un puntero al
`.env`, que es donde viven las credenciales y que sigue siendo `0600`. Por eso
va en `0644` y no en `0600`: la comprobación de desfase está pensada para
correr **sin `sudo`**, y con `0600` de root falla al leerlo.

```bash
INTRADIA_BOT_USER=fer
INTRADIA_BOT_DIR=/home/fer/intradia-bot
INTRADIA_BOT_PYTHON=/home/fer/intradia-bot/.venv/bin/python
INTRADIA_BOT_ENV_FILE=/home/fer/intradia-bot/.env
INTRADIA_BOT_ANALIZAR_LOG=/home/fer/intradia-bot/logs/analizar.log
INTRADIA_BOT_EVENT_LOG=/home/fer/intradia-bot/logs/pasada-evento.log
```

Instalación o recuperación en una Pi nueva:

```bash
sudo install -d -m 0755 /etc/intradia-bot
sudo install -m 0644 systemd.env /etc/intradia-bot/systemd.env
sudo ./deploy/install-systemd.sh
sudo systemctl daemon-reload
sudo systemctl enable --now intradia-bot.timer
sudo systemctl enable --now intradia-bot-event.timer
systemctl list-timers intradia-bot.timer intradia-bot-event.timer
```

Comprobación de desfase sin sudo:

```bash
python -m advisor.main verificar-systemd
```
