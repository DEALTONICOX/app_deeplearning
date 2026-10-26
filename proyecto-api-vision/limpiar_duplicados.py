"""Retira copias exactas de una misma persona a cuarentena, con manifiesto."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from auditar_dataset import auditar, huella_imagen, procedencia_repositorio


def planificar(informe: dict) -> list[dict]:
    # Una identidad contradictoria conserva todas sus copias para revisión.
    conflictos = {d["original"] for d in informe["duplicados"]
                  if Path(d["archivo"]).parent != Path(d["original"]).parent}
    return [d for d in informe["duplicados"] if d["original"] not in conflictos
            and Path(d["archivo"]).parent == Path(d["original"]).parent]


def aplicar(plan: list[dict], imagenes: Path, cuarentena: Path, procedencia=None) -> dict:
    raiz = imagenes.resolve(strict=True)
    destino_raiz = cuarentena.resolve()
    if destino_raiz.is_relative_to(raiz) or raiz.is_relative_to(destino_raiz):
        raise ValueError("La cuarentena debe estar separada de data/images.")
    if destino_raiz.exists():
        raise ValueError("Usa una carpeta de cuarentena nueva para conservar el historial.")
    movimientos = []
    for par in plan:
        ruta, original = Path(par["archivo"]), Path(par["original"])
        origen, conservado = ruta.resolve(strict=True), original.resolve(strict=True)
        if (ruta.is_symlink() or original.is_symlink()
                or not origen.is_relative_to(raiz) or not conservado.is_relative_to(raiz)
                or origen.parent != conservado.parent or origen == conservado):
            raise ValueError(f"Ruta fuera del dataset o pareja de duplicados inválida: {ruta}")
        huella = huella_imagen(origen)
        if huella != huella_imagen(conservado):
            raise ValueError(f"Las imágenes ya no son idénticas: {ruta}; vuelve a auditar.")
        destino = destino_raiz / origen.relative_to(raiz)
        if not destino.resolve().is_relative_to(destino_raiz):
            raise ValueError("Destino fuera de la cuarentena.")
        movimientos.append({"origen": str(origen), "conservado": str(conservado),
                            "cuarentena": str(destino), "sha256_pixeles": huella,
                            "sha256_archivo": hashlib.sha256(origen.read_bytes()).hexdigest(),
                            "movido": False})
    manifiesto = {"procedencia": procedencia, "movimientos": movimientos,
                  "fecha_utc": datetime.now(timezone.utc).isoformat()}
    if not movimientos:
        return manifiesto
    destino_raiz.mkdir(parents=True, exist_ok=False)
    registro = destino_raiz / "manifiesto.json"

    def guardar():
        registro.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")

    guardar()
    for movimiento in movimientos:
        destino = Path(movimiento["cuarentena"])
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(movimiento["origen"], str(destino))
        movimiento["movido"] = True
        guardar()
    return manifiesto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositorio", type=Path, default=Path("../proyecto-dataset-vision"))
    parser.add_argument("--aplicar", action="store_true", help="Sin esta opción solo muestra el plan.")
    args = parser.parse_args()
    procedencia = procedencia_repositorio(args.repositorio)
    imagenes = args.repositorio / "data/images"
    if not imagenes.is_dir():
        parser.error("Faltan las imágenes de integracion; ejecuta primero descargar_integracion.ps1.")
    informe = auditar(imagenes, args.repositorio / "sujetos.csv")
    plan = planificar(informe)
    print(f"Copias exactas retirables: {len(plan)}. Otras repeticiones en conflicto: {len(informe['duplicados']) - len(plan)}.")
    for par in plan:
        print(f"Conservar {par['original']} -> retirar copia {par['archivo']}")
    if args.aplicar:
        cuarentena = args.repositorio.resolve().parent / "cuarentena_duplicados" / uuid4().hex
        resultado = aplicar(plan, imagenes, cuarentena, procedencia)
        print(f"Movidos: {len(resultado['movimientos'])}.")
        if resultado["movimientos"]:
            print(f"Manifiesto y copias recuperables: {cuarentena}")
            print("El dataset cambió: repite la auditoría y actualiza su puntero DVC antes de versionarlo.")
    else:
        print("Simulación: no se modificó ninguna imagen. Usa --aplicar para limpiar.")


if __name__ == "__main__":
    main()
