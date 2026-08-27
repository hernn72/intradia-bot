"""Notificaciones por Telegram.

Copia reducida de ``app/telegram/notifier.py`` (trading-bot): aquí solo hace
falta enviar texto. Se añade ``send_long_message`` porque un informe del
asesor supera con holgura el límite de 4096 caracteres por mensaje.

Sin ``bot_token``/``chat_id`` el notificador queda deshabilitado y se limita
a registrar el mensaje en el log.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

# Límite duro de Telegram por mensaje; se deja margen para el sufijo de parte.
TELEGRAM_MAX_CHARS = 4096
_CHUNK_TARGET = 3900


class TelegramNotifier:
    """Envía mensajes a un chat de Telegram, con rate limiting básico."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"
    TIMEOUT_SECONDS = 10

    def __init__(
        self,
        bot_token: Optional[str],
        chat_id: Optional[str],
        min_interval_seconds: float = 1.0,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds debe ser >= 0")

        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self.min_interval_seconds = min_interval_seconds
        self._last_call: Optional[float] = None

    def _wait_for_rate_limit(self) -> None:
        if self._last_call is None:
            self._last_call = time.monotonic()
            return

        elapsed = time.monotonic() - self._last_call
        remaining = self.min_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()

    def send_message(self, text: str) -> bool:
        """Envía ``text`` al chat configurado.

        Devuelve ``True`` si se envió, ``False`` si Telegram está deshabilitado
        o si hubo un error de red. Nunca lanza por un fallo de envío: que no
        salga la notificación no debe tumbar la ejecución del asesor.
        """

        if not isinstance(text, str) or not text.strip():
            raise ValueError("text debe ser una cadena no vacía")

        if not self.enabled:
            logger.info("Telegram deshabilitado. Mensaje no enviado:\n%s", text)
            return False

        self._wait_for_rate_limit()

        url = self.BASE_URL.format(token=self.bot_token, method="sendMessage")
        try:
            response = requests.post(
                url,
                data={"chat_id": self.chat_id, "text": text},
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Error enviando mensaje a Telegram: %s", exc)
            return False

        return True

    def send_long_message(self, text: str) -> bool:
        """Envía un texto largo troceado en varios mensajes.

        Devuelve ``True`` solo si todas las partes se enviaron correctamente.
        """

        chunks = split_message(text)
        total = len(chunks)
        ok = True
        for index, chunk in enumerate(chunks, start=1):
            suffix = f"\n\n[{index}/{total}]" if total > 1 else ""
            ok = self.send_message(chunk + suffix) and ok
        return ok


def split_message(text: str, limit: int = _CHUNK_TARGET) -> List[str]:
    """Trocea ``text`` en partes de como mucho ``limit`` caracteres.

    Corta por saltos de línea siempre que puede, para no partir una tabla o
    una ficha por la mitad. Si una sola línea excede el límite, se parte por
    longitud como último recurso.
    """

    if limit <= 0:
        raise ValueError("limit debe ser mayor que 0")
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            chunks.append(line[:limit])
            line = line[limit:]

        extra = len(line) + (1 if current else 0)
        if current_len + extra > limit:
            chunks.append("\n".join(current))
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += extra

    if current:
        chunks.append("\n".join(current))

    return chunks
