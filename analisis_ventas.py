"""
Script de Análisis de Ventas de Farmacia
Autor: Javier
Fecha: Marzo 2026

Descripción:
Este script procesa las estadísticas de ventas de productos farmacéuticos
de los años 2024, 2025 y 2026, relacionándolos con el nomenclátor oficial
para obtener información de laboratorios, PVP y calcular KPIs.
"""

import polars as pl
from pathlib import Path
from datetime import datetime


def cargar_nomenclator(ruta_nomenclator: str) -> pl.DataFrame:
    """
    Carga el nomenclátor de facturación oficial.
    
    Args:
        ruta_nomenclator: Ruta al archivo CSV del nomenclátor
        
    Returns:
        DataFrame de Polars con el nomenclátor procesado
    """
    print("📚 Cargando nomenclátor...")
    
    df_nomenclator = pl.read_csv(
        ruta_nomenclator,
        separator=';',
        encoding='utf-8',
        null_values=[''],
        ignore_errors=True,
        infer_schema_length=10000
    )
    
    # Limpiar nombres de columnas (eliminar espacios extra y estandarizar)
    df_nomenclator = df_nomenclator.rename({
        col: col.strip() for col in df_nomenclator.columns
    })
    
    # Asegurar que Codigo_Nacional sea string para hacer join
    if 'Codigo_Nacional' in df_nomenclator.columns:
        df_nomenclator = df_nomenclator.with_columns([
            pl.col('Codigo_Nacional').cast(pl.Utf8, strict=False).alias('Codigo_Nacional')
        ])
    
    # Renombrar columnas para facilitar su uso
    rename_dict = {
        'Nombre_producto_farmaceutico': 'Nombre_Nomenclator',
        'Nombre_laboratorio_ofertante': 'Laboratorio',
        'Precio venta al publico con IVA': 'PVP_Referencia',
        'Principio activo o asociacion de principios activos': 'Principio_Activo'
    }
    
    # Aplicar renombramientos solo para columnas que existen
    rename_existing = {k: v for k, v in rename_dict.items() if k in df_nomenclator.columns}
    df_nomenclator = df_nomenclator.rename(rename_existing)
    
    # Seleccionar columnas relevantes
    columnas_a_mantener = ['Codigo_Nacional', 'Nombre_Nomenclator', 'Laboratorio', 
                           'Principio_Activo', 'Estado']
    
    # Agregar PVP_Referencia solo si existe
    if 'PVP_Referencia' in df_nomenclator.columns:
        columnas_a_mantener.append('PVP_Referencia')
    
    df_nomenclator = df_nomenclator.select([
        col for col in columnas_a_mantener if col in df_nomenclator.columns
    ])
    
    # Convertir PVP a numérico si existe
    if 'PVP_Referencia' in df_nomenclator.columns:
        df_nomenclator = df_nomenclator.with_columns([
            pl.col('PVP_Referencia').cast(pl.Float64, strict=False).alias('PVP_Referencia')
        ])
    else:
        # Si no existe la columna, crearla con valores null
        df_nomenclator = df_nomenclator.with_columns([
            pl.lit(None).cast(pl.Float64).alias('PVP_Referencia')
        ])
    
    print(f"✅ Nomenclátor cargado: {df_nomenclator.shape[0]:,} productos")
    return df_nomenclator


def cargar_estadisticas_año(ruta_estadisticas: str, año: int) -> pl.DataFrame:
    """
    Carga las estadísticas de ventas de un año específico.
    
    Args:
        ruta_estadisticas: Ruta al archivo CSV de estadísticas
        año: Año de las estadísticas (2024, 2025, 2026)
        
    Returns:
        DataFrame de Polars con las estadísticas procesadas
    """
    print(f"📊 Cargando estadísticas del año {año}...")
    
    df = pl.read_csv(
        ruta_estadisticas,
        separator=';',
        encoding='utf-8',
        null_values=[''],
        ignore_errors=True,
        infer_schema_length=10000  # Mejorar inferencia de tipos
    )
    
    # Limpiar nombres de columnas
    df = df.rename({col: col.strip() for col in df.columns})
    
    # Agregar columna de año
    df = df.with_columns([
        pl.lit(año).alias('Año')
    ])
    
    # Asegurar que las columnas de código y nombre sean strings
    if 'Codigo_Nacional' in df.columns:
        df = df.with_columns([
            pl.col('Codigo_Nacional').cast(pl.Utf8, strict=False).alias('Codigo_Nacional')
        ])
    
    if 'Codigo' in df.columns:
        df = df.with_columns([
            pl.col('Codigo').cast(pl.Utf8, strict=False).alias('Codigo')
        ])
    
    if 'Nombre' in df.columns:
        df = df.with_columns([
            pl.col('Nombre').cast(pl.Utf8, strict=False).alias('Nombre')
        ])
    
    # Convertir columnas de ventas mensuales a enteros
    columnas_ventas = [f'ventas{i}' for i in range(1, 13)]
    for col in columnas_ventas:
        if col in df.columns:
            df = df.with_columns([
                pl.col(col).cast(pl.Int64, strict=False).fill_null(0).alias(col)
            ])
    
    # Asegurar que Total Ventas sea numérico
    if 'Total Ventas' in df.columns:
        df = df.with_columns([
            pl.col('Total Ventas').cast(pl.Int64, strict=False).fill_null(0).alias('Total_Ventas')
        ])
    elif 'Total_Ventas' in df.columns:
        df = df.with_columns([
            pl.col('Total_Ventas').cast(pl.Int64, strict=False).fill_null(0).alias('Total_Ventas')
        ])
    
    print(f"✅ Estadísticas {año} cargadas: {df.shape[0]:,} productos")
    return df


