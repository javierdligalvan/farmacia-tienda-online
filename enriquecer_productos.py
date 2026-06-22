#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SCRIPT DE ENRIQUECIMIENTO DE PRODUCTOS FARMACÉUTICOS
=============================================================================
Autor: Especialista en Gestión Farmacéutica Española
Fecha: 2026-03-02

DESCRIPCIÓN:
    Lee el fichero CSV de estadísticas de artículos de la farmacia y genera
    un fichero CSV enriquecido con información detallada de cada producto:
    laboratorio, tipo legal, categoría, subcategoría, código ATC, PVP oficial
    y precio medio en farmacias online.

FUENTES DE DATOS:
    - Para obtener un codigo ATC fiable de 4 digitos que luego convertir en 5: CIMA
    - Para obtener el Laboratorio que vende el Medicamento: BOTPLUS (https://www.farmaceuticos.com/botplus/buscador-botplus-lite/medicamentos/)
    - Para obtener un PVP de referencia del Medicamento: Nomenclator
    1. API CIMA de la AEMPS (https://cima.aemps.es/cima/rest/)
       → Medicamentos registrados en España: laboratorio, ATC, PVP oficial
    2. Web scraping en Atida (atida.com/es-es)
       → Precios de parafarmacia y complementos alimenticios
    3. Web scraping en Dosfarma (dosfarma.com)
       → Precios de parafarmacia y complementos alimenticios
    4. Clasificación por patrones de nombres
       → Categorización automática de productos

PASO A PASO:
    1. Leer el fichero fuente (Informe_de_Estadisticas_de_Articulos 2024.csv)
    2. Para cada producto:
       a) Determinar si el código nacional es un código de medicamento (6 dígitos)
       b) Si es medicamento → consultar API CIMA para obtener datos oficiales
       c) Si no es medicamento → clasificar por patrones del nombre
       d) Para parafarmacia → buscar precios en Atida y Dosfarma
    3. Escribir resultado en PRODUCTOS_FARMACIA_ENRICHED.csv

USO:
    python enriquecer_productos.py
