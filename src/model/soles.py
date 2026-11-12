"""Motor de soles: convierte m³ en importe con la estructura tarifaria de Sedapal.

Las tarifas NO están en el código: se leen de config/ (se abren y editan en Excel):
  tarifas_volumen.csv     precio por m³ de agua y saneamiento, por vigencia, grupo, categoría y tramo
  tarifas_cargo_fijo.csv  cargo fijo mensual e IGV por vigencia
  codigos_tarifa.csv      T01..T05 -> categoría
Si Sedapal publica una tarifa nueva, se agregan filas con su vigencia y no se toca el código.

Cálculo (expediente, sección 5.5 y ejemplos de DS04):
  - el consumo del mes se reparte por tramos y cada tramo paga su precio (escalonado)
  - saneamiento solo si la conexión tiene ese servicio
  - IGV 18 % sobre cargo fijo + agua + saneamiento
  - Grupo 2: Punta Negra, Punta Hermosa, San Bartolo y Santa María del Mar; el resto Grupo 1

Uso: python -m src.model.soles
  1. Prueba los 3 ejemplos oficiales del recibo (10, 15 y 25 m³ doméstico).
  2. Valida contra los importes reales de DS01 (2025 y 2026).
  3. Pone soles a las alertas y calcula el recibo de cada medidor por mes.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
PROC = ROOT / "data" / "processed"
DISTRITOS_GRUPO2 = {"PUNTA NEGRA", "PUNTA HERMOSA", "SAN BARTOLO", "SANTA MARIA DEL MAR", "SANTA MARÍA DEL MAR"}


@lru_cache(maxsize=1)
def tarifas() -> tuple[pd.DataFrame, pd.DataFrame]:
    vol = pd.read_csv(CONFIG / "tarifas_volumen.csv", parse_dates=["vigencia_desde", "vigencia_hasta"])
    fijo = pd.read_csv(CONFIG / "tarifas_cargo_fijo.csv", parse_dates=["vigencia_desde", "vigencia_hasta"])
    for t in (vol, fijo):
        t["vigencia_hasta"] = t["vigencia_hasta"].fillna(pd.Timestamp("2100-01-01"))
    vol["hasta_m3"] = vol["hasta_m3"].fillna(np.inf)
    return vol, fijo


def grupo_de(distrito) -> int:
    return 2 if str(distrito).strip().upper() in DISTRITOS_GRUPO2 else 1


def importe(m3: float, categoria: str, periodo, grupo: int = 1, saneamiento: bool = True) -> dict:
    """Recibo de un mes. periodo: cualquier fecha dentro del mes facturado."""
    vol, fijo = tarifas()
    f = pd.Timestamp(periodo)
    t = vol[(vol["categoria"] == categoria) & (vol["grupo"] == grupo)
            & (vol["vigencia_desde"] <= f) & (vol["vigencia_hasta"] >= f)].sort_values("desde_m3")
    if t.empty:
        raise ValueError(f"Sin tarifa para {categoria}, grupo {grupo}, {f.date()}")
    cf = fijo[(fijo["vigencia_desde"] <= f) & (fijo["vigencia_hasta"] >= f)].iloc[0]
    m3_tramo = np.clip(m3 - t["desde_m3"].to_numpy(), 0, (t["hasta_m3"] - t["desde_m3"]).to_numpy())
    agua = float(np.round(m3_tramo * t["agua"].to_numpy(), 2).sum())
    sane = float(np.round(m3_tramo * t["saneamiento"].to_numpy(), 2).sum()) if saneamiento else 0.0
    igv = round((cf["cargo_fijo"] + agua + sane) * cf["igv"], 2)
    total = round(cf["cargo_fijo"] + agua + sane + igv, 2)
    return {"agua": round(agua, 2), "saneamiento": round(sane, 2), "cargo_fijo": cf["cargo_fijo"],
            "igv": igv, "total": total}


def importe_vec(m3: np.ndarray, categoria: str, periodo, grupo: int = 1) -> tuple[np.ndarray, float]:
    """Versión rápida para muchos valores de una misma categoría, grupo y mes.
    Devuelve (total con IGV, cargo fijo con IGV)."""
    vol, fijo = tarifas()
    f = pd.Timestamp(periodo)
    t = vol[(vol["categoria"] == categoria) & (vol["grupo"] == grupo)
            & (vol["vigencia_desde"] <= f) & (vol["vigencia_hasta"] >= f)].sort_values("desde_m3")
    cf = fijo[(fijo["vigencia_desde"] <= f) & (fijo["vigencia_hasta"] >= f)].iloc[0]
    x = np.asarray(m3, dtype=float)[:, None]
    tramo = np.clip(x - t["desde_m3"].to_numpy(), 0, (t["hasta_m3"] - t["desde_m3"]).to_numpy())
    precio = (t["agua"] + t["saneamiento"]).to_numpy()
    total = (cf["cargo_fijo"] + (tramo * precio).sum(axis=1)) * (1 + cf["igv"])
    return total.round(2), round(cf["cargo_fijo"] * (1 + cf["igv"]), 2)


def costo_extra(m3_base: float, m3_extra: float, categoria: str, periodo, grupo: int = 1) -> float:
    """Cuánto más paga en el mes por m3_extra sobre su consumo normal (con IGV, respeta tramos)."""
    return round(importe(m3_base + m3_extra, categoria, periodo, grupo)["total"]
                 - importe(m3_base, categoria, periodo, grupo)["total"], 2)


def proyectar_recibo(consumo_dias: pd.Series, dias_mes: int) -> float:
    """m³ proyectados al cierre: lo consumido + promedio de los últimos 7 días x días que faltan."""
    faltan = max(dias_mes - len(consumo_dias), 0)
    return float(consumo_dias.sum() + consumo_dias.tail(7).mean() * faltan)


# ---------- categoría de los medidores de telemetría (no viene en los datos) ----------
def categoria_supuesta(perfil: pd.DataFrame) -> pd.Series:
    """SUPUESTO declarado: colegio público y salud pública -> estatal; el resto -> comercial.
    Según el expediente, 58 % de los clientes especiales con telemetría son comerciales y 36 % estatales."""
    gestion = perfil.get("colegio_gestion", pd.Series(index=perfil.index, dtype=object)).astype(str).str.upper()
    inst = perfil.get("salud_institucion", pd.Series(index=perfil.index, dtype=object)).astype(str).str.upper()
    colegio_pub = perfil["perfil_probable"].eq("educacion") & gestion.str.startswith("PÚBLICA")
    salud_pub = perfil["perfil_probable"].eq("salud") & ~inst.str.contains("PRIVAD", na=False)
    return pd.Series(np.where(colegio_pub | salud_pub, "estatal", "comercial"), index=perfil.index)


# ---------- validaciones ----------
def probar_ejemplos() -> None:
    """Ejemplos oficiales (Parte 2 C-Ejemplo.pdf, tarifa 23.12.2025, Grupo 1)."""
    for m3, esperado in [(10, 49.68), (15, 72.33), (25, 125.67)]:
        r = importe(m3, "domestico", "2026-03-01")["total"]
        assert abs(r - esperado) < 0.02, f"{m3} m³: {r} != {esperado}"
    print("ejemplos oficiales del recibo: OK (10, 15 y 25 m³ = 49.68, 72.33, 125.67)")


def validar_ds01(path: Path = ROOT / "01 GESTIÓN COMERCIAL INFORMACION" / "DS01.xlsx") -> pd.DataFrame:
    """DS01 trae por mes el consumo y los importes de agua y alcantarillado (sin cargo fijo ni IGV)."""
    raw = pd.read_excel(path, sheet_name="DataSets", header=None)
    cab, datos = raw.iloc[2].tolist(), raw.iloc[3:].dropna(how="all")
    mitad = cab.index("tarifa", 4)  # segunda columna "tarifa": empieza el bloque 2026
    cod = pd.read_csv(CONFIG / "codigos_tarifa.csv").set_index("codigo")["categoria"]
    filas = []
    for _, r in datos.iterrows():
        for anio, ini, fin in ((2025, 0, mitad), (2026, mitad, len(cab))):
            bloque = dict(zip(cab[ini:fin], r.iloc[ini:fin]))
            cat = cod.get(str(bloque.get("tarifa", r.iloc[3])).strip())
            for m in range(1, 13):
                m3 = bloque.get(f"m{m}_csmo_f", bloque.get(f"m{m}_2026"))
                agu, alc = bloque.get(f"m{m}_im_agu"), bloque.get(f"m{m}_im_alc")
                if pd.isna(m3) or pd.isna(agu) or cat is None:
                    continue
                calc = importe(float(m3), cat, f"{anio}-{m:02d}-15", grupo_de(r.iloc[2]))
                filas.append((r.iloc[1], anio, m, cat, m3, agu, alc, calc["agua"], calc["saneamiento"]))
    v = pd.DataFrame(filas, columns=["suministro", "anio", "mes", "categoria", "m3", "im_agu_real",
                                     "im_alc_real", "im_agu_calc", "im_alc_calc"])
    v["cuadra"] = ((v["im_agu_real"] - v["im_agu_calc"]).abs() <= 0.05) & \
                  (((v["im_alc_real"] - v["im_alc_calc"]).abs() <= 0.05) | (v["im_alc_real"] == 0))
    return v


# ---------- aplicar a los resultados del modelo ----------
def soles_alertas(perfil: pd.DataFrame, periodo: str) -> pd.DataFrame:
    al = pd.read_csv(PROC / "alertas.csv")
    p = perfil.set_index("medidor")
    al["categoria"] = al["medidor"].map(p["categoria"])
    al["grupo"] = al["distrito"].map(grupo_de)
    base_mes = (al["p50"] * 30).fillna(0)
    al["soles_riesgo_mes"] = [costo_extra(b, e, c, periodo, g) for b, e, c, g in
                              zip(base_mes, al["exceso_m3_30d"].fillna(0), al["categoria"], al["grupo"])]
    # Prioridad: gravedad del tipo x criticidad del cliente x soles en riesgo (escala log)
    peso = al["tipo_alerta"].map({"fuga_continua": 3, "medidor_detenido": 2, "consumo_atipico": 1})
    al["prioridad"] = (peso * al["criticidad"] * np.log1p(al["soles_riesgo_mes"])).round(2)
    return al.sort_values(["vigente", "prioridad"], ascending=False)


def recibos_mensuales(perfil: pd.DataFrame) -> pd.DataFrame:
    cd = pd.read_csv(PROC / "consumo_diario.csv", parse_dates=["fecha"])
    cd["mes"] = cd["fecha"].dt.to_period("M")
    m = cd.groupby(["medidor", "mes"]).agg(m3=("consumo_m3", "sum"), dias=("consumo_m3", "size")).reset_index()
    p = perfil.set_index("medidor")
    m = m[m["medidor"].isin(p.index)]
    m["categoria"] = m["medidor"].map(p["categoria"])
    m["grupo"] = m["medidor"].map(p["distrito"]).map(grupo_de)
    tot = [importe(x, c, per.to_timestamp(), g) for x, c, per, g in zip(m["m3"], m["categoria"], m["mes"], m["grupo"])]
    m = pd.concat([m.reset_index(drop=True), pd.DataFrame(tot)], axis=1)
    m["m3"] = m["m3"].round(2)
    m["mes_completo"] = m["dias"] >= m["mes"].dt.days_in_month - 1
    return m


def main() -> None:
    probar_ejemplos()

    v = validar_ds01()
    print(f"DS01: {v['cuadra'].mean():.1%} de {len(v)} meses cuadran con el importe real (±S/ 0.05)")
    print(v.groupby(["anio", "categoria"])["cuadra"].mean().round(3).to_string())
    v.to_csv(PROC / "validacion_tarifa_ds01.csv", index=False)

    perfil = pd.read_csv(PROC / "medidores_perfil.csv", low_memory=False)
    perfil["categoria"] = categoria_supuesta(perfil)
    perfil[["medidor", "categoria"]].to_csv(PROC / "categoria_supuesta.csv", index=False)
    print(f"categoría supuesta: {perfil['categoria'].value_counts(normalize=True).round(2).to_dict()}")

    rec = recibos_mensuales(perfil)
    rec.to_csv(PROC / "recibos_mensuales.csv", index=False)
    oct_ = rec[(rec["mes"].astype(str) == "2026-10")]
    print(f"recibos: {len(rec)} | octubre: mediana S/ {oct_['total'].median():.2f}, total S/ {oct_['total'].sum():,.0f}")

    al = soles_alertas(perfil, "2026-10-15")
    al.to_csv(PROC / "alertas.csv", index=False)
    vig = al[al["vigente"]]
    print(f"alertas vigentes: {len(vig)}, soles en riesgo al mes S/ {vig['soles_riesgo_mes'].sum():,.0f}")
    print(vig.groupby("tipo_alerta")["soles_riesgo_mes"].agg(["size", "median", "sum"]).round(0).to_string())


if __name__ == "__main__":
    main()