def procesar_ventas_consolidadas(
    df_ventas: pl.DataFrame,
    df_nomenclator: pl.DataFrame
) -> pl.DataFrame:
    """
    Combina las estadísticas de ventas con el nomenclátor.
    
    Args:
        df_ventas: DataFrame con estadísticas de ventas
        df_nomenclator: DataFrame con información del nomenclátor
        
    Returns:
        DataFrame consolidado con toda la información
    """
    print("🔗 Relacionando ventas con nomenclátor...")
    
    # Join por Codigo_Nacional
    df_consolidado = df_ventas.join(
        df_nomenclator,
        on='Codigo_Nacional',
        how='left'
    )
    
    # Calcular unidades totales vendidas y estimación de ingresos
    df_consolidado = df_consolidado.with_columns([
        # Total unidades vendidas en el año
        pl.col('Total_Ventas').alias('Unidades_Vendidas'),
        
        # Ingresos estimados (unidades * PVP de referencia)
        (pl.col('Total_Ventas') * pl.col('PVP_Referencia')).alias('Ingresos_Estimados_PVP')
    ])
    
    # Calcular ventas por trimestre
    df_consolidado = df_consolidado.with_columns([
        # Q1 (Enero-Marzo)
        (pl.col('ventas1') + pl.col('ventas2') + pl.col('ventas3')).alias('Q1_Ventas'),
        # Q2 (Abril-Junio)
        (pl.col('ventas4') + pl.col('ventas5') + pl.col('ventas6')).alias('Q2_Ventas'),
        # Q3 (Julio-Septiembre)
        (pl.col('ventas7') + pl.col('ventas8') + pl.col('ventas9')).alias('Q3_Ventas'),
        # Q4 (Octubre-Diciembre)
        (pl.col('ventas10') + pl.col('ventas11') + pl.col('ventas12')).alias('Q4_Ventas')
    ])
    
    # Identificar productos sin información de nomenclátor
    productos_sin_nomenclator = df_consolidado.filter(
        pl.col('Laboratorio').is_null()
    ).shape[0]
    
    if productos_sin_nomenclator > 0:
        print(f"⚠️  Advertencia: {productos_sin_nomenclator} productos sin información en nomenclátor")
    
    print(f"✅ Consolidación completada: {df_consolidado.shape[0]:,} registros")
    return df_consolidado


