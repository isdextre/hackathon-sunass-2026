"""Utilidades compartidas por los conectores externos."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data" / "external"      # descargas crudas de fuentes externas
PROC = ROOT / "data" / "processed"    # tablas limpias
EXT.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

# Caja de Lima Metropolitana y Callao (sur, oeste, norte, este)
BBOX_LIMA = (-12.55, -77.20, -11.70, -76.75)
UA = {"User-Agent": "hackathon-sunass-yakubot/0.1 (uso academico)"}
R_TIERRA = 6_371_000.0


def num(s: pd.Series) -> pd.Series:
    """Convierte texto con coma o punto decimal a número."""
    return pd.to_numeric(s.astype("string").str.strip().str.replace(",", ".", regex=False), errors="coerce")


def en_lima(df: pd.DataFrame, lat="lat", lon="lon") -> pd.DataFrame:
    s, w, n, e = BBOX_LIMA
    return df[df[lat].between(s, n) & df[lon].between(w, e)]


def vecino_mas_cercano(origen: pd.DataFrame, destino: pd.DataFrame, cols: list[str], prefijo: str,
                       radio_m: float | None = None) -> pd.DataFrame:
    """Para cada fila de `origen` (lat, lon) busca el punto más cercano de `destino` (lat, lon).
    Devuelve columnas {prefijo}_dist_m y {prefijo}_<col>. Si radio_m se da, deja vacío lo que esté más lejos."""
    from sklearn.neighbors import BallTree

    out = pd.DataFrame(index=origen.index)
    if destino.empty:
        out[f"{prefijo}_dist_m"] = np.nan
        for c in cols:
            out[f"{prefijo}_{c}"] = pd.NA
        return out
    tree = BallTree(np.radians(destino[["lat", "lon"]].to_numpy()), metric="haversine")
    d, i = tree.query(np.radians(origen[["lat", "lon"]].to_numpy()), k=1)
    dist = d[:, 0] * R_TIERRA
    out[f"{prefijo}_dist_m"] = dist.round(1)
    for c in cols:
        vals = destino[c].to_numpy()[i[:, 0]]
        out[f"{prefijo}_{c}"] = vals
        if radio_m is not None:
            out.loc[dist > radio_m, f"{prefijo}_{c}"] = pd.NA
    return out


def contar_en_radio(origen: pd.DataFrame, destino: pd.DataFrame, radio_m: float) -> np.ndarray:
    from sklearn.neighbors import BallTree

    if destino.empty:
        return np.zeros(len(origen), dtype=int)
    tree = BallTree(np.radians(destino[["lat", "lon"]].to_numpy()), metric="haversine")
    return tree.query_radius(np.radians(origen[["lat", "lon"]].to_numpy()), r=radio_m / R_TIERRA, count_only=True)


def leer_tabla(path: Path) -> pd.DataFrame:
    """Lee CSV/XLSX/DBF probando separadores y codificaciones habituales del Estado peruano."""
    path = Path(path)
    suf = path.suffix.lower()
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suf == ".dbf":
        from dbfread import DBF
        return pd.DataFrame(iter(DBF(str(path), encoding="latin-1", char_decode_errors="replace")))
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No se pudo leer {path}")


def col(df: pd.DataFrame, *candidatas: str) -> str | None:
    """Primer nombre de columna que exista (sin distinguir mayúsculas)."""
    mapa = {c.upper().strip(): c for c in df.columns}
    for c in candidatas:
        if c.upper() in mapa:
            return mapa[c.upper()]
    return None