=============================================================================
"""

import csv
import re
import time
import json
import os
import sys
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "ESTADÍSTICAS", "Informe_de_Estadisticas_de_Articulos 2024.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "PRODUCTOS_FARMACIA_ENRICHED.csv")
LOG_FILE = os.path.join(BASE_DIR, "enriquecimiento.log")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Tiempos de espera entre peticiones para no sobrecargar servidores
DELAY_CIMA = 0.3        # segundos entre peticiones a CIMA
DELAY_WEB = 0.5          # segundos entre peticiones web scraping
REQUEST_TIMEOUT = 15      # timeout de peticiones HTTP

# Headers para simular navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Columnas del CSV de salida
OUTPUT_COLUMNS = [
    "CODIGO",
    "NOMBRE",
    "LABORATORIO / TITULAR EN ESPAÑA",
    "TIPO LEGAL",
    "CATEGORIA PRINCIPAL",
    "SUBCATEGORIA DETALLADA",
    "ATC",
    "PVP OFICIAL ESPAÑA (€)",
    "PRECIO MEDIO FARMACIA ONLINE ESPAÑA (€)"
]


# =============================================================================
# MODELO DE DATOS
# =============================================================================

@dataclass
class ProductoEnriquecido:
    """Estructura de datos para un producto enriquecido."""
    codigo: str = ""
    nombre: str = ""
    laboratorio: str = "PENDIENTE VERIFICACION"
    tipo_legal: str = "PENDIENTE VERIFICACION"
    categoria_principal: str = "PENDIENTE VERIFICACION"
    subcategoria: str = "PENDIENTE VERIFICACION"
    atc: str = "NO APLICA"
    pvp_oficial: str = "NO REGULADO"
    precio_online: str = "PENDIENTE VERIFICACION"
    fuentes: list = field(default_factory=list)

    def to_csv_row(self) -> list:
        return [
            self.codigo,
            self.nombre,
            self.laboratorio,
            self.tipo_legal,
            self.categoria_principal,
            self.subcategoria,
            self.atc,
            self.pvp_oficial,
            self.precio_online,
        ]


# =============================================================================
# PASO 1: CONSULTA A LA API CIMA DE LA AEMPS
# =============================================================================

class CIMAClient:
    """
    Cliente para la API REST de CIMA (Centro de Información de Medicamentos
    Autorizados) de la AEMPS (Agencia Española de Medicamentos y Productos Sanitarios).
    
    Documentación: https://cima.aemps.es/cima/rest
    """
    
    BASE_URL = "https://cima.aemps.es/cima/rest"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'FarmaciaEnriquecimiento/1.0'
        })
        self.cache = {}  # Cache para evitar peticiones repetidas
    
    def buscar_por_cn(self, codigo_nacional: str) -> Optional[dict]:
        """
        Busca un medicamento por su Código Nacional en CIMA.
        
        El CN en CIMA es de 6 dígitos. Si el código viene con formato
        8470XXXXXXXXX (EAN-13), extraemos los 6 dígitos del CN.
        
        Args:
            codigo_nacional: Código nacional del medicamento (6 dígitos)
            
        Returns:
            dict con datos del medicamento o None si no se encuentra.
        """
        cn = self._normalizar_cn(codigo_nacional)
        if not cn:
            return None
        
        if cn in self.cache:
            return self.cache[cn]
        
        try:
            url = f"{self.BASE_URL}/medicamento"
            params = {"cn": cn}
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Consulta CIMA por CN {cn} JSON response: {json.dumps(data)}...")
                if data and isinstance(data, dict) and data.get("nombre"):
                    self.cache[cn] = data
                    return data
            
            time.sleep(DELAY_CIMA)
            return None
            
        except Exception as e:
            logger.debug(f"Error consultando CIMA para CN {cn}: {e}")
            return None
    
    def buscar_por_nombre(self, nombre: str) -> Optional[dict]:
        """
        Busca un medicamento por nombre en CIMA.
        
        Args:
            nombre: Nombre del medicamento
            
        Returns:
            dict con datos del primer resultado o None.
        """
        # Limpiar el nombre para búsqueda
        nombre_busqueda = nombre.split(" EFG")[0].strip()
        nombre_busqueda = re.sub(r'\d+\s*(MG|MCG|ML|G|UI|MGML)\b.*', '', nombre_busqueda).strip()
        
        if not nombre_busqueda or len(nombre_busqueda) < 3:
            return None
        
        cache_key = f"nombre:{nombre_busqueda}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            url = f"{self.BASE_URL}/medicamentos"
            params = {"nombre": nombre_busqueda}
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                resultados = data.get("resultados", [])
                if resultados and len(resultados) > 0:
                    # Tomar el primer resultado
                    med = resultados[0]
                    self.cache[cache_key] = med
                    return med
            
            time.sleep(DELAY_CIMA)
            return None
            
        except Exception as e:
            logger.debug(f"Error buscando en CIMA por nombre '{nombre_busqueda}': {e}")
            return None
    
    def extraer_datos(self, data: dict) -> dict:
        """
        Extrae los campos relevantes de la respuesta de CIMA.
        
        Args:
            data: Respuesta JSON de la API CIMA
            
        Returns:
            dict con laboratorio, atc, pvp, tipo, etc.
        """
        resultado = {
            "laboratorio": "PENDIENTE VERIFICACION",
            "atc": "NO APLICA",
            "pvp": "NO REGULADO",
            "tipo_legal": "Medicamento marca",
            "receta": False,
            "es_efg": False,
            "es_hospitalario": False,
        }
        
        # Laboratorio
        lab = data.get("labtitular", "")
        if not lab:
            lab = data.get("labcomercializador", "")
        if lab:
            resultado["laboratorio"] = lab
        
        # Código ATC
        atc_info = data.get("atcs", [])
        if atc_info and len(atc_info) > 0:
            resultado["atc"] = atc_info[0].get("codigo", "NO APLICA")
        
        # PVP
        pvp = data.get("pvp")
        if pvp:
            resultado["pvp"] = f"{float(pvp):.2f}"
        
        # EFG
        nombre = data.get("nombre", "")
        if "EFG" in nombre.upper():
            resultado["es_efg"] = True
            resultado["tipo_legal"] = "Medicamento EFG"
        
        # Hospitalario
        cpresc = data.get("cpresc", "")
        if cpresc and "hospitalario" in str(cpresc).lower():
            resultado["es_hospitalario"] = True
            resultado["tipo_legal"] = "Medicamento hospitalario"
        
        # Condiciones de prescripción
        condiciones = data.get("condicionesDispensacion", "")
        if condiciones and "H" in str(condiciones):
            resultado["es_hospitalario"] = True
            resultado["tipo_legal"] = "Medicamento hospitalario"
        
        return resultado
    
    def _normalizar_cn(self, codigo: str) -> Optional[str]:
        """
        Normaliza un código a formato CN de 6 dígitos.
        Si es un EAN-13 (8470...), extrae el CN.
        """
        codigo = str(codigo).strip()
        
        # Si es un código numérico de 6 dígitos, es un CN directamente
        if re.match(r'^\d{6}$', codigo):
            return codigo
        
        # Si es un EAN-13 español (8470...), extraer CN
        # Formato: 8470 + XX + XXXXXX + D (check digit)
        # Los dígitos 5-10 son el CN
        if re.match(r'^8470\d{9}$', codigo):
            return codigo[4:10]
        
        return None


# =============================================================================
# PASO 2: WEB SCRAPING PARA PRECIOS ONLINE
# =============================================================================

class PreciosScraper:
    """
    Scraper para obtener precios de productos de parafarmacia en
    farmacias online españolas (Atida, Dosfarma, Promofarma).
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
    
    def buscar_precio_atida(self, nombre_producto: str) -> Optional[float]:
        """
        Busca el precio de un producto en Atida (atida.com/es-es).
        Usa la API de búsqueda de Atida.
        """
        try:
            # Simplificar nombre para búsqueda
            query = self._simplificar_nombre(nombre_producto)
            url = f"https://www.atida.com/es-es/catalogsearch/result/"
            params = {"q": query}
            
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Buscar el precio en los resultados
            # Atida usa data-price-amount en spans
            precio_elements = soup.select('[data-price-amount]')
            if precio_elements:
                precio_str = precio_elements[0].get('data-price-amount', '')
                if precio_str:
                    return float(precio_str)
            
            # Alternativa: buscar en el texto
            precio_pattern = re.compile(r'(\d+[,\.]\d{2})\s*€')
            for tag in soup.find_all(['span', 'div'], class_=re.compile(r'price|precio')):
                match = precio_pattern.search(tag.get_text())
                if match:
                    return float(match.group(1).replace(',', '.'))
            
            return None
            
        except Exception as e:
            logger.debug(f"Error buscando precio en Atida para '{nombre_producto}': {e}")
            return None
    
    def buscar_precio_dosfarma(self, nombre_producto: str) -> Optional[float]:
        """
        Busca el precio de un producto en Dosfarma (dosfarma.com).
        """
        try:
            query = self._simplificar_nombre(nombre_producto)
            url = f"https://www.dosfarma.com/catalogsearch/result/"
            params = {"q": query}
            
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Buscar data-price-amount
            precio_elements = soup.select('[data-price-amount]')
            if precio_elements:
                precio_str = precio_elements[0].get('data-price-amount', '')
                if precio_str:
                    return float(precio_str)
            
            # Alternativa: buscar en texto
            precio_pattern = re.compile(r'(\d+[,\.]\d{2})\s*€')
            for tag in soup.find_all(['span', 'div'], class_=re.compile(r'price|precio')):
                match = precio_pattern.search(tag.get_text())
                if match:
                    return float(match.group(1).replace(',', '.'))
            
            return None
            
        except Exception as e:
            logger.debug(f"Error buscando precio en Dosfarma para '{nombre_producto}': {e}")
            return None
    
    def obtener_precio_medio(self, nombre_producto: str) -> tuple[str, list]:
        """
        Obtiene el precio medio de un producto buscando en varias farmacias online.
        
        Returns:
            tuple: (precio_medio_str, lista_de_fuentes)
        """
        precios = []
        fuentes = []
        
        # Buscar en Atida
        precio_atida = self.buscar_precio_atida(nombre_producto)
        if precio_atida and precio_atida > 0:
            precios.append(precio_atida)
            fuentes.append(f"Atida: {precio_atida:.2f}€")
        time.sleep(DELAY_WEB)
        
        # Buscar en Dosfarma
        precio_dosfarma = self.buscar_precio_dosfarma(nombre_producto)
        if precio_dosfarma and precio_dosfarma > 0:
            precios.append(precio_dosfarma)
            fuentes.append(f"Dosfarma: {precio_dosfarma:.2f}€")
        time.sleep(DELAY_WEB)
        
        if precios:
            media = sum(precios) / len(precios)
            return f"{media:.2f}", fuentes
        
        return "PENDIENTE VERIFICACION", fuentes
    
    def _simplificar_nombre(self, nombre: str) -> str:
        """Simplifica el nombre del producto para búsqueda."""
        # Quitar unidades y cantidades del final
        nombre = re.sub(r'\s+\d+\s*UD(S|IDADES)?\.?\s*$', '', nombre, flags=re.IGNORECASE)
        # Quitar "1 UNIDAD", "1 UD", etc.
        nombre = re.sub(r'\s+1\s*(UNIDAD|UD)\.?\s*$', '', nombre, flags=re.IGNORECASE)
        # Tomar las primeras 4-5 palabras para no ser demasiado específico
        palabras = nombre.split()
        if len(palabras) > 5:
            nombre = ' '.join(palabras[:5])
        return nombre


# =============================================================================
# PASO 3: CLASIFICADOR DE PRODUCTOS POR PATRONES
# =============================================================================

