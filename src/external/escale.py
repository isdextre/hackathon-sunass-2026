"""Padrón de instituciones educativas (MINEDU - ESCALE).

ESCALE protege su web con verificación anti-robots, así que el padrón se descarga
a mano UNA vez desde el navegador:
    escale.minedu.gob.pe -> Archivo de datos -> B. Padrón de Servicios Educativos
    (Padron_web_AAAAMMDD.zip), descomprimido en data/external/.

Uso: python -m src.external.escale data/external/Padron_web_20261030/Padron_web.dbf

El padrón trae una fila por servicio educativo (inicial, primaria, secundaria...);
varios servicios comparten un mismo local. Aquí se agrupa por local (CODLOCAL),
que es lo que tiene un medidor de agua.
Se excluyen los programas no escolarizados (PRONOEI), que suelen funcionar en
viviendas, y no se guardan datos personales (director, teléfono, correo).

Salida: data/external/escale_lima.csv -> codlocal, lat, lon, niveles, n_servicios, gestion, turnos
"""
import sys

import pandas as pd

from src.external.comun import EXT, en_lima

SALIDA = EXT / "escale_lima.csv"
CAMPOS = ["CODLOCAL", "NLAT_IE", "NLONG_IE", "D_NIV_MOD", "D_GESTION", "D_COD_TUR", "D_DPTO", "D_ESTADO"]


def leer_dbf(archivo: str) -> pd.DataFrame:
    from dbfread import DBF

    # El DBF del MINEDU viene en cp850 (la ñ aparece como ¤ si se lee como latin-1)
    filas = [{k: r[k] for k in CAMPOS}
             for r in DBF(archivo, encoding="cp850", char_decode_errors="replace")
             if r["D_DPTO"] in ("LIMA", "CALLAO")]
    return pd.DataFrame(filas)


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df[(df["D_ESTADO"].str.upper() == "ACTIVO")
            & ~df["D_NIV_MOD"].str.contains("no escolarizado", case=False, na=False)]
    df = df.rename(columns={"NLAT_IE": "lat", "NLONG_IE": "lon"})
    df = en_lima(df.dropna(subset=["lat", "lon"]))
    unir = lambda s: " | ".join(sorted(set(s.dropna())))
    return (df.groupby("CODLOCAL")
              .agg(lat=("lat", "mean"), lon=("lon", "mean"), niveles=("D_NIV_MOD", unir),
                   n_servicios=("D_NIV_MOD", "size"), gestion=("D_GESTION", "first"), turnos=("D_COD_TUR", unir))
              .reset_index().rename(columns={"CODLOCAL": "codlocal"}))


def main(archivo: str) -> pd.DataFrame:
    if archivo.lower().endswith(".dbf"):
        crudo = leer_dbf(archivo)
    else:
        from src.external.comun import leer_tabla
        crudo = leer_tabla(archivo)
    edu = limpiar(crudo)
    edu.to_csv(SALIDA, index=False, encoding="utf-8")
    print(f"ESCALE Lima/Callao: {len(edu)} locales escolares activos "
          f"({edu['n_servicios'].sum()} servicios) | gestión: {edu['gestion'].value_counts().to_dict()}")
    return edu


if __name__ == "__main__":
    main(sys.argv[1])
