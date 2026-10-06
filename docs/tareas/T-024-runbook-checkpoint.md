# T-024 — Runbook del checkpoint mensual

Contrato operativo de la captura forward de T-024 (§6.3 y §7 de la ficha, D-72). Implementado en
`advisor/research/t024_forward.py` y operado en dos fases:

- **Fase A, Raspberry Pi 24/7:** captura forward automática. Un timer diario ejecuta
  `deploy/t024/checkpoint.py`; solo el día de un checkpoint declarado verifica identidad, calcula la
  petición, ejecuta `congelar` una vez, guarda artefactos y hashes, y para.
- **Fase B, PC:** revisión manual, copia verificada, versionado de evidencia y ejecución posterior de
  registro y conteos.

**No cambia ninguna regla metodológica**: concreta la petición exacta que la ficha ya exigía (`start`,
`end`, `interval = 1d`, `auto_adjust = False`, `actions = True`).

## Contrato de la petición

| Campo | Valor |
|---|---|
| `start` | `2021-08-30`, fijo e inclusivo (coherente con el comienzo estructural del histórico de P6) |
| `end` | exclusivo, como en yfinance: el **quinto día hábil anterior al checkpoint** |
| `interval` | `1d` |
| `auto_adjust` / `actions` | `False` / `True` |
| Símbolos | los 126 del manifiesto de la cosecha consumida `071ddb2b…` versionado en el repositorio (con cualquier `--data-dir`), ordenados; `SIMBOLOS_FORWARD_SHA256 = c7a896ab921a27dce3e6ea268187ff03ce77954dd67298ac2b62d7c4017b50b5`. Cubren activos, benchmarks y contexto. No se añade ni se quita ninguno por disponibilidad del día |
| Universo | `universe_vintage_id = 237b0056…` (el congelado de P6) |

- **Día hábil:** de lunes a viernes, menos los festivos laborales (Canarias) que se declaran para ese
  checkpoint con `--festivo`. Los festivos declarados viajan en la petición y en la entrada del registro,
  y el registro rechaza una entrada cuyo `end` no salga de esa regla.
- **Checkpoint:** el primer día hábil del mes. El código niega un checkpoint que no lo sea con los festivos
  declarados y niega congelar antes de la fecha del checkpoint (hora de Canarias).
- **Modo `period` histórico:** sin cambios. Las cosechas antiguas (`schema_version` 1) se cargan y
  verifican igual; la cosecha consumida conserva su `data_vintage_id`. Las forward son `schema_version` 2,
  con la petición completa en `request`. Una respuesta del proveedor con alguna barra fuera de
  `[start, end)` (fecha de la barra en la zona de su plaza) invalida ese símbolo; no se recorta nada.
- **Procedencia:** el manifiesto forward guarda en `request.context` el checkpoint, los festivos,
  `T024_PREREG_SHA` y el `T024_CODE_SHA` con que se congeló. Todo ello entra en el `data_vintage_id`. Una
  cosecha solo es apta si:
  - ese contexto coincide con el del registro;
  - se descargó el día del checkpoint o después (hora de Canarias).

  El registro admite un único checkpoint por mes.

## Primer checkpoint: 2026-11-03

El 2026-11-02 es festivo laboral en Canarias, así que el primer día hábil de noviembre es el martes 3.
Quedan fuera los cinco días hábiles anteriores: 26, 27, 28, 29 y 30 de octubre. Por tanto
**`end = 2026-10-26`** (exclusivo). La primera cosecha **no tiene previa**: `barras_nuevas` y
`barras_revisadas` salen `null`.

```sh
python -m advisor.research.t024_forward peticion --checkpoint 2026-11-03 --festivo 2026-11-02
```

Ese comando solo calcula la petición; no descarga nada.

## Fase A automática en la Pi

