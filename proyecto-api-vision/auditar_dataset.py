"""Audita los originales antes de entrenar; no modifica imágenes ni metadatos."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

EXTENSIONES = {".jpg", ".jpeg", ".png"}


def huella_imagen(ruta: Path) -> str:
    """Compara píxeles orientados, aunque el archivo tenga metadatos diferentes."""
    with Image.open(ruta) as original:
        imagen = ImageOps.exif_transpose(original).convert("RGB")
        imagen.load()
        return hashlib.sha256(str(imagen.size).encode() + imagen.tobytes()).hexdigest()


def procedencia_repositorio(repositorio: Path) -> dict:
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repositorio), *args], text=True, encoding="utf-8"
        ).strip()

    rama = git("branch", "--show-current")
    if rama != "integracion":
        raise ValueError(f"Se exige la rama integracion; la copia está en {rama!r}.")
    estado_metadatos = git("status", "--porcelain", "--", "sujetos.csv", "data/images.dvc")
    return {
        "rama": rama,
        "commit": git("rev-parse", "HEAD"),
        "metadatos_modificados": bool(estado_metadatos),
        "estado_metadatos": estado_metadatos,
        "csv_sha256": hashlib.sha256((repositorio / "sujetos.csv").read_bytes()).hexdigest(),
        "puntero_dvc": (repositorio / "data/images.dvc").read_text(encoding="utf-8"),
    }


def auditar(imagenes: Path, csv_sujetos: Path, minimo: int = 5) -> dict:
    informe = {"imagenes": str(imagenes.resolve()), "csv": str(csv_sujetos.resolve()),
               "errores": [], "avisos": [], "personas": [], "archivos": [], "duplicados": []}
    errores = informe["errores"]
    if not csv_sujetos.is_file():
        errores.append(f"No existe {csv_sujetos}.")
        return informe
    with csv_sujetos.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if lector.fieldnames != ["id_carpeta", "nombre_normalizado", "nombre_original"]:
            errores.append("Columnas CSV inválidas o invertidas.")
            return informe
        sujetos = list(lector)
    if not imagenes.is_dir():
        errores.append(f"No existe {imagenes}. Ejecuta dvc pull en integracion.")
    ids, nombres, huellas = set(), set(), {}
    for fila in sujetos:
        if None in fila or any(not (v or "").strip() for v in fila.values()):
            errores.append(f"Fila CSV incompleta o con columnas extra: {fila!r}")
            continue
        fila = {k: v.strip() for k, v in fila.items()}
        identificador, nombre = fila["id_carpeta"], fila["nombre_original"]
        if Path(identificador).name != identificador or identificador in {".", ".."}:
            errores.append(f"ID de carpeta inválido: {identificador!r}")
            continue
        if identificador in ids or fila["nombre_normalizado"] in nombres:
            errores.append(f"Sujeto duplicado en CSV: {identificador}.")
            continue
        ids.add(identificador)
        nombres.add(fila["nombre_normalizado"])
        carpeta = imagenes / identificador
        validas = 0
        if not carpeta.is_dir():
            errores.append(f"Falta carpeta: {identificador} ({nombre}).")
        else:
            for ruta in sorted(carpeta.iterdir()):
                if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES:
                    informe["avisos"].append(f"Archivo o subcarpeta no admitido: {ruta}")
                    continue
                try:
                    huella = huella_imagen(ruta)
                except (OSError, ValueError, Image.DecompressionBombError) as error:
                    errores.append(f"Imagen ilegible {ruta}: {error}")
                    continue
                if huella in huellas:
                    anterior = huellas[huella]
                    informe["duplicados"].append({"archivo": str(ruta), "original": anterior[1]})
                    if anterior[0] != identificador:
                        errores.append(f"Misma imagen con identidades distintas: {anterior[1]} y {ruta}.")
                    else:
                        informe["avisos"].append(f"Duplicado excluido del entrenamiento: {ruta}")
                    continue
                huellas[huella] = (identificador, str(ruta))
                validas += 1
                informe["archivos"].append({"ruta": str(ruta), "id_carpeta": identificador,
                                            "nombre": nombre, "sha256_pixeles": huella})
        informe["personas"].append({**fila, "imagenes_unicas": validas})
        if validas < minimo:
            errores.append(f"{identificador}: {validas} fotos únicas; se necesitan al menos {minimo}.")
    if len(informe["personas"]) < 3:
        errores.append("Se necesitan al menos 3 personas para calibrar desconocidos.")
    if imagenes.is_dir():
        for ruta in imagenes.iterdir():
            if ruta.is_file() or ruta.name not in ids:
                errores.append(f"Imagen suelta o carpeta fuera del CSV: {ruta}")
    informe["total_personas"] = len(informe["personas"])
    informe["total_imagenes_unicas"] = len(informe["archivos"])
    return informe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositorio", type=Path, default=Path("../proyecto-dataset-vision"))
    parser.add_argument("--salida", type=Path, default=Path("auditoria_integracion.json"))
    parser.add_argument("--minimo", type=int, default=5)
    args = parser.parse_args()
    if args.minimo < 5:
        parser.error("--minimo debe ser 5 o más para la evaluación y calibración.")
    procedencia = procedencia_repositorio(args.repositorio)
    informe = auditar(args.repositorio / "data/images", args.repositorio / "sujetos.csv", args.minimo)
    informe["procedencia"] = procedencia
    args.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Informe: {args.salida.resolve()}")
    print(f"Personas: {informe.get('total_personas', 0)}, fotos únicas: {len(informe['archivos'])}")
    for error in informe["errores"]:
        print(f"ERROR: {error}")
    raise SystemExit(bool(informe["errores"]))


if __name__ == "__main__":
    main()
