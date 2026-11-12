"""Corre todo el pipeline en orden, de los datos crudos a las tablas finales.

Uso (desde la raíz del proyecto):
    python scripts/correr_todo.py              # todo
    python scripts/correr_todo.py --desde consumo   # empieza en un paso (salta los lentos ya hechos)
    python scripts/correr_todo.py --sin-simulacion  # no corre la simulación (30 s)

Las fuentes externas que fallan (sin internet, OSM caído) se avisan y se siguen sin ellas.
"""
import argparse
import glob
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def padron() -> list[str]:
    dbf = sorted(glob.glob(str(ROOT / "data" / "external" / "Padron_web_*" / "Padron_web.dbf")))
    return [dbf[-1]] if dbf else []


# (nombre, módulo o script, argumentos, ¿es opcional?)
PASOS = [
    ("ingesta",      "src/ingest/punto.py",          [], False),
    ("lecturas",     "src/ingest/lecturas.py",       [], False),
    ("consumo",      "src.features.run_consumo",     [], False),
    ("geo",          "src.external.medidores_geo",   [], False),
    ("renipress",    "src.external.renipress",       [], True),
    ("osm",          "src.external.osm",             [], True),
    ("escale",       "src.external.escale",          None, True),   # None = usa el padrón más reciente
    ("integrar",     "src.external.integrar",        [], False),
    ("nocturno",     "src.features.nocturno",        [], False),
    ("detectar",     "src.model.detectar",           [], False),
    ("soles",        "src.model.soles",              [], False),   # debe ir después de detectar
    ("simulacion",   "src.simulate.fugas",           ["1259"], False),
    ("salida",       "src.model.salida",             [], False),   # debe ir después de soles
    ("diccionario",  "scripts/diccionario.py",       [], False),   # después de simulación y salida
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", choices=[p[0] for p in PASOS], default=PASOS[0][0])
    ap.add_argument("--sin-simulacion", action="store_true")
    a = ap.parse_args()
    nombres = [p[0] for p in PASOS]
    inicio = nombres.index(a.desde)
    for nombre, mod, args, opcional in PASOS[inicio:]:
        if nombre == "simulacion" and a.sin_simulacion:
            continue
        if args is None:
            args = padron()
            if not args:
                print(f"[{nombre}] sin padrón en data/external/Padron_web_*/ -> se omite")
                continue
        cmd = [sys.executable] + ([mod] if mod.endswith(".py") else ["-m", mod]) + args
        print(f"\n=== {nombre} ===", flush=True)
        t = time.time()
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            if opcional:
                print(f"[{nombre}] falló (opcional) -> se sigue sin esta fuente")
                continue
            sys.exit(f"[{nombre}] falló. Corrige el error y vuelve con: --desde {nombre}")
        print(f"[{nombre}] ok en {time.time() - t:.0f} s")
    print("\nListo. Tablas finales en data/processed/salida_*.csv y diccionario en docs/.")


if __name__ == "__main__":
    main()
