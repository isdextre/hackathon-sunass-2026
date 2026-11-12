"""Consumo diario (m³) por medidor a partir de lecturas acumuladas.

Funciona con cualquier densidad de lecturas (telemetría cada ~3 h o fotos
una vez al día): el índice se interpola a las 00:00 de cada día y el
consumo del día es la diferencia entre medianoches consecutivas.
"""
import numpy as np
import pandas as pd


def segundos(x) -> np.ndarray:
    """Fechas a segundos, sin depender de la resolución interna de pandas (ns o us)."""
    return np.asarray(pd.to_datetime(x).to_numpy(), dtype="datetime64[s]").astype("int64").astype(float)


def consumo_diario(lecturas: pd.DataFrame) -> pd.DataFrame:
    """lecturas: columnas medidor, fecha_hora, lectura_m3 (y opcional fuente).
    Devuelve medidor, fecha, consumo_m3, n_lecturas (lecturas usadas en el día).
    """
    salida = []
    for medidor, g in lecturas.sort_values("fecha_hora").groupby("medidor"):
        t = segundos(g["fecha_hora"])
        v = g["lectura_m3"].to_numpy(dtype=float)
        if len(t) < 2:
            continue
        dias = pd.date_range(g["fecha_hora"].min().normalize(), g["fecha_hora"].max().normalize(), freq="D")
        medianoches = segundos(dias)
        # Índice acumulado en cada medianoche (interpolación lineal, solo entre lecturas reales)
        en_rango = (medianoches >= t[0]) & (medianoches <= t[-1])
        idx = np.full(len(dias), np.nan)
        idx[en_rango] = np.interp(medianoches[en_rango], t, v)
        consumo = np.diff(idx)  # consumo entre medianoche i y i+1 -> día i
        n_lect = np.histogram(t, bins=np.append(medianoches, medianoches[-1] + 86400))[0][:-1]
        for i, c in enumerate(consumo):
            if np.isnan(c):
                continue
            salida.append((medidor, dias[i].date(), round(float(c), 3), int(n_lect[i]) if i < len(n_lect) else 0))
    return pd.DataFrame(salida, columns=["medidor", "fecha", "consumo_m3", "n_lecturas"])
