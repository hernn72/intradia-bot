"""Notificador de Telegram: troceado de mensajes largos y modo deshabilitado."""

from __future__ import annotations

import pytest

from advisor.telegram.notifier import TELEGRAM_MAX_CHARS, TelegramNotifier, split_message


class TestSplitMessage:
    def test_texto_corto_no_se_trocea(self) -> None:
        assert split_message("hola") == ["hola"]

    def test_trocea_por_saltos_de_linea(self) -> None:
        texto = "\n".join(f"línea {i}" for i in range(200))
        partes = split_message(texto, limit=100)
        assert len(partes) > 1
        assert all(len(p) <= 100 for p in partes)
        assert "\n".join(partes) == texto

    def test_una_linea_mas_larga_que_el_limite_se_parte(self) -> None:
        partes = split_message("x" * 250, limit=100)
        assert [len(p) for p in partes] == [100, 100, 50]

    def test_ninguna_parte_supera_el_limite_de_telegram(self) -> None:
        texto = "\n".join("=" * 90 for _ in range(500))
        assert all(len(p) <= TELEGRAM_MAX_CHARS for p in split_message(texto))

    def test_limite_invalido(self) -> None:
        with pytest.raises(ValueError):
            split_message("hola", limit=0)


class TestTelegramNotifier:
    def test_sin_credenciales_queda_deshabilitado(self) -> None:
        notifier = TelegramNotifier(None, None)
        assert notifier.enabled is False
        assert notifier.send_message("hola") is False

    def test_texto_vacio_es_un_error_de_programacion(self) -> None:
        with pytest.raises(ValueError):
            TelegramNotifier(None, None).send_message("   ")

    def test_intervalo_negativo(self) -> None:
        with pytest.raises(ValueError):
            TelegramNotifier("t", "c", min_interval_seconds=-1)

    def test_mensaje_largo_deshabilitado_no_lanza(self) -> None:
        notifier = TelegramNotifier(None, None)
        assert notifier.send_long_message("línea\n" * 5000) is False
