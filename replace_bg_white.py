"""
replace_bg_white.py
-------------------
Elimina el fondo de cualquier imagen mediante un flood-fill desde los bordes
y lo sustituye por blanco puro (#FFFFFF). Útil para imágenes de producto con
fondo de color uniforme (blanco, verde, azul, gris, etc.).

Restricciones de exportación (alineadas con el flujo WooCommerce):
  - Salida JPEG progresiva, subsampling=0, sRGB implícito.
  - Objetivo ≤ 100 KB; hasta 120 KB si es imprescindible para la calidad.
  - Calidad inicial 88; descenso automático en pasos de 4 hasta mínimo 60.
  - Si la salida es .png se guarda como PNG optimizado (sin límite de peso).

Uso:
    python replace_bg_white.py <imagen_entrada> <imagen_salida> [--tol 42]

Argumentos:
    src       Ruta a la imagen original (PNG, JPG, WEBP, …).
    out       Ruta de salida. Extensión .jpg/.jpeg → JPEG; cualquier otra → PNG.
    --tol     Tolerancia de color (distancia euclídea, 0-255). Default: 42.

Ejemplos:
    python replace_bg_white.py IMÁGENES/ABOCA/producto.png IMÁGENES/ABOCA/COMPRESSED/producto.jpg
    python replace_bg_white.py foto.jpg resultado.png --tol 30
"""

import argparse
import io
from collections import deque
from pathlib import Path

from PIL import Image

# ── Constantes de exportación ────────────────────────────────────────────────
TARGET_BYTES = 100_000   # 100 KB — objetivo principal
MAX_BYTES    = 120_000   # 120 KB — límite absoluto tolerado
JPEG_Q_START = 88
JPEG_Q_MIN   = 60
JPEG_Q_STEP  = 4


# ── Lógica de flood-fill ─────────────────────────────────────────────────────

def _flood_fill_mask(pixels, width: int, height: int, ref: tuple, tol: int):
    """Devuelve una máscara booleana [y][x] del fondo conectado desde los bordes."""

    tol_sq = tol * tol

    def close(c):
        return sum((int(c[i]) - int(ref[i])) ** 2 for i in range(3)) <= tol_sq

    mask = [[False] * width for _ in range(height)]
    queue = deque()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= width or y >= height or mask[y][x]:
            continue
        if not close(pixels[x, y][:3]):
            continue
        mask[y][x] = True
        queue.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    return mask


# ── Guardado JPEG con control de peso ────────────────────────────────────────

def _save_jpeg(canvas: Image.Image, out: Path):
    """Guarda como JPEG progresivo bajando calidad hasta cumplir el límite de peso."""
    quality = JPEG_Q_START
    while quality >= JPEG_Q_MIN:
        buf = io.BytesIO()
        canvas.save(
            buf,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling=0,
        )
        size = buf.tell()
        if size <= TARGET_BYTES or quality == JPEG_Q_MIN:
            break
        quality -= JPEG_Q_STEP

    if size > MAX_BYTES:
        print(
            f"  [aviso] Peso final {size / 1024:.1f} KB supera el máximo de "
            f"{MAX_BYTES / 1024:.0f} KB (calidad mínima alcanzada: {quality})."
        )

    out.write_bytes(buf.getvalue())
    print(f"Guardado: {out}  ({size / 1024:.1f} KB, calidad JPEG={quality})")


# ── Función principal ─────────────────────────────────────────────────────────

def replace_background_white(src: Path, out: Path, tol: int = 42):
    """Elimina el fondo de *src* y guarda en *out* con fondo blanco."""
    img = Image.open(src).convert("RGBA")
    width, height = img.size
    pixels = img.load()

    # Color de referencia: esquina superior izquierda.
    ref = pixels[0, 0][:3]

    mask = _flood_fill_mask(pixels, width, height, ref, tol)

    for y in range(height):
        for x in range(width):
            if mask[y][x]:
                pixels[x, y] = (255, 255, 255, 0)

    is_jpeg = out.suffix.lower() in (".jpg", ".jpeg")

    if is_jpeg:
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        canvas.paste(img, mask=img.split()[3])
        _save_jpeg(canvas, out)
    else:
        img.save(out, format="PNG", optimize=True)
        size = out.stat().st_size
        print(f"Guardado: {out}  ({size / 1024:.1f} KB, PNG)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Elimina el fondo de una imagen y lo reemplaza por blanco puro."
    )
    parser.add_argument("src", type=Path, help="Imagen de entrada.")
    parser.add_argument("out", type=Path, help="Imagen de salida (.jpg o .png).")
    parser.add_argument(
        "--tol",
        type=int,
        default=42,
        help="Tolerancia de color (distancia euclídea). Default: 42.",
    )
    args = parser.parse_args()

    if not args.src.exists():
        parser.error(f"No se encuentra la imagen de entrada: {args.src}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    replace_background_white(args.src, args.out, tol=args.tol)


if __name__ == "__main__":
    main()
