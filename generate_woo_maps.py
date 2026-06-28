"""
generate_woo_maps.py
Genera el bloque MAPA WOOCOMMERCE con valores reales (copy-paste directo)
para fichas de cualquier laboratorio en FICHAS_SEO/<LAB>/.

Uso:
  python generate_woo_maps.py                    # procesa todos los labs
  python generate_woo_maps.py --lab ABOCA        # solo un laboratorio
  python generate_woo_maps.py --lab ABOCA --lab LACER  # varios labs

SKU: se lee del campo "SKU / Código Nacional" en la tabla de PASO 1 del MD.
     Fallback: FICHAS_SEO/<LAB>/sku_map.json  (clave = nombre de archivo .md)
Imágenes: búsqueda por coincidencia exacta o parcial del nombre del producto
     contra las carpetas de IMÁGENES/<LAB>/COMPRESSED/.
"""
import re, pathlib, argparse, unicodedata, json

BASE     = pathlib.Path(__file__).parent
SEO_DIR  = BASE / "FICHAS_SEO"
IMG_BASE = BASE / "IMÁGENES"

# ── Normalización para búsqueda de carpetas ──────────────────────────────────

def normalize(text):
    """Mayúsculas, sin tildes ni signos de puntuación."""
    text = unicodedata.normalize("NFKD", text.upper())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9 ]", "", text).strip()

# ── Funciones de extracción ──────────────────────────────────────────────────

def field(content, name):
    """Extrae valor de tabla Markdown: | Nombre | Valor |"""
    m = re.search(r'\|\s*' + re.escape(name) + r'\s*\|\s*(.+?)\s*\|', content)
    return m.group(1).strip() if m else ""

def blue_block(content, *markers):
    """Extrae el contenido del primer bloque ``` después de un marcador 🔵"""
    for marker in markers:
        idx = content.find(marker)
        if idx == -1:
            continue
        after = content[idx: idx + 800]
        m = re.search(r'```\s*\n(.*?)\n```', after, re.DOTALL)
        if m:
            return m.group(1).strip()
    return ""

def keywords(content, n=6):
    """Extrae las primeras N keywords de la tabla de keywords"""
    rows = re.findall(r'\|\s*\d+\s*\|\s*`([^`]+)`', content)
    return rows[:n]

# ── Búsqueda de carpeta de imágenes ─────────────────────────────────────────

def find_img_folder(img_root, product_name):
    """
    Busca la carpeta de imágenes del producto en img_root:
    1. Coincidencia exacta (tras normalizar ambos lados).
    2. Coincidencia parcial: ≥60% de las palabras significativas (≥3 chars)
       del nombre aparecen en el nombre de carpeta.
    Devuelve el nombre de la carpeta (str) o None si no encuentra.
    """
    if not img_root.exists():
        return None
    folders = [d for d in img_root.iterdir() if d.is_dir()]
    norm_name = normalize(product_name)

    # 1. Exacta
    for folder in folders:
        if normalize(folder.name) == norm_name:
            return folder.name

    # 2. Parcial
    words = [w for w in norm_name.split() if len(w) >= 3]
    if not words:
        return None
    best, best_score = None, 0
    for folder in folders:
        norm_folder = normalize(folder.name)
        score = sum(1 for w in words if w in norm_folder)
        if score > best_score and score >= len(words) * 0.6:
            best_score = score
            best = folder.name
    return best

def list_images(img_root, folder_name):
    """Lista las imágenes comprimidas del producto, separadas por tipo"""
    img_dir = img_root / folder_name
    if not img_dir.exists():
        return [], []
    files = sorted(f.name for f in img_dir.iterdir() if f.is_file())
    webp = [f for f in files if f.lower().endswith(".webp")]
    jpg  = [f for f in files if f.lower().endswith((".jpg", ".jpeg"))]
    return webp, jpg

def filter_by_variant(files, variant_hint):
    """Para carpetas con múltiples variantes (ej. COLIGAS FAST), filtra por la variante actual"""
    nums = re.findall(r'\d+', variant_hint)
    if not nums:
        return files
    scored = sorted(files, key=lambda f: sum(10 for n in nums if len(n) >= 2 and n in f.lower()), reverse=True)
    if any(sum(10 for n in nums if len(n) >= 2 and n in f.lower()) > 0 for f in files):
        return [f for f in scored if sum(10 for n in nums if len(n) >= 2 and n in f.lower()) > 0]
    return files

