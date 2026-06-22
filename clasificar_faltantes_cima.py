#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clasifica los productos faltantes en ENRICHED consultando la API CIMA.
- Si CIMA devuelve resultado → MEDICAMENTO (guarda ATC, laboratorio, PVP)
- Si no → PARAFARMACIA (pendiente de categorizar manualmente)

Entrada:  RESULTADOS/codigos_faltantes_en_enriched.csv
Salida:   RESULTADOS/codigos_faltantes_clasificados.csv
"""

import re
import time
import requests
import polars as pl

# ── Configuración ────────────────────────────────────────────────────────────
INPUT  = r'c:\Users\javie\Escritorio\Javier\Experiencia_Laboral\Ecommerce_Farmacia\FARMACIA MURO\FARMACIA_ALEJANDRO_2024_2026\RESULTADOS\codigos_faltantes_en_enriched.csv'
OUTPUT = r'c:\Users\javie\Escritorio\Javier\Experiencia_Laboral\Ecommerce_Farmacia\FARMACIA MURO\FARMACIA_ALEJANDRO_2024_2026\RESULTADOS\codigos_faltantes_clasificados.csv'

CIMA_URL   = "https://cima.aemps.es/cima/rest/medicamento"
DELAY      = 0.3   # segundos entre peticiones
TIMEOUT    = 10

session = requests.Session()
session.headers.update({'Accept': 'application/json', 'User-Agent': 'FarmaciaMuro/1.0'})

# ── Helpers ──────────────────────────────────────────────────────────────────
def normalizar_cn(codigo: str):
    """Devuelve CN de 6 dígitos o None si el código no es consultable en CIMA."""
    c = str(codigo).strip().lstrip('0')  # quitar ceros a la izquierda
    c_padded = c.zfill(6)                 # rellenar hasta 6 dígitos

    # CN puro de 6 dígitos
    if re.match(r'^\d{6}$', c_padded):
        return c_padded

    # EAN-13 español (8470XXXXXXXXX)
    ean = str(codigo).strip()
    if re.match(r'^8470\d{9}$', ean):
        return ean[4:10]

    return None  # alfanumérico (parafarmacia)


def consultar_cima(cn: str):
    """Llama a CIMA y devuelve (atc, laboratorio, pvp) o None si no es medicamento."""
    try:
        r = session.get(CIMA_URL, params={"cn": cn}, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, dict) and data.get("nombre"):
                atc   = (data.get("atcs") or [{}])[0].get("codigo", "")
                lab   = data.get("labtitular") or data.get("labcomercializador") or ""
                pvp   = data.get("pvp") or ""
                return atc, lab, str(pvp)
    except Exception:
        pass
    time.sleep(DELAY)
    return None

# ── Main ─────────────────────────────────────────────────────────────────────
df = pl.read_csv(INPUT, separator=';', infer_schema_length=0)
total = len(df)
print(f"Productos a clasificar: {total}")

resultados = []

for i, row in enumerate(df.iter_rows(named=True), 1):
    codigo = row["Codigo_Nacional"]
    nombre = row["Nombre"]

    cn = normalizar_cn(codigo)

    if cn is None:
        # Código alfanumérico → parafarmacia directa, sin consultar CIMA
        resultados.append({
            "Codigo_Nacional": codigo,
            "Nombre": nombre,
            "TIPO": "PARAFARMACIA",
            "ATC": "",
            "LABORATORIO": "",
            "PVP_CIMA": "",
        })
        if i % 100 == 0:
            print(f"[{i}/{total}] {codigo} → PARAFARMACIA (alfanumérico)")
        continue

    resp = consultar_cima(cn)
    time.sleep(DELAY)

    if resp:
        atc, lab, pvp = resp
        resultados.append({
            "Codigo_Nacional": codigo,
            "Nombre": nombre,
            "TIPO": "MEDICAMENTO",
            "ATC": atc,
            "LABORATORIO": lab,
            "PVP_CIMA": pvp,
        })
    else:
        resultados.append({
            "Codigo_Nacional": codigo,
            "Nombre": nombre,
            "TIPO": "PARAFARMACIA",
            "ATC": "",
            "LABORATORIO": "",
            "PVP_CIMA": "",
        })

    if i % 100 == 0:
        tipo = "MEDICAMENTO" if resp else "PARAFARMACIA"
        print(f"[{i}/{total}] {cn} → {tipo}")

# ── Guardar resultado ────────────────────────────────────────────────────────
out_df = pl.DataFrame(resultados)

meds  = out_df.filter(pl.col("TIPO") == "MEDICAMENTO").shape[0]
para  = out_df.filter(pl.col("TIPO") == "PARAFARMACIA").shape[0]
print(f"\nResumen → MEDICAMENTOS: {meds} | PARAFARMACIA: {para}")

with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(out_df.write_csv(separator=';'))

print(f"Guardado en: {OUTPUT}")
