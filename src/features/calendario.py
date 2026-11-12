"""Calendario de Lima para el modelo de bandas.

Columnas: fecha, dia_semana (0=lunes), es_finde, es_feriado, nombre_feriado,
          sin_clases_escolares, tipo_dia
tipo_dia agrupa los días comparables: 'laborable', 'sabado', 'domingo_feriado'.

Fuentes:
- Feriados: librería `holidays` (Perú).
- Calendario escolar 2026 (MINEDU, colegios públicos):
    vacaciones de medio año 27/07 - 07/08, semana de gestión 12/10 - 16/10.
  Los colegios privados pueden tener otras fechas.
"""
import holidays
import pandas as pd

# Periodos sin clases para estudiantes en colegios públicos (MINEDU 2026)
SIN_CLASES = [
    ("2026-07-27", "2026-08-07"),  # vacaciones de medio año
    ("2026-10-12", "2026-10-16"),  # semana de gestión (sin estudiantes)
]


def calendario(inicio: str, fin: str) -> pd.DataFrame:
    fechas = pd.date_range(inicio, fin, freq="D")
    feriados = holidays.Peru(years=sorted(set(fechas.year)))
    cal = pd.DataFrame({"fecha": fechas})
    cal["dia_semana"] = cal["fecha"].dt.dayofweek
    cal["es_finde"] = cal["dia_semana"] >= 5
    cal["nombre_feriado"] = cal["fecha"].dt.date.map(feriados.get)
    cal["es_feriado"] = cal["nombre_feriado"].notna()

    cal["sin_clases_escolares"] = False
    for a, b in SIN_CLASES:
        cal.loc[cal["fecha"].between(a, b), "sin_clases_escolares"] = True
    cal["sin_clases_escolares"] |= cal["es_finde"] | cal["es_feriado"]

    cal["tipo_dia"] = "laborable"
    cal.loc[cal["dia_semana"] == 5, "tipo_dia"] = "sabado"
    cal.loc[(cal["dia_semana"] == 6) | cal["es_feriado"], "tipo_dia"] = "domingo_feriado"
    cal["fecha"] = cal["fecha"].dt.date
    return cal


def agregar_calendario(consumo: pd.DataFrame) -> pd.DataFrame:
    """Une el calendario a una tabla con columna 'fecha' (p. ej. consumo_diario)."""
    fechas = pd.to_datetime(consumo["fecha"])
    cal = calendario(fechas.min().strftime("%Y-%m-%d"), fechas.max().strftime("%Y-%m-%d"))
    out = consumo.copy()
    out["fecha"] = fechas.dt.date
    return out.merge(cal, on="fecha", how="left")


if __name__ == "__main__":
    c = calendario("2026-08-01", "2026-10-31")
    print(c["tipo_dia"].value_counts().to_string())
    print(c[c["es_feriado"]][["fecha", "nombre_feriado"]].to_string(index=False))
    print("días sin clases escolares:", int(c["sin_clases_escolares"].sum()))
