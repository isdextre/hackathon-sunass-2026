"""Calcula el consumo diario de todas las lecturas y prueba el caso sin telemetría.

Uso: python -m src.features.run_consumo
Salida: data/processed/consumo_diario.csv
"""
from pathlib import Path

import pandas as pd

from src.features.consumo_diario import consumo_diario
from src.features.limpieza import limpiar_lecturas

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"


def main() -> None:
    lect = pd.read_csv(PROC / "lecturas.csv", parse_dates=["fecha_hora"])
    lect, calidad = limpiar_lecturas(lect)
    calidad.to_csv(PROC / "calidad_medidores.csv", index=False)
    print(f"lecturas descartadas por bajar: {int(calidad['n_bajadas'].sum())}")
    cd = consumo_diario(lect)
    cd.to_csv(PROC / "consumo_diario.csv", index=False)
    print(f"consumo diario: {len(cd)} filas, {cd['medidor'].nunique()} medidores")
    print(cd["consumo_m3"].describe().round(2).to_string())

    # Prueba "sin telemetría": una sola lectura por día (la primera de la mañana, como una foto)
    foto = lect.assign(dia=lect["fecha_hora"].dt.normalize()).groupby(["medidor", "dia"]).head(1)
    cd_foto = consumo_diario(foto)
    # Comparar consumo semanal (con 1 lectura/día el corte diario se desplaza; por semana se compensa)
    def semanal(df):
        df = df.assign(semana=pd.to_datetime(df["fecha"]).dt.to_period("W"))
        return df.groupby(["medidor", "semana"])["consumo_m3"].sum()
    comp = pd.concat([semanal(cd).rename("telemetria"), semanal(cd_foto).rename("foto")], axis=1).dropna()
    comp = comp[comp["telemetria"] > 0]
    err = (comp["foto"] - comp["telemetria"]).abs() / comp["telemetria"]
    print(f"\nPrueba 1 lectura/día vs telemetría (semanal): error mediano {err.median():.1%}, p90 {err.quantile(0.9):.1%}")


if __name__ == "__main__":
    main()
