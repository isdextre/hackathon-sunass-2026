"""Detección de anomalías: compara cada día con la banda del medidor y aplica reglas físicas.

Uso: python -m src.model.detectar [fin_entrenamiento]   (por defecto 2026-09-30)
     Entrena con los días hasta esa fecha y evalúa los días siguientes.

Tipos de alerta (de más grave a menos):
  fuga_continua     la madrugada (0-5 am) consume más que su historial casi todas las noches
                    de la última semana: patrón típico de fuga después del medidor
  medidor_detenido  7 días seguidos en cero en un medidor que normalmente consume
  consumo_atipico   3 días seguidos por encima de su banda, o 1 día al triple del límite

No hay alerta por "consumo plano" (madrugada al ritmo del día): en estos datos el 22 % de
los medidores ya es plano en su historial (cisternas que llenan de noche, operación 24 h),
como advierte el expediente. Se marca como dato informativo `operacion_24h` y solo alerta
si la madrugada SUBE respecto a su propio historial (fuga_continua).

Salidas en data/processed/:
  bandas.csv               banda por medidor y tipo de día
  diagnostico_diario.csv   cada medidor y día del periodo evaluado, con banda y estado
  alertas.csv              una fila por medidor con su alerta vigente más reciente y prioridad
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.model.bandas import entrenar

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"
VENTANA = 7
PRIORIDAD_TIPO = {"fuga_continua": 3, "medidor_detenido": 2, "consumo_atipico": 1}


def cargar() -> pd.DataFrame:
    base = pd.read_csv(PROC / "base_diaria.csv", low_memory=False, parse_dates=["fecha"])
    noc = pd.read_csv(PROC / "consumo_nocturno.csv", parse_dates=["fecha"])
    return base.merge(noc, on=["medidor", "fecha"], how="left")


def _rolling(d: pd.DataFrame, col: str, n: int, f: str, min_periods: int) -> pd.Series:
    r = d.groupby("medidor")[col].rolling(n, min_periods=min_periods)
    return getattr(r, f)().reset_index(level=0, drop=True)


def diagnosticar(df: pd.DataFrame, bandas: pd.DataFrame) -> pd.DataFrame:
    d = df.merge(bandas, on=["medidor", "tipo_dia"], how="inner").sort_values(["medidor", "fecha"])
    d = d.reset_index(drop=True)

    # Banda diaria
    d["sobre_banda"] = d["consumo_m3"] > d["limite_sup"]
    d["muy_sobre_banda"] = d["consumo_m3"] > 3 * d["limite_sup"]
    d["exceso_m3"] = (d["consumo_m3"] - d["p50"]).clip(lower=0).where(d["sobre_banda"], 0.0)

    # Madrugada: ¿subió respecto a su propia historia?
    d["noche_alta"] = (d["consumo_noche_m3"] > d["noche_p90"].fillna(0) + 0.5).astype(float)
    d.loc[d["consumo_noche_m3"].isna(), "noche_alta"] = np.nan
    # Ritmo de madrugada vs ritmo del día (m³/h)
    ritmo_dia = (d["consumo_m3"] / 24).replace(0, np.nan)
    d["ratio_noche_dia"] = (d["consumo_noche_m3"] / 5) / ritmo_dia

    d["noches_altas_7d"] = _rolling(d, "noche_alta", VENTANA, "sum", 5)
    d["ratio_noche_7d"] = _rolling(d, "ratio_noche_dia", VENTANA, "median", 5)
    d["consumo_7d"] = _rolling(d, "consumo_m3", VENTANA, "mean", 5)
    d["es_cero"] = (d["consumo_m3"] == 0).astype(float)
    d["ceros_7d"] = _rolling(d, "es_cero", VENTANA, "sum", VENTANA)
    d["sobre_int"] = d["sobre_banda"].astype(float)
    d["sobre_3d"] = _rolling(d, "sobre_int", 3, "sum", 3)
    d["operacion_24h"] = d["ratio_noche_hist"] >= 0.8

    p50_max = d.groupby("medidor")["p50"].transform("max")
    reglas = {
        "fuga_continua": d["noches_altas_7d"] >= 6,
        "medidor_detenido": (d["ceros_7d"] >= VENTANA) & (p50_max >= 1),
        "consumo_atipico": (d["sobre_3d"] >= 3) | d["muy_sobre_banda"],
    }
    d["tipo_alerta"] = pd.Series(pd.NA, index=d.index, dtype="object")
    for tipo in reversed(list(reglas)):  # la más grave sobrescribe
        d.loc[reglas[tipo].fillna(False).astype(bool), "tipo_alerta"] = tipo
    d["estado"] = np.where(d["tipo_alerta"].notna(), "alerta", np.where(d["sobre_banda"], "sobre_banda", "normal"))
    return d.drop(columns=["es_cero", "sobre_int"])


def resumen_alertas(d: pd.DataFrame) -> pd.DataFrame:
    """Alerta vigente por medidor (la del último día con alerta) y exceso estimado."""
    al = d[d["tipo_alerta"].notna()]
    ultima = al.sort_values("fecha").groupby("medidor").tail(1)
    agg = al.groupby("medidor").agg(dias_en_alerta=("fecha", "size"), primera_alerta=("fecha", "min"))
    # Exceso diario (conservador, sin extrapolar):
    #   fuga y atípico: promedio de la semana sobre su mediana; en fugas, al menos lo que
    #                   la madrugada consume de más (medido en 5 h)
    #   medidor detenido: lo que normalmente consume y ahora no se registra ni se factura
    exceso_noche = (ultima["consumo_noche_m3"] - ultima["noche_p50"].fillna(0)).clip(lower=0)
    exceso_dia = (ultima["consumo_7d"] - ultima["p50"]).clip(lower=0)
    tipo = ultima["tipo_alerta"]
    exceso = np.select([tipo.eq("fuga_continua"), tipo.eq("medidor_detenido")],
                       [np.maximum(exceso_dia, exceso_noche), ultima["p50"]], exceso_dia)
    ultima = ultima.assign(exceso_m3_dia=np.round(exceso, 2))
    out = ultima.merge(agg, on="medidor")
    # Vigente: la alerta sigue activa en el último día con datos de ese medidor
    ultimo_dia = d.groupby("medidor")["fecha"].max()
    out["vigente"] = out["fecha"].eq(out["medidor"].map(ultimo_dia))
    out["exceso_m3_30d"] = (out["exceso_m3_dia"] * 30).round(1)
    out["prioridad"] = (out["tipo_alerta"].map(PRIORIDAD_TIPO) * out["criticidad"]
                        * np.log1p(out["exceso_m3_30d"])).round(2)
    cols = ["medidor", "tipo_alerta", "vigente", "fecha", "primera_alerta", "dias_en_alerta", "consumo_m3", "p50", "limite_sup",
            "consumo_noche_m3", "noche_p50", "ratio_noche_7d", "exceso_m3_dia", "exceso_m3_30d",
            "perfil_probable", "operacion_24h", "criticidad", "distrito", "prioridad"]
    return out[cols].rename(columns={"fecha": "ultima_alerta"}).sort_values(["vigente", "prioridad"], ascending=False)


def main(fin_entrenamiento: str = "2026-09-30") -> None:
    df = cargar()
    corte = pd.Timestamp(fin_entrenamiento)
    entreno = df[df["fecha"] <= corte]
    bandas = entrenar(entreno)
    bandas.to_csv(PROC / "bandas.csv", index=False)

    # Las ventanas de 7 días usan los últimos días del entrenamiento como contexto
    ctx = df[df["fecha"] > corte - pd.Timedelta(days=VENTANA)]
    d = diagnosticar(ctx, bandas)
    d = d[d["fecha"] > corte]
    d.to_csv(PROC / "diagnostico_diario.csv", index=False)
    alertas = resumen_alertas(d)
    alertas.to_csv(PROC / "alertas.csv", index=False)

    n_med = d["medidor"].nunique()
    print(f"bandas: {bandas['medidor'].nunique()} medidores ({bandas['banda_respaldo'].mean():.0%} con banda de respaldo)")
    print(f"evaluado: {d['fecha'].min().date()} a {d['fecha'].max().date()}, {n_med} medidores")
    print(f"días fuera de banda: {d['sobre_banda'].mean():.1%} | medidores con alerta: {len(alertas)} ({len(alertas)/n_med:.1%})")
    print(pd.crosstab(alertas["tipo_alerta"], alertas["vigente"].map({True: "vigente", False: "resuelta"})).to_string())


if __name__ == "__main__":
    main(*sys.argv[1:])
