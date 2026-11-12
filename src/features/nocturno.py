"""Consumo de madrugada (00:00 a 05:00) por medidor y día.

Es la señal clave de fuga: si nadie usa agua de madrugada y el medidor avanza,
el agua se está perdiendo. Se interpola el índice acumulado a las 00:00 y 05:00.
Solo se calcula si hay lecturas reales a menos de 4 horas de cada corte, para no
inventar consumo en los huecos de transmisión.

Uso: python -m src.features.nocturno
Salida: data/processed/consumo_nocturno.csv -> medidor, fecha, consumo_noche_m3
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.consumo_diario import segundos
from src.features.limpieza import limpiar_lecturas

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"
INICIO_H, FIN_H, MAX_HUECO_H = 0, 5, 4


def consumo_nocturno(lecturas: pd.DataFrame) -> pd.DataFrame:
    salida = []
    for medidor, g in lecturas.sort_values("fecha_hora").groupby("medidor"):
        t = segundos(g["fecha_hora"]) / 3600  # horas
        v = g["lectura_m3"].to_numpy(dtype=float)
        if len(t) < 2:
            continue
        dias = pd.date_range(g["fecha_hora"].min().normalize(), g["fecha_hora"].max().normalize(), freq="D")
        base = segundos(dias) / 3600
        t0, t1 = base + INICIO_H, base + FIN_H
        ok = (t0 >= t[0]) & (t1 <= t[-1])
        # distancia de cada corte a la lectura real más cercana
        def cerca(x):
            i = np.clip(np.searchsorted(t, x), 1, len(t) - 1)
            return np.minimum(np.abs(t[i] - x), np.abs(t[i - 1] - x)) <= MAX_HUECO_H
        ok &= cerca(t0) & cerca(t1)
        c = np.interp(t1, t, v) - np.interp(t0, t, v)
        salida += [(medidor, d.date(), round(float(x), 3)) for d, x, k in zip(dias, c, ok) if k]
    return pd.DataFrame(salida, columns=["medidor", "fecha", "consumo_noche_m3"])


def main() -> None:
    lect = pd.read_csv(PROC / "lecturas.csv", parse_dates=["fecha_hora"])
    noc = consumo_nocturno(limpiar_lecturas(lect)[0])
    noc.to_csv(PROC / "consumo_nocturno.csv", index=False)
    print(f"consumo nocturno: {len(noc)} noches, {noc['medidor'].nunique()} medidores")
    print(noc["consumo_noche_m3"].describe().round(2).to_string())
    print(f"noches con consumo > 0: {(noc['consumo_noche_m3'] > 0).mean():.0%}")


if __name__ == "__main__":
    main()
