"""Parámetros compartidos del pipeline (un solo lugar para cambiarlos)."""
# Último día usado para aprender las bandas; los días siguientes se diagnostican.
# En producción se movería cada día (por ejemplo, hoy menos 1 día).
CORTE_ENTRENAMIENTO = "2026-09-30"