class ClasificadorProductos:
    """
    Clasifica productos farmacéuticos en categorías basándose en
    patrones del nombre del producto y del código.
    """
    
    # ---- Patrones para detectar MEDICAMENTOS por nombre ----
    # Formas farmacéuticas típicas de medicamentos
    FORMAS_FARMACEUTICAS = (
        r'\b(COMP(RIMIDOS?)?|CAPS(ULAS?)?|GRAG(EAS?)?|TABL(ETAS?)?|'
        r'SOBR(ES?)?|AMP(OLLAS?)?|SUSP(ENSION)?|SOL(UCION)?|'
        r'JBE|JARABE|INY(ECTABLE)?|PLUM(AS?)?|INH(ALADOR)?|'
        r'PARCHES?|OVULOS?|SUPOSITORIOS?|CR(EMA)?\s+\d|'
        r'PDA|POMADA|GEL\s+\d|GOTAS?\s+\d|COLI(RIO)?|'
        r'SPRAY\s+NASAL|AEROSOL|POLVO.*INHAL|NEBULIZ|'
        r'VIAL(ES)?|CARTUCHO|SOLOST|JGA|JERINGA\s+PREC)\b'
    )
    
    # Marcas conocidas de nutrición deportiva
    MARCAS_NUTRICION_DEPORTIVA = [
        "226ERS", "KEEPGOING", "NAMEDSPORT", "ISOSTAR", "POWERBAR",
        "SIS", "GU ENERGY", "MAURTEN", "PRECISION FUEL",
    ]
    
    # Marcas conocidas de parafarmacia / higiene
    MARCAS_PARAFARMACIA = [
        "APOSAN", "ACOFAR", "ACOFARMA", "NESIRA", "VIVERA", "INTERAPOTHEK",
        "SUAVINEX", "NUK", "DODOT", "AUSONIA", "TENA",
        "CORYSAN", "LUSAN", "FARMALASTIC", "FUTURO",
    ]
    
    # Marcas de dermocosmética
    MARCAS_DERMOCOSMETICA = [
        "AVENE", "ANTHELIOS", "LA ROCHE", "ROCHE POSAY", "VICHY",
        "EUCERIN", "ISDIN", "BIODERMA", "SESDERMA", "MARTIDERM",
        "ENDOCARE", "BIRETIX", "CANTABRIA", "BEPANTHOL",
        "CICALFATE", "CLEANANCE", "COUVRANCE", "XERACALM",
        "BELCILS", "BEXIDENT", "BIMAIO", "BELLA AURORA",
        "BASIKO", "ACNIBEN", "BABE", "BIO OIL", "BABY NATURALS",
        "CAMALEON", "BALSODERM", "BE+",
    ]
    
    # Marcas de complementos alimenticios
    MARCAS_COMPLEMENTOS = [
        "AQUILEA", "ANA L J", "ANA LAJUSTICIA", "ARKOCAPS", "ARKOCAPSULAS",
        "ARKOVOX", "ARMOLIPID", "ARTIOK", "ARTIMUSC",
        "ASTENOLIT", "BIVOS", "BIE 3", "BIE3", "BIORALSUERO",
        "BION 3", "BION3", "ALFLOREX", "AORA", "ZZZQUIL",
        "AQUORAL", "ACUMAX", "ACUOK", "BROKEN", "ATERINA",
        "AUDIOVIT", "ANDROMAS", "ALIVIOLAS", "BLUEBERRY",
        "ALANERV", "ALASOD", "BOIRON", "BOI K", "BOLDO",
        "ADOMELLE", "BIFISELLE", "NUTERGIA", "BROMATECH",
    ]
    
    # Productos sanitarios (dispositivos médicos)
    PATRONES_PRODUCTO_SANITARIO = [
        r'\bTIRAS?\b.*\b(REACTIV|GLUCOS|TEST)\b',
        r'\bAGUJA', r'\bJERINGU', r'\bVENDA\b', r'\bESPARAD',
        r'\bAPOSITO', r'\bGUANTE', r'\bMASC(ARILLA)?\b',
        r'\bTERMOMETRO', r'\bPULSIOXIMETRO', r'\bNEBULIZADOR',
        r'\bCABESTRILLO', r'\bMULETA', r'\bBAST[OÓ]N',
        r'\bCALCETIN\b.*\bCOMPRESI', r'\bMEDIA\b.*\bCOMPRESI',
        r'\bBOLSA.*ORINA', r'\bSONDA\b', r'\bPARCHE\s+OCULAR',
        r'\bPASTILLERO', r'\bCORTADOR\b.*\bTRITURA',
        r'\bBISTURI', r'\bSUTURA', r'\bEMPAPADOR',
        r'\bABS\s+PANTS\b', r'\bABSORBENTE\b.*\bINCONTINENCIA',
        r'\bACCU-CHEK', r'\bAUTOTEST',
        r'\bBOLSA.*GEL.*FRIO', r'\bALMOHADA.*ELECTRI',
        r'\bBIBERON\b', r'\bASPIRADOR\s+NASAL',
        r'\bCUBRE\s+ESCAYOL',
        r'\bDILATADOR\s+NASAL',
        r'\bARO\s+PROTECTOR',
        r'\bREPEL', r'\bANTIPIOX',
        r'\bTAPON\b.*\b(CERA|SILIC)',
        r'\bZUECO\b', r'\bHANKSHOES\b',
    ]
    
    # Productos veterinarios
    PATRONES_VETERINARIO = [
        r'\bVET(ERINAR)?\b',
        r'\bPERRO', r'\bGATO', r'\bMASCOTA',
        r'\bBRAVECTO\b', r'\bBAYTRIL\b', r'\bADTAB\b',
        r'\bADOCAM\b', r'\bAMOXIBACTIN\b',
    ]
    
    # Productos de higiene bucal (no medicamentos)
    PATRONES_HIGIENE_BUCAL = [
        r'\bPASTA\s+(DENT|125|75)', r'\bCOLUTOR', r'\bENJUAGUE',
        r'\bCEPILLO.*DENT', r'\bSEDA.*DENT', r'\bHILO.*DENT',
        r'\bBEXIDENT\b', r'\bLACER\b(?!.*\bMG\b)', r'\bORTHODONTIC',
    ]
    
    # Alimentación infantil
    PATRONES_ALIMENTACION_INFANTIL = [
        r'\bALMIRON\b', r'\bBLEMIL\b', r'\bBLEVIT\b',
        r'\bHERO\s+BABY', r'\bNUTRIBEN',
    ]
    
    # Laboratorios conocidos para ciertos productos
    LABORATORIOS_CONOCIDOS = {
        "226ERS": "226ERS SPORTS THINGS, S.L.",
        "KEEPGOING": "KEEPGOING SPORTS, S.L.",
        "APOSAN": "LABORATORIOS HERBITAS, S.L. (marca Aposan)",
        "ACOFAR": "ACOFARMA DISTRIBUCIÓN, S.A.",
        "ACOFARMA": "ACOFARMA DISTRIBUCIÓN, S.A.",
        "NESIRA": "ACOFARMA DISTRIBUCIÓN, S.A.",
        "VIVERA": "ACOFARMA DISTRIBUCIÓN, S.A.",
        "ACOFARBABY": "ACOFARMA DISTRIBUCIÓN, S.A.",
        "INTERAPOTHEK": "INTER-PHARMA, S.A.U.",
        "AVENE": "PIERRE FABRE IBÉRICA, S.A.",
        "ANTHELIOS": "LA ROCHE-POSAY (L'ORÉAL)",
        "ROCHE POSAY": "LA ROCHE-POSAY (L'ORÉAL)",
        "SUAVINEX": "SUAVINEX, S.L.",
        "AQUILEA": "URIACH, S.A.",
        "ARKOCAPS": "ARKOPHARMA LABORATORIOS, S.A.",
        "ARKOCAPSULAS": "ARKOPHARMA LABORATORIOS, S.A.",
        "ARKOVOX": "ARKOPHARMA LABORATORIOS, S.A.",
        "ARKOSUEÑO": "ARKOPHARMA LABORATORIOS, S.A.",
        "ANA L J": "ANA MARIA LAJUSTICIA, S.L.",
        "ANA LAJUSTICIA": "ANA MARIA LAJUSTICIA, S.L.",
        "ARMOLIPID": "MYLAN (VIATRIS)",
        "ISDIN": "ISDIN, S.A.",
        "EUCERIN": "BEIERSDORF, S.A.",
        "BIODERMA": "NAOS (BIODERMA)",
        "BEPANTHOL": "BAYER HISPANIA, S.L.",
        "BIMAIO": "BIMAIO COSMECEUTICALS, S.L.",
        "BEXIDENT": "LABORATORIOS VIÑAS, S.A.",
        "BELCILS": "VIÑAS, S.A.",
        "BELLA AURORA": "BELLA AURORA LABS, S.A.",
        "ZZZQUIL": "PROCTER & GAMBLE ESPAÑA, S.A.",
        "BIVOS": "FERRING, S.A.U.",
        "BIE 3": "BIO3, S.L.",
        "BIE3": "BIO3, S.L.",
        "BIORALSUERO": "CASEN RECORDATI, S.L.",
        "ARNIDOL": "LABORATORIOS PHERGAL, S.A.",
        "ARNICA BOIRON": "BOIRON",
        "AFTER BITE": "ESTEVE",
        "BION 3": "MERCK, S.L.U.",
        "BION3": "MERCK, S.L.U.",
        "ALFLOREX": "BIOCODEX",
        "ASTENOLIT": "FAES FARMA, S.A.",
        "BROKEN": "VIÑAS, S.A.",
        "NUK": "JANÉ, S.A. (NUK)",
        "BETAFAR": "LABORATORIOS BETAFAR, S.L.",
        "CORYSAN": "CORYSAN, S.A.",
        "LUSAN": "LUSAN, S.A.",
        "BABE": "LABORATORIOS BABÉ, S.L.",
        "BIO OIL": "PERRIGO (BIO-OIL)",
        "BABY NATURALS": "CASEN RECORDATI, S.L.",
        "AUSONIA": "PROCTER & GAMBLE ESPAÑA, S.A.",
        "DODOT": "PROCTER & GAMBLE ESPAÑA, S.A.",
        "BLEFARIX": "THEA LABORATORIOS",
        "BLEPHADERM": "THEA LABORATORIOS",
        "BLEPHAEYEBAG": "THEA LABORATORIOS",
        "BIRETIX": "CANTABRIA LABS",
        "CAMALEON": "CAMALEON COSMETICS",
        "BALSODERM": "BALSODERM",
        "AFTALACER": "LACER, S.A.",
        "ALOCLAIR": "SINCLAIR PHARMA",
        "AFTEX": "LABORATORIOS VIÑAS, S.A.",
        "ALGASIV": "COMBE (ALGASIV)",
        "BETER": "BETER PRODUCTS, S.L.",
        "BOLDO": "URIACH, S.A.",
        "BOIRON": "BOIRON",
        "BE+": "CINFA BIOTECH",
    }
    
    def clasificar(self, codigo: str, nombre: str) -> ProductoEnriquecido:
        """
        Clasifica un producto basándose en su código y nombre.
        
        Args:
            codigo: Código del producto
            nombre: Nombre del producto
            
        Returns:
            ProductoEnriquecido con la clasificación inicial
        """
        producto = ProductoEnriquecido(codigo=codigo, nombre=nombre)
        nombre_upper = nombre.upper()
        
        # 1. ¿Es un producto veterinario?
        if self._match_patrones(nombre_upper, self.PATRONES_VETERINARIO):
            producto.tipo_legal = "Medicamento veterinario"
            producto.categoria_principal = "Veterinaria"
            producto.subcategoria = self._subcategoria_veterinaria(nombre_upper)
            producto.atc = "NO APLICA (veterinario)"
            producto.pvp_oficial = "NO REGULADO"
            return producto
        
        # 2. ¿Es nutrición deportiva?
        for marca in self.MARCAS_NUTRICION_DEPORTIVA:
            if marca in nombre_upper:
                producto.tipo_legal = "Complemento alimenticio"
                producto.categoria_principal = "Nutrición deportiva"
                producto.subcategoria = self._subcategoria_nutricion(nombre_upper)
                producto.laboratorio = self.LABORATORIOS_CONOCIDOS.get(marca, "PENDIENTE VERIFICACION")
                producto.pvp_oficial = "NO REGULADO"
                return producto
        
        # 3. ¿Es un producto sanitario / dispositivo médico?
        if self._match_patrones(nombre_upper, self.PATRONES_PRODUCTO_SANITARIO):
            producto.tipo_legal = "Producto sanitario"
            producto.categoria_principal = self._categoria_producto_sanitario(nombre_upper)
            producto.subcategoria = self._subcategoria_producto_sanitario(nombre_upper)
            producto.pvp_oficial = "NO REGULADO"
            producto.laboratorio = self._detectar_laboratorio(nombre_upper)
            return producto
        
        # 4. ¿Es alimentación infantil?
        if self._match_patrones(nombre_upper, self.PATRONES_ALIMENTACION_INFANTIL):
            producto.tipo_legal = "Alimento infantil"
            producto.categoria_principal = "Alimentación infantil"
            producto.subcategoria = self._subcategoria_infantil(nombre_upper)
            producto.laboratorio = self._detectar_laboratorio(nombre_upper)
            producto.pvp_oficial = "NO REGULADO"
            return producto
        
        # 5. ¿Es dermocosmética?
        for marca in self.MARCAS_DERMOCOSMETICA:
            if marca in nombre_upper:
                producto.tipo_legal = "Dermocosmética"
                producto.categoria_principal = "Dermocosmética"
                producto.subcategoria = self._subcategoria_dermocosmetica(nombre_upper)
                producto.laboratorio = self.LABORATORIOS_CONOCIDOS.get(marca, "PENDIENTE VERIFICACION")
                producto.pvp_oficial = "NO REGULADO"
                return producto
        
        # 6. ¿Es un complemento alimenticio conocido?
        for marca in self.MARCAS_COMPLEMENTOS:
            if marca in nombre_upper:
                producto.tipo_legal = "Complemento alimenticio"
                producto.categoria_principal = self._categoria_complemento(nombre_upper)
                producto.subcategoria = self._subcategoria_complemento(nombre_upper)
                producto.laboratorio = self.LABORATORIOS_CONOCIDOS.get(marca, "PENDIENTE VERIFICACION")
                producto.pvp_oficial = "NO REGULADO"
                return producto
        
        # 7. ¿Es parafarmacia conocida?
        for marca in self.MARCAS_PARAFARMACIA:
            if marca in nombre_upper:
                producto.tipo_legal = "Parafarmacia"
                producto.categoria_principal = self._categoria_parafarmacia(nombre_upper)
                producto.subcategoria = self._subcategoria_parafarmacia(nombre_upper)
                producto.laboratorio = self.LABORATORIOS_CONOCIDOS.get(marca, "PENDIENTE VERIFICACION")
                producto.pvp_oficial = "NO REGULADO"
                return producto
        
        # 8. ¿Tiene pinta de ser un medicamento por su nombre?
        # (contiene formas farmacéuticas y dosis)
        if re.search(r'\d+\s*MG\b', nombre_upper) and re.search(self.FORMAS_FARMACEUTICAS, nombre_upper):
            producto.tipo_legal = "Medicamento marca"
            if "EFG" in nombre_upper:
                producto.tipo_legal = "Medicamento EFG"
            producto.pvp_oficial = "PENDIENTE VERIFICACION"
            producto.precio_online = "SEGÚN PVP"
            return producto
        
        # 9. Detectar por código numérico de 6 dígitos (probable medicamento)
        if re.match(r'^\d{6}$', str(codigo).strip()):
            producto.tipo_legal = "Medicamento marca"
            if "EFG" in nombre_upper:
                producto.tipo_legal = "Medicamento EFG"
            producto.pvp_oficial = "PENDIENTE VERIFICACION"
            producto.precio_online = "SEGÚN PVP"
            return producto
        
        # 10. Otros productos - clasificar por nombre
        producto.tipo_legal = self._detectar_tipo_legal_generico(nombre_upper)
        producto.categoria_principal = self._detectar_categoria_generica(nombre_upper)
        producto.subcategoria = self._detectar_subcategoria_generica(nombre_upper)
        producto.laboratorio = self._detectar_laboratorio(nombre_upper)
        producto.pvp_oficial = "NO REGULADO"
        
        return producto
    
    def _match_patrones(self, texto: str, patrones: list) -> bool:
        """Comprueba si el texto coincide con alguno de los patrones."""
        for patron in patrones:
            if re.search(patron, texto, re.IGNORECASE):
                return True
        return False
    
    def _detectar_laboratorio(self, nombre: str) -> str:
        """Intenta detectar el laboratorio por el nombre."""
        for marca, lab in self.LABORATORIOS_CONOCIDOS.items():
            if marca.upper() in nombre.upper():
                return lab
        return "PENDIENTE VERIFICACION"
    
    # ---- Métodos de subcategorización ----
    
    def _subcategoria_nutricion(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["GEL ENERGE", "ENERGY GEL", "HIGH ENERGY", "HIGH FRUCTOSE GEL",
                                  "ISOTONIC GEL", "HYDRAJELLY"]):
            return "Geles energéticos"
        if any(x in n for x in ["ENERGY DRINK", "ISOTONIC DRINK", "HYDRAZERO"]):
            return "Bebidas isotónicas/energéticas"
        if any(x in n for x in ["RECOVERY", "RECUPERA"]):
            return "Recuperadores musculares"
        if any(x in n for x in ["PROTEIN", "WHEY", "ISOLATE"]):
            return "Proteínas"
        if "CREATINA" in n or "CREAPURE" in n:
            return "Creatina"
        if any(x in n for x in ["SALT", "ELECTROLYTE", "SUB9"]):
            return "Sales minerales/electrolitos"
        if any(x in n for x in ["CAFFEIN", "CAFEINA"]):
            return "Cafeína en cápsulas"
        if any(x in n for x in ["BAR ", "BARRIT", "GUMMI", "NEO BAR", "RACE DAY"]):
            return "Barritas/gominolas energéticas"
        if "BETA ALANINA" in n:
            return "Beta-alanina"
        if "VITAMIN" in n:
            return "Vitaminas deportivas"
        if "K-WEEKS" in n:
            return "Suplemento recuperación inmune"
        if "NITRO" in n or "REMOLACHA" in n:
            return "Suplemento rendimiento (nitratos)"
        if "ENERGY SHOT" in n:
            return "Shots energéticos"
        if "COFFEE" in n or "CAFÉ" in n:
            return "Café especialidad deportiva"
        if "CHEW" in n:
            return "Comprimidos masticables deportivos"
        return "Nutrición deportiva general"
    
    def _subcategoria_dermocosmetica(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["SPF", "SOLAR", "50+", "PROTEC", "ANTHELIOS"]):
            return "Protección solar"
        if any(x in n for x in ["ACNE", "CLEANANCE", "ACNIBEN", "COMEDOMED"]):
            return "Tratamiento acné"
        if any(x in n for x in ["ANTI-EDAD", "ANTI EDAD", "ARRUG", "RETINOL", "DERMABSOLU"]):
            return "Antiedad"
        if any(x in n for x in ["HIDRAT", "HYDRANCE"]):
            return "Hidratación facial"
        if any(x in n for x in ["CICALFATE", "CICATRI", "REPAR"]):
            return "Reparación cutánea"
        if any(x in n for x in ["CONTORNO", "OJOS"]):
            return "Contorno de ojos"
        if any(x in n for x in ["DESMAQ", "MICELAR", "LIMP"]):
            return "Limpieza facial"
        if any(x in n for x in ["SERUM", "SÉRUM"]):
            return "Sérum facial"
        if any(x in n for x in ["AGUA TERMAL"]):
            return "Agua termal"
        if any(x in n for x in ["XERACALM", "ATOPI"]):
            return "Piel atópica"
        if any(x in n for x in ["TATTOO", "TATUAJE"]):
            return "Cuidado tatuajes"
        if any(x in n for x in ["PESTA", "MASCARA"]):
            return "Maquillaje/pestañas"
        if any(x in n for x in ["BEBE", "BEBÉ", "PEDIAT"]):
            return "Dermocosmética pediátrica"
        if any(x in n for x in ["CORP", "BODY"]):
            return "Cuidado corporal"
        return "Dermocosmética general"
    
    def _subcategoria_complemento(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["SUEÑO", "MELATONIN", "DORMIG"]):
            return "Sueño y relajación"
        if any(x in n for x in ["MUCUS", "TOS", "GARGANTA", "PROPOLIS"]):
            return "Vías respiratorias"
        if any(x in n for x in ["COLAGEN", "ARTICU", "ARTIOK", "ARTIMUSC"]):
            return "Articulaciones y colágeno"
        if any(x in n for x in ["MAGNESIO", "MAGNESI"]):
            return "Magnesio"
        if any(x in n for x in ["OMEGA", "COLESTER", "ARMOLIPID"]):
            return "Cardiovascular / colesterol"
        if any(x in n for x in ["PROSTAT"]):
            return "Salud prostática"
        if any(x in n for x in ["VIGOR"]):
            return "Vitalidad sexual"
        if any(x in n for x in ["DRENAN", "DETOX", "SILUETA"]):
            return "Drenaje y control de peso"
        if any(x in n for x in ["GASES", "DIGEST"]):
            return "Digestivo"
        if any(x in n for x in ["EQUINACEA", "INMUN"]):
            return "Defensas/inmunidad"
        if any(x in n for x in ["LACTOBACIL", "PROBIO", "FLORA"]):
            return "Probióticos"
        if any(x in n for x in ["VITAMINA", "VITAMIN"]):
            return "Vitaminas"
        if any(x in n for x in ["TRIPTOF"]):
            return "Triptófano / bienestar emocional"
        if any(x in n for x in ["ALGAS", "ALCACHOFA", "CARDO"]):
            return "Fitoterapia"
        if any(x in n for x in ["ONAGRA"]):
            return "Ácido gamma-linolénico"
        if any(x in n for x in ["JENGIBRE"]):
            return "Fitoterapia digestiva"
        if any(x in n for x in ["ORAL", "SUERO"]):
            return "Rehidratación oral"
        return "Complemento alimenticio general"
    
    def _categoria_complemento(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["SUEÑO", "MELATONIN", "TRANQUIL"]):
            return "Sueño y bienestar"
        if any(x in n for x in ["MUCUS", "TOS", "RESPIRAT"]):
            return "Sistema respiratorio"
        if any(x in n for x in ["COLAGEN", "ARTICU"]):
            return "Aparato locomotor"
        if any(x in n for x in ["COLESTER", "OMEGA"]):
            return "Cardiovascular"
        if any(x in n for x in ["DRENAN", "DETOX", "SILUETA"]):
            return "Control de peso"
        if any(x in n for x in ["DIGEST", "GASES"]):
            return "Digestivo"
        if any(x in n for x in ["PROBIO", "LACTO", "FLORA"]):
            return "Probióticos"
        return "Complementos alimenticios"
    
    def _categoria_parafarmacia(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["GEL ", "JABON", "CHAMPU", "CHAMP", "TOALLITA"]):
            return "Higiene"
        if any(x in n for x in ["PROTECTOR LAB", "SPF"]):
            return "Protección solar"
        if any(x in n for x in ["BIBERON", "CHUPETE", "BEBE", "BEBÉ"]):
            return "Puericultura"
        if any(x in n for x in ["LENTILLA", "OCULAR"]):
            return "Óptica"
        if any(x in n for x in ["ALCOHOL", "AGUA OXIG", "CLORHEXI", "BIOCIDA"]):
            return "Desinfección"
        if any(x in n for x in ["CREMA DE MANOS", "LECHE MATERN"]):
            return "Cuidado personal"
        if any(x in n for x in ["FRESHMINT", "PERLA"]):
            return "Higiene bucal"
        return "Parafarmacia general"
    
    def _subcategoria_parafarmacia(self, nombre: str) -> str:
        n = nombre.upper()
        if "GEL" in n and ("BAÑO" in n or "DUCHA" in n or "750" in n or "1000" in n or "ML" in n):
            return "Gel de baño/ducha"
        if "JABON" in n and "MANOS" in n:
            return "Jabón de manos"
        if "CHAMPU" in n or "CHAMP" in n:
            return "Champú"
        if "TOALLITA" in n:
            return "Toallitas higiénicas"
        if "PROTECTOR LAB" in n:
            return "Protector labial"
        if "SPF" in n:
            return "Protección solar"
        if "ALCOHOL" in n:
            return "Alcohol sanitario"
        if "AGUA OXIG" in n:
            return "Agua oxigenada"
        if "BIBERON" in n:
            return "Biberones"
        if "FRESHMINT" in n or "PERLA" in n:
            return "Refrescante bucal"
        if "CREMA" in n and "MANOS" in n:
            return "Crema de manos"
        return "Parafarmacia general"
    
    def _subcategoria_veterinaria(self, nombre: str) -> str:
        n = nombre.upper()
        if "PERRO" in n:
            return "Medicamento veterinario canino"
        if "GATO" in n:
            return "Medicamento veterinario felino"
        return "Medicamento veterinario"
    
    def _categoria_producto_sanitario(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["ABS PANTS", "ABSORBENTE", "INCONTINENCIA"]):
            return "Incontinencia"
        if any(x in n for x in ["AGUJA", "JERINGU", "ACCU-CHEK"]):
            return "Material de inyección/diagnóstico"
        if any(x in n for x in ["APOSITO", "TIRA", "VENDA", "ESPARAD", "SUTURA"]):
            return "Curas y apósitos"
        if any(x in n for x in ["GUANTE", "MASCARILLA"]):
            return "Protección/EPI"
        if any(x in n for x in ["TERMOMETRO", "PULSIOXIMETRO"]):
            return "Diagnóstico"
        if any(x in n for x in ["CABESTRILLO", "MULETA", "BASTÓN"]):
            return "Ortopedia"
        if any(x in n for x in ["ZUECO", "HANKSHOES"]):
            return "Calzado sanitario"
        if any(x in n for x in ["BIBERON", "ASPIRADOR NASAL"]):
            return "Puericultura"
        return "Producto sanitario general"
    
    def _subcategoria_producto_sanitario(self, nombre: str) -> str:
        n = nombre.upper()
        if "ABS PANTS" in n or "ABSORBENTE" in n:
            return "Ropa interior absorbente"
        if "AGUJA" in n:
            return "Agujas"
        if "JERINGU" in n:
            return "Jeringas"
        if "APOSITO" in n:
            return "Apósitos estériles"
        if "TIRA" in n:
            if "REACTIV" in n or "GLUCOS" in n:
                return "Tiras reactivas glucemia"
            return "Tiritas/apósitos adhesivos"
        if "VENDA" in n:
            return "Vendas"
        if "ESPARAD" in n:
            return "Esparadrapo"
        if "GUANTE" in n:
            return "Guantes desechables"
        if "TERMOMETRO" in n:
            return "Termómetro"
        if "ZUECO" in n:
            return "Zueco sanitario"
        if "AUTOTEST" in n:
            return "Autotest diagnóstico"
        return "Producto sanitario"
    
    def _subcategoria_infantil(self, nombre: str) -> str:
        n = nombre.upper()
        if "ADVANCE 1" in n or "PROFUT" in n and "1" in n:
            return "Leche inicio (0-6 meses)"
        if "ADVANCE 2" in n:
            return "Leche continuación (6-12 meses)"
        if "ADVANCE 3" in n:
            return "Leche crecimiento (+12 meses)"
        if "DIGEST" in n:
            return "Leche antidigestión"
        if "AR " in n:
            return "Leche antirreflujo"
        if "CEREAL" in n or "GALLETA" in n:
            return "Cereales infantiles"
        if "NOCHES" in n or "SUEÑO" in n:
            return "Infusiones infantiles"
        return "Alimentación infantil"
    
    def _detectar_tipo_legal_generico(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["ACEITE ESEN", "AGUA AZAHAR", "AGUA DE ROSAS", "AGUA DESTILADA"]):
            return "Parafarmacia"
        if any(x in n for x in ["CALENTIT", "BOLSA AGUA", "BOLSA DE PLAST", "BOLSA GEL",
                                  "BOLSA MASC", "BOTIQUIN", "BRAGA PAPEL"]):
            return "Parafarmacia"
        if any(x in n for x in ["LAPIZ DE OJO", "POLVOS COMPACT", "BLUSH", "MASCARA DE PEST",
                                  "EYELINER"]):
            return "Cosmética decorativa"
        if any(x in n for x in ["BOLSA ISOTERMICA"]):
            return "Parafarmacia"
        return "PENDIENTE VERIFICACION"
    
    def _detectar_categoria_generica(self, nombre: str) -> str:
        n = nombre.upper()
        if any(x in n for x in ["ACEITE ESEN"]):
            return "Fitoterapia"
        if any(x in n for x in ["AGUA AZAHAR", "AGUA DE ROSAS"]):
            return "Formulación magistral"
        if any(x in n for x in ["AGUA DESTILADA"]):
            return "Material de laboratorio"
        if any(x in n for x in ["CALENTIT"]):
            return "Confort y calor"
        if any(x in n for x in ["LAPIZ", "POLVOS", "BLUSH", "MASCARA", "EYELINER"]):
            return "Maquillaje"
        return "PENDIENTE VERIFICACION"
    
    def _detectar_subcategoria_generica(self, nombre: str) -> str:
        return "PENDIENTE VERIFICACION"


