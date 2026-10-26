"""Importa fotos de un ZIP por nombre, respetando el CSV completo de integracion.

No modifica CSV ni puntero DVC; verifica todas las imágenes antes de copiarlas.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, ImageOps

from auditar_dataset import auditar, huella_imagen, procedencia_repositorio
from limpiar_duplicados import aplicar, planificar


def normalizar(texto):
    return " ".join(unicodedata.normalize("NFKD", texto).encode("ascii", "ignore")
                    .decode().lower().replace("_", " ").split())


def apartar_conflictos(informe, raiz, cuarentena, procedencia):
    pares = [d for d in informe["duplicados"] if Path(d["archivo"]).parent != Path(d["original"]).parent]
    nombres = sorted({d[c] for d in pares for c in ("archivo", "original")})
    movimientos = []
    for nombre in nombres:
        ruta = Path(nombre)
        origen = ruta.resolve(strict=True)
        destino = (cuarentena / origen.relative_to(raiz)).resolve()
        if ruta.is_symlink() or not origen.is_relative_to(raiz) or not destino.is_relative_to(cuarentena):
            raise ValueError("Ruta de conflicto fuera del dataset o cuarentena.")
        movimientos.append({"origen": str(origen), "cuarentena": str(destino),
                            "sha256_pixeles": huella_imagen(origen), "movido": False})
    registro = {"motivo": "Misma imagen con etiquetas contradictorias: se excluyen ambas sin elegir identidad.",
                "procedencia": procedencia, "conflictos": pares, "movimientos": movimientos}
    if movimientos:
        cuarentena.mkdir(parents=True, exist_ok=False)
        manifiesto = cuarentena / "manifiesto.json"
        manifiesto.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        for m in movimientos:
            destino = Path(m["cuarentena"])
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(m["origen"], str(destino))
            m["movido"] = True
            manifiesto.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return registro


def importar(zip_origen: Path, repositorio: Path, salida: Path, excluir_conflictos=False):
    procedencia = procedencia_repositorio(repositorio)
    campos = ["id_carpeta", "nombre_normalizado", "nombre_original"]
    with (repositorio / "sujetos.csv").open(encoding="utf-8-sig", newline="") as archivo:
        sujetos = list(csv.DictReader(archivo))
    por_nombre = {}
    for sujeto in sujetos:
        for clave in {normalizar(sujeto["nombre_original"]), normalizar(sujeto["id_carpeta"])}:
            if clave in por_nombre and por_nombre[clave] != sujeto:
                raise ValueError(f"Nombre ambiguo en CSV: {clave}")
            por_nombre[clave] = sujeto
    raiz = (repositorio / "data/images").resolve()
    pendientes = []
    ids = set()
    destinos = set()
    with zipfile.ZipFile(zip_origen) as comprimido:
        entradas = [e for e in comprimido.infolist() if not e.is_dir()]
        if sum(e.file_size for e in entradas) > 2 * 1024**3:
            raise ValueError("El ZIP excede 2 GiB descomprimidos; requiere revisión.")
        for entrada in entradas:
            ruta = PurePosixPath(entrada.filename.replace("\\", "/"))
            if ruta.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                raise ValueError(f"Archivo inesperado en ZIP: {ruta}")
            if ruta.is_absolute() or ".." in ruta.parts or len(ruta.parts) < 2:
                raise ValueError(f"Ruta no admitida: {ruta}")
            sujeto = por_nombre.get(normalizar(ruta.parent.name))
            if sujeto is None:
                raise ValueError(f"Carpeta sin correspondencia en integracion: {ruta.parent.name}")
            contenido = comprimido.read(entrada)
            with Image.open(io.BytesIO(contenido)) as original:
                imagen = ImageOps.exif_transpose(original).convert("RGB")
                imagen.load()
                huella = hashlib.sha256(str(imagen.size).encode() + imagen.tobytes()).hexdigest()
            identificador = sujeto["id_carpeta"]
            destino = (raiz / identificador / f"{identificador}_{ruta.name}").resolve()
            if not destino.is_relative_to(raiz) or destino in destinos:
                raise ValueError(f"Destino repetido o fuera de images: {destino}")
            destinos.add(destino)
            ids.add(identificador)
            if destino.exists() and huella_imagen(destino) != huella:
                raise ValueError(f"No se sobrescribirá una foto diferente: {destino}")
            pendientes.append((destino, contenido, {"entrada_zip": str(ruta),
                "ruta": str(destino), "id_carpeta": identificador, "sha256_pixeles": huella}))
    if not pendientes:
        raise ValueError("El ZIP no tiene imágenes.")
    salida.mkdir(parents=True, exist_ok=True)
    for destino, contenido, _ in pendientes:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists():
            with destino.open("xb") as archivo:
                archivo.write(contenido)
    informe = auditar(raiz, repositorio / "sujetos.csv")
    limpieza = aplicar(planificar(informe), raiz,
        repositorio.parent / "cuarentena_duplicados" / f"zip_{uuid4().hex}", procedencia)
    informe = auditar(raiz, repositorio / "sujetos.csv")
    conflictos = None
    if excluir_conflictos:
        conflictos = apartar_conflictos(informe, raiz,
            repositorio.parent / "cuarentena_duplicados" / f"conflictos_zip_{uuid4().hex}", procedencia)
        informe = auditar(raiz, repositorio / "sujetos.csv")
    informe["procedencia"] = procedencia
    sujetos_presentes = [s for s in sujetos if s["id_carpeta"] in ids]
    faltantes = [s for s in sujetos if s["id_carpeta"] not in ids]
    csv_parcial = salida / "sujetos_presentes.csv"
    with csv_parcial.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(sujetos_presentes)
    auditoria_parcial = auditar(raiz, csv_parcial)
    auditoria_parcial["advertencia"] = "Solo sujetos presentes en ZIP; no es el dataset completo de integracion."
    anteriores = Path(__file__).resolve().parent / "data/images"
    huellas_anteriores = {huella_imagen(p) for p in anteriores.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"} and p.stat().st_size}
    resumen = {"zip_origen": str(zip_origen.resolve()),
        "sha256_zip": hashlib.sha256(zip_origen.read_bytes()).hexdigest(),
        "procedencia": procedencia, "fotos_zip": len(pendientes),
        "personas_zip": len(ids), "personas_csv_integracion": len(sujetos),
        "personas_faltantes": faltantes,
        "coincidencias_pixeles_con_dataset_anterior": sum(
            r["sha256_pixeles"] in huellas_anteriores for _, _, r in pendientes),
        "limpieza": limpieza, "conflictos_apartados": conflictos,
        "archivos": [r for _, _, r in pendientes]}
    for nombre, datos in [("importacion.json", resumen), ("auditoria_integracion.json", informe),
                          ("auditoria_presentes.json", auditoria_parcial)]:
        (salida / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Importadas/verificadas: {len(pendientes)} fotos, {len(ids)} personas.")
    print(f"Personas faltantes del CSV: {len(faltantes)}.")
    print(f"Copias exactas retiradas a cuarentena: {len(limpieza['movimientos'])}.")
    print(f"Fotos idénticas por píxeles al dataset anterior: {resumen['coincidencias_pixeles_con_dataset_anterior']}.")
    print(f"Errores en los sujetos presentes: {len(auditoria_parcial['errores'])}.")
    print(f"Fotos utilizables de los sujetos presentes: {auditoria_parcial['total_imagenes_unicas']}.")
    print(f"Informes: {salida.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--repositorio", type=Path, default=Path("../proyecto-dataset-vision"))
    parser.add_argument("--salida", type=Path, default=Path("datos_zip_20261022"))
    parser.add_argument("--apartar-conflictos", action="store_true",
                        help="Aparta todas las copias con identidades contradictorias sin asignar identidad.")
    args = parser.parse_args()
    importar(args.zip.resolve(), args.repositorio.resolve(), args.salida.resolve(), args.apartar_conflictos)
