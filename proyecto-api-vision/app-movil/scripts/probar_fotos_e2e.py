"""Verifica cámara/foto -> multipart -> API real -> pantalla, sin medir generalización.

Requiere pip install playwright. En Windows utiliza Edge; en otros sistemas,
instala Chromium con python -m playwright install chromium.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from probar_e2e import crear_video_falso

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "pruebas_fotos_e2e"
PUERTO_API, PUERTO_APP = 8766, 5175


def esperar_api():
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO_API}/salud", timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError("La API no respondió; revisa pruebas_fotos_e2e/api.log.")


def escenario(playwright, nombre, video, archivo=None):
    navegador = playwright.chromium.launch(
        channel="msedge" if sys.platform == "win32" else None,
        headless=True,
        args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
              f"--use-file-for-fake-video-capture={video.resolve()}"],
    )
    try:
        contexto = navegador.new_context(viewport={"width": 390, "height": 844})
        contexto.add_init_script(f"localStorage.setItem('urlApi', 'http://127.0.0.1:{PUERTO_API}');")
        contexto.add_init_script("""
          const fetchOriginal = window.fetch.bind(window);
          window.fetch = async (url, opciones) => {
            if (opciones && opciones.body instanceof FormData) {
              window.fotosEnviadas = await Promise.all([...opciones.body.entries()].map(async ([campo, foto]) => {
                const imagen = await createImageBitmap(foto);
                const datos = {campo, ancho: imagen.width, alto: imagen.height, bytes: foto.size};
                imagen.close();
                return datos;
              }));
            }
            return fetchOriginal(url, opciones);
          };
        """)
        pagina = contexto.new_page()
        errores = []
        pagina.on("pageerror", lambda error: errores.append(str(error)))
        pagina.goto(f"http://localhost:{PUERTO_APP}/")
        pagina.wait_for_function("document.getElementById('video').readyState >= 2")
        with pagina.expect_response(lambda r: "/predecir-fotos/" in r.url and r.request.method == "POST") as recibida:
            if archivo:
                pagina.set_input_files("#entrada-archivo", str(archivo))
            else:
                pagina.click("#btn-identificar")
        respuesta = recibida.value
        assert respuesta.status == 200, respuesta.text()
        datos = respuesta.json()
        peticion = respuesta.request
        cabecera = peticion.headers["content-type"]
        assert "multipart/form-data" in cabecera
        partes = pagina.evaluate("window.fotosEnviadas")
        esperado = 1 if archivo else 3
        assert len(partes) == esperado, f"Se enviaron {len(partes)} fotos, se esperaban {esperado}."
        for parte in partes:
            assert parte["campo"] == "archivos" and parte["bytes"] > 0
            if not archivo:
                assert (parte["ancho"], parte["alto"]) == (480, 640), parte
        assert datos["fotogramas_analizados"] == esperado
        if nombre == "sin_rostro":
            assert not datos["rostro_detectado"] and not datos["identificado"]
        else:
            assert datos["rostro_detectado"], datos
        pagina.wait_for_selector("#resultado:not([hidden])")
        texto = pagina.inner_text("#resultado .nombre")
        assert texto == (datos["nombre"] if datos["identificado"] else "No fue posible identificar")
        assert not errores, errores
        pagina.screenshot(path=str(SALIDA / f"{nombre}.png"))
        print(f"OK {nombre}: {esperado} fotos, pantalla={texto}, confianza={datos['confianza']}")
        return {"escenario": nombre, "fotogramas": esperado, "respuesta": datos}
    finally:
        navegador.close()


def main():
    SALIDA.mkdir(exist_ok=True)
    foto = RAIZ / "data/images/ge_01/ge_01_04.jpeg"
    video, vacio = SALIDA / "persona.mjpeg", SALIDA / "sin_rostro.mjpeg"
    crear_video_falso(foto, video)
    crear_video_falso(None, vacio, con_rostro=False)
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO_APP),
        partial(SimpleHTTPRequestHandler, directory=str(RAIZ / "app-movil/www")))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    with (SALIDA / "api.log").open("w", encoding="utf-8") as registro:
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", str(PUERTO_API)],
            cwd=RAIZ, stdout=registro, stderr=registro,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        try:
            esperar_api()
            with sync_playwright() as playwright:
                resultados = [escenario(playwright, "camara", video),
                              escenario(playwright, "sin_rostro", vacio),
                              escenario(playwright, "archivo", video, foto)]
            (SALIDA / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
            print("3/3 recorridos completos. Esto valida integración; el modelo usado sigue siendo el disponible localmente.")
        finally:
            api.terminate()
            api.wait(timeout=20)
            servidor.shutdown()
            servidor.server_close()


if __name__ == "__main__":
    main()
