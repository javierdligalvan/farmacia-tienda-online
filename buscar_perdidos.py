import polars as pl, glob, os

BASE = r'c:\Users\javie\Escritorio\Javier\Experiencia_Laboral\Ecommerce_Farmacia\FARMACIA MURO'

final = pl.read_csv(BASE + r'\PRODUCTOS_FINAL.csv', separator=';', infer_schema_length=0, encoding='utf8-lossy')
codigos_final = set(final['CODIGO'].to_list())
print('Filas en FINAL:', len(final))

perdidos = {}  # cn -> {nombre, fuente}

# 1. Estadisticas 2024/2025/2026
STATS = BASE + r'\FARMACIA_ALEJANDRO_2024_2026\ESTADISTICAS\Informe_de_Estadisticas_de_Articulos {yr}.csv'
for yr in [2024, 2025, 2026]:
    df = pl.read_csv(STATS.format(yr=yr), separator=';', infer_schema_length=0, encoding='cp850')
    for row in df.iter_rows(named=True):
        cn_raw = str(row.get('Codigo_Nacional', '') or '').strip()
        nombre = str(row.get('Nombre', '') or '').strip()
        try:
            cn = str(int(float(cn_raw))).zfill(6)
        except:
            cn = cn_raw.strip()
        if cn and cn not in codigos_final:
            perdidos[cn] = {'nombre': nombre, 'fuente': f'stats_{yr}'}

# 2. PRODUCTOS_ENRIQUECIDOS_2024
try:
    df2 = pl.read_csv(BASE + r'\PRODUCTOS_ENRIQUECIDOS_2024.csv', separator=';', infer_schema_length=0, encoding='utf8-lossy')
    col_cod = [c for c in df2.columns if 'COD' in c.upper()][0]
    col_nom = [c for c in df2.columns if 'NOM' in c.upper()][0]
    for row in df2.iter_rows(named=True):
        cn_raw = str(row.get(col_cod, '') or '').strip()
        nombre = str(row.get(col_nom, '') or '').strip()
        try:
            cn = str(int(float(cn_raw))).zfill(6)
        except:
            cn = cn_raw.strip()
        if cn and cn not in codigos_final:
            if cn not in perdidos:
                perdidos[cn] = {'nombre': nombre, 'fuente': 'enriquecidos_2024'}
except Exception as e:
    print('enriquecidos_2024 error:', e)

# 3. ventas_consolidadas en RESULTADOS
for f in glob.glob(BASE + r'\FARMACIA_ALEJANDRO_2024_2026\RESULTADOS\ventas_consolidadas*.csv'):
    try:
        df3 = pl.read_csv(f, separator=';', infer_schema_length=0, encoding='utf8-lossy')
        col_cod = [c for c in df3.columns if 'COD' in c.upper()][0]
        col_nom = [c for c in df3.columns if 'NOM' in c.upper()][0]
        for row in df3.iter_rows(named=True):
            cn_raw = str(row.get(col_cod, '') or '').strip()
            nombre = str(row.get(col_nom, '') or '').strip()
            try:
                cn = str(int(float(cn_raw))).zfill(6)
            except:
                cn = cn_raw.strip()
            if cn and cn not in codigos_final:
                if cn not in perdidos:
                    perdidos[cn] = {'nombre': nombre, 'fuente': os.path.basename(f)}
    except Exception as e:
        print(f'Error {f}: {e}')

print(f'\nTotal codigos NO en FINAL encontrados: {len(perdidos)}')
for cn, info in sorted(perdidos.items()):
    nombre = info['nombre'][:50]
    fuente = info['fuente']
    print(f'  {cn}  {nombre:50s}  [{fuente}]')
