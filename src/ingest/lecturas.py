"""Convierte 'Lecturas de medidores.xlsx' al formato largo único.

Salida: data/processed/lecturas.csv con columnas
    medidor, fecha_hora, lectura_m3, fuente
"""
import sys
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
SHEETS = ["agosto", "setiembre", "octubre"]


def leer_hoja(wb, nombre: str) -> pd.DataFrame:
    filas = []
    for i, r in enumerate(wb[nombre].iter_rows(values_only=True)):
        if i < 2 or r[4] is None:  # saltar encabezados y filas vacías
            continue
        filas.append((r[1], r[3], r[4]))
    df = pd.DataFrame(filas, columns=["medidor", "lectura_m3", "fecha_hora"])
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
    df["medidor"] = df["medidor"].astype(str).str.strip().str.upper()
    return df.dropna(subset=["fecha_hora", "lectura_m3"])


def main(xlsx: str = "01 GESTIÓN COMERCIAL INFORMACION/Lecturas de medidores.xlsx") -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(ROOT / xlsx, read_only=True)
    df = pd.concat([leer_hoja(wb, s) for s in SHEETS], ignore_index=True)
    df["fuente"] = "telemetria"
    df = df.drop_duplicates(["medidor", "fecha_hora"]).sort_values(["medidor", "fecha_hora"])
    df.to_csv(PROC / "lecturas.csv", index=False, encoding="utf-8")
    print(f"lecturas: {len(df)} filas, {df['medidor'].nunique()} medidores -> {PROC / 'lecturas.csv'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