def desc_corta(nombre, lab, tipo_reg, para_que, formato):
    """Genera descripción corta del producto"""
    if "Producto Sanitario" in tipo_reg:
        tipo_s = "producto sanitario"
    elif "complemento" in tipo_reg.lower():
        tipo_s = "complemento alimenticio"
    else:
        tipo_s = "producto de parafarmacia"
    pq = para_que.split('.')[0].rstrip(',').strip()
    if len(pq) > 100:
        pq = pq[:97] + "..."
    return f"{nombre} de {lab} — {tipo_s} para {pq.lower()}. Presentación: {formato}. Sin receta. Envío a toda España en 24-72h."

# ── Carga de SKU fallback desde JSON ─────────────────────────────────────────

def load_sku_fallback(lab_dir):
    """Carga sku_map.json si existe en la carpeta del lab."""
    sku_file = lab_dir / "sku_map.json"
    if sku_file.exists():
        return json.loads(sku_file.read_text(encoding="utf-8"))
    return {}

# ── Generador del bloque ─────────────────────────────────────────────────────

def make_block(fname, content, img_root, lab, sku_fallback=None):
    # SKU: del MD primero, luego fallback del JSON
    sku = (field(content, "SKU / Código Nacional") or
           field(content, "SKU") or
           field(content, "Código Nacional") or
           (sku_fallback or "—"))

    nombre    = field(content, "Nombre comercial")
    lab_val   = field(content, "Laboratorio") or lab
    cat       = field(content, "Categoría / Subcategoría")
    pvp_raw   = field(content, "PVP")
    pvp       = pvp_raw.replace(" €", "").replace("€", "").replace(",", ".").strip()
    para_que  = field(content, "Para qué sirve")
    fmt       = field(content, "Formato / presentación")
    tipo_reg  = field(content, "Tipo regulatorio")

    url_raw   = blue_block(content, "🔵 **URL:**", "🔵 **URL slug", "🔵 **URL\n", "🔵 **URL")
    url_clean = url_raw.split("\n")[0].strip("/").strip()
    url_clean = re.sub(r'\s*\(.*?\)\s*$', '', url_clean).strip().strip("/")

    title     = blue_block(content, "🔵 **Meta Title", "🔵 Meta Title")
    meta_d    = blue_block(content, "🔵 **Meta Description", "🔵 Meta Description")

    kws       = keywords(content, 6)
    tags      = ", ".join(kws)
    focus_kw  = kws[0] if kws else "—"

    desc_c    = desc_corta(nombre, lab_val, tipo_reg, para_que, fmt)

    # Imágenes: buscar carpeta por nombre de producto
    img_fld = find_img_folder(img_root, nombre)
    if img_fld:
        webp_all, jpg_all = list_images(img_root, img_fld)
        webp = filter_by_variant(webp_all, nombre + " " + fmt)
        jpg  = filter_by_variant(jpg_all,  nombre + " " + fmt)
    else:
        webp = jpg = []
        img_fld = f"⚠ No encontrada para '{nombre}'"

    # Construir tabla de imágenes
    rows = []
    if webp:
        rows.append(f"| **Imagen destacada** | `{webp[0]}` | {nombre} {lab_val} |")
    frontes = [j for j in jpg if 'fronte' in j.lower()]
    latos   = [j for j in jpg if 'lato'   in j.lower()]
    retros  = [j for j in jpg if 'retro'  in j.lower()]
    if frontes: rows.append(f"| **Galería — 1ª** | `{frontes[0]}` | {nombre} {lab_val} — vista frontal |")
    if latos:   rows.append(f"| **Galería — 2ª** | `{latos[0]}`   | {nombre} {lab_val} — vista lateral |")
    if retros:  rows.append(f"| **Galería — 3ª** | `{retros[0]}`  | {nombre} {lab_val} — vista trasera |")
    if not jpg and len(webp) > 1:
        for i, w in enumerate(webp[1:4], start=1):
            rows.append(f"| **Galería — {i}ª** | `{w}` | {nombre} {lab_val} — vista {i} |")
    if not rows:
        rows.append(f"| ⚠ Sin imágenes detectadas | Verificar carpeta `{img_fld}` | — |")

    img_table    = "\n".join(rows)
    img_rel_path = f"IMÁGENES/{lab}/COMPRESSED/{img_fld}/"
    note_larga   = f"¿Qué es {nombre}" if nombre else "primer bloque del cuerpo"

    block = f"""## 🗂 MAPA WOOCOMMERCE — DATOS LISTOS PARA COPIAR
> Copia cada valor directamente en el campo correspondiente de WooCommerce. **No requiere interpretación.**

---

### ▶ 1. DATOS BÁSICOS DEL PRODUCTO

| Campo WooCommerce | Valor a copiar |
|---|---|
| **Nombre del producto** | {nombre} |
| **SKU** | {sku} |
| **Precio normal** | {pvp} |
| **Categoría** | {cat} |
| **Etiquetas (tags)** | {tags} |

---

### ▶ 2. DESCRIPCIÓN CORTA *(campo bajo el precio en la ficha de tienda)*

{desc_c}

---

### ▶ 3. DESCRIPCIÓN LARGA *(pestaña "Descripción" en WooCommerce)*

Copia **en este orden** desde la sección 3 de esta ficha:

| Orden | Qué copiar |
|---|---|
| 1 | Todo desde **## {note_larga}...** hasta el final de "Ventajas" |
| 2 | Las **10 FAQs** completas (§ 4) |
| 3 | La **Tabla comparativa** completa (§ 5) |

*(No copies: Análisis, Keywords, Mapa WooCommerce, JSON-LD, Enlazado ni Checklist)*

---

### ▶ 4. CAMPOS SEO *(plugin Yoast / Rank Math / SEOPress)*

| Campo del plugin | Valor a copiar |
|---|---|
| **Slug / Enlace permanente** | `{url_clean}` |
| **SEO Title** | {title} |
| **Meta Description** | {meta_d} |
| **Focus Keyphrase** | {focus_kw} |

> El **H1** NO se escribe aquí — WooCommerce lo genera automáticamente desde el campo "Nombre del producto".
> Verifica en vista previa que el H1 coincide con lo esperado.

---

### ▶ 5. IMÁGENES

Carpeta: `{img_rel_path}`

| Posición en WooCommerce | Archivo a subir | Alt text sugerido |
|---|---|---|
{img_table}

---

### ▶ 6. JSON-LD *(complemento SEO — no sustituye los campos anteriores)*

Pega el bloque completo de la **§ 6** de esta ficha en el plugin Schema (Rank Math / SEOPress)
o directamente en modo HTML al final de la descripción larga.
Verifica en: https://search.google.com/test/rich-results

---

"""
    return block

