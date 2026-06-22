#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convierte VADEMECUM_NIVEL_3.txt (jerarquía ATC) a un CSV plano de 4 columnas.

Lógica de niveles ATC:
  N1  →  1 letra           ej. "A"
  N2  →  letra + 2 dígitos ej. "A01"
  N3  →  N2 + 1 letra      ej. "A01A"
  N4  →  N3 + 2 letras     ej. "A01AA"
  N4* →  código con espacio ej. "A08A P1", "B03A M2"  (subgrupo específico)
"""

import csv
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = os.path.join(BASE_DIR, "VADEMECUM_NIVEL_3.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "VADEMECUM_ATC_NIVEL4.csv")

# ──────────────────────────────────────────────
# Patrones de reconocimiento de nivel
# ──────────────────────────────────────────────
RE_N1 = re.compile(r'^([A-Z]):(.+)$')               # "A: Tracto..."
RE_N2 = re.compile(r'^([A-Z]\d{2}):(.+)$')          # "A01: Preparados..."
RE_N3 = re.compile(r'^([A-Z]\d{2}[A-Z]):(.+)$')     # "A01A: Preparados..."
RE_N4 = re.compile(r'^([A-Z]\d{2}[A-Z]{2}):(.+)$')  # "A01AA: Agentes..."
RE_N4_ESPECIAL = re.compile(                         # "A08A P1: ...", "B03A M2: ..."
    r'^([A-Z]\d{2}[A-Z]? [A-Z][0-9]+):(.+)$'
)

def determinar_nivel(codigo: str) -> int | None:
    """Devuelve 1, 2, 3, 4 o None según el código ATC."""
    if re.match(r'^[A-Z]$', codigo):
        return 1
    if re.match(r'^[A-Z]\d{2}$', codigo):
        return 2
    if re.match(r'^[A-Z]\d{2}[A-Z]$', codigo):
        return 3
    if re.match(r'^[A-Z]\d{2}[A-Z]{2}$', codigo):
        return 4
    if re.match(r'^[A-Z]\d{2}[A-Z]? [A-Z][0-9]+$', codigo):
        return 4  # N4 especial
    return None


def main():
    # Contexto jerárquico: guarda (código, descripción) del nivel actual
    ctx = {1: None, 2: None, 3: None}

    filas = []

    with open(INPUT_FILE, encoding="utf-8") as f:
        for num_linea, linea in enumerate(f, start=1):
            linea = linea.strip()
            if not linea:
                continue

            # ── Intentar parsear la línea ──
            codigo = desc = None

            for patron in (RE_N4_ESPECIAL, RE_N4, RE_N3, RE_N2, RE_N1):
                m = patron.match(linea)
                if m:
                    codigo = m.group(1).strip()
                    desc   = m.group(2).strip()
                    break

            if codigo is None:
                # Línea que no sigue el patrón esperado → ignorar
                print(f"  [AVISO] Línea {num_linea} no reconocida: {linea!r}")
                continue

            nivel = determinar_nivel(codigo)
            if nivel is None:
                print(f"  [AVISO] Línea {num_linea} código sin nivel: {codigo!r}")
                continue

            entrada = (codigo, desc)

            # ── Actualizar contexto o generar fila ──
            if nivel == 1:
                ctx[1] = entrada
                ctx[2] = None
                ctx[3] = None

            elif nivel == 2:
                ctx[2] = entrada
                ctx[3] = None

            elif nivel == 3:
                ctx[3] = entrada

            elif nivel == 4:
                # Determinar N3 para esta fila
                if " " in codigo:
                    # N4 especial: el padre es la parte antes del espacio
                    codigo_padre = codigo.split()[0]

                    if ctx[3] is not None and ctx[3][0] == codigo_padre:
                        # El padre es el N3 actual → usar N3
                        n3_fila = ctx[3]
                    elif ctx[2] is not None and ctx[2][0] == codigo_padre:
                        # El padre es el N2 actual (ej. "A16 P2")
                        # En ese caso no hay N3 propiamente dicho → dejamos N3 vacío
                        n3_fila = ("", "")
                    else:
                        # Padre desconocido → usar N3 del contexto como fallback
                        n3_fila = ctx[3] if ctx[3] else ("", "")
                else:
                    n3_fila = ctx[3] if ctx[3] else ("", "")

                n2_fila = ctx[2] if ctx[2] else ("", "")
                n1_fila = ctx[1] if ctx[1] else ("", "")

                filas.append({
                    "COD_N4":                        codigo,
                    "N4_SUBG_QUIMICO_TERAP_FARMAT":  desc,
                    "COD_N3":                        n3_fila[0],
                    "N3_SUBG_TERAP_FARMAT":          n3_fila[1],
                    "COD_N2":                        n2_fila[0],
                    "N2_SBG_TERAP_PPAL":             n2_fila[1],
                    "COD_N1":                        n1_fila[0],
                    "N1_GRUPO_ANATOMICO":            n1_fila[1],
                })

    # ── Escribir CSV ──
    columnas = [
        "COD_N4",
        "N4_SUBG_QUIMICO_TERAP_FARMAT",
        "COD_N3",
        "N3_SUBG_TERAP_FARMAT",
        "COD_N2",
        "N2_SBG_TERAP_PPAL",
        "COD_N1",
        "N1_GRUPO_ANATOMICO",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        writer.writerows(filas)

    print(f"\n✅ CSV generado: {OUTPUT_FILE}")
    print(f"   Total filas (N4): {len(filas)}")


if __name__ == "__main__":
    main()
