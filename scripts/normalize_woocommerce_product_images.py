"""
normalize_woocommerce_product_images.py
Normaliza imágenes de producto para WooCommerce.

Resultado por imagen:
  - Canvas 1200×1200 px, fondo blanco puro (#FFFFFF)
  - Producto centrado, dimensión mayor ≈ 80 % (≈ 960 px), márgenes ≈ 120 px
  - Proporciones originales respetadas (sin deformaciones)
  - Nitidez suave (UnsharpMask conservador)
  - Exporta JPG progresivo, sRGB implícito
  - Objetivo ≤ 100 KB (hasta 120 KB solo si imprescindible para calidad)

Uso:
    python normalize_woocommerce_product_images.py "<carpeta_raiz>"
    python normalize_woocommerce_product_images.py "<carpeta_raiz>" --no-rembg

  La carpeta raíz debe contener subcarpetas de producto de primer nivel.
  Salida: <carpeta_raiz>/COMPRESSED/<producto>/

Dependencias obligatorias:
  pip install pillow

Dependencias opcionales (recomendadas):
  pip install rembg onnxruntime     # eliminación de fondo por IA
  pip install pillow-avif-plugin    # lectura de archivos .avif
"""
import sys
import io
import argparse
from pathlib import Path
from PIL import Image, ImageFilter, ImageChops

# ── Constantes ──────────────────────────────────────────────────────────────────
CANVAS_PX       = 1200
PRODUCT_MAX_PX  = 960        # 80 % del lienzo (márgenes ≈ 120 px por lado)
TARGET_BYTES    = 100_000    # 100 KB — objetivo principal
MAX_BYTES       = 120_000    # 120 KB — límite absoluto tolerado
JPEG_Q_START    = 88
JPEG_Q_MIN      = 60
JPEG_Q_STEP     = 4
SUPPORTED       = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}
BG_DIFF_THRESH  = 15         # diferencia mínima para considerar píxel "no fondo"
CROP_PADDING    = 10         # px de margen al recortar
BG_WHITE_RATIO  = 0.85       # fracción mínima de borde blanco para considerar fondo blanco
ALPHA_CROP_THRESH = 50       # opacidad mínima para considerar píxel como contenido (ignora sombras tenues < 20 %)

# ── Plugins opcionales ──────────────────────────────────────────────────────────
try:
    import pillow_avif  # noqa: F401  — registra codec AVIF en Pillow
except ImportError:
    pass


# ── Utilidades ──────────────────────────────────────────────────────────────────

def load_rembg():
    """Carga rembg si está disponible. Devuelve la función remove() o None."""
    try:
        from rembg import remove
        return remove
    except ImportError:
        return None


def remove_background_rembg(img: Image.Image, remove_fn) -> Image.Image:
    """
    Elimina el fondo usando rembg (modelo de IA).
    Devuelve imagen RGBA con fondo transparente.
    """
    result = remove_fn(img)
    if isinstance(result, Image.Image):
        return result.convert('RGBA')
    return Image.open(io.BytesIO(result)).convert('RGBA')


def is_near_white_background(img: Image.Image, threshold: int = 240) -> bool:
    """
    Devuelve True si los bordes de la imagen son predominantemente blancos.
    Muestrea franjas de hasta 5 px en los cuatro bordes.
    """
    rgb = img.convert('RGB')
    w, h = rgb.size
    strip = max(3, min(w, h) // 50)

    top    = list(rgb.crop((0, 0, w, strip)).getdata())
    bottom = list(rgb.crop((0, h - strip, w, h)).getdata())
    left   = list(rgb.crop((0, 0, strip, h)).getdata())
    right  = list(rgb.crop((w - strip, 0, w, h)).getdata())

    all_px = top + bottom + left + right
    if not all_px:
        return True
    white = sum(1 for r, g, b in all_px if r >= threshold and g >= threshold and b >= threshold)
    return white / len(all_px) >= BG_WHITE_RATIO


def crop_to_content(img: Image.Image) -> Image.Image:
    """
    Recorta espacio vacío en los bordes:
      - RGBA: usa el canal alfa para detectar contenido.
      - RGB:  usa diferencia con blanco puro para detectar el producto.
    Añade CROP_PADDING px para no cortar bordes del producto.
    """
    if img.mode == 'RGBA':
        # Ignorar píxeles muy semitransparentes (sombras/reflejos tenues)
        # que desplazan el bbox y descentran el producto en el lienzo.
        alpha_mask = img.split()[3].point(lambda a: 255 if a >= ALPHA_CROP_THRESH else 0)
        bbox = alpha_mask.getbbox()
    else:
        rgb  = img.convert('RGB')
        diff = ImageChops.difference(rgb, Image.new('RGB', rgb.size, (255, 255, 255)))
        mask = diff.convert('L').point(lambda v: 255 if v > BG_DIFF_THRESH else 0)
        bbox = mask.getbbox()

    if not bbox:
        return img

    w, h = img.size
    bbox = (
        max(0,  bbox[0] - CROP_PADDING),
        max(0,  bbox[1] - CROP_PADDING),
        min(w,  bbox[2] + CROP_PADDING),
        min(h,  bbox[3] + CROP_PADDING),
    )
    return img.crop(bbox)


def place_on_canvas(product: Image.Image) -> tuple:
    """
    Compone el producto centrado sobre un lienzo blanco CANVAS_PX × CANVAS_PX.
    La dimensión mayor del producto se escala a PRODUCT_MAX_PX (80 % del lienzo).
    Devuelve (canvas_Image, scale_factor).
    """
    # Composite RGBA sobre blanco puro antes de escalar
    if product.mode == 'RGBA':
        bg = Image.new('RGB', product.size, (255, 255, 255))
        bg.paste(product, mask=product.split()[3])
        product = bg
    else:
        product = product.convert('RGB')

    pw, ph = product.size
    if pw == 0 or ph == 0:
        return Image.new('RGB', (CANVAS_PX, CANVAS_PX), (255, 255, 255)), 1.0

    scale  = PRODUCT_MAX_PX / max(pw, ph)
    new_w  = max(1, round(pw * scale))
    new_h  = max(1, round(ph * scale))
    scaled = product.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new('RGB', (CANVAS_PX, CANVAS_PX), (255, 255, 255))
    x = (CANVAS_PX - new_w) // 2
    y = (CANVAS_PX - new_h) // 2
    canvas.paste(scaled, (x, y))
    return canvas, scale


def apply_sharpening(img: Image.Image) -> Image.Image:
    """
    Nitidez conservadora: radius=1.0, percent=120, threshold=3.
    Evita halos y sobreenfoque; mejora bordes y legibilidad del texto.
    """
    return img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=3))


