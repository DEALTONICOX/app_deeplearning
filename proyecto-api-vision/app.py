"""
API de reconocimiento de personas (EP2 - Deep Learning).

Recibe una imagen (o su matriz 128x128x3) y responde el nombre de la persona
o indica que no está en la base de datos.

Ejecución:
    uvicorn app:app --host 0.0.0.0 --port 8000
Documentación interactiva (Swagger): http://127.0.0.1:8000/docs

Endpoints:
    GET  /                  Estado del servicio.
    GET  /salud             Información del modelo cargado.
    POST /predecir-matriz/  Una matriz 128x128x3 (flujo básico de la app móvil).
    POST /predecir-lote/    Varias matrices 128x128x3 de la misma persona; promedia
                            las probabilidades (más robusto; lo usa la app).
    POST /predecir/         Una foto completa (útil para probar en /docs).
    POST /predecir-fotos/   Lote de fotos completas con recorte de rostro compartido.
"""

from __future__ import annotations

import io
import json
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from preprocesamiento import FORMA_ENTRADA, hay_rostro, imagen_a_matriz, lista_a_matriz

# Carpeta con modelo_rostros.keras, etiquetas.json y configuracion.json
DIRECTORIO_MODELO = Path(os.getenv("DIRECTORIO_MODELO", "salidas"))
CANTIDAD_CANDIDATOS = 3
MAXIMO_MATRICES_POR_LOTE = 5
MAXIMO_BYTES_IMAGEN = 8 * 1024 * 1024

# Recursos cargados una sola vez al iniciar el servidor
recursos: dict = {}


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    """Carga el modelo, las etiquetas y el umbral al iniciar la API."""
    configuracion = json.loads(
        (DIRECTORIO_MODELO / "configuracion.json").read_text(encoding="utf-8"))
    etiquetas = json.loads(
        (DIRECTORIO_MODELO / "etiquetas.json").read_text(encoding="utf-8"))
    if configuracion.get("motor") == "sface":
        from motor_rostros import MotorRostros
        recursos["motor_rostros"] = MotorRostros(DIRECTORIO_MODELO, configuracion)
    else:
        from tensorflow import keras
        recursos["modelo"] = keras.models.load_model(DIRECTORIO_MODELO / "modelo_rostros.keras")
    recursos["nombres"] = [etiquetas[str(i)] for i in range(len(etiquetas))]
    recursos["umbral"] = float(configuracion["umbral_confianza"])
    if (tuple(configuracion["forma_entrada"]) != FORMA_ENTRADA
            or ("modelo" in recursos and (tuple(recursos["modelo"].input_shape[1:]) != FORMA_ENTRADA
                or recursos["modelo"].output_shape[-1] != len(etiquetas)))
            or configuracion["numero_clases"] != len(etiquetas)
            or not 0 <= recursos["umbral"] <= 1):
        raise ValueError("Modelo, etiquetas y configuración incompatibles; usa la misma salida de entrenamiento.")
    recursos["configuracion"] = configuracion
    yield
    recursos.clear()


