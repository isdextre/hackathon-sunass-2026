"""Coordenadas de los medidores con telemetría (hoja BD_ESCE).

Salida: data/processed/medidores_geo.csv -> medidor, suministro, lat, lon, fecha_registro
"""
import sys

import pandas as pd

from src.external.comun import PROC, ROOT, num

XLSX = "01 GESTIÓN COMERCIAL INFORMACION/Lecturas de medidores.xlsx"


def main(xlsx: str = XLSX) -> pd.DataFrame:
    bd = pd.read_excel(ROOT / xlsx, sheet_name="BD_ESCE", header=1).dropna(subset=["ID MEDIDOR"])
    coords = bd["COORDENADAS"].astype("string").str.split(",", n=1, expand=True)
    geo = pd.DataFrame({
        "medidor": bd["ID MEDIDOR"].astype(str).str.strip().str.upper(),
        "suministro": bd["Suministro"].astype(str).str.strip(),
        "lat": num(coords[0]),
        "lon": num(coords[1]),
        "fecha_registro": pd.to_datetime(bd["FECHA DE REGISTRO"], errors="coerce"),
    }).dropna(subset=["lat", "lon"]).drop_duplicates("medidor")
    geo.to_csv(PROC / "medidores_geo.csv", index=False)
    print(f"medidores con coordenadas: {len(geo)}")
    return geo


if __name__ == "__main__":
    main(*sys.argv[1:])