def generar_kpis(df_consolidado: pl.DataFrame) -> dict:
    """
    Genera KPIs clave del análisis de ventas.
    
    Args:
        df_consolidado: DataFrame consolidado de ventas
        
    Returns:
        Diccionario con los KPIs calculados
    """
    print("📈 Generando KPIs...")
    
    kpis = {}
    
    # KPIs por año
    for año in df_consolidado['Año'].unique().sort():
        df_año = df_consolidado.filter(pl.col('Año') == año)
        
        kpis[f'año_{año}'] = {
            'total_productos_vendidos': df_año.filter(pl.col('Unidades_Vendidas') > 0).shape[0],
            'total_unidades_vendidas': df_año['Unidades_Vendidas'].sum(),
            'ingresos_totales_estimados': df_año['Ingresos_Estimados_PVP'].sum(),
            'ticket_medio': df_año['Ingresos_Estimados_PVP'].sum() / df_año['Unidades_Vendidas'].sum() if df_año['Unidades_Vendidas'].sum() > 0 else 0,
            
            # Top 10 productos por unidades
            'top_10_productos_unidades': df_año.sort('Unidades_Vendidas', descending=True)
                .select(['Nombre', 'Unidades_Vendidas', 'Laboratorio'])
                .head(10)
                .to_dicts(),
            
            # Top 10 productos por ingresos
            'top_10_productos_ingresos': df_año.sort('Ingresos_Estimados_PVP', descending=True)
                .select(['Nombre', 'Ingresos_Estimados_PVP', 'Unidades_Vendidas', 'Laboratorio'])
                .head(10)
                .to_dicts(),
            
            # Top 10 laboratorios
            'top_10_laboratorios': df_año.group_by('Laboratorio')
                .agg([
                    pl.col('Unidades_Vendidas').sum().alias('Total_Unidades'),
                    pl.col('Ingresos_Estimados_PVP').sum().alias('Total_Ingresos')
                ])
                .sort('Total_Ingresos', descending=True)
                .head(10)
                .to_dicts(),
            
            # Análisis trimestral
            'ventas_por_trimestre': {
                'Q1': df_año['Q1_Ventas'].sum(),
                'Q2': df_año['Q2_Ventas'].sum(),
                'Q3': df_año['Q3_Ventas'].sum(),
                'Q4': df_año['Q4_Ventas'].sum(),
            }
        }
    
    # KPIs comparativos entre años (si hay múltiples años)
    años_disponibles = sorted(df_consolidado['Año'].unique().to_list())
    if len(años_disponibles) > 1:
        kpis['comparativa_años'] = {}
        
        for i in range(len(años_disponibles) - 1):
            año_actual = años_disponibles[i + 1]
            año_anterior = años_disponibles[i]
            
            ventas_actual = kpis[f'año_{año_actual}']['total_unidades_vendidas']
            ventas_anterior = kpis[f'año_{año_anterior}']['total_unidades_vendidas']
            
            ingresos_actual = kpis[f'año_{año_actual}']['ingresos_totales_estimados']
            ingresos_anterior = kpis[f'año_{año_anterior}']['ingresos_totales_estimados']
            
            kpis['comparativa_años'][f'{año_anterior}_vs_{año_actual}'] = {
                'crecimiento_unidades_%': ((ventas_actual - ventas_anterior) / ventas_anterior * 100) if ventas_anterior > 0 else 0,
                'crecimiento_ingresos_%': ((ingresos_actual - ingresos_anterior) / ingresos_anterior * 100) if ingresos_anterior > 0 else 0,
            }
    
    print("✅ KPIs generados")
    return kpis


def guardar_resultados(
    df_consolidado: pl.DataFrame,
    kpis: dict,
    directorio_salida: str = 'RESULTADOS'
):
    """
    Guarda los resultados del análisis en archivos.
    
    Args:
        df_consolidado: DataFrame consolidado
        kpis: Diccionario con KPIs
        directorio_salida: Carpeta donde guardar los resultados
    """
    print("💾 Guardando resultados...")
    
    # Crear directorio de salida si no existe
    Path(directorio_salida).mkdir(exist_ok=True)
    
    # Guardar DataFrame consolidado en CSV
    ruta_csv = f"{directorio_salida}/ventas_consolidadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df_consolidado.write_csv(ruta_csv, separator=';')
    print(f"  ✓ CSV guardado: {ruta_csv}")
    
    # Guardar reporte de KPIs en texto
    ruta_kpis = f"{directorio_salida}/reporte_kpis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(ruta_kpis, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("REPORTE DE KPIs - ANÁLISIS DE VENTAS FARMACIA\n")
        f.write("=" * 80 + "\n\n")
        
        for año_key, año_data in kpis.items():
            if año_key.startswith('año_'):
                año = año_key.replace('año_', '')
                f.write(f"\n{'=' * 80}\n")
                f.write(f"AÑO {año}\n")
                f.write(f"{'=' * 80}\n\n")
                
                f.write(f"📊 RESUMEN GENERAL\n")
                f.write(f"  • Total productos vendidos: {año_data['total_productos_vendidos']:,}\n")
                f.write(f"  • Total unidades vendidas: {año_data['total_unidades_vendidas']:,}\n")
                f.write(f"  • Ingresos totales estimados: {año_data['ingresos_totales_estimados']:,.2f} €\n")
                f.write(f"  • Ticket medio: {año_data['ticket_medio']:.2f} €\n\n")
                
                f.write(f"📈 ANÁLISIS TRIMESTRAL\n")
                for q, ventas in año_data['ventas_por_trimestre'].items():
                    f.write(f"  • {q}: {ventas:,} unidades\n")
                f.write("\n")
                
                f.write(f"🏆 TOP 5 PRODUCTOS POR UNIDADES VENDIDAS\n")
                for i, prod in enumerate(año_data['top_10_productos_unidades'][:5], 1):
                    nombre = prod['Nombre'] if prod['Nombre'] else 'Sin nombre'
                    lab = prod['Laboratorio'] if prod['Laboratorio'] else 'Sin laboratorio'
                    f.write(f"  {i}. {nombre[:60]}\n")
                    f.write(f"     Unidades: {prod['Unidades_Vendidas']:,} | Lab: {lab}\n")
                f.write("\n")
                
                f.write(f"💰 TOP 5 PRODUCTOS POR INGRESOS\n")
                for i, prod in enumerate(año_data['top_10_productos_ingresos'][:5], 1):
                    nombre = prod['Nombre'] if prod['Nombre'] else 'Sin nombre'
                    ingresos = prod['Ingresos_Estimados_PVP'] if prod['Ingresos_Estimados_PVP'] else 0
                    f.write(f"  {i}. {nombre[:60]}\n")
                    f.write(f"     Ingresos: {ingresos:,.2f} € | Unidades: {prod['Unidades_Vendidas']:,}\n")
                f.write("\n")
                
                f.write(f"🏭 TOP 5 LABORATORIOS\n")
                for i, lab in enumerate(año_data['top_10_laboratorios'][:5], 1):
                    if lab['Laboratorio']:
                        f.write(f"  {i}. {lab['Laboratorio']}\n")
                        f.write(f"     Ingresos: {lab['Total_Ingresos']:,.2f} € | Unidades: {lab['Total_Unidades']:,}\n")
                f.write("\n")
        
        # Comparativas entre años
        if 'comparativa_años' in kpis:
            f.write(f"\n{'=' * 80}\n")
            f.write(f"COMPARATIVA ENTRE AÑOS\n")
            f.write(f"{'=' * 80}\n\n")
            
            for comp_key, comp_data in kpis['comparativa_años'].items():
                años = comp_key.replace('_vs_', ' vs ')
                f.write(f"📊 {años}\n")
                f.write(f"  • Crecimiento en unidades: {comp_data['crecimiento_unidades_%']:+.2f}%\n")
                f.write(f"  • Crecimiento en ingresos: {comp_data['crecimiento_ingresos_%']:+.2f}%\n\n")
    
    print(f"  ✓ Reporte KPIs guardado: {ruta_kpis}")
    print("✅ Todos los resultados guardados correctamente")


