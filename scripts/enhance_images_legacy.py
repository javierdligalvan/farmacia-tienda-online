"""
enhance_images.py
Mejora la calidad visual de imágenes AVIF (y otros formatos) de baja calidad.

Uso: python enhance_images.py "<carpeta>" [--target-kb 90] [--min-size 800] [--text-mode]

Estrategia:
  1. Leer AVIF con pillow-avif-plugin.
  2. Si ancho/alto < min_size (por defecto 800) → upscale con LANCZOS hasta min_size.
  3. Aplicar UnsharpMask para mejorar nitidez de texto y bordes.
  4. Guardar como JPEG progresivo en COMPRESSED/, ajustando calidad hasta ≤ target_kb.
     Calidad mínima garantizada: q=70 (no degradar más aunque supere target).
"""
import sys
import argparse
from pathlib import Path

try:
    import pillow_avif  # registra el codec AVIF en Pillow
except ImportError:
    print("WARN: pillow-avif-plugin no instalado. Intentar: pip install pillow-avif-plugin")

from PIL import Image, ImageFilter

SUPPORTED = {'.avif', '.jpg', '.jpeg', '.jfif', '.png', '.webp'}
DEFAULT_TARGET_KB = 90
DEFAULT_MIN_SIZE = 800
QUALITY_START = 90
QUALITY_MIN = 70


def enhance_and_save(src: Path, dst_dir: Path, target_bytes: int, min_size: int, text_mode: bool) -> tuple:
    """Mejora imagen y guarda como JPEG. Retorna (original_size, final_size, out_path, notes)."""
    original_size = src.stat().st_size
    dst_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as im:
        # Convertir a RGB siempre (sin alpha)
        img = im.convert('RGB')
        orig_w, orig_h = img.size

        # Upscale si resolución insuficiente
        notes = []
        if orig_w < min_size or orig_h < min_size:
            base = min(orig_w, orig_h) if text_mode else max(orig_w, orig_h)
            scale = min_size / base
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            factor_str = f'{scale:.1f}×'
            notes.append(f'upscale {orig_w}x{orig_h}→{new_w}x{new_h} ({factor_str})')
            if scale > 4.0:
                notes.append(f'WARN: upscale muy alto ({factor_str}), calidad limitada por fuente')
        else:
            notes.append(f'{orig_w}x{orig_h} (sin redimensionar)')

        # Sharpening: UnsharpMask mejora texto y bordes
        img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=180, threshold=2))
        notes.append('UnsharpMask')
        if text_mode:
            img = img.filter(ImageFilter.SHARPEN)
            notes.append('SHARPEN')

        # Guardar como JPEG progresivo, ajustando calidad
        out = dst_dir / (src.stem + '.jpg')
        final_size = None
        used_q = QUALITY_START

        for q in range(QUALITY_START, QUALITY_MIN - 1, -5):
            img.save(out, format='JPEG', quality=q, optimize=True, progressive=True)
            sz = out.stat().st_size
            if sz <= target_bytes:
                final_size = sz
                used_q = q
                break
            final_size = sz
            used_q = q

        notes.append(f'q={used_q}')
        return original_size, final_size, out, ' | '.join(notes)


def main():
    parser = argparse.ArgumentParser(description='Mejora imágenes AVIF/bajas calidad.')
    parser.add_argument('folder', help='Carpeta raíz con imágenes (sin subcarpetas)')
    parser.add_argument('--target-kb', type=int, default=DEFAULT_TARGET_KB,
                        help=f'Objetivo de tamaño en KB (por defecto {DEFAULT_TARGET_KB})')
    parser.add_argument('--min-size', type=int, default=DEFAULT_MIN_SIZE,
                        help=f'Resolución mínima en píxeles (por defecto {DEFAULT_MIN_SIZE})')
    parser.add_argument('--text-mode', action='store_true',
                        help='Prioriza legibilidad de texto: escala por el lado corto y añade nitidez extra')
    args = parser.parse_args()

    root = Path(args.folder).resolve()
    if not root.is_dir():
        print(f'ERROR: no existe {root}')
        sys.exit(1)

    target_bytes = args.target_kb * 1024
    compressed_dir = root / 'COMPRESSED'

    # Recopilar archivos (excluir COMPRESSED)
    files = sorted(
        f for f in root.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED
        and 'COMPRESSED' not in f.parts
    )

    if not files:
        print('No se encontraron imágenes compatibles en', root)
        sys.exit(0)

    print(f'\nModo mejora | Carpeta: {root}')
    print(f'Imágenes: {len(files)} | Target: {args.target_kb} KB | Min resolución: {args.min_size}px')
    print()
    print(f'{"Archivo":<45} {"Orig KB":>8} {"Final KB":>9} {"OK?":>6}  Notas')
    print('─' * 100)

    total_before = total_after = warnings = 0
    for src in files:
        try:
            before, after, out, notes = enhance_and_save(src, compressed_dir, target_bytes, args.min_size, args.text_mode)
            ok = 'OK' if after <= target_bytes else f'>{args.target_kb}KB'
            if after > target_bytes:
                warnings += 1
            print(f'{src.name:<45} {before/1024:>7.1f}K {after/1024:>8.1f}K {ok:>6}  {notes}')
            total_before += before
            total_after += after
        except Exception as e:
            print(f'{src.name:<45} ERROR: {e}')

    print('─' * 100)
    ratio = (total_after / total_before * 100) if total_before else 0
    print(f'{"TOTAL":<45} {total_before/1024:>7.1f}K {total_after/1024:>8.1f}K  Ratio: {ratio:.1f}%')
    if warnings:
        print(f'\nATENCIÓN: {warnings} imagen(es) superan {args.target_kb} KB.')
        print('  → Considera reducir --min-size o usar calidad más baja.')
    else:
        print(f'\nTodas las imágenes ≤ {args.target_kb} KB. ✓')
    print(f'\nSalida en: {compressed_dir}')


if __name__ == '__main__':
    main()