# =============================================================================
# PASO 4: CATEGORIZACIÓN ATC POR NOMBRE DE MEDICAMENTO
# =============================================================================

# Mapeo parcial de medicamentos conocidos a categorías ATC principales
MEDICAMENTOS_CATEGORIAS = {
    # Sistema Nervioso (N)
    "ABILIFY": ("Sistema nervioso", "Antipsicótico atípico"),
    "ALPRAZOLAM": ("Sistema nervioso", "Ansiolítico benzodiazepínico"),
    "BROMAZEP": ("Sistema nervioso", "Ansiolítico benzodiazepínico"),
    "ZOLPIDEM": ("Sistema nervioso", "Hipnótico"),
    "ZOPICLONA": ("Sistema nervioso", "Hipnótico"),
    "BESITRAN": ("Sistema nervioso", "Antidepresivo ISRS"),
    "BRINTELLIX": ("Sistema nervioso", "Antidepresivo multimodal"),
    "ANAFRANIL": ("Sistema nervioso", "Antidepresivo tricíclico"),
    "ARTANE": ("Sistema nervioso", "Antiparkinsoniano anticolinérgico"),
    "AKINETON": ("Sistema nervioso", "Antiparkinsoniano"),
    "AZILECT": ("Sistema nervioso", "Antiparkinsoniano IMAO-B"),
    "BIODRAMINA": ("Sistema nervioso", "Antiemético/antivertiginoso"),
    "ATOMOXETINA": ("Sistema nervioso", "TDAH"),
    "ZARELIS": ("Sistema nervioso", "Antidepresivo IRSN"),
    "ZEBINIX": ("Sistema nervioso", "Antiepiléptico"),
    "BRIVIACT": ("Sistema nervioso", "Antiepiléptico"),
    "ZONEGRAN": ("Sistema nervioso", "Antiepiléptico"),
    "ZONESME": ("Sistema nervioso", "Antiepiléptico"),
    "ZYPREXA": ("Sistema nervioso", "Antipsicótico atípico"),
    "ZOMIG": ("Sistema nervioso", "Antimigrañoso (triptán)"),
    "ALMOGRAN": ("Sistema nervioso", "Antimigrañoso (triptán)"),
    "ALMOTRIPTAN": ("Sistema nervioso", "Antimigrañoso (triptán)"),
    "ZOLMITRIPTAN": ("Sistema nervioso", "Antimigrañoso (triptán)"),
    
    # Cardiovascular (C)
    "ADIRO": ("Cardiovascular", "Antiagregante plaquetario"),
    "AAS": ("Cardiovascular", "Antiagregante plaquetario (AAS dosis baja)"),
    "ADALAT": ("Cardiovascular", "Antagonista del calcio"),
    "AMLODIPINO": ("Cardiovascular", "Antagonista del calcio"),
    "ATENOLOL": ("Cardiovascular", "Betabloqueante"),
    "BISOPROLOL": ("Cardiovascular", "Betabloqueante"),
    "ALDACTONE": ("Cardiovascular", "Diuréticos ahorradores de potasio"),
    "AMERIDE": ("Cardiovascular", "Diurético combinado"),
    "ACOVIL": ("Cardiovascular", "IECA"),
    "APROVEL": ("Cardiovascular", "ARA II"),
    "ATORVASTATINA": ("Cardiovascular", "Estatina"),
    "ATOZET": ("Cardiovascular", "Estatina + ezetimiba"),
    "ALIPZA": ("Cardiovascular", "Estatina"),
    "ZARATOR": ("Cardiovascular", "Estatina"),
    "CADUET": ("Cardiovascular", "Estatina + antagonista calcio"),
    "BIPRETERAX": ("Cardiovascular", "IECA + diurético"),
    "BALZAK": ("Cardiovascular", "ARA II + antagonista calcio"),
    "BRILIQUE": ("Cardiovascular", "Antiagregante plaquetario"),
    "APIXABAN": ("Cardiovascular", "Anticoagulante oral directo"),
    "APOCARD": ("Cardiovascular", "Antiarrítmico"),
    "ANORO": ("Respiratorio", "Broncodilatador doble LABA/LAMA"),
    "ATROVENT": ("Respiratorio", "Broncodilatador anticolinérgico"),
    "AVAMYS": ("Respiratorio", "Corticoide nasal"),
    "BUDESONIDA": ("Respiratorio", "Corticoide inhalado/nasal"),
    "BIRESP": ("Respiratorio", "Corticoide + broncodilatador inhalado"),
    "BRALTUS": ("Respiratorio", "Broncodilatador anticolinérgico"),
    "BRIMICA": ("Respiratorio", "Broncodilatador doble + corticoide"),
    
    # Aparato digestivo (A)
    "ALMAX": ("Digestivo", "Antiácido"),
    "ALMAGATO": ("Digestivo", "Antiácido"),
    "AERO RED": ("Digestivo", "Antiflatulento"),
    "AGIOLAX": ("Digestivo", "Laxante"),
    "BUSCAPINA": ("Digestivo", "Antiespasmódico"),
    "BLASGINA": ("Digestivo", "Antifúngico vaginal"),
    
    # Antiinfecciosos (J)
    "AMOXICILINA": ("Antiinfeccioso", "Antibiótico penicilínico"),
    "AMOXCLAV": ("Antiinfeccioso", "Antibiótico penicilínico + inhibidor betalactamasa"),
    "AUGMENTINE": ("Antiinfeccioso", "Antibiótico penicilínico + inhibidor betalactamasa"),
    "AZITROMICINA": ("Antiinfeccioso", "Antibiótico macrólido"),
    "ZITROMAX": ("Antiinfeccioso", "Antibiótico macrólido"),
    "ACICLOVIR": ("Antiinfeccioso", "Antiviral"),
    "ZOVIRAX": ("Antiinfeccioso", "Antiviral"),
    "ANACLOSIL": ("Antiinfeccioso", "Antibiótico penicilínico"),
    "ZINNAT": ("Antiinfeccioso", "Antibiótico cefalosporínico"),
    "BACTROBAN": ("Antiinfeccioso", "Antibiótico tópico (mupirocina)"),
    
    # Dermatología (D)
    "ADVENTAN": ("Dermatología", "Corticoide tópico"),
    "BETNOVATE": ("Dermatología", "Corticoide tópico"),
    "BLASTOESTIMULINA": ("Dermatología", "Cicatrizante tópico"),
    
    # Musculoesquelético (M)
    "ARCOXIA": ("Musculoesquelético", "Antiinflamatorio COX-2"),
    "AIRTAL": ("Musculoesquelético", "Antiinflamatorio AINE"),
    "ALOPURINOL": ("Musculoesquelético", "Antigotoso"),
    "ADENURIC": ("Musculoesquelético", "Antigotoso"),
    "ALGIDOL": ("Musculoesquelético", "Analgésico combinado"),
    "ASPIRINA": ("Analgésico/Antiinflamatorio", "AINE / Analgésico"),
    "ANTIDOL": ("Analgésico", "Paracetamol"),
    "APIRETAL": ("Analgésico", "Paracetamol pediátrico"),
    "APIROFENO": ("Analgésico", "Ibuprofeno pediátrico"),
    
    # Otros
    "ACFOL": ("Hematología", "Ácido fólico"),
    "AC ALENDRONICO": ("Metabolismo óseo", "Bifosfonato"),
    "AC IBANDRONICO": ("Metabolismo óseo", "Bifosfonato"),
    "ACTIVELLE": ("Ginecología", "Terapia hormonal sustitutiva"),
    "AZARGA": ("Oftalmología", "Antiglaucomatoso combinado"),
    "ALPHAGAN": ("Oftalmología", "Antiglaucomatoso"),
    "BILAXTEN": ("Alergología", "Antihistamínico"),
    "BILASTINA": ("Alergología", "Antihistamínico"),
    "AERIUS": ("Alergología", "Antihistamínico"),
    "BETAHISTINA": ("Otorrinolaringología", "Antivertiginoso"),
    "BETMIGA": ("Urología", "Tratamiento vejiga hiperactiva"),
    "AVIDART": ("Urología", "Hiperplasia benigna de próstata"),
    "BLISSEL": ("Ginecología", "Estriol vaginal"),
    "BONJESTA": ("Ginecología", "Antiemético embarazo"),
}


