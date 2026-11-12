"""Establecimientos con uso relevante de agua desde OpenStreetMap (API Overpass).

Salida: data/external/osm_lima.csv -> lat, lon, grupo, etiqueta
"""
import pandas as pd
import requests

from src.external.comun import BBOX_LIMA, EXT, UA

OVERPASS = "https://overpass-api.de/api/interpreter"
SALIDA = EXT / "osm_lima.csv"

# etiqueta OSM -> grupo de uso de agua
GRUPOS = {
    "amenity": {
        "school": "educacion", "kindergarten": "educacion", "college": "educacion", "university": "educacion",
        "hospital": "salud", "clinic": "salud", "doctors": "salud",
        "restaurant": "alimentos", "fast_food": "alimentos", "cafe": "alimentos", "marketplace": "mercado",
        "car_wash": "lavado", "police": "gobierno", "fire_station": "gobierno", "townhall": "gobierno",
        "prison": "gobierno", "place_of_worship": "culto",
    },
    "tourism": {"hotel": "alojamiento", "hostel": "alojamiento", "motel": "alojamiento"},
    "shop": {"supermarket": "mercado", "mall": "mercado", "laundry": "lavado", "dry_cleaning": "lavado"},
    "leisure": {"sports_centre": "deporte", "swimming_pool": "deporte", "fitness_centre": "deporte", "stadium": "deporte"},
    "office": {"government": "gobierno"},
    "building": {"industrial": "industria", "warehouse": "industria"},
}


def consulta() -> str:
    s, w, n, e = BBOX_LIMA
    partes = [f'nwr["{k}"~"^({"|".join(v)})$"]({s},{w},{n},{e});' for k, v in GRUPOS.items()]
    return f"[out:json][timeout:300];({''.join(partes)});out center tags;"


def main() -> pd.DataFrame:
    r = requests.post(OVERPASS, data={"data": consulta()}, headers=UA, timeout=360)
    r.raise_for_status()
    filas = []
    for el in r.json()["elements"]:
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        tags = el.get("tags", {})
        for k, mapa in GRUPOS.items():
            if tags.get(k) in mapa:
                filas.append((lat, lon, mapa[tags[k]], f"{k}={tags[k]}"))
                break
    df = pd.DataFrame(filas, columns=["lat", "lon", "grupo", "etiqueta"]).dropna(subset=["lat", "lon"])
    df.to_csv(SALIDA, index=False)
    print(f"OSM Lima/Callao: {len(df)} lugares | {df['grupo'].value_counts().to_dict()}")
    return df


if __name__ == "__main__":
    main()
