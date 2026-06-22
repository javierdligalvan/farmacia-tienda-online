# 📊 Análisis de Ventas - Farmacia Muro

## 🎯 Descripción del Proyecto

Este proyecto analiza las ventas de productos farmacéuticos de los años 2024, 2025 y 2026, relacionándolos con el nomenclátor oficial para obtener KPIs detallados sobre laboratorios, productos más vendidos, ingresos estimados y tendencias.

## 🚀 Instalación y Configuración

### Paso 1: Crear Entorno Virtual

**Opción A - Windows (PowerShell):**
```powershell
# Navegar a la carpeta del proyecto
cd "c:\Users\javie\Escritorio\Javier\Experiencia_Laboral\Ecommerce_Farmacia\FARMACIA MURO"

# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
.\venv\Scripts\Activate.ps1
```

Si obtienes un error de ejecución de scripts, ejecuta:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Opción B - Windows (CMD):**
```cmd
cd "c:\Users\javie\Escritorio\Javier\Experiencia_Laboral\Ecommerce_Farmacia\FARMACIA MURO"
python -m venv venv
venv\Scripts\activate.bat
```

### Paso 2: Instalar Dependencias

Con el entorno virtual activado:
```powershell
pip install -r requirements.txt
```

### Paso 3: Ejecutar el Análisis

```powershell
python analisis_ventas.py
```

## 📁 Estructura del Proyecto

```
FARMACIA MURO/
│
├── 20260301_Nomenclator_de_Facturacion.csv    # Nomenclátor oficial
├── ESTADÍSTICAS/
│   ├── Informe_de_Estadisticas_de_Articulos 2024.csv
│   ├── Informe_de_Estadisticas_de_Articulos 2025.csv
│   └── Informe_de_Estadisticas_de_Articulos 2026.csv
│
├── analisis_ventas.py                          # Script principal
├── requirements.txt                            # Dependencias
├── README_INSTRUCCIONES.md                     # Este archivo
│
└── RESULTADOS/                                 # Se crea automáticamente
    ├── ventas_consolidadas_YYYYMMDD_HHMMSS.csv
    ├── analisis_completo_YYYYMMDD_HHMMSS.xlsx
    └── reporte_kpis_YYYYMMDD_HHMMSS.txt
```

## 📊 Resultados Generados

El script genera tres tipos de archivos en la carpeta `RESULTADOS/`:

### 1. **ventas_consolidadas_[fecha].csv**
Archivo CSV con todos los datos consolidados:
- Información de ventas mensuales (ventas1 a ventas12)
- Datos del nomenclátor (Laboratorio, PVP, Principio Activo)
- Columnas calculadas:
  - `Unidades_Vendidas`: Total de unidades vendidas en el año
  - `Ingresos_Estimados_PVP`: Ingresos calculados (Unidades × PVP)
  - `Q1_Ventas`, `Q2_Ventas`, `Q3_Ventas`, `Q4_Ventas`: Ventas trimestrales
  - `Año`: Año de las estadísticas (2024, 2025, 2026)

### 2. **analisis_completo_[fecha].xlsx**
Archivo Excel con los datos consolidados listos para análisis adicional en Excel/Power BI.

### 3. **reporte_kpis_[fecha].txt**
Reporte de texto con KPIs detallados:

#### KPIs por Año:
- Total de productos vendidos
- Total de unidades vendidas
- Ingresos totales estimados
- Ticket medio
- Análisis trimestral (Q1, Q2, Q3, Q4)
- Top 5 productos por unidades vendidas
- Top 5 productos por ingresos
- Top 5 laboratorios

#### KPIs Comparativos:
- Crecimiento porcentual de unidades entre años
- Crecimiento porcentual de ingresos entre años

## 🔍 KPIs Principales Calculados

### Ventas y Rentabilidad
- **Total Unidades Vendidas**: Suma de todas las unidades vendidas
- **Ingresos Estimados**: Unidades × PVP de referencia
- **Ticket Medio**: Ingresos totales / Unidades totales

### Análisis Temporal
- **Ventas Trimestrales**: Agrupación por trimestres (Q1-Q4)
- **Tendencias Anuales**: Comparación año sobre año

### Análisis por Producto
- **Top Productos por Volumen**: Productos más vendidos en unidades
- **Top Productos por Ingresos**: Productos que generan más ingresos

### Análisis por Laboratorio
- **Top Laboratorios**: Clasificación por ingresos y unidades
- **Cuota de Mercado**: Participación de cada laboratorio

## 💡 Ventajas de Usar Polars

1. **Velocidad**: 5-10x más rápido que Pandas
2. **Eficiencia de Memoria**: Usa menos RAM
3. **Sintaxis Moderna**: API más clara y expresiva
4. **Lazy Evaluation**: Optimiza automáticamente las consultas
5. **Escalabilidad**: Maneja grandes volúmenes de datos sin problemas

## 🔧 Personalización

### Modificar el Script

Puedes personalizar el análisis editando `analisis_ventas.py`:

```python
# Cambiar las rutas de los archivos (líneas 290-295)
ruta_nomenclator = "tu_ruta_personalizada.csv"

# Agregar más KPIs en la función generar_kpis() (línea 150)

# Modificar los filtros y agrupaciones según necesites
```

### Análisis Adicionales

El DataFrame consolidado incluye todas las columnas necesarias para:
- Análisis de estacionalidad
- Segmentación por principio activo
- Análisis de productos sin información
- Comparativas entre laboratorios
- Proyecciones de ventas

## 🐛 Solución de Problemas

### Error: "No se puede ejecutar scripts"
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Error: "Module not found: polars"
```powershell
# Asegúrate de tener el entorno virtual activado
pip install -r requirements.txt
```

### Error: "Archivo no encontrado"
Verifica que las rutas de los archivos CSV sean correctas y que los archivos existan.

### Advertencia: "Productos sin información en nomenclátor"
Es normal si algunos códigos nacionales no están en el nomenclátor. Estos productos aparecerán con valores NULL en las columnas del nomenclátor.

## 📈 Próximos Pasos Sugeridos

1. **Visualización**: Crear dashboards en Power BI o Tableau con los datos exportados
2. **Análisis Predictivo**: Usar machine learning para proyecciones de ventas
3. **Automatización**: Programar la ejecución automática del script mensualmente
4. **Alertas**: Configurar notificaciones para productos con bajo rendimiento
5. **Integración**: Conectar con sistemas de inventario y compras

## 📞 Soporte

Para dudas o mejoras del script, contacta con el equipo de análisis de datos.

---

**Última actualización**: Marzo 2026  
**Versión**: 1.0  
**Autor**: Javier
