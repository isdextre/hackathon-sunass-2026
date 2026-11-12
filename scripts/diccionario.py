"""Genera docs/diccionario_datos.xlsx a partir de las tablas de salida.
Uso: python scripts/diccionario.py"""
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "diccionario_datos.xlsx"

AZUL, GRIS = "1F4E79", "F2F2F2"
F = "Arial"
borde = Border(bottom=Side(style="thin", color="D9D9D9"))

# columna: (tipo, unidad, descripción, usado_por)
MEDIDOR = {
 "medidor": ("texto", "", "Código del medidor de telemetría (ID MEDIDOR de BD_ESCE). Llave para unir con salida_diaria.", "ambos"),
 "distrito": ("texto", "", "Distrito del medidor, por sus coordenadas y los límites del INEI.", "dashboard"),
 "lat": ("número", "grados", "Latitud del medidor (BD_ESCE).", "dashboard (mapa)"),
 "lon": ("número", "grados", "Longitud del medidor (BD_ESCE).", "dashboard (mapa)"),
 "perfil_probable": ("texto", "", "Tipo probable de cliente por cercanía (≤60 m): salud, educacion o sin_identificar (u otro grupo de OSM si se corrió). Es una inferencia, no un dato confirmado.", "ambos"),
 "categoria": ("texto", "", "Categoría tarifaria SUPUESTA: estatal si es colegio o salud públicos; comercial en otro caso. Los datos de telemetría no traen la categoría.", "ambos"),
 "grupo": ("entero", "", "Grupo tarifario: 2 para Punta Negra, Punta Hermosa, San Bartolo y Santa María del Mar; 1 para el resto.", "interno"),
 "criticidad": ("entero", "1 a 3", "Importancia social del cliente: 3 salud y colegios; 2 gobierno, hoteles, mercados; 1 resto.", "dashboard"),
 "ultima_fecha": ("fecha", "", "Último día con consumo calculado para ese medidor.", "ambos"),
 "dias_sin_datos": ("entero", "días", "Días entre el último dato del medidor y el último día de la base. Mayor a 1 = el medidor dejó de transmitir (revisar telemetría).", "dashboard"),
 "consumo_m3": ("número", "m³", "Consumo del último día.", "ambos"),
 "banda_p50_m3": ("número", "m³/día", "Consumo normal (mediana) para ese tipo de día, según su propio historial.", "ambos"),
 "limite_alerta_m3": ("número", "m³/día", "Consumo por encima del cual el día se considera fuera de banda.", "dashboard"),
 "consumo_noche_m3": ("número", "m³", "Consumo de 0 a 5 am del último día.", "ambos"),
 "noche_normal_m3": ("número", "m³", "Consumo normal de 0 a 5 am (mediana de su historial).", "ambos"),
 "consumo_mes_acum_m3": ("número", "m³", "Consumo acumulado del mes hasta ultima_fecha.", "ambos"),
 "soles_mes_acum": ("número", "S/ con IGV", "Importe acumulado del mes (cargo fijo + agua + saneamiento + IGV).", "ambos"),
 "recibo_proyectado_soles": ("número", "S/ con IGV", "Recibo estimado al cierre del mes si sigue al ritmo de los últimos 7 días.", "ambos"),
 "alerta_vigente": ("sí/no", "", "TRUE si el medidor tiene una alerta activa en ultima_fecha.", "ambos"),
 "tipo_alerta": ("texto", "", "fuga_continua, medidor_detenido o consumo_atipico (ver hoja 'Que predice el modelo'). Vacío si no hay alerta vigente.", "ambos"),
 "primera_alerta": ("fecha", "", "Primer día con alerta en el periodo evaluado.", "dashboard"),
 "dias_en_alerta": ("entero", "días", "Días con alerta en el periodo evaluado.", "ambos"),
 "exceso_m3_dia": ("número", "m³/día", "Promedio de los últimos 7 días por encima de su semana normal (en fugas, al menos el exceso de madrugada; si el medidor está detenido, lo que deja de registrar).", "ambos"),
 "soles_riesgo_mes": ("número", "S/ con IGV", "Cuánto más se pagaría (o dejaría de facturarse) por cada mes que el problema siga.", "ambos"),
 "prioridad": ("número", "", "Puntaje para ordenar la atención: peso del tipo de alerta × criticidad × log(1 + soles en riesgo).", "dashboard"),
 "ranking_prioridad": ("entero", "", "Puesto en la lista de atención (1 = más urgente). Vacío si no hay alerta.", "dashboard"),
 "destinatario": ("texto", "", "A quién va el aviso: cliente, o cliente_y_sedapal cuando hay alerta (Sedapal ve el caso en el panel).", "agente"),
 "mensaje_sugerido": ("texto", "", "Texto base para WhatsApp con las cifras ya calculadas. El LLM lo reescribe en lenguaje natural sin cambiar los números.", "agente"),
}
DIARIA = {
 "medidor": MEDIDOR["medidor"],
 "fecha": ("fecha", "", "Día de consumo (de 00:00 a 00:00).", "ambos"),
 "tipo_dia": ("texto", "", "laborable, sabado o domingo_feriado. Cada día se compara con su mismo tipo.", "dashboard"),
 "es_feriado": ("sí/no", "", "Feriado nacional (librería holidays, Perú).", "dashboard"),
 "nombre_feriado": ("texto", "", "Nombre del feriado.", "dashboard"),
 "sin_clases_escolares": ("sí/no", "", "Día sin clases en colegios públicos (vacaciones o semana de gestión MINEDU 2026, fines de semana y feriados).", "dashboard"),
 "periodo_modelo": ("texto", "", "entrenamiento (días usados para aprender la banda, hasta el 30/09/2026) o evaluacion (días diagnosticados).", "interno"),
 "consumo_m3": ("número", "m³", "Consumo del día: diferencia del índice del medidor entre medianoches (interpolado).", "ambos"),
 "banda_p10_m3": ("número", "m³", "Percentil 10 de su consumo normal para ese tipo de día.", "dashboard"),
 "banda_p50_m3": ("número", "m³", "Mediana de su consumo normal para ese tipo de día.", "ambos"),
 "banda_p90_m3": ("número", "m³", "Percentil 90 de su consumo normal para ese tipo de día.", "dashboard"),
 "limite_alerta_m3": MEDIDOR["limite_alerta_m3"],
 "consumo_noche_m3": ("número", "m³", "Consumo de 0 a 5 am de ese día. Vacío si faltan lecturas cerca de esas horas.", "ambos"),
 "noche_normal_m3": MEDIDOR["noche_normal_m3"],
 "estado": ("texto", "", "historial (entrenamiento), normal, sobre_banda (día alto pero sin alerta), alerta, o sin_banda (medidor con menos de 10 días de historial).", "ambos"),
 "tipo_alerta": ("texto", "", "Tipo de alerta activa ese día, si la hay.", "ambos"),
 "soles_dia": ("número", "S/ con IGV", "Costo del agua de ese día (sin cargo fijo), respetando los tramos del mes.", "ambos"),
 "consumo_mes_acum_m3": MEDIDOR["consumo_mes_acum_m3"],
 "soles_mes_acum": MEDIDOR["soles_mes_acum"],
 "consumo_mes_proyectado_m3": ("número", "m³", "Consumo estimado al cierre del mes: acumulado + promedio de los últimos 7 días × días que faltan.", "ambos"),
 "recibo_proyectado_soles": MEDIDOR["recibo_proyectado_soles"],
 "categoria": MEDIDOR["categoria"], "grupo": MEDIDOR["grupo"], "perfil_probable": MEDIDOR["perfil_probable"],
 "criticidad": MEDIDOR["criticidad"], "distrito": MEDIDOR["distrito"],
}


