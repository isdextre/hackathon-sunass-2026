"""Simulación de fugas para medir el detector.

Toma medidores reales SIN ninguna alerta en el periodo evaluado, les inyecta una fuga
artificial (caudal constante desde un momento conocido) o congela su medidor, y corre
exactamente el mismo detector. Como se sabe dónde y cuándo empezó el problema, se mide:
  - % detectado antes del fin del periodo
  - días hasta la primera alerta
La inyección se hace sobre las LECTURAS crudas (índice acumulado) y se redondea a m³
enteros como el medidor real, así la simulación sufre la misma resolución que los datos.

Uso: python -m src.simulate.fugas [n_medidores]     (por defecto 300)
Salidas en data/processed/:
  simulacion_casos.csv     un caso por medidor x escenario, con si se detectó y cuándo
  simulacion_resumen.csv   tasa de detección y días por escenario
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.calendario import agregar_calendario
from src.features.consumo_diario import consumo_diario
from src.features.limpieza import limpiar_lecturas
from src.features.nocturno import consumo_nocturno
from src.model.bandas import entrenar
from src.model.detectar import VENTANA, cargar, diagnosticar

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"
CORTE = pd.Timestamp("2026-09-30")              # fin del entrenamiento
INICIO_FUGA = ("2026-10-06", "2026-10-18")       # la fuga empieza en algún momento de este rango
FUGAS_M3H = [0.05, 0.1, 0.25, 0.5, 1.0]          # caudal de fuga en m³/hora (1.2 a 24 m³/día)
SEMILLA = 7


def inyectar(lect: pd.DataFrame, inicio: dict, escenario: str, q: float = 0.0) -> pd.DataFrame:
    """lect: lecturas de los medidores elegidos. inicio: medidor -> Timestamp de inicio."""
    l = lect.copy()
    t0 = l["medidor"].map(inicio)
    despues = l["fecha_hora"] >= t0
    if escenario == "fuga":
        horas = (l["fecha_hora"] - t0).dt.total_seconds() / 3600
        l.loc[despues, "lectura_m3"] = np.floor(l.loc[despues, "lectura_m3"] + q * horas[despues])
    elif escenario == "detenido":
        congelado = l[~despues].groupby("medidor")["lectura_m3"].last()
        l.loc[despues, "lectura_m3"] = l.loc[despues, "medidor"].map(congelado)
    return l


def diagnosticar_lecturas(l: pd.DataFrame, perfil: pd.DataFrame, bandas: pd.DataFrame) -> pd.DataFrame:
    cd = agregar_calendario(consumo_diario(l))
    noc = consumo_nocturno(l)
    df = cd.merge(noc, on=["medidor", "fecha"], how="left").merge(perfil, on="medidor", how="left")
    df["fecha"] = pd.to_datetime(df["fecha"])
    d = diagnosticar(df[df["fecha"] > CORTE - pd.Timedelta(days=VENTANA)], bandas)
    return d[d["fecha"] > CORTE]


def main(n: str = "300") -> None:
    rng = np.random.default_rng(SEMILLA)
    base = cargar()
    bandas = entrenar(base[base["fecha"] <= CORTE])
    perfil = (base[["medidor", "perfil_probable", "criticidad", "distrito"]].drop_duplicates("medidor"))

    # Medidores limpios: con banda y sin ninguna alerta en el periodo evaluado
    diag = pd.read_csv(PROC / "diagnostico_diario.csv", usecols=["medidor", "tipo_alerta"])
    con_alerta = set(diag.loc[diag["tipo_alerta"].notna(), "medidor"])
    limpios = sorted(set(diag["medidor"]) - con_alerta)
    elegidos = list(rng.choice(limpios, size=min(int(n), len(limpios)), replace=False))
    print(f"medidores limpios: {len(limpios)}, simulados: {len(elegidos)}")

    lect = pd.read_csv(PROC / "lecturas.csv", parse_dates=["fecha_hora"])
    lect = limpiar_lecturas(lect[lect["medidor"].isin(elegidos)])[0]
    lect = lect[lect["fecha_hora"] >= CORTE - pd.Timedelta(days=VENTANA + 2)]

    a, b = (pd.Timestamp(x).value for x in INICIO_FUGA)
    inicio = {m: pd.Timestamp(rng.integers(a, b)).floor("h") for m in elegidos}
    p50 = bandas[bandas["tipo_dia"] == "laborable"].set_index("medidor")["p50"]

    # Control: los mismos medidores sin tocar (debe dar 0 alertas: así se eligieron)
    escenarios = [("control", 0.0)] + [("fuga", q) for q in FUGAS_M3H] + [("detenido", 0.0)]
    casos = []
    for esc, q in escenarios:
        d = diagnosticar_lecturas(inyectar(lect, inicio, esc, q), perfil, bandas)
        d["inicio"] = d["medidor"].map(inicio).dt.normalize()
        al = d[d["tipo_alerta"].notna() & (d["fecha"] >= d["inicio"])]
        primera = al.sort_values("fecha").groupby("medidor").first()
        c = pd.DataFrame({"medidor": elegidos})
        c["escenario"], c["fuga_m3h"] = esc, q
        c["inicio"] = c["medidor"].map(inicio)
        c = c.merge(primera[["tipo_alerta", "fecha"]].rename(columns={"fecha": "fecha_alerta"}),
                    left_on="medidor", right_index=True, how="left")
        c["detectado"] = c["fecha_alerta"].notna()
        c["dias_a_alerta"] = (pd.to_datetime(c["fecha_alerta"]) - c["inicio"].dt.normalize()).dt.days
        c["consumo_p50_m3d"] = c["medidor"].map(p50)
        c["fuga_vs_consumo"] = (q * 24 / c["consumo_p50_m3d"].replace(0, np.nan)).round(2)
        casos.append(c)
        print(f"{esc:9s} q={q:<5} detectado {c['detectado'].mean():6.1%} | "
              f"días mediana {c['dias_a_alerta'].median()}")
    casos = pd.concat(casos, ignore_index=True)
    casos.to_csv(PROC / "simulacion_casos.csv", index=False)

    res = casos.groupby(["escenario", "fuga_m3h"]).agg(
        casos=("detectado", "size"), detectado=("detectado", "mean"),
        dias_mediana=("dias_a_alerta", "median"), dias_p90=("dias_a_alerta", lambda s: s.quantile(0.9)),
    ).reset_index()
    res["fuga_m3_dia"] = res["fuga_m3h"] * 24
    res.to_csv(PROC / "simulacion_resumen.csv", index=False)

    # Detección según el tamaño de la fuga frente al consumo normal del cliente
    f = casos[casos["escenario"] == "fuga"].copy()
    f["fuga_relativa"] = pd.cut(f["fuga_vs_consumo"], [0, 0.1, 0.25, 0.5, 1, np.inf],
                                labels=["<10%", "10-25%", "25-50%", "50-100%", ">100%"])
    print("\nDetección según tamaño de la fuga vs su consumo normal:")
    print(f.groupby("fuga_relativa", observed=True)["detectado"].agg(["size", "mean"]).round(2).to_string())


if __name__ == "__main__":
    main(*sys.argv[1:])
