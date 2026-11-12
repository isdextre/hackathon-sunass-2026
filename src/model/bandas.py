"""Banda de consumo esperado por medidor y tipo de día.

Para cada medidor se aprende, con su propio historial, el rango normal de consumo
en días laborables, sábados y domingos/feriados (percentiles P10, P50, P90), y su
consumo normal de madrugada. Un hospital y un colegio tienen bandas distintas
porque cada uno se compara consigo mismo.

Si un medidor tiene pocos días de un tipo, se usa su banda general como respaldo.
"""
import numpy as np
import pandas as pd

MIN_DIAS_TIPO = 4      # mínimo de días de ese tipo para su propia banda
MIN_DIAS_TOTAL = 10    # mínimo de días para tener banda
N_REFERENCIA = 12      # con menos días de un tipo, el margen se ensancha


def _pct(s: pd.Series) -> pd.Series:
    return pd.Series({"n": s.size, "p10": s.quantile(0.10), "p50": s.median(), "p90": s.quantile(0.90)})


def entrenar(base: pd.DataFrame) -> pd.DataFrame:
    """base: medidor, tipo_dia, consumo_m3, consumo_noche_m3 (periodo de entrenamiento).
    Devuelve una fila por medidor x tipo_dia con la banda."""
    # En colegios, los laborables sin clases (vacaciones) no son "normales": bajarían la banda
    # y los días con clases saldrían como atípicos. Se excluyen del entrenamiento.
    if {"perfil_probable", "sin_clases_escolares"} <= set(base.columns):
        vac_colegio = (base["perfil_probable"].eq("educacion") & base["tipo_dia"].eq("laborable")
                       & base["sin_clases_escolares"].astype(str).str.lower().eq("true"))
        base = base[~vac_colegio]
    por_tipo = base.groupby(["medidor", "tipo_dia"])["consumo_m3"].apply(_pct).unstack().reset_index()
    general = base.groupby("medidor")["consumo_m3"].apply(_pct).unstack().add_prefix("g_").reset_index()
    tipos = pd.MultiIndex.from_product([general["medidor"], ["laborable", "sabado", "domingo_feriado"]],
                                       names=["medidor", "tipo_dia"]).to_frame(index=False)
    b = tipos.merge(por_tipo, how="left").merge(general, on="medidor")
    b = b[b["g_n"] >= MIN_DIAS_TOTAL].copy()
    pocos = b["n"].fillna(0) < MIN_DIAS_TIPO
    for c in ("p10", "p50", "p90"):
        b.loc[pocos, c] = b.loc[pocos, f"g_{c}"]
    b["banda_respaldo"] = pocos
    # Margen sobre el P90: nunca menos de 1 m³ (resolución de las lecturas) y más ancho
    # cuando hay pocos días de ese tipo (sábados y domingos tienen 4 a 10 días), porque un
    # P90 con pocas muestras subestima el rango real.
    n_ef = b["n"].where(~pocos, b["g_n"]).astype(float)
    inflar = np.maximum(1.0, np.sqrt(N_REFERENCIA / n_ef))
    b["limite_sup"] = b["p90"] + np.maximum(1.0, 0.5 * (b["p90"] - b["p10"])) * inflar

    noc = base.dropna(subset=["consumo_noche_m3"])
    noche = noc.groupby("medidor")["consumo_noche_m3"].agg(
        noche_p50="median", noche_p90=lambda s: s.quantile(0.9),
        noche_frac_pos=lambda s: (s > 0).mean()).reset_index()
    # Ritmo de madrugada / ritmo del día en su historial. Muchos clientes son "planos" por
    # naturaleza (cisternas que llenan de noche, operación 24 h): solo alarma un cambio.
    tot = noc.groupby("medidor")[["consumo_noche_m3", "consumo_m3"]].sum()
    noche["ratio_noche_hist"] = noche["medidor"].map(
        (tot["consumo_noche_m3"] / 5) / (tot["consumo_m3"] / 24).replace(0, np.nan))
    b = b.merge(noche, on="medidor", how="left")
    return b[["medidor", "tipo_dia", "n", "p10", "p50", "p90", "limite_sup", "banda_respaldo",
              "noche_p50", "noche_p90", "noche_frac_pos", "ratio_noche_hist"]].round(3)
