"""Une DS01 (consumo mensual), DS02 (medidores) y DS03 (reclamos) por suministro.

Uso:
    python src/ingest/punto.py "01 GESTIÓN COMERCIAL INFORMACION"

Salida:
    data/processed/maestro_suministros.csv  -> una fila por suministro
    data/processed/reclamos.csv             -> reclamos con su suministro
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"


def norm_key(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.upper()


def load_ds01(path: Path) -> pd.DataFrame:
    # Fila 1 vacía, fila 2 = año, fila 3 = encabezados
    df = pd.read_excel(path, sheet_name="DataSets", header=2)
    df = df.dropna(how="all")
    df = df.rename(columns={"DISTRTITO": "distrito"})
    # El bloque 2026 repite nombres de 2025; pandas los marca con ".1". Los renombramos a *_2026.
    df.columns = [c[:-2] + "_2026" if c.endswith(".1") else c for c in df.columns]
    df["Suministro_publico"] = norm_key(df["Suministro_publico"])
    df["Medidor_publico"] = norm_key(df["Medidor_publico"])
    df = df.dropna(subset=["Suministro_publico"])
    return df


def load_ds02(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=0)
    # La columna "Suministro_publico" aparece dos veces: la 1ª es el medidor (MED-), la 2ª el suministro (SUM-)
    cols = list(df.columns)
    cols[0] = "MeterID"  # MeterID_publico (00-MED-...)
    cols[1] = "Medidor_publico"
    cols[3] = "Suministro_publico"
    df.columns = cols
    df["Suministro_publico"] = norm_key(df["Suministro_publico"])
    df["Medidor_publico"] = norm_key(df["Medidor_publico"])
    keep = ["Suministro_publico", "Medidor_publico", "MeterID", "Meter Type", "Meter Model", "Reading Method"]
    return df[keep].dropna(subset=["Suministro_publico"]).drop_duplicates("Suministro_publico")


def load_ds03(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="BASE_RECLAMOS_SOL", header=0)
    df["Suministro_publico"] = norm_key(df["Suministro_publico"])
    return df.dropna(subset=["Suministro_publico"])


def main(input_dir: str = "01 GESTIÓN COMERCIAL INFORMACION") -> None:
    base = ROOT / input_dir
    PROC.mkdir(parents=True, exist_ok=True)

    d1 = load_ds01(base / "DS01.xlsx")
    d2 = load_ds02(base / "DS02.xlsx")
    d3 = load_ds03(base / "DS03.xlsx")

    s1, s2, s3 = set(d1.Suministro_publico), set(d2.Suministro_publico), set(d3.Suministro_publico)
    print(f"DS01 suministros: {len(s1)} | DS02: {len(s2)} | DS03: {len(s3)}")
    print(f"Cruzan DS01 y DS02: {len(s1 & s2)} | DS01 y DS03: {len(s1 & s3)} | solo DS02 sin DS01: {len(s2 - s1)}")

    # Maestro: una fila por suministro de DS01, con medidor y nº de reclamos
    reclamos_por_sum = d3.groupby("Suministro_publico").size().rename("n_reclamos")
    maestro = (
        d1.merge(d2.drop(columns=["Medidor_publico"]), on="Suministro_publico", how="left", indicator="cruce_ds02")
        .merge(reclamos_por_sum, on="Suministro_publico", how="left")
    )
    maestro["n_reclamos"] = maestro["n_reclamos"].fillna(0).astype(int)
    maestro["cruce_ds02"] = maestro["cruce_ds02"].map({"both": "ok", "left_only": "sin_medidor_en_DS02"})

    maestro.to_csv(PROC / "maestro_suministros.csv", index=False, encoding="utf-8")
    d3.to_csv(PROC / "reclamos.csv", index=False, encoding="utf-8")
    print(f"Guardado: {PROC / 'maestro_suministros.csv'} ({len(maestro)} filas)")
    print(f"Guardado: {PROC / 'reclamos.csv'} ({len(d3)} filas)")


if __name__ == "__main__":
    main(*sys.argv[1:])
