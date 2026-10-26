"""
Prueba automática de la API con el modelo entrenado (sin levantar el servidor).

Verifica los 4 comportamientos que exige la pauta:
    1. Foto de una persona de la base de datos -> devuelve su nombre.
    2. Matriz 128x128x3 (flujo de la app)     -> devuelve su nombre.
    3. Imagen que no es un rostro conocido    -> "no está en la base de datos".
    4. Entradas inválidas                     -> errores claros (400 / 422).

Uso:  python probar_api.py
"""

import io
import os
import time
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app import app
from preprocesamiento import imagen_a_matriz

RUTA_IMAGENES = Path("data/images")


def foto_de(carpeta: str, indice: int = 0) -> Path:
    return sorted((RUTA_IMAGENES / carpeta).glob("*"))[indice]


def png_en_memoria(imagen: Image.Image) -> bytes:
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


def main():
    with TestClient(app) as cliente:
        print("GET /salud ->", cliente.get("/salud").json())

        print("\n1) POST /predecir/ con fotos reales (una por persona):")
        for carpeta in ["nc_01", "mf_01", "la_01", "jm_01", "ge_01", "fv_01", "fq_01", "cv_01", "bp_01"]:
            ruta = foto_de(carpeta, indice=9)  # última foto de cada persona
            inicio = time.perf_counter()
            respuesta = cliente.post(
                "/predecir/", files={"archivo": (ruta.name, ruta.read_bytes(), "image/jpeg")})
            milisegundos = (time.perf_counter() - inicio) * 1000
            datos = respuesta.json()
            print(f"   {carpeta}: HTTP {respuesta.status_code} | {datos['mensaje']} "
                  f"| confianza={datos['confianza']:.2f} | {milisegundos:.0f} ms")

        print("\n2) POST /predecir-matriz/ (matriz 128x128x3 en 0-255, como enviará la app):")
        with Image.open(foto_de("ge_01", 3)) as imagen:
            matriz, _ = imagen_a_matriz(imagen)
        carga = {"matriz": (matriz * 255).round().astype(int).tolist(), "normalizada": False}
        respuesta = cliente.post("/predecir-matriz/", json=carga)
        print("  ", respuesta.status_code, respuesta.json()["mensaje"],
              "| confianza =", respuesta.json()["confianza"])

        print("\n2b) POST /predecir-lote/ (3 fotogramas de la misma persona, como lo usa la app):")
        matrices = []
        for indice in (7, 8, 9):
            with Image.open(foto_de("fq_01", indice)) as imagen:
                matriz, _ = imagen_a_matriz(imagen)
            matrices.append((matriz * 255).round().astype(int).tolist())
        respuesta = cliente.post("/predecir-lote/", json={"matrices": matrices, "normalizada": False})
        datos = respuesta.json()
        print(f"   {respuesta.status_code} {datos['mensaje']} | confianza={datos['confianza']:.2f} "
              f"| fotogramas con rostro: {datos['fotogramas_con_rostro']}/{datos['fotogramas_analizados']}")

        blanco = np.full((128, 128, 3), 255).tolist()
        respuesta = cliente.post(
            "/predecir-lote/", json={"matrices": [matrices[0], blanco, blanco], "normalizada": False})
        datos = respuesta.json()
        print(f"   lote con solo 1 de 3 fotogramas con rostro -> identificado={datos['identificado']} "
              f"({datos['fotogramas_con_rostro']}/{datos['fotogramas_analizados']})")
        respuesta = cliente.post("/predecir-lote/", json={"matrices": [], "normalizada": False})
        print("   lote vacío          ->", respuesta.status_code)
        respuesta = cliente.post("/predecir-lote/", json={"matrices": [matrices[0]] * 6})
        print("   lote de 6 (máx. 5)  ->", respuesta.status_code)

        print("\n3) Imágenes que NO son personas de la base de datos:")
        rng = np.random.default_rng(0)
        casos = {
            "ruido aleatorio": Image.fromarray(rng.integers(0, 255, (300, 300, 3), dtype=np.uint8)),
            "imagen blanca": Image.new("RGB", (300, 300), "white"),
            "degradado": Image.fromarray(
                np.tile(np.linspace(0, 255, 300, dtype=np.uint8)[:, None, None], (1, 300, 3))),
        }
        for nombre, imagen in casos.items():
            respuesta = cliente.post(
                "/predecir/", files={"archivo": ("x.png", png_en_memoria(imagen), "image/png")})
            datos = respuesta.json()
            print(f"   {nombre}: identificado={datos['identificado']} "
                  f"confianza={datos['confianza']:.2f} -> {datos['mensaje']}")

        print("\n4) Entradas inválidas:")
        respuesta = cliente.post("/predecir/", files={"archivo": ("x.txt", b"hola", "text/plain")})
        print("   archivo no imagen   ->", respuesta.status_code, respuesta.json()["detail"])
        respuesta = cliente.post("/predecir-matriz/", json={"matriz": [[[0, 0, 0]]]})
        print("   matriz 1x1x3        ->", respuesta.status_code, respuesta.json()["detail"])
        respuesta = cliente.post("/predecir-matriz/", json={"matriz": "texto"})
        print("   matriz mal formada  ->", respuesta.status_code)


if __name__ == "__main__":
    main()