Producción permanece en `/home/fer/intradia-bot`. La captura forward corre en el worktree dedicado
`/home/fer/intradia-t024`, con el intérprete del venv del bot. Ese worktree se crea desde el commit de
`main` posterior a fusionar el PR #46, o un descendiente, porque `T024_CODE_SHA =
1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0` no contiene `deploy/t024`. Antes de instalar se comprueba que
`deploy/t024/checkpoint.py` existe, que las rutas protegidas no difieren contra `T024_CODE_SHA` y que
`verificar_identidad()` devuelve exactamente ese SHA. Esto evita tocar el release productivo y permite
desplegar el wrapper sin cambiar el ejecutor metodológico. La unidad systemd no fuerza `TZ`; el wrapper
calcula explícitamente la fecha en Canarias y la congelación ve el mismo entorno que una ejecución manual
con el venv.

```sh
git -C /home/fer/intradia-bot fetch origin
git -C /home/fer/intradia-bot worktree add --detach /home/fer/intradia-t024 <SHA de main tras fusionar #46>
git -C /home/fer/intradia-t024 diff --quiet 1a697c3fa2ab76ddfcf567c2ef3f5ab56492eaf0 HEAD -- advisor config.yaml universe.yaml exchange_overrides.yaml pyproject.toml requirements.txt
test -f /home/fer/intradia-t024/deploy/t024/checkpoint.py
```

El timer diario de `deploy/t024/systemd/` llama a:

```sh
python deploy/t024/checkpoint.py ejecutar --data-dir /home/fer/intradia-bot/data/vintages --artefactos /home/fer/t024-forward
```

El wrapper:

1. Valida `deploy/t024/calendario-checkpoints.json`.
2. Toma un lock no bloqueante.
3. Marca como `PERDIDO` cualquier checkpoint pasado sin directorio de artefactos.
4. Si hoy no es un checkpoint declarado, no ejecuta ningún comando del módulo forward.
5. Si hoy es checkpoint, crea `intento.json`, verifica preflight e identidad, escribe `peticion.json`,
   comprueba que la petición coincide con el calendario y ejecuta `congelar` una sola vez.
6. Escribe `congelacion.json`, `congelar.stderr.log`, `estado.json` y después `SHA256SUMS`, que cubre
   también `estado.json`.

La fase A **no registra, no captura conteos, no decide y no reintenta automáticamente**. `NO_APTA`,
`ERROR_*`, `INTERRUMPIDO` y `PERDIDO` quedan visibles para el propietario.

Política de fallos:

- `APTA`: queda lista para copiar y revisar en PC.
- `NO_APTA`: la unidad systemd falla; la cosecha parcial no cuenta como checkpoint.
- `ERROR_*`: se conserva el intento y se requiere intervención.
- `INTERRUMPIDO`: existe `intento.json` sin cierre; no se descarga otra vez.
- `PERDIDO`: se detectó tarde un checkpoint pasado sin artefactos; no se descarga retrospectivamente.

## Fase B manual en el PC

La fecha en que se ejecute esta fase no cambia el checkpoint: manda la cosecha congelada en la Pi.

1. **Copiar y verificar artefactos de la Pi.**

   ```sh
   python deploy/t024/traer_cosecha.py copiar \
     --checkpoint 2026-11-03 \
     --destino-artefactos evidence/T-024-forward/2026-11-03/pi \
     --data-dir data/vintages \
     --pi-artefactos /home/fer/t024-forward \
     --pi-data-dir /home/fer/intradia-bot/data/vintages
   ```

   `copiar` usa `rsync -a` sin borrar destino, exige `APTA` y verifica hashes, manifiesto, petición,
   contexto y sidecar de identidad en staging. Solo después promueve artefactos y vintage con `os.replace`.
   Si un destino ya existe, exige igualdad byte a byte del árbol completo y no lo toca. Los staging viven
   junto a los destinos finales y se borran ante cualquier fallo, dejando intactos artefactos y vintage
   finales.

2. **Registro.**

   ```sh
   python -m advisor.research.t024_forward registrar --data-vintage-id <id> --checkpoint 2026-11-03 --festivo 2026-11-02 --registro evidence/T-024-forward/registro-forward.json
   ```

   Vuelve a verificar la cosecha completa y la identidad, y añade la entrada. Niega una cosecha no apta,
   un checkpoint no creciente o un `data_vintage_id` repetido.

3. **Commit de evidencia** del registro, artefactos de Pi y manifiesto versionable de la cosecha. El árbol
   debe quedar limpio antes de capturar, porque desde el segundo checkpoint el registro modificado entra en
   la identidad.

4. **Captura de conteos.**

   ```sh
   python -m advisor.research.t024_forward capturar --data-vintage-id <id> --registro evidence/T-024-forward/registro-forward.json > evidence/T-024-forward/2026-11-03/conteos.json
   ```

   Usa `c_e` = checkpoint. Desde el segundo checkpoint, la cosecha inmediatamente anterior del registro se
   usa **solo** para `barras_nuevas` y `barras_revisadas`.

5. Commit solo de evidencia de `conteos.json`.

## Formatos

**Entrada del registro** (lista cerrada de claves; cualquier otra invalida el registro): `checkpoint`,
`data_vintage_id`, `manifest_hash`, `manifest_file_sha256`, `requested_start`, `requested_end`,
`end_exclusive`, `interval`, `auto_adjust`, `actions`, `symbols_sha256`, `n_symbols`, `festivos`,
`universe_vintage_id`, `provider`, `provider_version`, `T024_PREREG_SHA`, `T024_CODE_SHA`.

El registro es `{schema, schema_version, cosechas, sha256, entradas_sha256}`:
- `sha256` es el hash que recalcula `cargar_registro_forward` (solo `data_vintage_id` y `checkpoint`);
- `entradas_sha256` cubre las entradas completas.

Se serializa de forma canónica (claves ordenadas, sangría 2). `cargar_registro_forward`, el lector de la
ruta decisoria, solo acepta este registro canónico completo.

**Salida de captura:** `checkpoint`, `c_e`, `data_vintage_id`, `previa_data_vintage_id`,
`barras_nuevas`, `barras_revisadas` y, para B2, S2 y C0:
- `senales_operar`, `ejecutables`, `rechazos` (motivos previos a la entrada), `q_p`, `w_p`;
- `exclusiones`.

Nada más. En particular no emite salidas, `R`, D1–D4, P&L, ventanas ni el «cumple»; el umbral
(`Q_p ≥ 120` y `W_p ≥ 26`) se lee de los conteos. Barra revisada = barra ya vista en la previa cuyo OHLCV
cambia o que desaparece.

## Prohibido en un checkpoint

`ejecutar_mirada`, D1, D2, D2o, D2c, D3, D4, no solapamiento, salidas y cualquier marca de mirada. El
módulo forward no importa ninguna de esas funciones (test de imports cerrado), y la salida y el registro
se validan contra listas cerradas de claves.