app = FastAPI(
    title="API de reconocimiento de personas - Duoc UC",
    description="Clasifica el rostro de una persona y devuelve su nombre, "
                "o indica que no está en la base de datos.",
    version="2.0.0",
    lifespan=ciclo_de_vida,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Modelos de datos (contrato de la API)
# ---------------------------------------------------------------------------
class MatrizImagen(BaseModel):
    """Imagen ya convertida por la app a matriz RGB de 128 x 128 x 3."""

    matriz: list[list[list[float]]] = Field(
        ..., description="Matriz [alto=128][ancho=128][canal RGB=3].")
    normalizada: bool = Field(
        False, description="False: valores en 0-255 (por defecto). True: valores en 0-1.")


class LoteMatrices(BaseModel):
    """Varias matrices 128 x 128 x 3 de la misma persona (fotogramas consecutivos)."""

    matrices: list[list[list[list[float]]]] = Field(
        ..., min_length=1, max_length=MAXIMO_MATRICES_POR_LOTE,
        description=f"De 1 a {MAXIMO_MATRICES_POR_LOTE} matrices [128][128][3].")
    normalizada: bool = Field(
        False, description="False: valores en 0-255 (por defecto). True: valores en 0-1.")


class Candidato(BaseModel):
    nombre: str
    probabilidad: float


class RespuestaPrediccion(BaseModel):
    rostro_detectado: bool = Field(..., description="False si la imagen no contiene un rostro frontal.")
    identificado: bool = Field(..., description="True si la persona está en la base de datos.")
    nombre: str | None = Field(None, description="Nombre de la persona; null si no se identificó.")
    confianza: float = Field(..., description="Probabilidad de la mejor coincidencia (0-1).")
    umbral: float = Field(..., description="Confianza mínima exigida para identificar.")
    mensaje: str
    candidatos: list[Candidato]
    fotogramas_analizados: int = Field(1, description="Imágenes recibidas en la solicitud.")
    fotogramas_con_rostro: int = Field(1, description="Imágenes en las que se detectó un rostro.")
    tipo_puntuacion: str = "probabilidad"
    margen: float = 0.0
    margen_minimo: float = 0.0
    consenso: bool = True


# ---------------------------------------------------------------------------
# Lógica de clasificación
# ---------------------------------------------------------------------------
def _respuesta_sin_rostro(analizados: int, con_rostro: int) -> RespuestaPrediccion:
    return RespuestaPrediccion(
        rostro_detectado=False, identificado=False, nombre=None, confianza=0.0,
        umbral=round(recursos["umbral"], 4), candidatos=[],
        fotogramas_analizados=analizados, fotogramas_con_rostro=con_rostro,
        mensaje="No se detectó un rostro frontal suficiente para identificar. "
                "Centra el rostro y mejora la iluminación.")


def _responder(probabilidades: np.ndarray, analizados: int, con_rostro: int, consenso=True) -> RespuestaPrediccion:
    """Aplica el umbral de confianza a un vector de probabilidades y arma la respuesta."""
    orden = np.argsort(probabilidades)[::-1]
    mejor = int(orden[0])
    confianza = float(np.clip(probabilidades[mejor], 0, 1))
    umbral = recursos["umbral"]
    margen = float(probabilidades[mejor] - probabilidades[orden[1]]) if len(orden) > 1 else 1.0
    margen_minimo = recursos["configuracion"].get("margen_minimo", 0.0)
    identificado = confianza >= umbral and margen >= margen_minimo and consenso
    nombre_mejor = recursos["nombres"][mejor]

    return RespuestaPrediccion(
        rostro_detectado=True,
        tipo_puntuacion=recursos["configuracion"].get("tipo_puntuacion", "probabilidad"),
        margen=round(margen, 4), margen_minimo=margen_minimo, consenso=consenso,
        identificado=identificado,
        nombre=nombre_mejor if identificado else None,
        confianza=round(confianza, 4),
        umbral=round(umbral, 4),
        mensaje=(f"Persona identificada: {nombre_mejor}" if identificado
                 else "No se pudo identificar a la persona con suficiente confianza."),
        candidatos=[
            Candidato(nombre=recursos["nombres"][int(i)],
                      probabilidad=round(float(np.clip(probabilidades[i], 0, 1)), 4))
            for i in orden[:CANTIDAD_CANDIDATOS]
        ],
        fotogramas_analizados=analizados,
        fotogramas_con_rostro=con_rostro,
    )


def clasificar(matrices: list[np.ndarray], con_rostro: list[bool]) -> RespuestaPrediccion:
    """
    Clasifica una o varias matrices (128,128,3) en [0,1] de la misma persona.

    Filtros, en orden:
      1. Al menos la mitad de las imágenes debe contener un rostro frontal.
      2. Se promedian las probabilidades de las imágenes con rostro.
      3. La mejor probabilidad promedio debe superar el umbral de confianza.
    """
    analizados = len(matrices)
    cantidad_con_rostro = int(sum(con_rostro))
    if cantidad_con_rostro < math.ceil(analizados / 2):
        return _respuesta_sin_rostro(analizados, cantidad_con_rostro)

    con_cara = np.stack([m for m, hay in zip(matrices, con_rostro) if hay])
    if "motor_rostros" in recursos:
        if analizados > 1 and cantidad_con_rostro < 2:
            return _respuesta_sin_rostro(analizados, cantidad_con_rostro)
        scores = np.stack([recursos["motor_rostros"].puntuar(v) for v in con_cara])
        promedio = scores.mean(axis=0)
        votos = int(np.sum(scores.argmax(axis=1) == promedio.argmax()))
        return _responder(promedio, analizados, cantidad_con_rostro,
                          votos >= math.ceil(cantidad_con_rostro * 2 / 3))
    probabilidades = recursos["modelo"](con_cara, training=False).numpy().mean(axis=0)
    return _responder(probabilidades, analizados, cantidad_con_rostro)


def _a_matrices(listas, normalizada: bool) -> list[np.ndarray]:
    """Valida y convierte listas anidadas en matrices; devuelve 422 si alguna es inválida."""
    try:
        return [lista_a_matriz(valores, normalizada=normalizada) for valores in listas]
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", summary="Estado del servicio")
def raiz():
    return {"servicio": "API de reconocimiento de personas", "estado": "activo",
            "documentacion": "/docs"}


@app.get("/salud", summary="Información del modelo cargado")
def salud():
    return {
        "estado": "ok",
        "personas_en_base_de_datos": len(recursos["nombres"]),
        "forma_entrada": list(FORMA_ENTRADA),
        "umbral_confianza": recursos["umbral"],
        "procedencia_dataset": recursos["configuracion"].get("procedencia_dataset"),
        "aumento_datos": recursos["configuracion"].get("aumento_datos"),
        "preprocesamiento_fotos": "recorte_rostro_servidor",
        "motor": recursos["configuracion"].get("motor", "keras"),
        "tipo_puntuacion": recursos["configuracion"].get("tipo_puntuacion", "probabilidad"),
        "margen_minimo": recursos["configuracion"].get("margen_minimo", 0.0),
    }


@app.post("/predecir-matriz/", response_model=RespuestaPrediccion,
          summary="Clasifica la matriz 128x128x3 enviada por la app")
def predecir_matriz(entrada: MatrizImagen):
    matriz = _a_matrices([entrada.matriz], entrada.normalizada)[0]
    if "motor_rostros" in recursos:
        return _clasificar_matrices_sface([matriz])
    return clasificar([matriz], [hay_rostro(matriz)])


@app.post("/predecir-lote/", response_model=RespuestaPrediccion,
          summary="Clasifica varias matrices 128x128x3 de la misma persona y promedia")
def predecir_lote(entrada: LoteMatrices):
    matrices = _a_matrices(entrada.matrices, entrada.normalizada)
    if "motor_rostros" in recursos:
        return _clasificar_matrices_sface(matrices)
    return clasificar(matrices, [hay_rostro(m) for m in matrices])


def _clasificar_matrices_sface(matrices):
    vectores = [recursos["motor_rostros"].extraer(Image.fromarray((m * 255).astype(np.uint8)))[0]
                for m in matrices]
    return clasificar(vectores, [v is not None for v in vectores])


@app.post("/predecir/", response_model=RespuestaPrediccion,
          summary="Clasifica una foto completa (recorta el rostro en el servidor)")
async def predecir_imagen(archivo: UploadFile = File(..., description="Foto JPG o PNG")):
    matriz, rostro_detectado = await _leer_foto(archivo)
    return clasificar([matriz], [rostro_detectado])


async def _leer_foto(archivo: UploadFile):
    contenido = await archivo.read(MAXIMO_BYTES_IMAGEN + 1)
    if len(contenido) > MAXIMO_BYTES_IMAGEN:
        raise HTTPException(status_code=413, detail="Cada foto debe ocupar como máximo 8 MiB.")
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            if "motor_rostros" in recursos:
                vector, _ = recursos["motor_rostros"].extraer(imagen)
                return vector, vector is not None
            return imagen_a_matriz(imagen, recortar=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=400,
                            detail="El archivo no es una imagen válida.") from error


@app.post("/predecir-fotos/", response_model=RespuestaPrediccion,
          summary="Recorta y clasifica de 1 a 5 fotos de la misma persona")
async def predecir_fotos(archivos: list[UploadFile] = File(...)):
    if not 1 <= len(archivos) <= MAXIMO_MATRICES_POR_LOTE:
        raise HTTPException(status_code=422, detail="Envía de 1 a 5 fotos de la misma persona.")
    matrices, detecciones = [], []
    for archivo in archivos:
        matriz, detectado = await _leer_foto(archivo)
        matrices.append(matriz)
        detecciones.append(detectado)
    return clasificar(matrices, detecciones)
