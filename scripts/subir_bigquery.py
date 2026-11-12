"""Sube las tablas finales a BigQuery (reemplaza las anteriores).

Antes, una sola vez:
  1. Instalar Google Cloud CLI: https://cloud.google.com/sdk/docs/install
  2. gcloud auth application-default login
  3. En .env:  GCP_PROJECT=viirs-peru   BQ_DATASET=yakubot   BQ_LOCATION=US
  4. pip install google-cloud-bigquery

Uso: python scripts/subir_bigquery.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

# tabla en BigQuery -> (archivo, columnas de fecha)
TABLAS = {
    "salida_medidor": ("salida_medidor.csv", ["ultima_fecha", "primera_alerta"]),
    "salida_diaria": ("salida_diaria.csv", ["fecha"]),
    "alertas": ("alertas.csv", ["ultima_alerta", "primera_alerta"]),
    "recibos_mensuales": ("recibos_mensuales.csv", []),
}


def main() -> None:
    load_dotenv(ROOT / ".env")
    proyecto = os.environ["GCP_PROJECT"]
    dataset = os.environ.get("BQ_DATASET", "yakubot")
    ubicacion = os.environ.get("BQ_LOCATION", "US")

    cliente = bigquery.Client(project=proyecto)
    print(f"proyecto: {proyecto} | dataset: {dataset} | cuenta: {getattr(cliente._credentials, 'service_account_email', 'usuario de gcloud')}")
    try:
        cliente.get_dataset(f"{proyecto}.{dataset}")  # si ya existe (p. ej. creado en la consola), no lo crea
    except NotFound:
        ds = bigquery.Dataset(f"{proyecto}.{dataset}")
        ds.location = ubicacion
        cliente.create_dataset(ds)
        print(f"dataset {dataset} creado en {ubicacion}")

    for tabla, (archivo, fechas) in TABLAS.items():
        df = pd.read_csv(PROC / archivo, low_memory=False)
        for c in fechas:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
        for c in df.columns:  # texto mixto -> string, para que BigQuery no adivine mal
            if df[c].dtype == object and c not in fechas:
                df[c] = df[c].astype("string")
        destino = f"{proyecto}.{dataset}.{tabla}"
        job = cliente.load_table_from_dataframe(
            df, destino, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"))
        job.result()
        print(f"{destino}: {cliente.get_table(destino).num_rows} filas")


if __name__ == "__main__":
    main()