# =============================================================================
# PASO 5: MOTOR PRINCIPAL DE ENRIQUECIMIENTO
# =============================================================================

class MotorEnriquecimiento:
    """Motor principal que coordina el enriquecimiento de cada producto."""
    
    def __init__(self):
        self.cima = CIMAClient()
        self.scraper = PreciosScraper()
        self.clasificador = ClasificadorProductos()
        self.productos_procesados = 0
        self.productos_total = 0
    
    def procesar_producto(self, codigo: str, codigo_barras: str, nombre: str) -> ProductoEnriquecido:
        """
        Procesa un producto individual: clasifica, busca datos en CIMA y/o web.
        
        Args:
            codigo: Código Nacional del producto
            codigo_barras: EAN-13
            nombre: Nombre exacto del producto
            
        Returns:
            ProductoEnriquecido con todos los datos posibles.
        """
        self.productos_procesados += 1
        logger.info(f"[{self.productos_procesados}/{self.productos_total}] "
                     f"Procesando: {nombre[:60]}...")
        
        # PASO 1: Clasificación inicial por patrones
        producto = self.clasificador.clasificar(codigo, nombre)
        
        # PASO 2: Si parece medicamento, consultar CIMA
        if producto.tipo_legal in ("Medicamento marca", "Medicamento EFG",
                                    "Medicamento hospitalario", "PENDIENTE VERIFICACION"):
            datos_cima = self._consultar_cima(codigo, codigo_barras, nombre)
            if datos_cima:
                producto = self._aplicar_datos_cima(producto, datos_cima)
                producto.fuentes.append("CIMA (AEMPS)")
        
        # PASO 3: Si aún no tiene categoría, intentar por mapeo de nombres conocidos
        if producto.categoria_principal == "PENDIENTE VERIFICACION":
            cat_info = self._buscar_en_mapeo_medicamentos(nombre)
            if cat_info:
                producto.categoria_principal = cat_info[0]
                producto.subcategoria = cat_info[1]
        
        # PASO 4: Para productos NO regulados (parafarmacia, complementos, etc.)
        #         buscar precio online
        if producto.pvp_oficial == "NO REGULADO" and producto.precio_online in (
            "PENDIENTE VERIFICACION", ""):
            # Solo buscar si es un producto que se vendería en farmacias online
            if producto.tipo_legal not in ("Medicamento veterinario", "Cosmética decorativa"):
                precio_online, fuentes_precio = self.scraper.obtener_precio_medio(nombre)
                producto.precio_online = precio_online
                producto.fuentes.extend(fuentes_precio)
        
        # PASO 5: Para medicamentos regulados con PVP, poner "SEGÚN PVP" en precio online
        if producto.pvp_oficial not in ("NO REGULADO", "PENDIENTE VERIFICACION"):
            producto.precio_online = "SEGÚN PVP"
        
        # Log resultado
        logger.info(f"  → Tipo: {producto.tipo_legal} | Lab: {producto.laboratorio[:30]} | "
                     f"PVP: {producto.pvp_oficial} | Online: {producto.precio_online}")
        
        return producto
    
    def _consultar_cima(self, codigo: str, codigo_barras: str, nombre: str) -> Optional[dict]:
        """Intenta obtener datos de CIMA por CN, EAN-13, o nombre."""
        
        # Intentar por código nacional (6 dígitos)
        if re.match(r'^\d{6}$', str(codigo).strip()):
            data = self.cima.buscar_por_cn(codigo)
            if data:
                return data
            time.sleep(DELAY_CIMA)
        
        # Intentar por código de barras (EAN-13)
        if re.match(r'^8470\d{9}$', str(codigo_barras).strip()):
            data = self.cima.buscar_por_cn(codigo_barras)
            if data:
                return data
            time.sleep(DELAY_CIMA)
        
        # Intentar por nombre
        data = self.cima.buscar_por_nombre(nombre)
        if data:
            return data
        time.sleep(DELAY_CIMA)
        
        return None
    
    def _aplicar_datos_cima(self, producto: ProductoEnriquecido, data: dict) -> ProductoEnriquecido:
        """Aplica los datos de CIMA al producto."""
        extracted = self.cima.extraer_datos(data)
        
        if extracted["laboratorio"] != "PENDIENTE VERIFICACION":
            producto.laboratorio = extracted["laboratorio"]
        
        if extracted["atc"] != "NO APLICA":
            producto.atc = extracted["atc"]
        
        if extracted["pvp"] != "NO REGULADO":
            producto.pvp_oficial = extracted["pvp"]
        
        producto.tipo_legal = extracted["tipo_legal"]
        
        return producto
    
    def _buscar_en_mapeo_medicamentos(self, nombre: str) -> Optional[tuple]:
        """Busca el medicamento en el mapeo de categorías conocidas."""
        nombre_upper = nombre.upper()
        for clave, (cat, subcat) in MEDICAMENTOS_CATEGORIAS.items():
            if clave in nombre_upper:
                return (cat, subcat)
        return None