def estilo_titulo(ws, fila, texto, size=14):
    ws.cell(fila, 1, texto).font = Font(name=F, size=size, bold=True, color=AZUL)


def tabla(ws, fila, encabezados, filas, anchos):
    for j, h in enumerate(encabezados, 1):
        c = ws.cell(fila, j, h)
        c.font = Font(name=F, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for i, r in enumerate(filas, fila + 1):
        for j, v in enumerate(r, 1):
            c = ws.cell(i, j, v)
            c.font = Font(name=F, size=10)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = borde
            if (i - fila) % 2 == 0:
                c.fill = PatternFill("solid", fgColor=GRIS)
    for j, w in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    return fila + len(filas) + 2


def hoja_columnas(wb, nombre, archivo, spec, df, intro):
    ws = wb.create_sheet(nombre)
    estilo_titulo(ws, 1, f"{archivo}")
    ws.cell(2, 1, intro).font = Font(name=F, size=10, italic=True)
    ej = df.iloc[0]
    filas = []
    for col in df.columns:
        tipo, unidad, desc, uso = spec[col]
        v = ej[col]
        v = "" if pd.isna(v) else (str(v)[:120] + "…" if len(str(v)) > 120 else str(v))
        filas.append((col, tipo, unidad, desc, uso, v))
    tabla(ws, 4, ["Columna", "Tipo", "Unidad", "Descripción", "Lo usa", "Ejemplo (primera fila)"], filas,
          [26, 10, 12, 70, 16, 34])
    ws.freeze_panes = "B5"


def main():
    med = pd.read_csv(PROC / "salida_medidor.csv", low_memory=False)
    dia = pd.read_csv(PROC / "salida_diaria.csv", low_memory=False)
    dia_ej = dia[dia["estado"] == "alerta"].head(1)
    assert set(med.columns) == set(MEDIDOR), set(med.columns) ^ set(MEDIDOR)
    assert set(dia.columns) == set(DIARIA), set(dia.columns) ^ set(DIARIA)
    sim = pd.read_csv(PROC / "simulacion_resumen.csv")
    casos = pd.read_csv(PROC / "simulacion_casos.csv")
    det = casos[casos["escenario"] == "detenido"]
    det_ok = det[det["consumo_p50_m3d"] >= 1]["detectado"].mean()
    bajo = (det["consumo_p50_m3d"] < 1).mean()
    fu = casos[casos["escenario"] == "fuga"].copy()
    fu["rel"] = pd.cut(fu["fuga_vs_consumo"], [0, 0.25, 0.5, 1, float("inf")])
    rel = fu.groupby("rel", observed=True)["detectado"].mean().tolist()
    val = pd.read_csv(PROC / "validacion_tarifa_ds01.csv")
    n_ok, n_val = int(val["cuadra"].sum()), len(val)
    al = pd.read_csv(PROC / "alertas.csv")
    n_eval = pd.read_csv(PROC / "diagnostico_diario.csv", usecols=["medidor"])["medidor"].nunique()

    wb = Workbook()
    ws = wb.active
    ws.title = "Leeme"
    estilo_titulo(ws, 1, "Diccionario de datos - YakuBot (Hackathon Sunass, Desafío 1)", 16)
    texto = [
        ("Qué es", "Las tablas que produce el modelo estadístico y que leen el agente de WhatsApp y el dashboard de Sedapal."),
        ("Tablas", "salida_medidor.csv: una fila por medidor, su situación hoy. salida_diaria.csv: una fila por medidor y día, para gráficos e historial."),
        ("Dónde están", "data/processed/ (local) y, en la nube, las tablas del mismo nombre en BigQuery."),
        ("Llave", "medidor (código ID MEDIDOR de BD_ESCE). Une las dos tablas."),
        ("Cómo se generan", "python -m src.model.detectar, luego python -m src.model.soles y python -m src.model.salida (orden completo en el README)."),
        ("Periodo", f"Datos de {dia['fecha'].min()} a {dia['fecha'].max()}. Banda aprendida hasta 2026-09-30; octubre es el periodo diagnosticado."),
        ("Soles", f"Con la estructura tarifaria de Sedapal (config/tarifas_*.csv), validada contra los importes reales de DS01 ({n_ok} de {n_val} meses cuadran). Incluye IGV 18 %."),
        ("Supuesto 1", "La categoría tarifaria de los medidores de telemetría no viene en los datos: colegio o salud públicos = estatal; el resto = comercial."),
        ("Supuesto 2", "El perfil (colegio, salud) se infiere por cercanía a establecimientos de ESCALE y RENIPRESS (60 m). No guarda nombres para no reidentificar al cliente (Ley 29733)."),
        ("Hojas", "salida_medidor y salida_diaria: columna por columna. 'Que predice el modelo': qué calcula, cómo, y qué tan bien funciona."),
    ]
    tabla(ws, 3, ["Tema", "Detalle"], texto, [18, 110])

    hoja_columnas(wb, "salida_medidor", "salida_medidor.csv", MEDIDOR, med,
                  "Una fila por medidor. Ordenada: primero alertas vigentes por prioridad. Es lo que consulta el agente al escribirle a un cliente.")
    hoja_columnas(wb, "salida_diaria", "salida_diaria.csv", DIARIA, dia_ej if len(dia_ej) else dia,
                  "Una fila por medidor y día (el ejemplo es un día con alerta). Sirve para el gráfico de consumo vs banda y el historial del cliente.")

    ws = wb.create_sheet("Que predice el modelo")
    estilo_titulo(ws, 1, "Qué predice el modelo", 16)
    preds = [
        ("Consumo esperado (banda)", "Para cada medidor y tipo de día (laborable, sábado, domingo/feriado): su consumo normal (P50) y su rango (P10 a P90).",
         "Percentiles de su propio historial. En colegios se excluyen los días de vacaciones. Con pocos días de un tipo, el margen se ensancha.",
         "banda_p10_m3, banda_p50_m3, banda_p90_m3, limite_alerta_m3"),
        ("Consumo normal de madrugada", "Cuánto consume normalmente de 0 a 5 am.",
         "Mediana y P90 de sus madrugadas. Base para detectar fugas, que siguen corriendo cuando nadie usa agua.", "noche_normal_m3"),
        ("Estado del día", "Si el consumo del día es normal, alto o parte de una alerta.",
         "Fuera de banda si supera limite_alerta_m3 = P90 + margen (mínimo 1 m³).", "estado"),
        ("Tipo de alerta", "Qué problema es probable: fuga continua, medidor detenido o consumo atípico.",
         "Reglas sobre ventanas de 3 y 7 días (tabla de abajo).", "tipo_alerta, alerta_vigente, dias_en_alerta"),
        ("Recibo proyectado", "Cuánto pagará al cierre del mes.",
         "Acumulado del mes + promedio de los últimos 7 días × días que faltan, pasado por la tarifa.", "recibo_proyectado_soles"),
        ("Soles en riesgo", "Cuánto cuesta el problema al mes si sigue.",
         "Diferencia de recibo entre (consumo normal de un mes + exceso de 30 días) y consumo normal, con tramos e IGV. Consumo normal = promedio de su banda en una semana típica.", "soles_riesgo_mes"),
        ("Prioridad", "Qué casos atender primero en Sedapal.",
         "Peso del tipo (fuga 3, detenido 2, atípico 1) × criticidad (1 a 3) × log(1 + soles en riesgo).", "prioridad, ranking_prioridad"),
    ]
    f = tabla(ws, 3, ["Predicción", "Qué dice", "Cómo se calcula", "Columnas"], preds, [28, 48, 62, 36])

    estilo_titulo(ws, f, "Tipos de alerta", 12)
    reglas = [
        ("fuga_continua", "La madrugada (0-5 am) supera su propio P90 + 0.5 m³ en 6 de las últimas 7 noches.",
         "Fuga interna después del medidor (cisterna, inodoro, tubería).", "Cliente: prueba de cerrar llaves. Sedapal: seguimiento."),
        ("medidor_detenido", "7 días seguidos en 0 m³ cuando, según su banda, en una semana normal consumiría ≥ 5 m³.",
         "Medidor parado o manipulado: agua que no se factura (o local cerrado).", "Sedapal: inspección. Cliente: confirmar si estuvo cerrado."),
        ("consumo_atipico", "3 días seguidos sobre su límite, o 1 día por encima del triple del límite.",
         "Cambio de uso o fuga que empieza. Suele ser la primera señal de una fuga.", "Cliente: triaje por WhatsApp."),
        ("(no es alerta) operación 24 h", "Consume de madrugada al mismo ritmo que de día en su historial (22 % de los medidores).",
         "Cisternas que llenan de noche, operación continua. Solo alerta si la madrugada SUBE.", "Ninguna."),
    ]
    f = tabla(ws, f + 1, ["Alerta", "Regla", "Qué suele significar", "Acción sugerida"], reglas, [28, 48, 62, 36])

    estilo_titulo(ws, f, "Qué tan bien detecta (simulación con fugas inyectadas en 1,259 medidores reales)", 12)
    filas = []
    for _, r in sim.iterrows():
        if r["escenario"] == "control":
            continue
        nombre = f"Fuga {r['fuga_m3h']:g} m³/h ({r['fuga_m3_dia']:g} m³/día)" if r["escenario"] == "fuga" else f"Medidor detenido ({det_ok:.0%} si consume ≥ 1 m³/día)"
        filas.append((nombre, f"{r['detectado']:.0%}", f"{r['dias_mediana']:g}", f"{r['dias_p90']:g}"))
    f = tabla(ws, f + 1, ["Escenario", "Detectado", "Días hasta la alerta (mediana)", "Días (p90)"], filas, [28, 48, 62, 36])

    estilo_titulo(ws, f, "Límites que hay que declarar", 12)
    lim = [
        ("Tamaño de la fuga", f"Lo que manda es la fuga frente al consumo normal del cliente: si es menos del 25 % se detecta en {rel[0]:.0%} de los casos; entre 25 y 50 %, en {rel[1]:.0%}; entre 50 y 100 %, en {rel[2]:.0%}; si es mayor que su consumo normal, en {rel[3]:.0%}."),
        ("Medidor detenido", f"Se detecta en el {det_ok:.0%} de los medidores que consumen ≥ 1 m³/día. Los que consumen menos ({bajo:.0%}) casi no se pueden evaluar."),
        ("Falsas alarmas", f"No hay casos confirmados de fuga, así que no se puede medir la tasa de falsas alarmas. En el periodo evaluado: {al['vigente'].sum() / n_eval:.0%} de medidores con alerta vigente al cierre y {len(al) / n_eval:.0%} con alguna alerta."),
        ("Historial", "La banda usa 2 meses. Con más meses (estacionalidad, verano) las bandas serán más estables y habrá menos alertas."),
        ("Resolución", "Lecturas cada ~3 h y en m³ enteros. No se presenta consumo hora por hora."),
        ("Datos simulados", "Las fugas de la simulación son artificiales; se rotulan como tales."),
    ]
    tabla(ws, f + 1, ["Tema", "Detalle"], lim, [28, 110])

    for w in wb.worksheets:
        w.sheet_view.showGridLines = False
    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print(f"guardado {OUT}")


if __name__ == "__main__":
    main()