def main():
    """Función principal que ejecuta todo el análisis."""
    print("\n" + "=" * 80)
    print("🏥 ANÁLISIS DE VENTAS - FARMACIA MURO")
    print("=" * 80 + "\n")
    
    # Rutas de los archivos
    base_path = Path(__file__).parent
    
    ruta_nomenclator = base_path / "20260301_Nomenclator_de_Facturacion.csv"
    rutas_estadisticas = {
        2024: base_path / "ESTADÍSTICAS" / "Informe_de_Estadisticas_de_Articulos 2024.csv",
        2025: base_path / "ESTADÍSTICAS" / "Informe_de_Estadisticas_de_Articulos 2025.csv",
        2026: base_path / "ESTADÍSTICAS" / "Informe_de_Estadisticas_de_Articulos 2026.csv",
    }
    
    try:
        # 1. Cargar nomenclátor
        df_nomenclator = cargar_nomenclator(str(ruta_nomenclator))
        
        # 2. Cargar y procesar estadísticas de cada año
        dfs_años = []
        for año, ruta in rutas_estadisticas.items():
            if ruta.exists():
                df_año = cargar_estadisticas_año(str(ruta), año)
                dfs_años.append(df_año)
            else:
                print(f"⚠️  Archivo no encontrado: {ruta}")
        
        # 3. Concatenar todos los años
        print("\n🔗 Consolidando todos los años...")
        df_ventas_todos_años = pl.concat(dfs_años)
        print(f"✅ Total registros consolidados: {df_ventas_todos_años.shape[0]:,}")
        
        # 4. Procesar ventas consolidadas
        df_consolidado = procesar_ventas_consolidadas(df_ventas_todos_años, df_nomenclator)
        
        # 5. Generar KPIs
        kpis = generar_kpis(df_consolidado)
        
        # 6. Guardar resultados
        guardar_resultados(df_consolidado, kpis)
        
        print("\n" + "=" * 80)
        print("✅ ANÁLISIS COMPLETADO EXITOSAMENTE")
        print("=" * 80 + "\n")
        
        # Mostrar resumen rápido
        print("📊 RESUMEN EJECUTIVO:")
        for año in sorted(df_consolidado['Año'].unique().to_list()):
            año_kpis = kpis[f'año_{año}']
            print(f"\n  Año {año}:")
            print(f"    • Productos vendidos: {año_kpis['total_productos_vendidos']:,}")
            print(f"    • Unidades totales: {año_kpis['total_unidades_vendidas']:,}")
            print(f"    • Ingresos estimados: {año_kpis['ingresos_totales_estimados']:,.2f} €")
        
        if 'comparativa_años' in kpis:
            print(f"\n  Crecimiento:")
            for comp_key, comp_data in kpis['comparativa_años'].items():
                print(f"    • {comp_key}: {comp_data['crecimiento_ingresos_%']:+.2f}% ingresos")
        
        print("\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
