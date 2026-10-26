"""
Preprocesamiento de imágenes para el clasificador de rostros (EP2 - Deep Learning).

Este módulo es la ÚNICA fuente de verdad del preprocesamiento: lo usan tanto el
entrenamiento como la API, de modo que el modelo siempre recibe datos con el
mismo formato con el que fue entrenado.

Flujo:
    foto original -> corrección de orientación -> recorte del rostro (cuadrado)
    -> redimensión a 128x128 -> matriz float32 (128, 128, 3) normalizada a [0, 1]
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Constantes de configuración
# ---------------------------------------------------------------------------
ALTO_IMAGEN = 128
ANCHO_IMAGEN = 128
CANALES_IMAGEN = 3
FORMA_ENTRADA = (ALTO_IMAGEN, ANCHO_IMAGEN, CANALES_IMAGEN)

LADO_MAXIMO_DETECCION = 800   # se reduce la foto solo para detectar (más rápido)
MARGEN_RECORTE = 0.35         # margen alrededor del rostro (35 % del tamaño)
TAMANO_MINIMO_ROSTRO = 60     # píxeles, en la imagen reducida

_detector_rostros = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def _caja_cuadrada_dentro_de_imagen(centro_x, centro_y, lado, ancho_img, alto_img):
    """Devuelve (izq, sup, der, inf) de un cuadrado que no se sale de la imagen."""
    lado = int(min(lado, ancho_img, alto_img))
    izq = int(round(centro_x - lado / 2))
    sup = int(round(centro_y - lado / 2))
    izq = max(0, min(izq, ancho_img - lado))
    sup = max(0, min(sup, alto_img - lado))
    return izq, sup, izq + lado, sup + lado


def recortar_rostro(imagen: Image.Image) -> tuple[Image.Image, bool]:
    """
    Recorta un cuadrado centrado en el rostro más grande de la imagen.

    Returns:
        (imagen_recortada, rostro_detectado). Si no se detecta ningún rostro
        (por ejemplo, perfiles o cabeza inclinada) se usa un recorte central
        de respaldo y `rostro_detectado` es False.
    """
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")
    ancho_img, alto_img = imagen.size

    factor_reduccion = min(1.0, LADO_MAXIMO_DETECCION / max(ancho_img, alto_img))
    reducida = imagen.resize(
        (int(ancho_img * factor_reduccion), int(alto_img * factor_reduccion))
    )
    gris = cv2.cvtColor(np.asarray(reducida), cv2.COLOR_RGB2GRAY)
    rostros = _detector_rostros.detectMultiScale(
        gris, scaleFactor=1.1, minNeighbors=4,
        minSize=(TAMANO_MINIMO_ROSTRO, TAMANO_MINIMO_ROSTRO),
    )

    if len(rostros) > 0:
        x, y, w, h = max(rostros, key=lambda r: r[2] * r[3])  # el más grande
        centro_x = (x + w / 2) / factor_reduccion
        centro_y = (y + h / 2) / factor_reduccion
        lado = max(w, h) / factor_reduccion * (1 + 2 * MARGEN_RECORTE)
        detectado = True
    else:
        # Respaldo: cuadrado centrado horizontalmente, en el tercio superior,
        # donde normalmente queda el rostro en una foto tipo selfie/retrato.
        centro_x = ancho_img / 2
        centro_y = alto_img * 0.38
        lado = min(ancho_img, alto_img) * 0.75
        detectado = False

    caja = _caja_cuadrada_dentro_de_imagen(centro_x, centro_y, lado, ancho_img, alto_img)
    return imagen.crop(caja), detectado


def imagen_a_matriz(imagen: Image.Image, recortar: bool = True) -> tuple[np.ndarray, bool]:
    """
    Convierte una imagen en la matriz (128, 128, 3) float32 en [0, 1] que
    espera el modelo.

    Args:
        imagen: imagen PIL de cualquier tamaño.
        recortar: si es True, recorta primero el rostro. Debe ser False cuando
            la app ya envía la imagen recortada y reducida a 128x128.
    """
    detectado = True
    if recortar:
        imagen, detectado = recortar_rostro(imagen)
    else:
        imagen = ImageOps.exif_transpose(imagen).convert("RGB")

    imagen = imagen.resize((ANCHO_IMAGEN, ALTO_IMAGEN), Image.LANCZOS)
    matriz = np.asarray(imagen, dtype=np.float32) / 255.0
    return matriz, detectado


def hay_rostro(matriz: np.ndarray) -> bool:
    """
    Compuerta de seguridad: indica si la matriz (128, 128, 3) en [0, 1] contiene
    un rostro frontal.

    Un clasificador softmax siempre elige a alguien, incluso ante ruido o una
    imagen sin persona. Esta verificación evita identificar "personas" en
    imágenes que no contienen un rostro. Parámetros calibrados con el dataset:
    detecta ~81 % de los rostros reales y 0 % de falsos positivos en ruido,
    imágenes blancas y degradados.
    """
    gris = cv2.cvtColor((matriz * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gris = cv2.resize(gris, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    rostros = _detector_rostros.detectMultiScale(
        gris, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50))
    return len(rostros) > 0


def lista_a_matriz(valores, normalizada: bool = True) -> np.ndarray:
    """
    Convierte una lista anidada (la matriz 128x128x3 enviada por la app en JSON)
    en un arreglo float32 validando su forma.

    Args:
        valores: lista anidada con forma (128, 128, 3).
        normalizada: True si los valores ya están en [0, 1]; False si vienen
            en [0, 255] (se dividen por 255).
    """
    matriz = np.asarray(valores, dtype=np.float32)
    if matriz.shape != FORMA_ENTRADA:
        raise ValueError(
            f"La matriz debe tener forma {FORMA_ENTRADA}, se recibió {matriz.shape}."
        )
    limite = 1.0 if normalizada else 255.0
    if not np.isfinite(matriz).all() or np.any(matriz < 0) or np.any(matriz > limite):
        raise ValueError(f"Los píxeles deben ser finitos y estar en [0, {limite}].")
    if not normalizada:
        matriz = matriz / 255.0
    return matriz
