"""Superbot — paper trading visible (operacional).

Cartera simulada completa —cash, posiciones, órdenes, fills, salidas, P&L,
equity, dashboard y Telegram— **separada del laboratorio**: no importa nada de
``paper/`` (T-025), no lee ``paper.db`` ni ``intradia.db`` y no usa las
políticas B2/S2/C0 ni la puntuación del asesor, cuyos desenlaces están sellados
mientras dure el embargo de T-024 (D-73, D-75).

La estrategia es la de tendencia de ``trading-bot`` (iTrade Bot), portada sin
cambiar sus reglas. Nada de lo que produce este paquete valida una estrategia.
"""

LABEL = "PAPER OPERACIONAL / NO VALIDADA PARA CAPITAL REAL"