# =============================================================================
# PASO 6: LECTURA CSV Y ESCRITURA DE RESULTADOS
# =============================================================================

def leer_productos_fuente(filepath: str) -> list[tuple[str, str, str]]:
    """
    Lee el fichero CSV fuente y extrae código, código barras y nombre.
    
    Returns:
        Lista de tuplas (codigo, codigo_barras, nombre)
    """
    productos = []
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)  # Saltar cabecera
        
        for row in reader:
            if len(row) >= 3:
                codigo = row[0].strip()
                codigo_barras = row[1].strip()
                nombre = row[2].strip()
                if nombre:  # Solo si tiene nombre
                    productos.append((codigo, codigo_barras, nombre))
    
    return productos


def escribir_csv_enriquecido(filepath: str, productos: list[ProductoEnriquecido]):
    """Escribe todos los productos enriquecidos en el CSV de salida."""
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(OUTPUT_COLUMNS)
        
        for producto in productos:
            writer.writerow(producto.to_csv_row())


def escribir_producto_incremental(filepath: str, producto: ProductoEnriquecido, es_primero: bool):
    """Escribe un producto al CSV de forma incremental (append)."""
    
    mode = 'w' if es_primero else 'a'
    
    with open(filepath, mode, newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if es_primero:
            writer.writerow(OUTPUT_COLUMNS)
        writer.writerow(producto.to_csv_row())


# =============================================================================
# PASO 7: PUNTO DE ENTRADA PRINCIPAL
# =============================================================================

def main():
    """Función principal del script de enriquecimiento."""
    
    inicio = datetime.now()
    logger.info("=" * 70)
    logger.info("INICIO DEL PROCESO DE ENRIQUECIMIENTO DE PRODUCTOS")
    logger.info(f"Fecha: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    # Verificar que existe el fichero fuente
    # if not os.path.exists(INPUT_FILE):
        # logger.error(f"No se encuentra el fichero fuente: {INPUT_FILE}")
        # sys.exit(1)
    
    # PASO 1: Leer productos del CSV fuente
    # logger.info(f"Leyendo fichero fuente: {INPUT_FILE}")
    # productos_fuente = leer_productos_fuente(INPUT_FILE)
    # logger.info(f"Se encontraron {len(productos_fuente)} productos para procesar.")
    
    # PASO 2: Inicializar el motor de enriquecimiento
    motor = MotorEnriquecimiento()
    #motor.productos_total = len(productos_fuente)
    
    # PASO 3: Procesar cada producto
    productos_enriquecidos = []
    errores = 0
    productos_fuente = [("650427", "8470006504277", "ACETILCISTEINA CINF 200M 30S I")]
    
    for i, (codigo, codigo_barras, nombre) in enumerate(productos_fuente):
        try:
            producto = motor.procesar_producto(codigo, codigo_barras, nombre)
            productos_enriquecidos.append(producto)
            
            # Escribir de forma incremental para no perder progreso
            #escribir_producto_incremental(OUTPUT_FILE, producto, es_primero=(i == 0))
            
        except Exception as e:
            logger.error(f"Error procesando producto '{nombre}': {e}")
            errores += 1
            
            # Crear entrada con error
            producto_error = ProductoEnriquecido(
                codigo=codigo, nombre=nombre,
                laboratorio="ERROR", tipo_legal="ERROR",
                categoria_principal="ERROR", subcategoria=str(e),
                precio_online="ERROR"
            )
            productos_enriquecidos.append(producto_error)
            #escribir_producto_incremental(OUTPUT_FILE, producto_error, es_primero=(i == 0))
    
    # PASO 4: Escribir CSV final completo (sobrescribir la versión incremental)
    logger.info(f"\nEscribiendo CSV final: {OUTPUT_FILE}")
    #escribir_csv_enriquecido(OUTPUT_FILE, productos_enriquecidos)
    
    # PASO 5: Resumen final
    fin = datetime.now()
    duracion = fin - inicio
    
    logger.info("\n" + "=" * 70)
    logger.info("RESUMEN DEL PROCESO")
    logger.info("=" * 70)
    logger.info(f"Total productos procesados: {len(productos_enriquecidos)}")
    logger.info(f"Errores: {errores}")
    logger.info(f"Duración total: {duracion}")
    logger.info(f"Fichero de salida: {OUTPUT_FILE}")
    
    # Estadísticas por tipo
    tipos = {}
    for p in productos_enriquecidos:
        tipos[p.tipo_legal] = tipos.get(p.tipo_legal, 0) + 1
    
    logger.info("\nDistribución por tipo legal:")
    for tipo, count in sorted(tipos.items(), key=lambda x: -x[1]):
        logger.info(f"  {tipo}: {count}")
    
    logger.info("=" * 70)
    logger.info("PROCESO COMPLETADO")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
