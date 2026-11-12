"""Distrito y ubigeo de cada medidor por punto-en-polígono.

Fuente: límites distritales INEI (vía GEO Perú / IDEP), publicados en
https://github.com/juaneladio/peru-geojson (peru_distrital_simple.geojson).
"""
import json

import pandas as pd
import requests

from src.external.comun import EXT, UA

URL = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_distrital_simple.geojson"
ARCHIVO = EXT / "peru_distrital_simple.geojson"


def descargar() -> None:
    if ARCHIVO.exists():
        return
    r = requests.get(URL, headers=UA, timeout=120)
    r.raise_for_status()
    ARCHIVO.write_bytes(r.content)


def asignar_distrito(puntos: pd.DataFrame) -> pd.DataFrame:
    """puntos: lat, lon. Devuelve ubigeo, distrito, provincia (solo Lima y Callao)."""
    from shapely import STRtree, points
    from shapely.geometry import shape

    descargar()
    feats = [f for f in json.loads(ARCHIVO.read_text(encoding="utf-8"))["features"]
             if f.get("geometry") and f["properties"].get("NOMBDEP") in ("LIMA", "CALLAO")]
    geoms = [shape(f["geometry"]) for f in feats]
    tree = STRtree(geoms)
    pts = points(puntos["lon"].to_numpy(), puntos["lat"].to_numpy())
    idx_pt, idx_poly = tree.query(pts, predicate="within")
    out = pd.DataFrame(index=puntos.index, columns=["ubigeo", "distrito", "provincia"], dtype="object")
    for p, g in zip(idx_pt, idx_poly):
        props = feats[g]["properties"]
        out.iloc[p] = [props.get("IDDIST"), props.get("NOMBDIST"), props.get("NOMBPROV")]
    return out
