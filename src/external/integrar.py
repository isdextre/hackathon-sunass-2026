"""Base integral: une consumo diario, calendario, clima y el perfil externo de cada medidor.

Cada fuente externa es opcional: si su archivo no existe, se omite con un aviso.

Uso (desde la raíz del proyecto):
    python -m src.external.integrar

Salidas en data/processed/:
    medidores_perfil.csv  -> una fila por medidor: distrito, cercanía a colegios, salud y
                             otros lugares, perfil probable y criticidad
    base_diaria.csv       -> una fila por medidor y día: consumo + calendario + clima + perfil

Privacidad (Ley 29733): del establecimiento más cercano solo se guarda su tipo y
distancia, nunca su nombre ni dirección, para no reidentificar al cliente.
El perfil es una inferencia por cercanía, no un dato confirmado.
"""
import numpy as np
import pandas as pd

from src.external import distritos
from src.external.comun import EXT, PROC, contar_en_radio, vecino_mas_cercano
from src.features.calendario import agregar_calendario

# Distancia máxima para considerar que el medidor "es" de ese establecimiento.
# Las coordenadas del medidor y del padrón no coinciden exactamente; 60 m cubre una manzana.
RADIO_PERFIL_M = 60
CRITICIDAD = {"salud": 3, "educacion": 3, "gobierno": 2, "alojamiento": 2, "mercado": 2}


def cargar(nombre: str) -> pd.DataFrame | None:
    p = EXT / nombre
    if not p.exists():
        print(f"  aviso: falta {p.name}, se omite esa fuente")
        return None
    return pd.read_csv(p)


def perfil_medidores() -> pd.DataFrame:
    med = pd.read_csv(PROC / "medidores_geo.csv")
    print(f"medidores: {len(med)}")

    try:
        med = med.join(distritos.asignar_distrito(med))
    except Exception as e:  # sin internet o sin shapely
        print(f"  aviso: no se asignó distrito ({e})")

    edu = cargar("escale_lima.csv")
    if edu is not None:
        med = med.join(vecino_mas_cercano(med, edu, ["niveles", "n_servicios", "gestion", "turnos"], "colegio", RADIO_PERFIL_M))

    salud = cargar("renipress_lima.csv")
    if salud is not None:
        if "relevante_agua" in salud:  # solo hospitales, clínicas con internamiento y hemodiálisis
            salud = salud[salud["relevante_agua"].astype(str).str.lower() == "true"]
        med = med.join(vecino_mas_cercano(med, salud, ["categoria", "clasificacion"], "salud", RADIO_PERFIL_M))

    osm = cargar("osm_lima.csv")
    if osm is not None:
        med = med.join(vecino_mas_cercano(med, osm, ["grupo"], "osm", RADIO_PERFIL_M))
        med["osm_lugares_200m"] = contar_en_radio(med, osm, 200)  # densidad comercial alrededor

    # Perfil probable: salud > educación > OSM, siempre dentro del radio
    perfil = pd.Series("sin_identificar", index=med.index)
    if "osm_grupo" in med:
        perfil = med["osm_grupo"].fillna("sin_identificar").astype(str)
    if "colegio_dist_m" in med:
        perfil = perfil.mask(med["colegio_dist_m"] <= RADIO_PERFIL_M, "educacion")
    if "salud_dist_m" in med:
        perfil = perfil.mask(med["salud_dist_m"] <= RADIO_PERFIL_M, "salud")
    med["perfil_probable"] = perfil
    med["criticidad"] = med["perfil_probable"].map(CRITICIDAD).fillna(1).astype(int)

    med.to_csv(PROC / "medidores_perfil.csv", index=False)
    print(f"perfil probable: {med['perfil_probable'].value_counts().to_dict()}")
    return med


def base_diaria(perfil: pd.DataFrame) -> pd.DataFrame:
    cd = pd.read_csv(PROC / "consumo_diario.csv")
    base = agregar_calendario(cd)

    clima = cargar("clima_lima.csv")
    if clima is not None:
        clima["fecha"] = pd.to_datetime(clima["fecha"]).dt.date
        base = base.merge(clima.drop(columns="fuente"), on="fecha", how="left")

    cols = [c for c in ["medidor", "distrito", "ubigeo", "perfil_probable", "criticidad",
                        "colegio_niveles", "colegio_turnos", "salud_categoria", "osm_lugares_200m"] if c in perfil]
    base = base.merge(perfil[cols], on="medidor", how="left")
    base["sin_coordenadas"] = base["perfil_probable"].isna()
    base.to_csv(PROC / "base_diaria.csv", index=False)
    cubre = 1 - base["sin_coordenadas"].mean()
    print(f"base diaria: {len(base)} filas, {base['medidor'].nunique()} medidores, "
          f"{cubre:.0%} de filas con perfil, {base.shape[1]} columnas")
    return base


def main() -> None:
    perfil = perfil_medidores()
    base_diaria(perfil)


if __name__ == "__main__":
    main()