# ── Procesado por laboratorio ────────────────────────────────────────────────

START = "## 🗂 MAPA WOOCOMMERCE"
END   = "## 3. ELEMENTOS SEO ON PAGE"

def process_lab(lab):
    lab_dir  = SEO_DIR / lab
    img_root = IMG_BASE / lab / "COMPRESSED"
    if not lab_dir.exists():
        print(f"  ERROR: No existe {lab_dir}")
        return 0, 0

    sku_fallback = load_sku_fallback(lab_dir)
    files = sorted(lab_dir.glob("*.md"))
    ok = err = 0

    for f in files:
        content = f.read_text(encoding="utf-8")
        idx_s = content.find(START)
        idx_e = content.find(END)
        if idx_s == -1 or idx_e == -1:
            print(f"  SKIP (marcadores no encontrados): {f.name}")
            err += 1
            continue
        new_block    = make_block(f.name, content, img_root, lab,
                                  sku_fallback=sku_fallback.get(f.name))
        new_content  = content[:idx_s] + new_block + content[idx_e:]
        f.write_text(new_content, encoding="utf-8")
        ok += 1
        print(f"  OK  {f.name}")

    return ok, err

# ── Punto de entrada ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Genera bloques MAPA WOOCOMMERCE en fichas SEO de cualquier laboratorio."
    )
    parser.add_argument(
        "--lab", action="append", dest="labs", metavar="LAB",
        help="Nombre del laboratorio (carpeta en FICHAS_SEO/). Repetible. "
             "Sin --lab procesa todos los laboratorios."
    )
    args = parser.parse_args()

    if args.labs:
        labs = args.labs
    else:
        if not SEO_DIR.exists():
            print(f"ERROR: No existe {SEO_DIR}")
            return
        labs = [d.name for d in SEO_DIR.iterdir() if d.is_dir()]
        if not labs:
            print("No se encontraron laboratorios en FICHAS_SEO/")
            return

    total_ok = total_err = 0
    for lab in sorted(labs):
        print(f"\n── {lab} ──")
        ok, err = process_lab(lab)
        total_ok  += ok
        total_err += err

    print(f"\nTotal: {total_ok} actualizados | {total_err} errores/saltados")

if __name__ == "__main__":
    main()
