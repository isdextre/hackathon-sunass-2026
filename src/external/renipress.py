"""Establecimientos de salud (RENIPRESS, SUSALUD) en Lima y Callao.

Fuente: Plataforma Nacional de Datos Abiertos
https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress
Se publica un CSV mensual; se descarga el más reciente.
Salida: data/external/renipress_lima.csv -> lat, lon, categoria, tipo, clasificacion, institucion
"""
import re

import pandas as pd
import requests

from src.external.comun import EXT, UA, col, en_lima, leer_tabla, num

PAGINA = "https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress"
RESPALDO = "https://www.datosabiertos.gob.pe/sites/default/files/RENIPRESS_30-10-2026.csv"
CRUDO = EXT / "renipress.csv"
SALIDA = EXT / "renipress_lima.csv"


def url_mas_reciente() -> str:
    try:
        html = requests.get(PAGINA, headers=UA, timeout=60).text
        nombres = set(re.findall(r"RENIPRESS_(\d{2})-(\d{2})-(\d{4})\.csv", html))
        if nombres:
            d, m, a = max(nombres, key=lambda x: (x[2], x[1], x[0]))
            return f"https://www.datosabiertos.gob.pe/sites/default/files/RENIPRESS_{d}-{m}-{a}.csv"
    except requests.RequestException:
        pass
    return RESPALDO


def descargar() -> None:
    if CRUDO.exists():
        return
    url = url_mas_reciente()
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    CRUDO.write_bytes(r.content)
    print(f"RENIPRESS descargado de {url}")


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    # El CSV real usa NORTE (latitud) y ESTE (longitud); el diccionario los llama LONGITUD_NORTE/ESTE.
    # Por si cambian, se decide cuál es latitud por el rango de valores.
    c1, c2 = col(df, "NORTE", "LONGITUD_NORTE", "LATITUD"), col(df, "ESTE", "LONGITUD_ESTE", "LONGITUD")
    a, b = num(df[c1]), num(df[c2])
    lat, lon = (a, b) if a.between(-19, 0).mean() > b.between(-19, 0).mean() and b.lt(-60).mean() > 0.5 else (b, a)
    out = pd.DataFrame({
        "lat": lat, "lon": lon,
        "categoria": df[col(df, "CATEGORIA_IPRESS", "CATEGORIA")],
        "tipo": df[col(df, "TIPO_ESTABLECIMIENTO", "TIPO")],
        "clasificacion": df[col(df, "CLASIFICACION")],
        "institucion": df[col(df, "INSTITUCION")],
    })
    estado = col(df, "ESTADO")
    if estado:
        out = out[df[estado].astype("string").str.upper().str.contains("ACTIV", na=False).to_numpy()]
    # Relevante para el agua: hospitales y clínicas con internamiento, categorías II y III,
    # y centros de hemodiálisis (alto consumo de agua). Los consultorios pequeños no definen el perfil.
    tipo = out["tipo"].astype("string").str.upper()
    cat = out["categoria"].astype("string").str.upper()
    clas = out["clasificacion"].astype("string").str.upper()
    out["relevante_agua"] = (tipo.str.contains("CON INTERNAMIENTO", na=False)
                             | cat.str.match(r"^(II|III)", na=False)
                             | clas.str.contains("HEMODIALISIS|HOSPITAL", na=False))
    return en_lima(out.dropna(subset=["lat", "lon"]))


def main() -> pd.DataFrame:
    descargar()
    salud = limpiar(leer_tabla(CRUDO))
    salud.to_csv(SALIDA, index=False)
    print(f"RENIPRESS Lima/Callao activos: {len(salud)} ({int(salud['relevante_agua'].sum())} relevantes para el agua)")
    return salud


if __name__ == "__main__":
    main()
