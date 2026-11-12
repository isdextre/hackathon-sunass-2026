# YakuBot - Hackathon Sunass (Desafío 1)

Consumo diario y alertas de anomalías para clientes especiales.

## Configuración
1. Copia `.env.example` a `.env` y llena tus valores.
2. `pip install -r requirements.txt`

## Orden de ejecución (desde la raíz del proyecto)

```bash
python src/ingest/punto.py                 # une DS01, DS02, DS03
python src/ingest/lecturas.py              # lecturas de telemetría en formato largo
python -m src.features.run_consumo         # consumo diario por medidor
python -m src.external.medidores_geo       # coordenadas de medidores (BD_ESCE)
python -m src.external.renipress           # salud: descarga automática (Datos Abiertos)
python -m src.external.osm                 # lugares: descarga automática (OpenStreetMap)
python -m src.external.escale data/external/Padron_web_20261030/Padron_web.dbf  # colegios (bajado a mano)
python -m src.external.integrar            # base integral
python -m src.features.nocturno            # consumo de madrugada (0-5 am)
python -m src.model.detectar               # bandas, reglas y alertas
python -m src.model.soles                  # soles: valida tarifa, recibos y soles en riesgo
python -m src.simulate.fugas 1259          # simulación de fugas (detección y días)
python -m src.model.salida                 # tablas finales para el agente y el dashboard
python scripts/diccionario.py              # docs/diccionario_datos.xlsx
```

## Tarifas

Las tarifas están en `config/` como CSV (se abren y editan en Excel) y el código las lee de ahí:
`tarifas_volumen.csv` (precio por m³ por vigencia, grupo, categoría y tramo), `tarifas_cargo_fijo.csv`
(cargo fijo e IGV) y `codigos_tarifa.csv` (T01..T05). Si sale una tarifa nueva, se agregan filas con su vigencia.
Incluye la estructura de El Peruano 31.12.2024 (2025 y enero 2026) y la de 23.12.2025 (desde febrero 2026).

## Fuentes externas

| Fuente | Entidad | Acceso | Aporta |
|---|---|---|---|
| Límites distritales | INEI vía GEO Perú/IDEP (repo juaneladio/peru-geojson) | automático | distrito y ubigeo de cada medidor |
| RENIPRESS | SUSALUD, Datos Abiertos | automático (CSV mensual) | hospitales y clínicas cercanos |
| OpenStreetMap | Comunidad OSM, API Overpass | automático | hoteles, mercados, lavanderías, etc. |
| Padrón de IIEE (ESCALE) | MINEDU | manual (la web tiene verificación anti-robots) | colegios, nivel y alumnos |
| Datos hidrometeorológicos | SENAMHI | manual (requiere registro y código) | temperatura y lluvia diaria |
| Feriados y calendario escolar | El Peruano / MINEDU | en código (`src/features/calendario.py`) | tipo de día |

Cada fuente es opcional: `integrar` omite la que falte. El perfil del cliente es una inferencia por cercanía (60 m), no un dato confirmado; del establecimiento solo se guarda tipo y distancia, nunca nombre ni dirección (Ley 29733).

## Para el agente y el dashboard

Leen `data/processed/salida_medidor.csv` (situación de cada medidor hoy, alerta, soles, prioridad y mensaje sugerido) y `salida_diaria.csv` (historial día a día). Cada columna está explicada en `docs/diccionario_datos.xlsx`, que también tiene una hoja sobre qué predice el modelo y qué tan bien detecta.
