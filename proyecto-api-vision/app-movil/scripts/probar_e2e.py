"""
Prueba de punta a punta de la app: navegador Chromium sin interfaz + cámara simulada
+ API real con el modelo entrenado.

Qué verifica:
  1. La app abre la "cámara" y captura 3 fotogramas.
  2. Cada fotograma se convierte en una matriz 128 x 128 x 3 con enteros 0-255.
  3. La API responde y la pantalla muestra el nombre o "No está en la base de datos".

Requisitos: `pip install playwright` + Chromium instalado, y `npm`/`node` disponibles.
Uso (desde la carpeta eva2/):
    python app-movil/scripts/probar_e2e.py
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]            # carpeta eva2/
SALIDA = Path(os.getenv("DIRECTORIO_PRUEBAS", RAIZ / "pruebas_e2e"))
PUERTO_API, PUERTO_APP = 8765, 5174
ANCHO_VIDEO, ALTO_VIDEO = 480, 640                    # video vertical, como un celular

sys.path.insert(0, str(RAIZ))
from preprocesamiento import _detector_rostros  # noqa: E402


def crear_video_falso(foto: Path, destino: Path, con_rostro: bool = True) -> None:
    """
    Crea un video MJPEG vertical con el rostro de `foto` centrado y ocupando ~60 %
    del ancho (lo que haría una persona que usa la guía ovalada). Si `con_rostro`
    es False genera un video gris liso (sin persona).
    """
    if not con_rostro:
        marco = Image.new("RGB", (ANCHO_VIDEO, ALTO_VIDEO), (128, 128, 128))
    else:
        imagen = ImageOps.exif_transpose(Image.open(foto)).convert("RGB")
        reducida = imagen.copy()
        reducida.thumbnail((800, 800))
        factor = imagen.width / reducida.width
        gris = cv2.cvtColor(np.asarray(reducida), cv2.COLOR_RGB2GRAY)
        rostros = _detector_rostros.detectMultiScale(gris, 1.1, 4, minSize=(60, 60))
        if len(rostros) == 0:
            raise RuntimeError(f"No se detectó rostro en {foto.name}")
        x, y, w, h = max(rostros, key=lambda r: r[2] * r[3])
        centro_x, centro_y = (x + w / 2) * factor, (y + h / 2) * factor
        ancho_recorte = (w * factor) / 0.59           # el rostro ocupa ~59 % del ancho
        alto_recorte = ancho_recorte * ALTO_VIDEO / ANCHO_VIDEO
        caja = (int(centro_x - ancho_recorte / 2), int(centro_y - alto_recorte / 2),
                int(centro_x + ancho_recorte / 2), int(centro_y + alto_recorte / 2))
        marco = imagen.crop(caja).resize((ANCHO_VIDEO, ALTO_VIDEO), Image.LANCZOS)

    buffer = io.BytesIO()
    marco.save(buffer, format="JPEG", quality=92)
    destino.write_bytes(buffer.getvalue() * 30)       # 30 fotogramas idénticos


def esperar(url: str, intentos: int = 60) -> None:
    for _ in range(intentos):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"No respondió {url}")


def validar_matriz(matriz) -> list[str]:
    errores = []
    arreglo = np.asarray(matriz)
    if arreglo.shape != (128, 128, 3):
        errores.append(f"forma {arreglo.shape} en lugar de (128, 128, 3)")
    if arreglo.dtype.kind not in "iu":
        errores.append("los valores no son enteros")
    elif arreglo.min() < 0 or arreglo.max() > 255:
        errores.append("valores fuera de 0-255")
    return errores


def ejecutar_escenario(playwright, nombre, video, esperado):
    navegador = playwright.chromium.launch(args=[
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        f"--use-file-for-fake-video-capture={video}",
    ])
    contexto = navegador.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    contexto.add_init_script(
        f"localStorage.setItem('urlApi', 'http://127.0.0.1:{PUERTO_API}');")
    pagina = contexto.new_page()

    errores_consola = []
    pagina.on("pageerror", lambda error: errores_consola.append(str(error)))

    cuerpos = []
    pagina.on("request", lambda p: cuerpos.append(p.post_data)
              if p.method == "POST" and "predecir" in p.url else None)

    pagina.goto(f"http://localhost:{PUERTO_APP}/")
    pagina.wait_for_function("document.getElementById('video').videoWidth > 0", timeout=15000)
    time.sleep(0.5)
    pagina.click("#btn-identificar")
    pagina.wait_for_selector("#resultado:not([hidden])", timeout=60000)

    texto_nombre = pagina.inner_text("#resultado .nombre")
    tarjeta = pagina.get_attribute("#resultado", "class")
    pagina.eval_on_selector("#resultado details", "d => d.open = true")
    pagina.screenshot(path=str(SALIDA / f"pantalla_{nombre}.png"))

    problemas = list(errores_consola)
    if not cuerpos:
        problemas.append("la app no envió ninguna solicitud a la API")
    else:
        carga = json.loads(cuerpos[-1])
        matrices = carga.get("matrices") or [carga.get("matriz")]
        if len(matrices) != 3:
            problemas.append(f"se esperaban 3 fotogramas y se enviaron {len(matrices)}")
        for i, matriz in enumerate(matrices):
            problemas += [f"fotograma {i + 1}: {e}" for e in validar_matriz(matriz)]
        # Guarda lo que "ve" el modelo para inspeccionarlo a simple vista
        Image.fromarray(np.asarray(matrices[0], dtype=np.uint8)).resize(
            (384, 384), Image.NEAREST).save(SALIDA / f"matriz_enviada_{nombre}.png")

    if esperado not in texto_nombre:
        problemas.append(f"se esperaba «{esperado}» y la pantalla muestra «{texto_nombre}»")

    navegador.close()
    print(f"  [{'OK' if not problemas else 'FALLA'}] {nombre}: pantalla = «{texto_nombre}» "
          f"({tarjeta.split()[-1]})")
    for problema in problemas:
        print(f"        - {problema}")
    return not problemas


def principal() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    datos = RAIZ / "data" / "images"
    # Fotos frontales que la API ya identifica correctamente (ver probar_api.py):
    # así se comprueba que la app produce lo mismo que el preprocesamiento del servidor.
    escenarios = [
        ("fq_01", crear_video_falso, datos / "fq_01" / "fq_01_10.jpg", "Francisco Quintana"),
        ("fv_01", crear_video_falso, datos / "fv_01" / "fv_01_10.jpg", "Fabian Verasay"),
        ("cv_01", crear_video_falso, datos / "cv_01" / "cv_01_10.jpg", "Carlos Vasquez"),
        ("bp_01", crear_video_falso, datos / "bp_01" / "bp_01_10.png", "Benjamin Palma"),
        ("sin_persona", None, None, "No está en la base de datos"),
    ]

    entorno = {**os.environ, "TF_CPP_MIN_LOG_LEVEL": "3"}
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(PUERTO_API), "--log-level", "warning"],
        cwd=RAIZ, env=entorno)
    servidor = subprocess.Popen(
        ["node", "scripts/servidor_estatico.mjs", str(PUERTO_APP)], cwd=RAIZ / "app-movil")
    try:
        esperar(f"http://127.0.0.1:{PUERTO_API}/salud")
        esperar(f"http://localhost:{PUERTO_APP}/")
        resultados = []
        with sync_playwright() as playwright:
            for nombre, creador, foto, esperado in escenarios:
                video = SALIDA / f"video_{nombre}.mjpeg"
                if creador:
                    creador(foto, video)
                else:
                    crear_video_falso(None, video, con_rostro=False)
                resultados.append(ejecutar_escenario(playwright, nombre, video, esperado))
        print(f"\n{sum(resultados)}/{len(resultados)} escenarios correctos. "
              f"Capturas en {SALIDA}")
        return 0 if all(resultados) else 1
    finally:
        api.terminate()
        servidor.terminate()


if __name__ == "__main__":
    sys.exit(principal())
