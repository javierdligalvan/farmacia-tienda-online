"""
compress_images.py
Estructura de salida:
  <root>/COMPRESSED/<producto>/  ← todas las imágenes del producto al mismo nivel (sin subcarpetas)

Uso: python compress_images.py "<carpeta_raiz>"
  - <carpeta_raiz> debe contener subcarpetas de producto de primer nivel.
  - JPG / WebP sin alpha  → Progressive JPEG, calidad 82 bajando de 8 en 8 hasta 50
  - PNG con alpha         → WebP calidad 85 bajando (75, 65, 55) hasta ≤100 KB
  - PNG sin alpha         → Progressive JPEG igual que JPG
  - Objetivo: ≤100 KB por imagen. Nunca sobreescribe originales.
"""
import sys
from pathlib import Path
from PIL import Image

TARGET_BYTES = 100_000
JPEG_Q_START = 82
SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp'}


# ── Compresión ────────────────────────────────────────────────────────────────

def save_jpeg(img: Image.Image, out: Path, q: int) -> int:
    img.convert('RGB').save(out, format='JPEG', quality=q, optimize=True, progressive=True)
    return out.stat().st_size


def save_webp(img: Image.Image, out: Path, q: int) -> int:
    img.save(out, format='WEBP', quality=q, method=6)
    return out.stat().st_size


def compress_file(src: Path, dst_dir: Path) -> tuple[int, int, Path]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    original_size = src.stat().st_size

    with Image.open(src) as im:
        has_alpha = 'A' in im.getbands()

        if src.suffix.lower() == '.png' and has_alpha:
            out = dst_dir / src.with_suffix('.webp').name
            size = 0
            for q in (85, 75, 65, 55):
                size = save_webp(im, out, q)
                if size <= TARGET_BYTES:
                    break
            return original_size, size, out

        # JPG / PNG sin alpha / WebP sin alpha → JPEG progresivo
        out = dst_dir / src.with_suffix('.jpg').name
        size = save_jpeg(im, out, JPEG_Q_START)
        for q in range(JPEG_Q_START - 8, 49, -8):
            if size <= TARGET_BYTES:
                break
            size = save_jpeg(im, out, q)
        return original_size, size, out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print('Uso: python compress_images.py "<carpeta_raiz>"')
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f'ERROR: no existe {root}')
        sys.exit(1)

    compressed_root = root / 'COMPRESSED'
    compressed_root.mkdir(exist_ok=True)

    # Recopila (archivo_src, nombre_producto) ignorando la carpeta COMPRESSED
    tasks: list[tuple[Path, str]] = []
    for product_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name != 'COMPRESSED'):
        for src in sorted(product_dir.rglob('*')):
            if src.is_file() and src.suffix.lower() in SUPPORTED and 'COMPRESSED' not in src.parts:
                tasks.append((src, product_dir.name))

    if not tasks:
        print('No se encontraron imágenes compatibles.')
        sys.exit(0)

    print(f'Raíz: {root}')
    print(f'Imágenes: {len(tasks)}\n')
    print(f'{"Producto / Archivo":<62} {"Antes":>8} {"Después":>8} {"Ratio":>7} {"OK?":>6}')
    print('─' * 98)

    total_before = total_after = over = 0
    for src, product in tasks:
        dst_dir = compressed_root / product
        label = f'{product}/{src.name}'
        try:
            before, after, out = compress_file(src, dst_dir)
            ratio = after / before * 100
            ok = 'OK' if after <= TARGET_BYTES else '>100KB'
            print(f'{label:<62} {before/1024:>7.1f}K {after/1024:>7.1f}K {ratio:>6.1f}% {ok:>6}')
            total_before += before
            total_after += after
            if after > TARGET_BYTES:
                over += 1
        except Exception as e:
            print(f'{label:<62}  ERROR: {e}')

    print('─' * 98)
    print(f'TOTAL  {total_before/1024:.1f} KB → {total_after/1024:.1f} KB  ({total_after/total_before*100:.1f}%)')
    if over:
        print(f'Aviso: {over} imagen(s) superan 100 KB.')
    print(f'\nResultado en: {compressed_root}')


if __name__ == '__main__':
    main()


if __name__ == '__main__':
    main()
