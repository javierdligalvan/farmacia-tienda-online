import polars as pl, re

BASE = r'c:\Users\javie\Escritorio\Javier\Experiencia_Laboral\Ecommerce_Farmacia\FARMACIA MURO'
STATS = BASE + r'\FARMACIA_ALEJANDRO_2024_2026\ESTADISTICAS\Informe_de_Estadisticas_de_Articulos {yr}.csv'

final = pl.read_csv(BASE + r'\PRODUCTOS_FINAL.csv', separator=';', infer_schema_length=0, encoding='utf8-lossy')
codigos_final = set(final['CODIGO'].to_list())

# ── 1. AÑADIR los 12 recuperables ────────────────────────────────────────────
perdidos = pl.read_csv(
    BASE + r'\FARMACIA_ALEJANDRO_2024_2026\RESULTADOS\PRODUCTOS_PERDIDOS.csv',
    separator=';', infer_schema_length=0, encoding='utf8-lossy'
)
nuevos = perdidos.filter(~pl.col('CODIGO').is_in(list(codigos_final)))
final_ampliado = pl.concat([final, nuevos], how='diagonal')
with open(BASE + r'\PRODUCTOS_FINAL.csv', 'w', encoding='utf-8') as f:
    f.write(final_ampliado.write_csv(separator=';'))
print(f'PRODUCTOS_FINAL actualizado: {final_ampliado.shape[0]} filas (+{nuevos.shape[0]} anadidas)')

# ── 2. MOSTRAR los irrecuperables ─────────────────────────────────────────────
irrecuperables = []
vistos = set()
for yr in [2024, 2025, 2026]:
    df = pl.read_csv(STATS.format(yr=yr), separator=';', infer_schema_length=0, encoding='cp850')
    for row in df.iter_rows(named=True):
        cn_raw = str(row.get('Codigo_Nacional', '') or '').strip()
        nombre = str(row.get('Nombre', '') or '').strip()
        es_cientifico = bool(re.search(r'[Ee][+\-]?\d+', cn_raw) or ',' in cn_raw)
        es_roto = bool(re.search(r'[^\x20-\x7E]', cn_raw))
        if es_cientifico or es_roto:
            key = cn_raw + '|' + nombre
            if key not in vistos:
                vistos.add(key)
                motivo = 'notacion_cientifica' if es_cientifico else 'encoding_roto'
                irrecuperables.append((str(yr), cn_raw, nombre, motivo))

print(f'\nCodigos IRRECUPERABLES ({len(irrecuperables)}):')
print(f'  {"AÑO":<6}  {"CODIGO_ORIGINAL":<20}  {"MOTIVO":<22}  NOMBRE')
print(f'  {"-"*6}  {"-"*20}  {"-"*22}  {"-"*50}')
for yr, cn, nombre, motivo in irrecuperables:
    print(f'  {yr:<6}  {cn:<20}  {motivo:<22}  {nombre[:60]}')

if __name__ == '__main__':
    pass

final = pl.read_csv(BASE + r'\PRODUCTOS_FINAL.csv', separator=';', infer_schema_length=0, encoding='utf8-lossy')
codigos_final = set(final['CODIGO'].to_list())

def es_codigo_valido(cn):
    """Solo acepta codigos numericos de 6-13 digitos o alfanumericos limpios"""
    if not cn:
        return False
    cn = cn.strip()
    if re.match(r'^\d{6,13}$', cn):
        return True
    if re.match(r'^[A-Z0-9]{4,13}$', cn):
        return True
    return False

perdidos = {}  # cn -> {nombre, laboratorio, categoria, subcategoria, pvp}

# --- Fuente 1: ventas_consolidadas (codigos ya normalizados y limpios) ---
import glob
for f in sorted(glob.glob(BASE + r'\FARMACIA_ALEJANDRO_2024_2026\RESULTADOS\ventas_consolidadas*.csv')):
    df = pl.read_csv(f, separator=';', infer_schema_length=0, encoding='utf8-lossy')
    col_cod = next((c for c in df.columns if 'COD' in c.upper()), None)
    col_nom = next((c for c in df.columns if 'NOM' in c.upper()), None)
    if not col_cod or not col_nom:
        continue
    for row in df.iter_rows(named=True):
        cn = str(row.get(col_cod, '') or '').strip()
        nombre = str(row.get(col_nom, '') or '').strip()
        if es_codigo_valido(cn) and cn not in codigos_final and cn not in perdidos:
            perdidos[cn] = {'nombre': nombre, 'laboratorio': '', 'categoria': '', 'subcategoria': '', 'pvp': ''}

# --- Fuente 2: PRODUCTOS_ENRIQUECIDOS_2024 (tiene CATEGORIA/SUBCATEGORIA) ---
try:
    df2 = pl.read_csv(BASE + r'\PRODUCTOS_ENRIQUECIDOS_2024.csv', separator=';', infer_schema_length=0, encoding='utf8-lossy')
    print('Columnas ENRIQUECIDOS_2024:', df2.columns)
    col_cod = next((c for c in df2.columns if 'COD' in c.upper()), None)
    col_nom = next((c for c in df2.columns if 'NOM' in c.upper()), None)
    col_cat = next((c for c in df2.columns if 'CAT' in c.upper()), None)
    col_sub = next((c for c in df2.columns if 'SUB' in c.upper()), None)
    col_lab = next((c for c in df2.columns if 'LAB' in c.upper()), None)
    col_pvp = next((c for c in df2.columns if 'PVP' in c.upper()), None)
    for row in df2.iter_rows(named=True):
        cn_raw = str(row.get(col_cod, '') or '').strip()
        try:
            cn = str(int(float(cn_raw))).zfill(6)
        except:
            cn = cn_raw.strip()
        if not es_codigo_valido(cn):
            continue
        nombre = str(row.get(col_nom, '') or '').strip() if col_nom else ''
        lab    = str(row.get(col_lab, '') or '').strip() if col_lab else ''
        cat    = str(row.get(col_cat, '') or '').strip() if col_cat else ''
        sub    = str(row.get(col_sub, '') or '').strip() if col_sub else ''
        pvp    = str(row.get(col_pvp, '') or '').strip() if col_pvp else ''
        if cn not in codigos_final:
            perdidos[cn] = {'nombre': nombre, 'laboratorio': lab, 'categoria': cat, 'subcategoria': sub, 'pvp': pvp}
        elif cn in perdidos and not perdidos[cn]['categoria']:
            # Enriquecer con categoria si ya estaba
            perdidos[cn].update({'laboratorio': lab, 'categoria': cat, 'subcategoria': sub, 'pvp': pvp})
except Exception as e:
    print('Error enriquecidos_2024:', e)

print(f'\nCodigos recuperables NO en FINAL: {len(perdidos)}')
for cn, info in sorted(perdidos.items()):
    print(f"  {cn}  {info['nombre'][:50]:50s}  cat={info['categoria']}")

# --- Guardar fichero ---
rows = []
for cn, info in sorted(perdidos.items()):
    rows.append({
        'CODIGO':      cn,
        'NOMBRE':      info['nombre'].upper(),
        'LABORATORIO': info['laboratorio'].upper(),
        'CATEGORIA':   info['categoria'].upper(),
        'SUBCATEGORIA':info['subcategoria'].upper(),
        'PVP_AI':      info['pvp'],
    })

df_out = pl.DataFrame(rows)
out_path = BASE + r'\FARMACIA_ALEJANDRO_2024_2026\RESULTADOS\PRODUCTOS_PERDIDOS.csv'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(df_out.write_csv(separator=';'))
print(f'\nGuardado: {out_path} ({len(rows)} filas)')