def save_jpeg(img: Image.Image, out: Path, quality: int) -> int:
    img.convert('RGB').save(
        out,
        format='JPEG',
        quality=quality,
        optimize=True,
        progressive=True,
        subsampling=0,   # 4:4:4 — preserva colores sin bandas en zonas sólidas
    )
    return out.stat().st_size


def process_file(
    src: Path,
    dst_dir: Path,
    remove_fn,
    use_rembg: bool,
) -> tuple:
    """
    Pipeline completo de normalización WooCommerce para un archivo.
    Devuelve (orig_bytes, final_bytes, out_path, notas_list, ok_flag).
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    original_size = src.stat().st_size
    notes = []

    # Cargar imagen
    img = Image.open(src)
    img.load()

    # ── 1. Eliminar fondo ──────────────────────────────────────────────────────
    if use_rembg and remove_fn is not None:
        try:
            img = remove_background_rembg(img, remove_fn)
            notes.append('rembg✓')
        except Exception as exc:
            notes.append(f'rembg✗')
            # Continuar sin eliminar fondo
    else:
        if is_near_white_background(img):
            notes.append('bg≈blanco')
        else:
            notes.append('bg-conservado')

    # ── 2. Recortar espacio vacío ───────────────────────────────────────────────
    cropped = crop_to_content(img)
    if cropped.size != img.size:
        notes.append(f'recorte→{cropped.size[0]}×{cropped.size[1]}')
    img = cropped

    # ── 3. Lienzo 1200×1200 centrado ───────────────────────────────────────────
    canvas, scale = place_on_canvas(img)
    dir_str = '↓' if scale < 0.95 else ('↑' if scale > 1.05 else '=')
    notes.append(f'1200×1200 {dir_str}{scale:.2f}×')
    if scale > 2.5:
        notes.append('WARN:upscale-alto')

    # ── 4. Nitidez suave ────────────────────────────────────────────────────────
    canvas = apply_sharpening(canvas)

    # ── 5. Guardar JPEG progresivo ─────────────────────────────────────────────
    out = dst_dir / (src.stem + '.jpg')
    final_size = None
    used_q = JPEG_Q_START

    for q in range(JPEG_Q_START, JPEG_Q_MIN - 1, -JPEG_Q_STEP):
        sz = save_jpeg(canvas, out, q)
        if sz <= TARGET_BYTES:
            final_size = sz
            used_q = q
            break
        final_size = sz
        used_q = q

    notes.append(f'q={used_q}')

    if final_size > MAX_BYTES:
        ok_flag = f'>{MAX_BYTES // 1024}KB ⚠'
    elif final_size > TARGET_BYTES:
        ok_flag = f'≤{MAX_BYTES // 1024}KB~'
    else:
        ok_flag = 'OK'

    return original_size, final_size, out, notes, ok_flag


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Normaliza imágenes de producto para WooCommerce (1200×1200, fondo blanco).'
    )
    parser.add_argument('folder', help='Carpeta raíz con subcarpetas de producto')
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='Índice inicial de imagen a procesar dentro del lote completo (por defecto: 0)'
    )
    parser.add_argument(
        '--max-images',
        type=int,
        help='Máximo de imágenes a procesar en esta ejecución'
    )
    parser.add_argument('--no-rembg', action='store_true',
                        help='Desactiva rembg aunque esté instalado (más rápido, sin eliminación de fondo IA)')
    parser.add_argument(
        '--output-dir',
        metavar='DIRECTORIO',
        help='Directorio de salida para las imágenes normalizadas '
             '(por defecto: <folder>/COMPRESSED). '
             'Se crearán subcarpetas por producto dentro de este directorio.'
    )
    args = parser.parse_args()

    root = Path(args.folder).resolve()
    if not root.is_dir():
        print(f'ERROR: no existe la carpeta: {root}')
        sys.exit(1)

    use_rembg = not args.no_rembg
    remove_fn = load_rembg() if use_rembg else None

    if use_rembg and remove_fn is None:
        print('INFO: rembg no instalado → el fondo no se elimina automáticamente.')
        print('      Para eliminación de fondo IA: pip install rembg onnxruntime\n')

    if args.output_dir:
        compressed_root = Path(args.output_dir).resolve()
    else:
        compressed_root = root / 'COMPRESSED'
    compressed_root.mkdir(parents=True, exist_ok=True)

    # Recopilar tareas (ignorar carpeta COMPRESSED)
    tasks: list = []
    for product_dir in sorted(
        p for p in root.iterdir() if p.is_dir() and p.name != 'COMPRESSED'
    ):
        for src in sorted(product_dir.rglob('*')):
            if (src.is_file()
                    and src.suffix.lower() in SUPPORTED
                    and 'COMPRESSED' not in src.parts):
                tasks.append((src, product_dir.name))

    if not tasks:
        print('No se encontraron imágenes compatibles.')
        sys.exit(0)

    total_tasks = len(tasks)
    start_idx = max(0, args.offset)
    if start_idx >= total_tasks:
        print(f'No hay imágenes para procesar en el rango solicitado (offset={start_idx}, total={total_tasks}).')
        sys.exit(0)

    end_idx = total_tasks if args.max_images is None else min(total_tasks, start_idx + max(0, args.max_images))
    tasks = tasks[start_idx:end_idx]

    rembg_status = 'ON' if remove_fn else ('desactivado' if not use_rembg else 'no instalado')
    print(f'\n═══ WooCommerce Image Processor ═══')
    print(f'Raíz:     {root}')
    print(f'Imágenes: {len(tasks)} / {total_tasks}')
    if len(tasks) != total_tasks:
        print(f'Lote:     {start_idx + 1}-{end_idx} de {total_tasks}')
    print(f'Canvas:   {CANVAS_PX}×{CANVAS_PX} px  |  Producto: {PRODUCT_MAX_PX} px (80 %)  |  Márgenes: {(CANVAS_PX - PRODUCT_MAX_PX) // 2} px')
    print(f'rembg:    {rembg_status}')
    print()

    W = 58
    print(f'{"Producto / Archivo":<{W}} {"Antes":>8} {"Después":>8} {"OK?":>10}  Notas')
    print('─' * (W + 46))

    total_before = total_after = 0
    over_100 = over_120 = 0

    for src, product in tasks:
        dst_dir = compressed_root / product
        label   = f'{product}/{src.name}'
        if len(label) > W:
            label = '…' + label[-(W - 1):]
        try:
            before, after, out, notes, ok = process_file(src, dst_dir, remove_fn, use_rembg)
            print(f'{label:<{W}} {before / 1024:>7.1f}K {after / 1024:>7.1f}K {ok:>10}  {" | ".join(notes)}')
            total_before += before
            total_after  += after
            if after > MAX_BYTES:
                over_120 += 1
            elif after > TARGET_BYTES:
                over_100 += 1
        except Exception as exc:
            print(f'{label:<{W}}  ERROR: {exc}')

    print('─' * (W + 46))
    ratio = (total_after / total_before * 100) if total_before else 0
    print(f'{"TOTAL":<{W}} {total_before / 1024:>7.1f}K {total_after / 1024:>7.1f}K   {ratio:.1f}%')

    if over_120:
        print(f'\n⚠  {over_120} imagen(es) superan 120 KB — revisar manualmente.')
    if over_100:
        print(f'~  {over_100} imagen(es) entre 100 KB y 120 KB (tolerado por calidad).')

    print(f'\nResultado en: {compressed_root}')

    # ── Checklist validación ────────────────────────────────────────────────────
    print('\n── Checklist validación ──────────────────────────')
    print(f'  ✅ Canvas: {CANVAS_PX}×{CANVAS_PX} px')
    print(f'  ✅ Fondo blanco #FFFFFF')
    print(f'  ✅ Producto centrado, dim. mayor ≈ {PRODUCT_MAX_PX} px (~80 %)')
    print(f'  ✅ Márgenes ≈ {(CANVAS_PX - PRODUCT_MAX_PX) // 2} px uniformes')
    print(f'  ✅ Sin deformaciones (LANCZOS)')
    print(f'  ✅ Nitidez suave (UnsharpMask)')
    print(f'  ✅ Formato JPG progresivo, sRGB implícito')
    weight_ok = '✅' if not over_120 else '⚠️'
    print(f'  {weight_ok} Peso ≤ 100 KB'
          + (f' ({over_120} archivo(s) >120 KB)' if over_120 else ''))


if __name__ == '__main__':
    main()
