"""Clima diario de Lima.

Fuente principal: SENAMHI (estación Campo de Marte u otra de Lima). SENAMHI exige
registro y código de verificación, así que el archivo se descarga a mano desde
https://www.senamhi.gob.pe/?&p=descarga-datos-hidrometeorologicos
Formato: texto separado por espacios -> año mes día precipitación tmax tmin (-99.9 = sin dato).

Uso: python -m src.external.clima data/external/senamhi_campo_de_marte.txt
     python -m src.external.clima --open-meteo 2026-08-01 2026-10-31   (respaldo, ver nota)

Nota: Open-Meteo NO está en la lista de fuentes del expediente; úsalo solo como respaldo
y declárelo en la presentación.
Salida: data/external/clima_lima.csv -> fecha, tmax, tmin, precip_mm, fuente
"""
import sys

import numpy as np
import pandas as pd
import requests

from src.external.comun import EXT, UA

SALIDA = EXT / "clima_lima.csv"


def senamhi(archivo: str) -> pd.DataFrame:
    df = pd.read_csv(archivo, sep=r"\s+", header=None, comment="#",
                     names=["anio", "mes", "dia", "precip_mm", "tmax", "tmin"], usecols=range(6))
    df = df.replace(-99.9, np.nan)
    df["fecha"] = pd.to_datetime(dict(year=df.anio, month=df.mes, day=df.dia), errors="coerce").dt.date
    df["fuente"] = "senamhi"
    return df.dropna(subset=["fecha"])[["fecha", "tmax", "tmin", "precip_mm", "fuente"]]


def open_meteo(inicio: str, fin: str, lat: float = -12.07, lon: float = -77.04) -> pd.DataFrame:
    r = requests.get("https://archive-api.open-meteo.com/v1/archive", headers=UA, timeout=60, params={
        "latitude": lat, "longitude": lon, "start_date": inicio, "end_date": fin, "timezone": "America/Lima",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum"})
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.DataFrame({"fecha": pd.to_datetime(d["time"]).date, "tmax": d["temperature_2m_max"],
                         "tmin": d["temperature_2m_min"], "precip_mm": d["precipitation_sum"], "fuente": "open-meteo"})


def main(*args: str) -> pd.DataFrame:
    df = open_meteo(args[1], args[2]) if args[0] == "--open-meteo" else senamhi(args[0])
    df.to_csv(SALIDA, index=False)
    print(f"clima: {len(df)} días ({df['fuente'].iloc[0]}), tmax media {df['tmax'].mean():.1f} °C")
    return df


if __name__ == "__main__":
    main(*sys.argv[1:])
