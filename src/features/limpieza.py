"""Limpieza de lecturas acumuladas.

El índice del medidor solo puede subir. En los datos hay lecturas sueltas que bajan
y luego vuelven (0.65 % del total, en ~400 medidores): son errores de transmisión o
flujo inverso momentáneo. Se descartan las lecturas por debajo del máximo previo y se
cuenta cuántas hubo por medidor, como indicador de calidad del dato.
"""
import pandas as pd


def limpiar_lecturas(lecturas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (lecturas limpias, calidad por medidor)."""
    l = lecturas.sort_values(["medidor", "fecha_hora"])
    prev_max = l.groupby("medidor")["lectura_m3"].transform(lambda s: s.cummax().shift())
    baja = l["lectura_m3"] < prev_max
    calidad = (l.assign(baja=baja).groupby("medidor")
                .agg(n_lecturas=("baja", "size"), n_bajadas=("baja", "sum")).reset_index())
    calidad["pct_bajadas"] = (calidad["n_bajadas"] / calidad["n_lecturas"]).round(4)
    return l[~baja], calidad
