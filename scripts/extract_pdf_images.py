"""
extract_pdf_images.py
=====================
Extrae todas las imágenes embebidas en los PDFs de una carpeta y las guarda
en subcarpetas con el nombre de cada PDF (sin extensión).

Estructura de salida:
  <carpeta_pdfs>/<nombre_pdf>/img_001.png
                             /img_002.png
                             ...
  <carpeta_pdfs>/<otro_pdf>/img_001.png
                            ...

Uso:
  python extract_pdf_images.py "<carpeta_con_pdfs>"

Dependencias:
    uv sync

Nota:
  - Sólo extrae imágenes *embebidas* en el PDF (XObject de tipo Image).
  - No renderiza páginas enteras — extrae los recursos gráficos originales.
  - Si un PDF no tiene imágenes embebidas, se avisa y se omite.
  - Formatos soportados de salida: PNG, JPEG, JPEG2000, JBIG2, CCITT.
"""

import sys
import re
import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF no está instalado.")
    print("Instálalo con:  uv sync")
    sys.exit(1)


def sanitize_folder_name(name: str) -> str:
    """Convierte el nombre del PDF en un nombre de carpeta válido."""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '_', name)   # Caracteres no permitidos en Windows
    name = re.sub(r'\s+', ' ', name)             # Espacios múltiples → uno
    return name


def extract_images_from_pdf(pdf_path: Path, output_dir: Path) -> int:
    """
    Extrae todas las imágenes embebidas de un PDF y las guarda en output_dir.
    Devuelve el número de imágenes extraídas.
    """
    doc = fitz.open(str(pdf_path))
    count = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]  # xref del objeto imagen

            try:
                base_image = doc.extract_image(xref)
            except Exception as e:
                print(f"  ⚠️  No se pudo extraer imagen xref={xref} (pág. {page_num + 1}): {e}")
                continue

            image_bytes = base_image["image"]
            image_ext   = base_image["ext"]      # png, jpeg, jp2, jb2, ccitt…

            # Nombre de archivo: pág + índice para evitar colisiones entre páginas
            img_filename = f"p{page_num + 1:03d}_img{img_index + 1:03d}.{image_ext}"
            output_path  = output_dir / img_filename

            # Evitar sobrescribir si ya existe (por si se ejecuta dos veces)
            if output_path.exists():
                stem  = output_path.stem
                sufx  = output_path.suffix
                n = 1
                while output_path.exists():
                    output_path = output_dir / f"{stem}_{n}{sufx}"
                    n += 1

            output_path.write_bytes(image_bytes)
            count += 1

    doc.close()
    return count


def process_folder(folder: Path, output_base: Path | None = None) -> None:
    pdf_files = sorted(folder.glob("*.pdf"))

    if not pdf_files:
        print(f"No se encontraron archivos PDF en: {folder}")
        return

    base = output_base if output_base is not None else folder

    print(f"\nCarpeta PDFs:  {folder}")
    print(f"Destino salida: {base}")
    print(f"PDFs encontrados: {len(pdf_files)}\n")
    print("─" * 60)

    total_images = 0

    for pdf_path in pdf_files:
        folder_name = sanitize_folder_name(pdf_path.stem)
        output_dir  = base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"📄 {pdf_path.name}")
        print(f"   → Subcarpeta: {output_dir.name}")

        try:
            n = extract_images_from_pdf(pdf_path, output_dir)
        except Exception as e:
            print(f"   ❌ Error al procesar: {e}")
            continue

        if n == 0:
            print("   ⚠️  Sin imágenes embebidas detectadas.")
        else:
            print(f"   ✅ {n} imagen{'es' if n > 1 else ''} extraída{'s' if n > 1 else ''}.")
            total_images += n

        print()

    print("─" * 60)
    print(f"✅ Proceso completado. Total imágenes extraídas: {total_images}")


def main():
    parser = argparse.ArgumentParser(
        description='Extrae imágenes embebidas de PDFs y las organiza por producto.'
    )
    parser.add_argument('folder', help='Carpeta con los archivos PDF')
    parser.add_argument(
        '--output-dir',
        metavar='DIRECTORIO',
        help='Directorio base donde crear las subcarpetas de producto '
             '(por defecto: la misma carpeta que los PDFs)'
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists():
        print(f"ERROR: La carpeta no existe: {folder}")
        sys.exit(1)
    if not folder.is_dir():
        print(f"ERROR: La ruta indicada no es una carpeta: {folder}")
        sys.exit(1)

    output_base = None
    if args.output_dir:
        output_base = Path(args.output_dir)
        output_base.mkdir(parents=True, exist_ok=True)

    process_folder(folder, output_base)


if __name__ == "__main__":
    main()
