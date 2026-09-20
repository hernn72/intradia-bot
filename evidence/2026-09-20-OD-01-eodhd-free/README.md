# Sondeo del plan gratuito de EODHD — OD-01 (D-39)

**Estado: preparado, sin ejecutar.** Falta la cuenta gratuita y la API key, que
son trabajo del propietario.

## Qué pregunta responde

Una sola, y no la del precio: **si el JSON real de EODHD trae `filing_date`**,
es decir fecha de publicación por línea y no solo periodo fiscal. De eso depende
la alternativa de OD-01:

- **con `filing_date`** → point-in-time posible → alternativa (a), P8 viable;
- **sin `filing_date`** → alternativa (b): solo producción con etiqueta «no
  point-in-time», y P8 imposible con esta fuente.

Además comprueba estados financieros (balance, resultados, flujo de caja), ISIN,
EPS, deuda y flujo de caja libre, sobre dos valores europeos del universo
(`SAP.XETRA` y `ASML.AS`).

## Cómo se ejecuta

1. Crear la cuenta gratuita en EODHD y obtener la API key.
2. Añadirla a `.env` como `EODHD_API_KEY=...`. **Nunca al repositorio**: `.env`
   está en `.gitignore` y el sondeo registra la URL con la clave recortada.
3. Ejecutar:

       .venv/bin/python evidence/2026-09-20-OD-01-eodhd-free/sondeo_eodhd.py

Deja `crudo-<simbolo>.json` con la respuesta tal cual y `resultado.md` con el
inventario de campos. Se comprueba contra el JSON crudo, no contra la
documentación del proveedor.

## Lo que hay que distinguir al leerlo

Un campo ausente puede significar dos cosas opuestas, y la conclusión cambia:

- **el proveedor no lo da** → descarta a EODHD para ese uso;
- **este plan no lo da** → no dice nada del proveedor, solo del plan gratuito.

El sondeo separa las dos: un `HTTP 402` o un `403` se informan como restricción
de plan, y un `429` como cuota diaria agotada, no como ausencia del dato.

## Lo que este sondeo no hace

No toca `advisor/`. B-00 (GATE B0) exige la ficha de proveedor antes de que
ninguna fuente externa entre en el sistema, y esta prueba es el material con el
que se escribe esa ficha.
