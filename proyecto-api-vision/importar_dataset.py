"""
Importa fotos organizadas como <origen>/<Nombre Persona>/*.jpg a la estructura
del proyecto: data/images/<id_carpeta>/<id_carpeta>_NN.<ext>.

Las fotos se COPIAN (los originales no se modifican). La correspondencia
nombre -> id_carpeta se toma de sujetos.csv (columna nombre_original, sin
distinguir tildes ni mayúsculas). Si la carpeta de origen ya se llama como un
id_carpeta (p. ej. bp_01), se usa directamente.

Uso:
    python importar_dataset.py --origen ../dataset_pr5/dataset_raw --csv sujetos.csv --destino data/images
"""

from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

EXTENSIONES = {".jpg", ".jpeg", ".png"}


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni espacios extremos."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto.strip().lower()


def clave_orden(ruta: Path):
    """Ordena 'Nombre (2).jpg' antes que 'Nombre (10).jpg'; el resto, por nombre."""
    numero = re.search(r"\((\d+)\)", ruta.stem)
    return (int(numero.group(1)) if numero else 0, ruta.name)


def importar(origen: Path, csv: Path, destino: Path) -> None:
    sujetos = pd.read_csv(csv, encoding="utf-8-sig")
    por_nombre = {normalizar(n): i for n, i in zip(sujetos.nombre_original, sujetos.id_carpeta)}
    ids_validos = set(sujetos.id_carpeta)

    for carpeta in sorted(p for p in origen.iterdir() if p.is_dir()):
        id_carpeta = carpeta.name if carpeta.name in ids_validos else por_nombre.get(normalizar(carpeta.name))
        if id_carpeta is None:
            print(f"  [omitida] {carpeta.name}: no está en {csv.name}")
            continue
        fotos = sorted((f for f in carpeta.iterdir()
                        if f.suffix.lower() in EXTENSIONES and f.stat().st_size > 0), key=clave_orden)
        salida = destino / id_carpeta
        salida.mkdir(parents=True, exist_ok=True)
        for indice, foto in enumerate(fotos, start=1):
            shutil.copy2(foto, salida / f"{id_carpeta}_{indice:02d}{foto.suffix.lower()}")
        print(f"  {carpeta.name:<22} -> {id_carpeta}: {len(fotos)} fotos")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origen", type=Path, required=True)
    parser.add_argument("--csv", type=Path, default=Path("sujetos.csv"))
    parser.add_argument("--destino", type=Path, default=Path("data/images"))
    args = parser.parse_args()
    importar(args.origen, args.csv, args.destino)


if __name__ == "__main__":
    main()
