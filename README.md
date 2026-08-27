# intradia-bot

**Asesor de inversión.** Analiza un universo de activos, puntúa cada
oportunidad de 0 a 100, fija entrada, stop y objetivos, y redacta una
recomendación con el formato completo — para que la ejecutes **a mano en
Trade Republic**.

> ⚠️ **No ejecuta órdenes.** No se conecta a ningún bróker ni mueve dinero.
> Produce informes; decides tú. Las recomendaciones **no son asesoramiento
> financiero**.

Es un proyecto **independiente** de `trading-bot` (el bot de paper trading
que decide y simula por su cuenta). Aquel opera un universo fijo con una
estrategia validada; este propone ideas para un humano. Comparten idea pero
no código en ejecución: ver [Qué se reutiliza](#qué-se-reutiliza-de-trading-bot).

## Qué hace y qué no

| Hace | No hace |
|---|---|
| Puntúa oportunidades con seis dimensiones ponderadas | Consultar noticias, resultados o el calendario macro |
| Sitúa entrada, stop y objetivos por estructura y volatilidad (ATR) | Analizar fundamentales (PER, ROIC, EV/EBITDA) |
| Muestra todos los precios legibles en euros | Verificar por sí solo la disponibilidad en Trade Republic |
| Clasifica en 🟢 OPERAR / 🟡 VIGILAR / 🔴 DESCARTAR | Estimar probabilidades que no ha medido |
| Sigue posiciones abiertas contra su tesis original | Ejecutar, enviar o modificar órdenes |

Lo que no puede hacer **no lo simula**: los campos sin fuente de datos salen
como `N/D` y la dimensión fundamental se excluye del cómputo, con la
puntuación normalizada sobre los puntos realmente evaluables. La alternativa
—puntuar a cero lo que no se sabe— haría que ningún activo superase nunca el
umbral por una carencia del bot, no del activo.

## Inicio rápido

```bash
cd intradia-bot

python3 -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # Telegram y Anthropic son opcionales

# Informe de swing sobre todo el universo
python -m advisor.main analizar --horizonte swing

# Intradía, solo blue chips europeos, enviado por Telegram
python -m advisor.main analizar --horizonte intradia --grupos europa --telegram
```

## Comandos

| Comando | Para qué |
|---|---|
| `analizar` | Analiza el universo y genera el informe |
| `seguimiento` | Revisa las posiciones abiertas contra su tesis |
| `abrir` | Registra una compra ejecutada en Trade Republic |
| `cerrar` | Cierra una posición registrada |
| `posiciones` | Lista las posiciones abiertas |

```bash
python -m advisor.main analizar --horizonte medio --sin-ia
python -m advisor.main abrir --symbol SAP.DE --precio 240.50 --cantidad 4 \
    --tesis "Ruptura del máximo anual con volumen" --objetivo 265 --stop 232
python -m advisor.main seguimiento
python -m advisor.main cerrar --symbol SAP.DE --precio 262.00 --motivo "objetivo 2 alcanzado"
```

### Horizontes

El horizonte elige la ventana de datos y determina el tipo de operación:

| Horizonte | Velas | Histórico | Tipo de operación |
|---|---|---|---|
| `intradia` | 15 min | 60 días | ⚡ Intradía |
| `swing` | 1 día | 1 año | 🚀 Swing / corto plazo |
| `medio` | 1 día | 2 años | 📈 Medio plazo |

## Los euros

Las órdenes se ejecutan a mano en Trade Republic, en euros, así que **todo
precio de una recomendación —entrada, stop y objetivos— se muestra en
euros**:

- Activo que ya cotiza en euros → `240,50 €`.
- Activo en otra divisa → `100,00 USD (≈ 80,00 €)`. Se conserva el precio
  nativo porque es al que se cruzará la orden; el euro es orientativo.
- Sin tipo de cambio disponible → se dice, y no se inventa la conversión.

La conversión usa el cierre diario del par correspondiente, se descarga una
sola vez por informe y se declara al pie con su fecha. Es una **capa de
presentación**: no toca cálculos ni contabilidad. Los porcentajes (potencial,
riesgo, ratio) son invariantes a la divisa y no se convierten.

## El universo

`universe.yaml` agrupa los activos con los metadatos que la restricción de
Trade Republic obliga a comprobar: nombre, ticker, ISIN, mercado, divisa y
disponibilidad.

**Dos campos hay que rellenarlos a mano**, porque no hay forma de obtenerlos
automáticamente:

```yaml
isin: DE0007164600
trade_republic: yes        # yes | no | unknown
```

Todos los activos nacen con `isin: null` y `trade_republic: unknown`, y el
informe los marca como *⚠️ PENDIENTE DE VERIFICACIÓN*. Un `unknown` no
impide recomendarlos: lo que está prohibido es **afirmar** una disponibilidad
sin comprobar. Un `no` explícito sí los descarta.

El ISIN se valida al cargar el universo (formato + dígito de control Luhn),
así que una errata al teclearlo hace fallar el arranque en lugar de colarse
en una recomendación.

Los índices (`^VIX`, `^GDAXI`, `^N225`…) llevan `analizable: false`: sirven
de contexto y nunca se recomiendan.

## La puntuación

Seis dimensiones, todas calculadas en Python:

| Dimensión | Puntos | De dónde sale |
|---|---:|---|
| Catalizador | 20 | Volumen anormal, hueco de apertura, ruptura de máximos |
| Fundamental | 20 | **Excluida**: no hay fuente de datos fundamentales |
| Técnico | 20 | EMA rápida/lenta, SMA larga, RSI, MACD, fortaleza relativa |
| Beneficio/riesgo | 20 | Ratio calculado sobre el objetivo 2 |
| Contexto | 10 | VIX y tendencia del índice de referencia |
| Convicción | 10 | Histórico disponible, indicadores presentes, volatilidad |

**El agente IA no puntúa.** Redacta tesis, catalizador, escenarios y riesgos
a partir de números ya fijados, y el prompt le prohíbe explícitamente
recalcularlos, contradecirlos o inventar catalizadores externos. Si un modelo
pudiera mover la nota, la nota dejaría de ser comparable entre ejecuciones.

Umbrales: ≥70 → 🟢 OPERAR · 60-69 → 🟡 VIGILAR · <60 → 🔴 DESCARTAR. Además,
una oportunidad con buena nota baja a VIGILAR si el precio está extendido
(*no perseguir precio*), si el contexto es hostil, o si el ratio no llega al
mínimo.

## Configuración

Todo en `config.yaml`; los secretos solo en `.env`:

| Variable | Para qué |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Enviar informes por Telegram |
| `ANTHROPIC_API_KEY` | Capa narrativa del agente (opcional) |

Sin `ANTHROPIC_API_KEY`, o con `ai.enabled: false`, el informe se genera
igual usando textos construidos a partir de los datos calculados.

## Estructura

```
intradia-bot/
├── advisor/
│   ├── main.py              # CLI
│   ├── config.py            # config.yaml validado (pydantic)
│   ├── data/                # yfinance + conversión a euros
│   ├── indicators/          # SMA, EMA, RSI, ATR, MACD, fortaleza relativa
│   ├── universe/            # universe.yaml: metadatos, ISIN, Trade Republic
│   ├── analysis/            # foto técnica → niveles → puntuación → decisión
│   ├── ai/                  # agente narrador (prompt en ai/prompts/)
│   ├── report/              # formato del informe, euros, seguimiento
│   ├── storage/             # SQLite: recomendaciones, posiciones, revisiones
│   └── telegram/            # notificaciones
├── tests/                   # pytest, sin red
├── config.yaml
└── universe.yaml
```

El flujo de análisis está separado por pureza: `snapshot`, `levels`,
`scoring` y `opportunity` no hacen I/O y se prueban sin red; solo `analyzer`,
`overview` y `market_context` descargan datos.

## Qué se reutiliza de trading-bot

Cuatro módulos se copiaron porque no tenían ninguna dependencia del resto de
aquel paquete:

| Módulo | Origen |
|---|---|
| `advisor/data/market_data.py` | `app/data/market_data.py` (+ `get_last_close`) |
| `advisor/indicators/technical.py` | `app/indicators/technical.py` (+ EMA, MACD, fortaleza relativa) |
| `advisor/telegram/notifier.py` | `app/telegram/notifier.py` (reducido, + troceado) |
| `advisor/analysis/market_context.py` | adaptado de `app/market/regime.py` |

Son **copias, no importaciones**: este proyecto no depende de `trading-bot`
para arrancar. La contrapartida es que una corrección en aquel repositorio no
llega sola hasta aquí y hay que replicarla.

La estrategia, la gestión de riesgo, el broker simulado y los motores de
backtest **no** se reutilizan: pertenecen a un bot que decide solo, no a un
asesor que propone.

## Desarrollo

```bash
pip install -r requirements-dev.txt
pytest                       # sin red: todos los datos son sintéticos
ruff check advisor tests
mypy advisor
```

## Limitaciones conocidas

1. **Sin catalizadores externos.** Solo se detecta la huella que un
   catalizador deja en el precio (volumen, hueco, ruptura), nunca su causa.
2. **Sin fundamentales.** La dimensión existe pero está excluida.
3. **Disponibilidad en Trade Republic e ISIN, manuales.** No hay API pública.
4. **Sin probabilidades de escenario.** Se describen los tres escenarios,
   pero no se les asigna una probabilidad que nadie ha medido.
5. **Intradía limitado por yfinance.** Las velas de 15 minutos llegan con
   retraso y con un histórico corto: sirven para contexto, no para operar al
   segundo.
6. **Ninguna recomendación está validada por backtest.** A diferencia de
   `trading-bot`, aquí no hay motor de backtest: la puntuación es un criterio
   razonado, no una ventaja demostrada.
