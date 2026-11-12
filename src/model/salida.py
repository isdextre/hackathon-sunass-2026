"""Tablas finales para el agente de WhatsApp y el dashboard (el "contrato" del equipo).

Uso: python -m src.model.salida      (después de detectar y soles)

Salidas en data/processed/:
  salida_diaria.csv    una fila por medidor y día: consumo, banda, madrugada, estado, soles
  salida_medidor.csv   una fila por medidor: su situación al último día con datos,
                       alerta vigente, soles en riesgo, prioridad y mensaje sugerido
Las columnas están explicadas en docs/diccionario_datos.xlsx.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import CORTE_ENTRENAMIENTO
from src.model.soles import grupo_de, importe_vec

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"
CORTE = pd.Timestamp(CORTE_ENTRENAMIENTO)


def tabla_diaria() -> pd.DataFrame:
    base = pd.read_csv(PROC / "base_diaria.csv", low_memory=False, parse_dates=["fecha"])
    noc = pd.read_csv(PROC / "consumo_nocturno.csv", parse_dates=["fecha"])
    bandas = pd.read_csv(PROC / "bandas.csv")
    diag = pd.read_csv(PROC / "diagnostico_diario.csv", low_memory=False, parse_dates=["fecha"],
                       usecols=["medidor", "fecha", "estado", "tipo_alerta"])
    cat = pd.read_csv(PROC / "categoria_supuesta.csv")

    d = (base.merge(noc, on=["medidor", "fecha"], how="left")
             .merge(bandas[["medidor", "tipo_dia", "p10", "p50", "p90", "limite_sup", "noche_p50"]],
                    on=["medidor", "tipo_dia"], how="left")
             .merge(diag, on=["medidor", "fecha"], how="left")
             .merge(cat, on="medidor", how="left"))
    d["periodo_modelo"] = np.where(d["fecha"] > CORTE, "evaluacion", "entrenamiento")
    d.loc[d["periodo_modelo"].eq("entrenamiento"), "estado"] = "historial"
    d.loc[d["estado"].isna(), "estado"] = "sin_banda"
    d["grupo"] = d["distrito"].map(grupo_de)
    d["categoria"] = d["categoria"].fillna("comercial")

    # Acumulado del mes, proyección al cierre y soles
    d = d.sort_values(["medidor", "fecha"]).reset_index(drop=True)
    d["mes"] = d["fecha"].dt.to_period("M")
    g = d.groupby(["medidor", "mes"])["consumo_m3"]
    d["consumo_mes_acum_m3"] = g.cumsum()
    prom7 = g.transform(lambda s: s.rolling(7, min_periods=1).mean())
    faltan = d["fecha"].dt.days_in_month - d["fecha"].dt.day
    d["consumo_mes_proyectado_m3"] = d["consumo_mes_acum_m3"] + prom7 * faltan

    for col in ("soles_mes_acum", "recibo_proyectado_soles", "_fijo"):
        d[col] = np.nan
    for (c, gr, mes), idx in d.groupby(["categoria", "grupo", "mes"]).groups.items():
        acum, fijo = importe_vec(d.loc[idx, "consumo_mes_acum_m3"], c, mes.to_timestamp(), gr)
        proy, _ = importe_vec(d.loc[idx, "consumo_mes_proyectado_m3"], c, mes.to_timestamp(), gr)
        d.loc[idx, "soles_mes_acum"], d.loc[idx, "recibo_proyectado_soles"], d.loc[idx, "_fijo"] = acum, proy, fijo
    variable = d["soles_mes_acum"] - d["_fijo"]
    d["soles_dia"] = variable - variable.groupby([d["medidor"], d["mes"]]).shift(fill_value=0)

    cols = ["medidor", "fecha", "tipo_dia", "es_feriado", "nombre_feriado", "sin_clases_escolares",
            "periodo_modelo", "consumo_m3", "p10", "p50", "p90", "limite_sup", "consumo_noche_m3", "noche_p50",
            "estado", "tipo_alerta", "soles_dia", "consumo_mes_acum_m3", "soles_mes_acum",
            "consumo_mes_proyectado_m3", "recibo_proyectado_soles", "categoria", "grupo",
            "perfil_probable", "criticidad", "distrito"]
    d = d[cols].rename(columns={"p10": "banda_p10_m3", "p50": "banda_p50_m3", "p90": "banda_p90_m3",
                                "limite_sup": "limite_alerta_m3", "noche_p50": "noche_normal_m3"})
    num = d.select_dtypes("number").columns.drop(["grupo", "criticidad"], errors="ignore")
    d[num] = d[num].round(2)
    return d


def mensaje(r: pd.Series) -> str:
    """Texto base para el agente (el LLM lo reescribe en lenguaje natural)."""
    hoy = (f"Ayer consumiste {r.consumo_m3:.1f} m³ (S/ {r.soles_dia:.2f}). En lo que va del mes llevas "
           f"{r.consumo_mes_acum_m3:.0f} m³ y S/ {r.soles_mes_acum:,.2f}; si sigues así tu recibo sería "
           f"de unos S/ {r.recibo_proyectado_soles:,.2f}.")
    if not r.alerta_vigente:
        return hoy
    if r.tipo_alerta == "fuga_continua":
        return (f"Posible fuga: de madrugada (0 a 5 am) tu medidor marca {r.consumo_noche_m3:.1f} m³, cuando lo "
                f"normal para ti es {r.noche_normal_m3:.1f} m³, y lleva {r.dias_en_alerta} días así. Si sigue, "
                f"te costaría unos S/ {r.soles_riesgo_mes:,.0f} más al mes. ¿Puedes cerrar todas las llaves "
                f"y revisar si el medidor sigue girando? " + hoy)
    if r.tipo_alerta == "consumo_atipico":
        return (f"Tu consumo de los últimos días está por encima de lo normal para ti (normal: "
                f"{r.banda_p50_m3:.1f} m³/día). Si sigue así, son unos S/ {r.soles_riesgo_mes:,.0f} más al mes. "
                f"¿Hubo algún cambio en tu operación? " + hoy)
    if r.tipo_alerta == "medidor_detenido":
        return (f"Tu medidor no registra consumo hace {r.dias_en_alerta} días, aunque normalmente consumes "
                f"{r.banda_p50_m3:.1f} m³/día. ¿El local estuvo cerrado? Si no, puede ser una falla del medidor "
                f"y Sedapal la revisará.")
    return hoy


def tabla_medidor(diaria: pd.DataFrame) -> pd.DataFrame:
    al = pd.read_csv(PROC / "alertas.csv")
    geo = pd.read_csv(PROC / "medidores_geo.csv")[["medidor", "lat", "lon"]]
    ult = diaria.sort_values("fecha").groupby("medidor").tail(1).rename(columns={"fecha": "ultima_fecha"})
    m = (ult.merge(geo, on="medidor", how="left")
            .merge(al[["medidor", "tipo_alerta", "vigente", "primera_alerta", "dias_en_alerta",
                       "exceso_m3_dia", "exceso_m3_30d", "soles_riesgo_mes", "prioridad"]]
                   .rename(columns={"tipo_alerta": "tipo_alerta_ultima"}), on="medidor", how="left"))
    m["alerta_vigente"] = m["vigente"].fillna(False).astype(bool)
    # Medidores que dejaron de transmitir: su último dato es anterior al último día de la base
    m["dias_sin_datos"] = (pd.to_datetime(diaria["fecha"]).max() - pd.to_datetime(m["ultima_fecha"])).dt.days
    m["tipo_alerta"] = m["tipo_alerta_ultima"].where(m["alerta_vigente"])
    for c in ("exceso_m3_dia", "exceso_m3_30d", "soles_riesgo_mes", "prioridad"):
        m[c] = m[c].where(m["alerta_vigente"], 0.0)
    m["dias_en_alerta"] = m["dias_en_alerta"].where(m["alerta_vigente"], 0).astype(int)
    m["destinatario"] = np.select([m["tipo_alerta"].eq("medidor_detenido"), m["alerta_vigente"]],
                                  ["cliente_y_sedapal", "cliente_y_sedapal"], "cliente")
    m["ranking_prioridad"] = m["prioridad"].rank(ascending=False, method="first").where(m["alerta_vigente"])
    m["mensaje_sugerido"] = m.apply(mensaje, axis=1)
    cols = ["medidor", "distrito", "lat", "lon", "perfil_probable", "categoria", "grupo", "criticidad",
            "ultima_fecha", "dias_sin_datos", "consumo_m3", "banda_p50_m3", "limite_alerta_m3", "consumo_noche_m3",
            "noche_normal_m3", "consumo_mes_acum_m3", "soles_mes_acum", "recibo_proyectado_soles",
            "alerta_vigente", "tipo_alerta", "primera_alerta", "dias_en_alerta", "exceso_m3_dia",
            "soles_riesgo_mes", "prioridad", "ranking_prioridad", "destinatario", "mensaje_sugerido"]
    return m[cols].sort_values(["alerta_vigente", "prioridad"], ascending=False)


def main() -> None:
    diaria = tabla_diaria()
    diaria.to_csv(PROC / "salida_diaria.csv", index=False)
    med = tabla_medidor(diaria)
    med.to_csv(PROC / "salida_medidor.csv", index=False)
    print(f"salida_diaria: {len(diaria)} filas x {diaria.shape[1]} columnas")
    print(f"salida_medidor: {len(med)} medidores, {int(med['alerta_vigente'].sum())} con alerta vigente")
    print("\nEjemplo de mensaje (prioridad 1):\n" + med.iloc[0]["mensaje_sugerido"])


if __name__ == "__main__":
    main()
